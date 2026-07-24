"""WS5 buyer-intent write-path tests (against the seeded database).

Locks the acceptance criteria (05_ACCEPTANCE_CRITERIA §D) and the data laws that
must never regress on the platform's first write path:
  D1 Germany -> DE + full raw_input · D2 RENT persists · D3 no lead required
  UNKNOWN != SKIPPED (raw_input) · known FALSE survives · no-budget -> NULL currency
  canonical-only resolution (invalid use_case/country -> 422) · >=1 signal required
  create writes zero match_result and zero commercial_lead rows.

These require the seed; they skip when DATABASE_URL is unset (see conftest).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.buyer_requirement import BuyerRequirement


def _post(client, body):
    return client.post("/api/buyer-requirements", json=body)


def _created_id(client, body) -> str:
    resp = _post(client, body)
    assert resp.status_code == 201, (resp.status_code, resp.text)
    data = resp.json()
    assert set(data.keys()) == {"id"}
    uuid.UUID(data["id"])  # valid UUID
    return data["id"]


def _fetch(req_id: str) -> BuyerRequirement:
    with SessionLocal() as session:
        row = session.get(BuyerRequirement, uuid.UUID(req_id))
        assert row is not None
        session.expunge(row)
        return row


def _scalar(sql: str, **params) -> int:
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        return conn.execute(text(sql), params).scalar_one()


# ---- D1 -----------------------------------------------------------------

def test_d1_germany_logistics_resolves_de_and_keeps_raw_input(client, database_url) -> None:
    raw = {
        "wizard_version": 1,
        "answers": {
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics",
                     "task_description": "Move totes from conveyor to pallets"},
            "industry": {"state": "ANSWERED", "value": "logistics"},
            "country": {"state": "ANSWERED", "value": "DE"},
            "payload": {"state": "UNKNOWN"},
            "environment": {"state": "SKIPPED"},
        },
    }
    req_id = _created_id(client, {
        "use_case": "warehouse-logistics",
        "industry": "logistics",
        "task_description": "Move totes from conveyor to pallets",
        "country": "DE",
        "raw_input": raw,
    })
    row = _fetch(req_id)

    # country resolved to the canonical DE region row.
    de_id = _scalar("SELECT id FROM region WHERE code = 'DE'")
    assert str(row.country_region_id) == str(de_id)
    # use_case resolved.
    uc_id = _scalar("SELECT id FROM use_case WHERE slug = 'warehouse-logistics'")
    assert str(row.use_case_id) == str(uc_id)
    # full answers retained verbatim.
    assert row.raw_input == raw


# ---- D2 -----------------------------------------------------------------

def test_d2_rent_preference_persists(client, database_url) -> None:
    req_id = _created_id(client, {"preferred_transaction": "RENT"})
    assert _fetch(req_id).preferred_transaction == "RENT"


# ---- D3 -----------------------------------------------------------------

def test_d3_requirement_exists_without_lead_or_match(client, database_url) -> None:
    req_id = _created_id(client, {"use_case": "warehouse-logistics"})
    assert _scalar(
        "SELECT count(*) FROM commercial_lead WHERE requirement_id = :i", i=req_id
    ) == 0
    assert _scalar(
        "SELECT count(*) FROM match_result WHERE requirement_id = :i", i=req_id
    ) == 0


# ---- UNKNOWN != SKIPPED --------------------------------------------------

def test_unknown_vs_skipped_preserved_in_raw_input(client, database_url) -> None:
    raw = {
        "wizard_version": 1,
        "answers": {
            "payload": {"state": "UNKNOWN"},
            "environment": {"state": "SKIPPED"},
        },
    }
    # Both project to NULL structured columns; raw_input keeps them distinct.
    req_id = _created_id(client, {"raw_input": raw})  # UNKNOWN answer is the signal
    row = _fetch(req_id)
    assert row.payload_min_kg is None
    assert row.environment is None
    assert row.raw_input["answers"]["payload"]["state"] == "UNKNOWN"
    assert row.raw_input["answers"]["environment"]["state"] == "SKIPPED"


# ---- known FALSE survives ------------------------------------------------

def test_manipulation_false_persists_as_false(client, database_url) -> None:
    req_id = _created_id(client, {"manipulation_required": False})
    row = _fetch(req_id)
    assert row.manipulation_required is False  # not None, not dropped


def test_manipulation_true_persists(client, database_url) -> None:
    row = _fetch(_created_id(client, {"manipulation_required": True}))
    assert row.manipulation_required is True


# ---- budget: no silent USD ----------------------------------------------

def test_no_budget_does_not_fabricate_currency(client, database_url) -> None:
    row = _fetch(_created_id(client, {"use_case": "warehouse-logistics"}))
    assert row.budget_min is None and row.budget_max is None
    assert row.budget_currency is None  # DDL DEFAULT 'USD' must NOT fire


def test_budget_with_amount_keeps_currency(client, database_url) -> None:
    req_id = _created_id(client, {"budget": {"currency": "EUR", "max": 250000}})
    row = _fetch(req_id)
    assert row.budget_currency == "EUR"
    assert float(row.budget_max) == 250000.0
    assert row.budget_min is None


def test_budget_amount_without_currency_is_422(client, database_url) -> None:
    resp = _post(client, {"budget": {"max": 250000}})
    assert resp.status_code == 422


def test_budget_min_gt_max_is_422(client, database_url) -> None:
    resp = _post(client, {"budget": {"currency": "USD", "min": 100, "max": 10}})
    assert resp.status_code == 422


# ---- canonical resolution only ------------------------------------------

def test_invalid_use_case_is_422(client, database_url) -> None:
    resp = _post(client, {"use_case": "no-such-use-case"})
    assert resp.status_code == 422


def test_invalid_country_is_422_not_null(client, database_url) -> None:
    # A stated country that does not resolve is a rejection, never a silent NULL.
    resp = _post(client, {"country": "ZZ", "use_case": "warehouse-logistics"})
    assert resp.status_code == 422


# ---- at least one requirement signal ------------------------------------

def test_empty_body_is_422_no_signal(client, database_url) -> None:
    resp = _post(client, {})
    assert resp.status_code == 422


def test_all_skipped_no_signal_is_422(client, database_url) -> None:
    raw = {"wizard_version": 1, "answers": {
        "payload": {"state": "SKIPPED"}, "environment": {"state": "SKIPPED"}}}
    resp = _post(client, {"raw_input": raw})
    assert resp.status_code == 422


def test_lone_unknown_answer_is_a_signal(client, database_url) -> None:
    raw = {"wizard_version": 1, "answers": {"payload": {"state": "UNKNOWN"}}}
    assert _post(client, {"raw_input": raw}).status_code == 201


def test_explicit_unknown_transaction_choice_is_a_signal(client, database_url) -> None:
    # Explicitly choosing "Unknown" for transaction (ANSWERED, value UNKNOWN) is a
    # first-class demand signal — distinct from skipping the step.
    raw = {"wizard_version": 1,
           "answers": {"transaction": {"state": "ANSWERED", "value": "UNKNOWN"}}}
    resp = _post(client, {"preferred_transaction": "UNKNOWN", "raw_input": raw})
    assert resp.status_code == 201


# ---- defaults ------------------------------------------------------------

def test_buyer_type_defaults_unknown(client, database_url) -> None:
    row = _fetch(_created_id(client, {"use_case": "warehouse-logistics"}))
    assert row.buyer_type == "UNKNOWN"


def test_bad_enum_is_422(client, database_url) -> None:
    assert _post(client, {"preferred_transaction": "BUYNOW"}).status_code == 422
    assert _post(client, {"autonomy_required": "SUPER"}).status_code == 422


# ---- regions read (drives the canonical Country step) -------------------

def test_regions_country_list_includes_de(client, database_url) -> None:
    resp = client.get("/api/regions", params={"type": "COUNTRY"})
    assert resp.status_code == 200
    rows = resp.json()
    assert all(r["type"] == "COUNTRY" for r in rows)
    de = next((r for r in rows if r["code"] == "DE"), None)
    assert de is not None and de["name"] == "Germany" and de["iso_country"] == "DE"


# ---- global invariant: WS5 creates no matches or leads ------------------

def test_create_writes_zero_matches_and_leads_globally(client, database_url) -> None:
    before_m = _scalar("SELECT count(*) FROM match_result")
    before_l = _scalar("SELECT count(*) FROM commercial_lead")
    for body in ({"use_case": "warehouse-logistics"}, {"preferred_transaction": "RAAS"},
                 {"manipulation_required": False}):
        _created_id(client, body)
    assert _scalar("SELECT count(*) FROM match_result") == before_m
    assert _scalar("SELECT count(*) FROM commercial_lead") == before_l
