"""WS7 commercial-lead API tests (against the seeded database).

Covers the ratified WS7 acceptance tests L1–L14 for `POST /api/commercial-leads`:
matched per-card / shortlist capture, spoof protection, zero-match, repeated and
concurrent capture, identity conflict, direct Robot-Detail capture, message
round-trip, canonical-region resolution, deterministic PENDING-only provider
routing (positive + every negative), no-false-introduction, and the WS5
anonymity regression.

Routing tests build a fully controlled fixture graph (fresh manufacturer / robot
/ provider / availability_offer with unique slugs) so no seed data interferes and
nothing is left behind — the verified catalogue is never mutated to make routing
"work" (WS7 §14).
"""
from __future__ import annotations

import threading
import uuid

from sqlalchemy import text

from app.db.session import engine


def _scalar(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        return conn.execute(text(sql), params).scalar_one()


def _rows(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        return conn.execute(text(sql), params).all()


def _create_requirement(client, body) -> str:
    resp = client.post("/api/buyer-requirements", json=body)
    assert resp.status_code == 201, (resp.status_code, resp.text)
    return resp.json()["id"]


def _warehouse_requirement(client) -> str:
    """A requirement that matches several seeded robots (Digit best)."""
    raw = {
        "wizard_version": 1,
        "answers": {
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
            "country": {"state": "ANSWERED", "value": "US"},
            "payload": {"state": "ANSWERED", "value": 10},
        },
    }
    return _create_requirement(client, {
        "use_case": "warehouse-logistics", "country": "US", "payload_min_kg": 10,
        "preferred_transaction": "RAAS", "raw_input": raw,
    })


def _matches(client, rid) -> list[dict]:
    resp = client.get(f"/api/buyer-requirements/{rid}/matches")
    assert resp.status_code == 200, (resp.status_code, resp.text)
    return resp.json()["matches"]


def _lead_robots(lead_id: str):
    """(slug, match_score_or_None, is_selected) for a lead, best score first."""
    return _rows(
        "SELECT r.slug, clr.match_score, clr.is_selected "
        "FROM commercial_lead_robot clr JOIN robot r ON r.id = clr.robot_id "
        "WHERE clr.lead_id = :l ORDER BY clr.match_score DESC NULLS LAST, r.slug",
        l=lead_id,
    )


# ---- L1 — matched per-card ------------------------------------------------

def test_l1_matched_per_card(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    assert len(matches) >= 2
    surfaced = {m["robot"]["slug"]: m["score"] for m in matches}
    clicked = matches[0]["robot"]["slug"]

    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "contact_name": "Test Buyer", "organization": "Acme", "robot_slugs": [clicked],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["lead_status"] == "NEW"
    lid = body["id"]

    # exactly one lead for the requirement
    assert _scalar("SELECT count(*) FROM commercial_lead WHERE requirement_id=:i", i=rid) == 1
    # the FULL surfaced shortlist is persisted as decision context
    rows = _lead_robots(lid)
    assert len(rows) == len(surfaced)
    for slug, score, is_selected in rows:
        assert int(score) == surfaced[slug]              # exact persisted score copied
        assert is_selected == (slug == clicked)          # only the clicked one selected


# ---- L2 — shortlist -------------------------------------------------------

def test_l2_shortlist_all_selected(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    all_slugs = [m["robot"]["slug"] for m in matches]

    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": all_slugs,
    })
    assert resp.status_code == 201, resp.text
    rows = _lead_robots(resp.json()["id"])
    assert len(rows) == len(all_slugs)
    assert all(is_selected for _, _, is_selected in rows)


# ---- L3 — spoof protection ------------------------------------------------

def test_l3_spoof_robot_not_in_shortlist_422(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    _matches(client, rid)
    leads_before = _scalar("SELECT count(*) FROM commercial_lead")
    robots_before = _scalar("SELECT count(*) FROM commercial_lead_robot")

    # 'unitree-g1' is a real published robot but NOT in this requirement's
    # persisted shortlist — the browser may not attach it.
    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": ["unitree-g1"],
    })
    assert resp.status_code == 422, resp.text
    # no writes
    assert _scalar("SELECT count(*) FROM commercial_lead") == leads_before
    assert _scalar("SELECT count(*) FROM commercial_lead_robot") == robots_before


# ---- L4 — zero match ------------------------------------------------------

def test_l4_zero_match_capture(client, database_url) -> None:
    # A GENUINE zero-match flow (not merely an unmatched requirement). WS6-E7
    # controlled state: give every published robot a KNOWN low payload so a
    # huge-payload requirement hard-excludes ALL of them (UNKNOWN payloads would
    # otherwise survive). The REAL matcher runs, persists nothing, and we then
    # capture the zero-match demand lead. Restore the payloads afterwards.
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        original = conn.execute(
            text("SELECT id, payload_kg FROM robot WHERE is_published")
        ).all()
        conn.execute(text("UPDATE robot SET payload_kg = 1 WHERE is_published"))
    try:
        raw = {"wizard_version": 1, "answers": {"payload": {"state": "ANSWERED", "value": 9999}}}
        rid = _create_requirement(client, {"payload_min_kg": 9999, "raw_input": raw})

        # Real matcher -> genuinely empty, and nothing persisted.
        m = client.get(f"/api/buyer-requirements/{rid}/matches")
        assert m.status_code == 200 and m.json()["matches"] == [], m.text
        assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == 0

        # A non-empty selection is rejected (no surfaced match backs it)...
        bad = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": ["digit"],
        })
        assert bad.status_code == 422, bad.text
        # ...and the empty selection creates the demand lead.
        resp = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [],
        })
        assert resp.status_code == 201, resp.text
        lid = resp.json()["id"]
        assert _scalar("SELECT count(*) FROM commercial_lead_robot WHERE lead_id=:l", l=lid) == 0
        # snapshot frozen server-side, and identity is NOT duplicated inside it
        snap = _scalar("SELECT requirements_snapshot FROM commercial_lead WHERE id=:l", l=lid)
        assert snap and snap["snapshot_version"] == 1
        assert "contact_email" not in snap and "contact_name" not in snap
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET search_path TO humanoid, public"))
            for robot_id, payload in original:
                conn.execute(
                    text("UPDATE robot SET payload_kg = :p WHERE id = :i"),
                    {"p": payload, "i": robot_id},
                )


