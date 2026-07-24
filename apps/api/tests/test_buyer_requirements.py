"""WS5 buyer-intent write-path tests (against the seeded database).

Locks the acceptance criteria (05_ACCEPTANCE_CRITERIA §D) and the data/contract
laws that must never regress on the platform's first write path:
  D1 Germany -> DE + full raw_input · D2 RENT persists · D3 no lead required
  UNKNOWN != SKIPPED (raw_input) · known FALSE survives · no-budget -> NULL currency
  canonical COUNTRY-only resolution (EU/GLOBAL/ZZ -> 422) · anonymous (no contact)
  versioned raw_input required · >=1 signal · create writes zero match_result/lead.

These require the seed; they skip when DATABASE_URL is unset (see conftest).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.buyer_requirement import BuyerRequirement


def rawv(answers: dict | None = None) -> dict:
    """A valid versioned raw_input wrapper (WS5 requires this on every POST)."""
    return {"wizard_version": 1, "answers": answers or {}}


def _post(client, body):
    return client.post("/api/buyer-requirements", json=body)


def _created_id(client, body) -> str:
    resp = _post(client, body)
    assert resp.status_code == 201, (resp.status_code, resp.text)
    data = resp.json()
    assert set(data.keys()) == {"id"}
    uuid.UUID(data["id"])
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


def _req_count() -> int:
    return _scalar("SELECT count(*) FROM buyer_requirement")


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

    de_id = _scalar("SELECT id FROM region WHERE code = 'DE'")
    assert str(row.country_region_id) == str(de_id)
    uc_id = _scalar("SELECT id FROM use_case WHERE slug = 'warehouse-logistics'")
    assert str(row.use_case_id) == str(uc_id)
    assert row.raw_input == raw


# ---- D2 -----------------------------------------------------------------

def test_d2_rent_preference_persists(client, database_url) -> None:
    req_id = _created_id(client, {
        "preferred_transaction": "RENT",
        "raw_input": rawv({"transaction": {"state": "ANSWERED", "value": "RENT"}}),
    })
    assert _fetch(req_id).preferred_transaction == "RENT"


# ---- D3 -----------------------------------------------------------------

def test_d3_requirement_exists_without_lead_or_match(client, database_url) -> None:
    req_id = _created_id(client, {
        "use_case": "warehouse-logistics",
        "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"}}),
    })
    assert _scalar("SELECT count(*) FROM commercial_lead WHERE requirement_id = :i", i=req_id) == 0
    assert _scalar("SELECT count(*) FROM match_result WHERE requirement_id = :i", i=req_id) == 0


# ---- UNKNOWN != SKIPPED --------------------------------------------------

def test_unknown_vs_skipped_preserved_in_raw_input(client, database_url) -> None:
    raw = {
        "wizard_version": 1,
        "answers": {
            "payload": {"state": "UNKNOWN"},
            "environment": {"state": "SKIPPED"},
        },
    }
    req_id = _created_id(client, {"raw_input": raw})  # UNKNOWN answer is the signal
    row = _fetch(req_id)
    assert row.payload_min_kg is None
    assert row.environment is None
    assert row.raw_input["answers"]["payload"]["state"] == "UNKNOWN"
    assert row.raw_input["answers"]["environment"]["state"] == "SKIPPED"


# ---- known FALSE survives ------------------------------------------------

def test_manipulation_false_persists_as_false(client, database_url) -> None:
    req_id = _created_id(client, {
        "manipulation_required": False,
        "raw_input": rawv({"manipulation": {"state": "ANSWERED", "value": False}}),
    })
    assert _fetch(req_id).manipulation_required is False


def test_manipulation_true_persists(client, database_url) -> None:
    req_id = _created_id(client, {
        "manipulation_required": True,
        "raw_input": rawv({"manipulation": {"state": "ANSWERED", "value": True}}),
    })
    assert _fetch(req_id).manipulation_required is True


# ---- budget: no silent USD ----------------------------------------------

def test_no_budget_does_not_fabricate_currency(client, database_url) -> None:
    req_id = _created_id(client, {
        "use_case": "warehouse-logistics",
        "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
                           "budget": {"state": "SKIPPED"}}),
    })
    row = _fetch(req_id)
    assert row.budget_min is None and row.budget_max is None
    assert row.budget_currency is None  # DDL DEFAULT 'USD' must NOT fire


def test_budget_with_amount_keeps_currency(client, database_url) -> None:
    req_id = _created_id(client, {
        "budget": {"currency": "EUR", "max": 250000},
        "raw_input": rawv({"budget": {"state": "ANSWERED", "currency": "EUR", "max": 250000}}),
    })
    row = _fetch(req_id)
    assert row.budget_currency == "EUR"
    assert float(row.budget_max) == 250000.0
    assert row.budget_min is None


def test_budget_amount_without_currency_is_422(client, database_url) -> None:
    resp = _post(client, {
        "budget": {"max": 250000},
        "raw_input": rawv({"budget": {"state": "ANSWERED"}}),
    })
    assert resp.status_code == 422


def test_budget_min_gt_max_is_422(client, database_url) -> None:
    resp = _post(client, {
        "budget": {"currency": "USD", "min": 100, "max": 10},
        "raw_input": rawv({"budget": {"state": "ANSWERED"}}),
    })
    assert resp.status_code == 422


# ---- canonical resolution only ------------------------------------------

def test_invalid_use_case_is_422(client, database_url) -> None:
    resp = _post(client, {"use_case": "no-such-use-case", "raw_input": rawv()})
    assert resp.status_code == 422


def test_country_resolves_only_to_canonical_country_rows(client, database_url) -> None:
    # DE is a COUNTRY -> 201; EU (economic zone) and GLOBAL must NOT resolve; ZZ
    # does not exist. Every rejection leaves the requirement count unchanged.
    def country_body(code):
        answer = {"country": {"state": "ANSWERED", "value": code}}
        return {"country": code, "raw_input": rawv(answer)}

    assert _post(client, country_body("DE")).status_code == 201

    before = _req_count()
    for bad in ("EU", "GLOBAL", "ZZ"):
        resp = _post(client, country_body(bad))
        assert resp.status_code == 422, (bad, resp.status_code, resp.text)
    assert _req_count() == before  # no partial persistence on rejected requests


# ---- anonymous: no contact identity in WS5 ------------------------------

def test_contact_fields_are_rejected(client, database_url) -> None:
    before = _req_count()
    for field in ("contact_email", "contact_name", "organization"):
        resp = _post(client, {
            "use_case": "warehouse-logistics",
            field: "someone@example.com" if field == "contact_email" else "Someone",
            "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"}}),
        })
        assert resp.status_code == 422, (field, resp.status_code, resp.text)
    assert _req_count() == before


# ---- versioned raw_input required ---------------------------------------

def test_missing_raw_input_is_422(client, database_url) -> None:
    before = _req_count()
    resp = _post(client, {"use_case": "warehouse-logistics"})
    assert resp.status_code == 422
    assert _req_count() == before


def test_unversioned_raw_input_is_422(client, database_url) -> None:
    resp = _post(client, {"use_case": "warehouse-logistics", "raw_input": {"answers": {}}})
    assert resp.status_code == 422


def test_invalid_answer_state_is_422(client, database_url) -> None:
    resp = _post(client, {
        "raw_input": {"wizard_version": 1, "answers": {"payload": {"state": "MAYBE"}}},
    })
    assert resp.status_code == 422


# ---- at least one requirement signal ------------------------------------

def test_all_skipped_no_signal_is_422(client, database_url) -> None:
    raw = {"wizard_version": 1, "answers": {
        "payload": {"state": "SKIPPED"}, "environment": {"state": "SKIPPED"}}}
    resp = _post(client, {"raw_input": raw})
    assert resp.status_code == 422


def test_lone_unknown_answer_is_a_signal(client, database_url) -> None:
    raw = {"wizard_version": 1, "answers": {"payload": {"state": "UNKNOWN"}}}
    assert _post(client, {"raw_input": raw}).status_code == 201


def test_explicit_unknown_transaction_choice_is_a_signal(client, database_url) -> None:
    raw = {"wizard_version": 1,
           "answers": {"transaction": {"state": "ANSWERED", "value": "UNKNOWN"}}}
    resp = _post(client, {"preferred_transaction": "UNKNOWN", "raw_input": raw})
    assert resp.status_code == 201


# ---- defaults ------------------------------------------------------------

def test_buyer_type_defaults_unknown(client, database_url) -> None:
    req_id = _created_id(client, {
        "use_case": "warehouse-logistics",
        "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"}}),
    })
    assert _fetch(req_id).buyer_type == "UNKNOWN"


def test_bad_enum_is_422(client, database_url) -> None:
    bad_txn = _post(client, {"preferred_transaction": "BUYNOW", "raw_input": rawv()})
    assert bad_txn.status_code == 422
    bad_autonomy = _post(client, {"autonomy_required": "SUPER", "raw_input": rawv()})
    assert bad_autonomy.status_code == 422


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
    for body in (
        {"use_case": "warehouse-logistics",
         "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"}})},
        {"preferred_transaction": "RAAS",
         "raw_input": rawv({"transaction": {"state": "ANSWERED", "value": "RAAS"}})},
        {"manipulation_required": False,
         "raw_input": rawv({"manipulation": {"state": "ANSWERED", "value": False}})},
    ):
        _created_id(client, body)
    assert _scalar("SELECT count(*) FROM match_result") == before_m
    assert _scalar("SELECT count(*) FROM commercial_lead") == before_l
