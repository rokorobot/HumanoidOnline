"""WS6 matching API tests (against the seeded database).

Covers the frozen trigger/persistence contract for
`GET /api/buyer-requirements/{id}/matches`: first-fetch scores + persists,
second-fetch is idempotent (no rescoring, no duplicate rows), concurrent first
fetches are safe (row lock), unknown id -> 404, matching writes zero
commercial_lead rows, and the anonymous requirement read for Adjust.
"""
from __future__ import annotations

import threading
import uuid

from sqlalchemy import text

from app.db.session import engine


def _scalar(sql: str, **params) -> int:
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        return conn.execute(text(sql), params).scalar_one()


#: Merged into every _create call — the wizard's contact step now requires
#: this on every /api/buyer-requirements POST; these tests care about the
#: WS6 matching/persistence contract, not requirement identity specifically.
_REQ_IDENTITY = {
    "contact_name": "Test Buyer", "organization": "Test Org",
    "contact_email": "buyer@example.com",
}


def _create(client, body) -> str:
    resp = client.post("/api/buyer-requirements", json={**_REQ_IDENTITY, **body})
    assert resp.status_code == 201, (resp.status_code, resp.text)
    return resp.json()["id"]


def _warehouse(client) -> str:
    raw = {
        "wizard_version": 1,
        "answers": {
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
            "country": {"state": "ANSWERED", "value": "US"},
            "payload": {"state": "ANSWERED", "value": 10},
        },
    }
    return _create(client, {
        "use_case": "warehouse-logistics", "country": "US", "payload_min_kg": 10,
        "preferred_transaction": "RAAS", "raw_input": raw,
    })


# ---- first fetch: score + persist ---------------------------------------

def test_first_fetch_scores_and_persists(client, database_url) -> None:
    rid = _warehouse(client)
    assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == 0

    body = client.get(f"/api/buyer-requirements/{rid}/matches")
    assert body.status_code == 200
    data = body.json()
    assert data["requirement_id"] == rid
    assert 1 <= len(data["matches"]) <= 4
    assert "excluded_count" in data and "no_match_explanation" in data

    # persisted rows now match the response.
    assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == len(
        data["matches"]
    )

    first = data["matches"][0]
    assert first["rank"] == 1 and first["category"] == "BEST_OVERALL"
    # E6 for EVERY returned match: score == round(sum(breakdown)) and >= 2 reasons.
    for m in data["matches"]:
        assert m["score"] == round(sum(m["score_breakdown"].values()))
        assert len(m["reasons"]) >= 2
    assert set(first["score_breakdown"]) == {
        "use_case_fit", "commercial_availability", "technical_fit",
        "geographic_fit", "budget_fit", "deployment_readiness",
    }
    # ranks are contiguous and scores are non-increasing.
    ranks = [m["rank"] for m in data["matches"]]
    assert ranks == list(range(1, len(ranks) + 1))
    scores = [m["score"] for m in data["matches"]]
    assert scores == sorted(scores, reverse=True)


# ---- second fetch: idempotent ------------------------------------------

def test_second_fetch_is_idempotent(client, database_url) -> None:
    rid = _warehouse(client)
    a = client.get(f"/api/buyer-requirements/{rid}/matches").json()
    n_after_first = _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid)
    b = client.get(f"/api/buyer-requirements/{rid}/matches").json()
    # byte-identical response, and no new rows written.
    assert a == b
    n2 = _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid)
    assert n2 == n_after_first


# ---- concurrent first fetch: safe --------------------------------------

def test_concurrent_first_fetch_persists_once(client, database_url) -> None:
    rid = _warehouse(client)
    results: list = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(client.get(f"/api/buyer-requirements/{rid}/matches"))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r.status_code == 200 for r in results)
    j0, j1 = (r.json() for r in results)
    slugs0 = [m["robot"]["slug"] for m in j0["matches"]]
    slugs1 = [m["robot"]["slug"] for m in j1["matches"]]
    assert slugs0 == slugs1
    # exactly one row per match — no duplicate persistence under the row lock.
    n = _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid)
    assert n == len(j0["matches"])


# ---- zero leads ---------------------------------------------------------

def test_matching_writes_no_commercial_lead(client, database_url) -> None:
    before = _scalar("SELECT count(*) FROM commercial_lead")
    rid = _warehouse(client)
    client.get(f"/api/buyer-requirements/{rid}/matches")
    assert _scalar("SELECT count(*) FROM commercial_lead") == before


# ---- E7 at the API boundary: all candidates excluded --------------------

def test_e7_all_candidates_excluded_returns_deterministic_empty(client, database_url) -> None:
    # Controlled state: give every published robot a KNOWN low payload, then
    # require a huge payload so all are hard-excluded. Restore afterwards.
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        original = conn.execute(
            text("SELECT id, payload_kg FROM robot WHERE is_published")
        ).all()
        conn.execute(text("UPDATE robot SET payload_kg = 1 WHERE is_published"))
    try:
        leads_before = _scalar("SELECT count(*) FROM commercial_lead")
        raw = {"wizard_version": 1, "answers": {"payload": {"state": "ANSWERED", "value": 9999}}}
        rid = _create(client, {"payload_min_kg": 9999, "raw_input": raw})

        a = client.get(f"/api/buyer-requirements/{rid}/matches")
        assert a.status_code == 200
        ja = a.json()
        assert ja["matches"] == []
        assert ja["no_match_explanation"] and "payload" in ja["no_match_explanation"].lower()
        assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == 0

        # idempotent second GET — same response, still zero persisted rows.
        jb = client.get(f"/api/buyer-requirements/{rid}/matches").json()
        assert ja == jb
        assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id=:i", i=rid) == 0
        # matching still writes no leads.
        assert _scalar("SELECT count(*) FROM commercial_lead") == leads_before
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET search_path TO humanoid, public"))
            for robot_id, payload in original:
                conn.execute(
                    text("UPDATE robot SET payload_kg = :p WHERE id = :i"),
                    {"p": payload, "i": robot_id},
                )


# ---- unknown id ---------------------------------------------------------

def test_matches_unknown_id_404(client, database_url) -> None:
    assert client.get(f"/api/buyer-requirements/{uuid.uuid4()}/matches").status_code == 404
    assert client.get("/api/buyer-requirements/not-a-uuid/matches").status_code == 404


# ---- anonymous requirement read (Adjust) --------------------------------

def test_requirement_read_is_anonymous_with_raw_input(client, database_url) -> None:
    rid = _warehouse(client)
    data = client.get(f"/api/buyer-requirements/{rid}").json()
    assert data["id"] == rid
    assert data["use_case"] == "warehouse-logistics"
    assert data["country"] == "US"
    # anonymous: no contact keys are exposed.
    assert not ({"contact_name", "contact_email", "organization"} & set(data))
    # raw_input round-trips (Adjust re-seeds the wizard from it).
    assert data["raw_input"]["wizard_version"] == 1
    assert data["raw_input"]["answers"]["task"]["use_case"] == "warehouse-logistics"


def test_requirement_read_unknown_id_404(client, database_url) -> None:
    assert client.get(f"/api/buyer-requirements/{uuid.uuid4()}").status_code == 404