# ---- L5 — repeated capture extends, never duplicates ----------------------

def test_l5_repeated_capture_extends(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    all_slugs = [m["robot"]["slug"] for m in matches]
    clicked = all_slugs[0]

    first = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [clicked],
    })
    assert first.status_code == 201
    lid = first.json()["id"]

    # same identity, now the whole shortlist -> 200, SAME lead, no duplicates
    second = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "Jane@Example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": all_slugs,
    })
    assert second.status_code == 200, second.text
    assert second.json()["id"] == lid
    assert _scalar("SELECT count(*) FROM commercial_lead WHERE requirement_id=:i", i=rid) == 1
    rows = _lead_robots(lid)
    assert len(rows) == len(all_slugs)                   # no duplicate robot links
    assert all(is_selected for _, _, is_selected in rows)  # selection unioned in


# ---- L6 — concurrent first capture ----------------------------------------

def test_l6_concurrent_capture_one_lead(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    slug = matches[0]["robot"]["slug"]
    results: list = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
        }))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r.status_code in (200, 201) for r in results), [r.status_code for r in results]
    # exactly one lead, and its robot links are not duplicated
    assert _scalar("SELECT count(*) FROM commercial_lead WHERE requirement_id=:i", i=rid) == 1
    lid = str(_scalar("SELECT id FROM commercial_lead WHERE requirement_id=:i", i=rid))
    n_links = _scalar("SELECT count(*) FROM commercial_lead_robot WHERE lead_id=:l", l=lid)
    assert n_links == len(matches)


