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
        "organization": "Acme", "robot_slugs": [clicked],
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
        "robot_slugs": ["unitree-g1"],
    })
    assert resp.status_code == 422, resp.text
    # no writes
    assert _scalar("SELECT count(*) FROM commercial_lead") == leads_before
    assert _scalar("SELECT count(*) FROM commercial_lead_robot") == robots_before


# ---- L4 — zero match ------------------------------------------------------

def test_l4_zero_match_capture(client, database_url) -> None:
    # A requirement with no persisted match_result. Only an empty selection is
    # valid; the lead is created as demand intelligence with zero robot rows.
    raw = {"wizard_version": 1, "answers": {"industry": {"state": "ANSWERED", "value": "logistics"}}}  # noqa: E501
    rid = _create_requirement(client, {"industry": "logistics", "raw_input": raw})
    assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == 0

    # a non-empty selection is rejected
    bad = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com", "robot_slugs": ["digit"],
    })
    assert bad.status_code == 422, bad.text

    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com", "robot_slugs": [],
    })
    assert resp.status_code == 201, resp.text
    lid = resp.json()["id"]
    assert _scalar("SELECT count(*) FROM commercial_lead_robot WHERE lead_id=:l", l=lid) == 0
    # snapshot frozen server-side, and identity is NOT duplicated inside it
    snap = _scalar("SELECT requirements_snapshot FROM commercial_lead WHERE id=:l", l=lid)
    assert snap and snap["snapshot_version"] == 1 and snap["industry"] == "logistics"
    assert "contact_email" not in snap and "contact_name" not in snap


# ---- L5 — repeated capture extends, never duplicates ----------------------

def test_l5_repeated_capture_extends(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    matches = _matches(client, rid)
    all_slugs = [m["robot"]["slug"] for m in matches]
    clicked = all_slugs[0]

    first = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com", "robot_slugs": [clicked],
    })
    assert first.status_code == 201
    lid = first.json()["id"]

    # same identity, now the whole shortlist -> 200, SAME lead, no duplicates
    second = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "Jane@Example.com", "robot_slugs": all_slugs,
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
            "requirement_id": rid, "contact_email": "jane@example.com", "robot_slugs": [slug],
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
        "requirement_id": rid, "contact_email": "alice@example.com", "robot_slugs": [slug],
    })
    assert first.status_code == 201

    conflict = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "bob@example.com", "robot_slugs": [slug],
    })
    assert conflict.status_code == 409, conflict.text
    # existing identity unchanged
    email = _scalar("SELECT contact_email FROM commercial_lead WHERE requirement_id=:i", i=rid)
    assert email == "alice@example.com"


# ---- L8 — direct Robot-Detail capture -------------------------------------

def test_l8_direct_capture(client, database_url) -> None:
    reqs_before = _scalar("SELECT count(*) FROM buyer_requirement")
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com", "robot_slugs": ["digit"],
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


def test_l8_direct_capture_requires_a_robot(client, database_url) -> None:
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com", "robot_slugs": [],
    })
    assert resp.status_code == 422, resp.text


# ---- L9 — message round-trip ----------------------------------------------

def test_l9_message_round_trips(client, database_url) -> None:
    rid = _warehouse_requirement(client)
    slug = _matches(client, rid)[0]["robot"]["slug"]
    msg = "We are evaluating 20 units for a 2027 deployment."
    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "jane@example.com",
        "robot_slugs": [slug], "message": msg,
    })
    assert resp.status_code == 201
    assert _scalar("SELECT message FROM commercial_lead WHERE id=:l", l=resp.json()["id"]) == msg


# ---- L10 — canonical region -----------------------------------------------

def test_l10_canonical_region(client, database_url) -> None:
    # DE resolves to a COUNTRY region on the lead
    ok = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com", "robot_slugs": ["digit"], "country": "DE",
    })
    assert ok.status_code == 201, ok.text
    de_id = _scalar("SELECT id FROM region WHERE code='DE' AND type='COUNTRY'")
    assert str(_scalar(
        "SELECT country_region_id FROM commercial_lead WHERE id=:l", l=ok.json()["id"]
    )) == str(de_id)

    # EU is an economic zone, not a COUNTRY -> 422
    eu = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com", "robot_slugs": ["digit"], "country": "EU",
    })
    assert eu.status_code == 422, eu.text
    # a nonsense code -> 422
    bad = client.post("/api/commercial-leads", json={
        "contact_email": "dev@example.com", "robot_slugs": ["digit"], "country": "ZZ",
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
            "(robot_id, provider_id, region_id, transaction_type, availability_status, is_current) "
            "VALUES (:r, :p, :reg, :t, :st, true)"
        ), {"r": robot_id, "p": provider_id, "reg": offer_region_id,
            "t": transaction_type, "st": availability_status})

    payload = {"contact_email": "dev@example.com", "robot_slugs": [robot_slug]}
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
    # inaccessible availability
    assert len(_routing_case(client, availability_status="NOT_AVAILABLE")) == 0
    assert len(_routing_case(client, availability_status="DISCONTINUED")) == 0
    # wrong transaction mode (RENT preference vs PURCHASE-only offer)
    assert len(_routing_case(client, transaction_type="PURCHASE", lead_pref="RENT")) == 0
    # wrong geography (offer scoped to US, buyer in DE)
    assert len(_routing_case(client, offer_region_code="US", lead_country="DE")) == 0


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