# ---- L7 — identity conflict -----------------------------------------------

def test_l7_identity_conflict_409(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    slug = matches[0]["robot"]["slug"]

    first = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "alice@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert first.status_code == 201

    conflict = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "bob@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert conflict.status_code == 409, conflict.text
    # existing identity unchanged
    email = _scalar("SELECT contact_email FROM commercial_lead WHERE requirement_id=:i", i=rid)
    assert email == "alice@example.com"


# ---- L8 — direct Robot-Detail capture -------------------------------------

def test_l8_direct_capture(client, database_url) -> None:
    reqs_before = _scalar("SELECT count(*) FROM buyer_requirement")
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": ["digit"],
    })
    assert resp.status_code == 201, resp.text
    lid = resp.json()["id"]

    # a fresh minimal requirement was created and linked, atomically
    assert _scalar("SELECT count(*) FROM buyer_requirement") == reqs_before + 1
    req_id, btype = _rows(
        "SELECT requirement_id, "
        "(SELECT buyer_type FROM buyer_requirement WHERE id = cl.requirement_id) "
        "FROM commercial_lead cl WHERE cl.id=:l", l=lid,
    )[0]
    assert req_id is not None
    assert btype == "UNKNOWN"
    # selected robot attached with NULL match_score (never produced by the matcher)
    rows = _lead_robots(lid)
    assert len(rows) == 1
    slug, score, is_selected = rows[0]
    assert slug == "digit" and score is None and is_selected is True
    # origin retained in the requirement's versioned raw_input
    raw = _scalar("SELECT raw_input FROM buyer_requirement WHERE id=:i", i=str(req_id))
    assert raw["answers"]["robot_interest"] == {"state": "ANSWERED", "value": "digit"}


def test_l8_direct_capture_requires_exactly_one_robot(client, database_url) -> None:
    reqs_before = _scalar("SELECT count(*) FROM buyer_requirement")
    # zero robots -> 422
    empty = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [],
    })
    assert empty.status_code == 422, empty.text
    # more than one robot -> 422 (no such direct UI; adversarial handcrafted POST)
    many = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": ["digit", "unitree-g1", "apollo"],
    })
    assert many.status_code == 422, many.text
    # zero writes for either rejection
    assert _scalar("SELECT count(*) FROM buyer_requirement") == reqs_before


# ---- L9 — message round-trip ----------------------------------------------

def test_l9_message_round_trips(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    slug = _matches(client, rid)[0]["robot"]["slug"]
    msg = "We are evaluating 20 units for a 2027 deployment."
    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [slug], "message": msg,
    })
    assert resp.status_code == 201
    assert _scalar("SELECT message FROM commercial_lead WHERE id=:l", l=resp.json()["id"]) == msg


# ---- L10 — canonical region -----------------------------------------------

def test_l10_canonical_region(client, database_url) -> None:
    # DE resolves to a COUNTRY region on the lead
    ok = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": ["digit"], "country": "DE",
    })
    assert ok.status_code == 201, ok.text
    de_id = _scalar("SELECT id FROM region WHERE code='DE' AND type='COUNTRY'")
    assert str(_scalar(
        "SELECT country_region_id FROM commercial_lead WHERE id=:l", l=ok.json()["id"]
    )) == str(de_id)

    # EU is an economic zone, not a COUNTRY -> 422
    eu = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": ["digit"], "country": "EU",
    })
    assert eu.status_code == 422, eu.text
    # a nonsense code -> 422
    bad = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": ["digit"], "country": "ZZ",
    })
    assert bad.status_code == 422, bad.text


# ---- provider routing fixtures (L11–L13) ----------------------------------

def _region_id(code: str):
    return _scalar("SELECT id FROM region WHERE code=:c", c=code)


def _routing_case(
    client,
    *,
    is_active: bool = True,
    accepts_leads: bool = True,
    availability_status: str = "AVAILABLE",
    transaction_type: str = "RAAS",
    offer_region_code: str | None = None,
    lead_country: str | None = None,
    lead_pref: str | None = "RAAS",
):
    """Build an isolated manufacturer/robot/provider/offer graph, run one direct
    capture, and return (route_count, lead_id, provider_slug, route_status,
    route_contacted_at). Tears the whole graph down afterwards — no residue."""
    tag = uuid.uuid4().hex[:8]
    mfr_slug, robot_slug, provider_slug = f"m-{tag}", f"r-{tag}", f"p-{tag}"
    offer_region_id = _region_id(offer_region_code) if offer_region_code else None

    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        mfr_id = conn.execute(text(
            "INSERT INTO manufacturer (slug, name) VALUES (:s, :n) RETURNING id"
        ), {"s": mfr_slug, "n": f"Fixture Mfr {tag}"}).scalar_one()
        robot_id = conn.execute(text(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, true) RETURNING id"
        ), {"s": robot_slug, "m": mfr_id, "n": f"Fixture Robot {tag}"}).scalar_one()
        provider_id = conn.execute(text(
            "INSERT INTO provider (slug, type, name, is_active, accepts_leads) "
            "VALUES (:s, 'RAAS_PROVIDER', :n, :a, :al) RETURNING id"
        ), {"s": provider_slug, "n": f"Fixture Provider {tag}",
            "a": is_active, "al": accepts_leads}).scalar_one()
        conn.execute(text(
            "INSERT INTO availability_offer "
            "(robot_id, provider_id, region_id, transaction_type, "
            "availability_status, is_current) "
            "VALUES (:r, :p, :reg, :t, :st, true)"
        ), {"r": robot_id, "p": provider_id, "reg": offer_region_id,
            "t": transaction_type, "st": availability_status})

    payload = {
        "contact_email": "dev@example.com",
        "contact_name": "Test Buyer",
        "organization": "Test Org",
        "robot_slugs": [robot_slug],
    }
    if lead_country is not None:
        payload["country"] = lead_country
    if lead_pref is not None:
        payload["preferred_transaction"] = lead_pref
    resp = client.post("/api/commercial-leads", json=payload)
    assert resp.status_code == 201, resp.text
    lead_id = resp.json()["id"]

    routes = _rows(
        "SELECT p.slug, clp.status, clp.contacted_at FROM commercial_lead_provider clp "
        "JOIN provider p ON p.id = clp.provider_id WHERE clp.lead_id=:l", l=lead_id,
    )

    # teardown: lead (cascades robot/provider links), its requirement, then graph
    req_id = _scalar("SELECT requirement_id FROM commercial_lead WHERE id=:l", l=lead_id)
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        conn.execute(text("DELETE FROM commercial_lead WHERE id=:l"), {"l": lead_id})
        if req_id is not None:
            conn.execute(text("DELETE FROM buyer_requirement WHERE id=:i"), {"i": req_id})
        conn.execute(text("DELETE FROM availability_offer WHERE robot_id=:r"), {"r": robot_id})
        conn.execute(text("DELETE FROM robot WHERE id=:r"), {"r": robot_id})
        conn.execute(text("DELETE FROM provider WHERE id=:p"), {"p": provider_id})
        conn.execute(text("DELETE FROM manufacturer WHERE id=:m"), {"m": mfr_id})

    return routes


# ---- L11 — provider routing positive + L13 no false introduction ----------

def test_l11_routing_positive(client, database_url) -> None:
    routes = _routing_case(
        client, is_active=True, accepts_leads=True, availability_status="AVAILABLE",
        transaction_type="RAAS", offer_region_code=None, lead_pref="RAAS",
    )
    assert len(routes) == 1
    slug, status, contacted_at = routes[0]
    # L13: candidate route only — PENDING, never contacted.
    assert status == "PENDING"
    assert contacted_at is None


def test_l11_routing_all_accessible_statuses_are_eligible(client, database_url) -> None:
    # The canonical commercially_accessible() predicate: everything EXCEPT
    # NOT_AVAILABLE / DISCONTINUED counts as a real commercial path.
    for status in ("AVAILABLE", "WAITLIST", "PREORDER", "LIMITED", "ON_REQUEST"):
        routes = _routing_case(client, availability_status=status, lead_pref="RAAS")
        assert len(routes) == 1, f"{status} should be routable"


def test_l11_routing_flexible_matches_any_mode(client, database_url) -> None:
    routes = _routing_case(client, transaction_type="PURCHASE", lead_pref="FLEXIBLE")
    assert len(routes) == 1


def test_l11_routing_geography_ancestor_and_global(client, database_url) -> None:
    # offer scoped to the US COUNTRY, buyer in the US -> routes (exact match)
    assert len(_routing_case(client, offer_region_code="US", lead_country="US")) == 1
    # GLOBAL offer routes to any country
    assert len(_routing_case(client, offer_region_code="GLOBAL", lead_country="DE")) == 1


# ---- L12 — provider routing negatives -------------------------------------

def test_l12_routing_negatives(client, database_url) -> None:
    # accepts_leads = false
    assert len(_routing_case(client, accepts_leads=False)) == 0
    # inactive provider
    assert len(_routing_case(client, is_active=False)) == 0
    # inaccessible availability (the only two NOT commercially_accessible)
    assert len(_routing_case(client, availability_status="NOT_AVAILABLE")) == 0
    assert len(_routing_case(client, availability_status="DISCONTINUED")) == 0
    # wrong transaction mode (RENT preference vs PURCHASE-only offer)
    assert len(_routing_case(client, transaction_type="PURCHASE", lead_pref="RENT")) == 0
    # wrong geography (offer scoped to US, buyer in DE)
    assert len(_routing_case(client, offer_region_code="US", lead_country="DE")) == 0


# ---- Fix 2 — extension refines the LEAD only + route reconciliation --------

def _make_linked_fixture(
    *,
    transaction_type: str = "RAAS",
    offer_region_code: str | None = None,
    req_country: str = "US",
    req_pref: str = "RAAS",
):
    """Insert a controlled robot/provider/offer graph + a buyer_requirement with a
    persisted match_result for that robot, bypassing the matcher for determinism.
    Returns identifiers; call `_drop_linked_fixture` to tear it down."""
    tag = uuid.uuid4().hex[:8]
    offer_region_id = _region_id(offer_region_code) if offer_region_code else None
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        mfr_id = conn.execute(text(
            "INSERT INTO manufacturer (slug, name) VALUES (:s, :n) RETURNING id"
        ), {"s": f"m-{tag}", "n": f"Fixture Mfr {tag}"}).scalar_one()
        robot_id = conn.execute(text(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, true) RETURNING id"
        ), {"s": f"r-{tag}", "m": mfr_id, "n": f"Fixture Robot {tag}"}).scalar_one()
        provider_id = conn.execute(text(
            "INSERT INTO provider (slug, type, name, is_active, accepts_leads) "
            "VALUES (:s, 'RAAS_PROVIDER', :n, true, true) RETURNING id"
        ), {"s": f"p-{tag}", "n": f"Fixture Provider {tag}"}).scalar_one()
        conn.execute(text(
            "INSERT INTO availability_offer "
            "(robot_id, provider_id, region_id, transaction_type, "
            "availability_status, is_current) "
            "VALUES (:r, :p, :reg, :t, 'AVAILABLE', true)"
        ), {"r": robot_id, "p": provider_id, "reg": offer_region_id, "t": transaction_type})
        req_country_id = _region_id(req_country)
        req_id = conn.execute(text(
            "INSERT INTO buyer_requirement (country_region_id, preferred_transaction) "
            "VALUES (:c, :pref) RETURNING id"
        ), {"c": req_country_id, "pref": req_pref}).scalar_one()
        conn.execute(text(
            "INSERT INTO match_result (requirement_id, robot_id, score, rank, category) "
            "VALUES (:req, :rob, 90, 1, 'BEST_OVERALL')"
        ), {"req": req_id, "rob": robot_id})
    return {
        "robot_slug": f"r-{tag}", "robot_id": robot_id, "provider_id": provider_id,
        "mfr_id": mfr_id, "req_id": str(req_id), "req_country_id": req_country_id,
    }


def _drop_linked_fixture(fx) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        req = {"i": fx["req_id"]}
        rob = {"r": fx["robot_id"]}
        conn.execute(text("DELETE FROM commercial_lead WHERE requirement_id=:i"), req)
        conn.execute(text("DELETE FROM buyer_requirement WHERE id=:i"), req)
        conn.execute(text("DELETE FROM availability_offer WHERE robot_id=:r"), rob)
        conn.execute(text("DELETE FROM robot WHERE id=:r"), rob)
        conn.execute(text("DELETE FROM provider WHERE id=:p"), {"p": fx["provider_id"]})
        conn.execute(text("DELETE FROM manufacturer WHERE id=:m"), {"m": fx["mfr_id"]})


def test_extension_refines_lead_never_requirement(client, database_url) -> None:
    fx = _make_linked_fixture(req_country="US", req_pref="RAAS")
    try:
        rid = fx["req_id"]
        first = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Jane Doe", "organization": "Acme First",
            "robot_slugs": [fx["robot_slug"]],
        })
        assert first.status_code == 201, first.text

        # refine country + transaction on the SAME lead; a DIFFERENT organization
        # is submitted too, to prove the existing non-null identity field is
        # never silently overwritten by extension (contact_name/organization are
        # required on every submission now, so "NULL -> filled" is no longer
        # reachable via the public API; "non-null -> never replaced" still is).
        second = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Jane Doe", "organization": "Acme Later",
            "robot_slugs": [fx["robot_slug"]], "country": "DE",
            "preferred_transaction": "BUY",
        })
        assert second.status_code == 200, second.text

        de_id = _region_id("DE")
        lead = _rows(
            "SELECT country_region_id, preferred_transaction, organization "
            "FROM commercial_lead WHERE requirement_id=:i", i=rid,
        )[0]
        assert str(lead[0]) == str(de_id)          # lead country refined
        assert lead[1] == "BUY"                     # lead transaction refined
        assert lead[2] == "Acme First"               # org NEVER overwritten once set

        # the historical scoring requirement is UNCHANGED
        req = _rows(
            "SELECT country_region_id, preferred_transaction "
            "FROM buyer_requirement WHERE id=:i", i=rid,
        )[0]
        assert str(req[0]) == str(fx["req_country_id"])  # still US
        assert req[1] == "RAAS"                           # still RAAS
    finally:
        _drop_linked_fixture(fx)


def test_extension_reconciles_routes_add_remove_retain(client, database_url) -> None:
    # Provider offers the fixture robot ONLY under RAAS (region-agnostic).
    fx = _make_linked_fixture(transaction_type="RAAS", offer_region_code=None, req_pref="RAAS")
    try:
        rid, slug = fx["req_id"], fx["robot_slug"]

        def route_rows():
            return _rows(
                "SELECT status, contacted_at FROM commercial_lead_provider "
                "WHERE lead_id=(SELECT id FROM commercial_lead WHERE requirement_id=:i)",
                i=rid,
            )

        # First capture as BUY: RAAS offer is transaction-incompatible -> 0 routes.
        c1 = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [slug], "preferred_transaction": "BUY",
        })
        assert c1.status_code == 201, c1.text
        assert len(route_rows()) == 0

        # Refine to RAAS -> reconcile ADDS one PENDING route.
        c2 = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [slug], "preferred_transaction": "RAAS",
        })
        assert c2.status_code == 200, c2.text
        rows = route_rows()
        assert len(rows) == 1 and rows[0][0] == "PENDING" and rows[0][1] is None

        # Simulate ops marking the route CONTACTED (non-PENDING history).
        with engine.begin() as conn:
            conn.execute(text("SET search_path TO humanoid, public"))
            conn.execute(text(
                "UPDATE commercial_lead_provider SET status='CONTACTED', contacted_at=now() "
                "WHERE lead_id=(SELECT id FROM commercial_lead WHERE requirement_id=:i)"
            ), {"i": rid})

        # Refine back to BUY -> route is now ineligible, but it is CONTACTED, so it
        # is RETAINED as operational history (never removed, contacted_at intact).
        c3 = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [slug], "preferred_transaction": "BUY",
        })
        assert c3.status_code == 200, c3.text
        rows = route_rows()
        assert len(rows) == 1 and rows[0][0] == "CONTACTED" and rows[0][1] is not None
    finally:
        _drop_linked_fixture(fx)


def test_extension_removes_now_ineligible_pending_route(client, database_url) -> None:
    fx = _make_linked_fixture(transaction_type="RAAS", offer_region_code=None, req_pref="RAAS")
    try:
        rid, slug = fx["req_id"], fx["robot_slug"]

        def n_routes():
            return _scalar(
                "SELECT count(*) FROM commercial_lead_provider "
                "WHERE lead_id=(SELECT id FROM commercial_lead WHERE requirement_id=:i)",
                i=rid,
            )

        c1 = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [slug], "preferred_transaction": "RAAS",
        })
        assert c1.status_code == 201 and n_routes() == 1

        # Refine to BUY -> the still-PENDING RAAS route is now ineligible -> removed.
        c2 = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "jane@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [slug], "preferred_transaction": "BUY",
        })
        assert c2.status_code == 200 and n_routes() == 0
    finally:
        _drop_linked_fixture(fx)


# ---- L14 — WS5 anonymity regression ---------------------------------------

def test_l14_ws5_still_rejects_contact_fields(client, database_url) -> None:
    base_raw = {"wizard_version": 1, "answers": {"industry": {"state": "ANSWERED", "value": "logistics"}}}  # noqa: E501
    for field, value in (
        ("contact_email", "leak@example.com"),
        ("contact_name", "Jane"),
        ("organization", "Acme"),
    ):
        body = {"industry": "logistics", "raw_input": base_raw, field: value}
        resp = client.post("/api/buyer-requirements", json=body)
        assert resp.status_code == 422, (field, resp.status_code, resp.text)


# ---- Find a Humanoid contact-information enhancement -----------------------
# contact_name/organization are now required (API-layer only — the DB columns
# stay nullable); contact_phone is a new, genuinely optional, unvalidated field.

def test_contact_valid_submission_with_name_organization_email_succeeds(
    client, database_url
) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "valid-submit@example.com",
        "contact_name": "Valid Buyer", "organization": "Valid Org",
        "robot_slugs": ["digit"],
    })
    assert resp.status_code == 201, resp.text
    lid = resp.json()["id"]
    name, org = _rows(
        "SELECT contact_name, organization FROM commercial_lead WHERE id=:i", i=lid,
    )[0]
    assert name == "Valid Buyer"
    assert org == "Valid Org"


def test_contact_missing_full_name_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "no-name@example.com", "organization": "Some Org",
        "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_blank_full_name_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "blank-name@example.com", "contact_name": "   ",
        "organization": "Some Org", "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_missing_organization_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "no-org@example.com", "contact_name": "Some Buyer",
        "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_blank_organization_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "blank-org@example.com", "contact_name": "Some Buyer",
        "organization": "   ", "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_missing_email_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_name": "Some Buyer", "organization": "Some Org",
        "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_phone_omitted_succeeds(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "phone-omitted@example.com",
        "contact_name": "No Phone Buyer", "organization": "No Phone Org",
        "robot_slugs": ["digit"],
    })
    assert resp.status_code == 201, resp.text
    lid = resp.json()["id"]
    phone = _scalar("SELECT contact_phone FROM commercial_lead WHERE id=:i", i=lid)
    assert phone is None


def test_contact_phone_supplied_and_persisted(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "phone-supplied@example.com",
        "contact_name": "Phone Buyer", "organization": "Phone Org",
        "contact_phone": " +1 (555) 123-4567 ", "robot_slugs": ["digit"],
    })
    assert resp.status_code == 201, resp.text
    lid = resp.json()["id"]
    phone = _scalar("SELECT contact_phone FROM commercial_lead WHERE id=:i", i=lid)
    # trimmed, not otherwise reformatted/normalized
    assert phone == "+1 (555) 123-4567"


def test_contact_phone_over_max_length_rejected(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "phone-toolong@example.com",
        "contact_name": "Phone Buyer", "organization": "Phone Org",
        "contact_phone": "1" * 41, "robot_slugs": ["digit"],
    })
    assert resp.status_code == 422, resp.text


def test_contact_phone_extension_fills_null_but_never_overwrites(
    client, database_url
) -> None:
    fx = _make_linked_fixture()
    try:
        rid, slug = fx["req_id"], fx["robot_slug"]
        first = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "phone-ext@example.com",
            "contact_name": "Phone Ext Buyer", "organization": "Phone Ext Org",
            "robot_slugs": [slug],
        })
        assert first.status_code == 201, first.text
        assert _scalar(
            "SELECT contact_phone FROM commercial_lead WHERE requirement_id=:i", i=rid
        ) is None

        # extend with a phone number -> fills the currently-NULL value
        second = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "phone-ext@example.com",
            "contact_name": "Phone Ext Buyer", "organization": "Phone Ext Org",
            "contact_phone": "+1-555-0100", "robot_slugs": [slug],
        })
        assert second.status_code == 200, second.text
        assert _scalar(
            "SELECT contact_phone FROM commercial_lead WHERE requirement_id=:i", i=rid
        ) == "+1-555-0100"

        # extend again with a DIFFERENT phone -> the existing non-null value stays
        third = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": "phone-ext@example.com",
            "contact_name": "Phone Ext Buyer", "organization": "Phone Ext Org",
            "contact_phone": "+1-555-9999", "robot_slugs": [slug],
        })
        assert third.status_code == 200, third.text
        assert _scalar(
            "SELECT contact_phone FROM commercial_lead WHERE requirement_id=:i", i=rid
        ) == "+1-555-0100"
    finally:
        _drop_linked_fixture(fx)


def test_historical_lead_rows_without_name_organization_phone_remain_valid(
    client, database_url
) -> None:
    """A row written before this change (all three NULL, as the API used to
    allow) must still be a perfectly valid, selectable row — the required-field
    rule is enforced only at the API edge, never by a DB constraint that would
    invalidate history."""
    lead_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        conn.execute(
            text(
                "INSERT INTO commercial_lead (id, contact_email, contact_name, "
                "organization, contact_phone) "
                "VALUES (:id, :email, NULL, NULL, NULL)"
            ),
            {"id": lead_id, "email": "historical-null@example.com"},
        )
    try:
        row = _rows(
            "SELECT contact_name, organization, contact_phone "
            "FROM commercial_lead WHERE id=:i", i=lead_id,
        )[0]
        assert row[0] is None and row[1] is None and row[2] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET search_path TO humanoid, public"))
            conn.execute(text("DELETE FROM commercial_lead WHERE id=:i"), {"i": lead_id})
