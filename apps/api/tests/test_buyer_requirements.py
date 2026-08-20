"""WS5 buyer-intent write-path tests (against the seeded database).

Locks the acceptance criteria (05_ACCEPTANCE_CRITERIA §D) and the data/contract
laws that must never regress on the platform's first write path:
  D1 Germany -> DE + full raw_input · D2 RENT persists · D3 no lead required
  UNKNOWN != SKIPPED (raw_input) · known FALSE survives · no-budget -> NULL currency
  canonical COUNTRY-only resolution (EU/GLOBAL/ZZ -> 422) · contact identity
  required (full name / organization / business email; telephone optional) ·
  versioned raw_input required · >=1 signal · create writes zero match_result/lead ·
  identity never leaks through the public requirement read and never affects
  matching.

These require the seed; they skip when DATABASE_URL is unset (see conftest).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.buyer_requirement import BuyerRequirement

#: Merged into every `_post`/`_created_id` call so the many pre-existing
#: requirement-shape tests below don't each need their own identity — only
#: the tests specifically exercising identity requiredness bypass this by
#: calling `client.post(...)` directly with a deliberately incomplete body.
DEFAULT_IDENTITY = {
    "contact_name": "Test Buyer",
    "organization": "Test Org",
    "contact_email": "buyer@example.com",
}


def rawv(answers: dict | None = None) -> dict:
    """A valid versioned raw_input wrapper (WS5 requires this on every POST)."""
    return {"wizard_version": 1, "answers": answers or {}}


def _post(client, body):
    return client.post("/api/buyer-requirements", json={**DEFAULT_IDENTITY, **body})


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


# ---- contact identity: required (Find a Humanoid contact step) ---------
# WS5's original "anonymous intent" design was reversed by explicit product
# decision: the questionnaire now ends with a contact step before submission.
# contact_name/organization/contact_email are required; contact_phone stays
# optional. extra="forbid" still blocks genuinely unknown/server-owned fields.

def test_contact_identity_persists_on_submission(client, database_url) -> None:
    req_id = _created_id(client, {
        "contact_name": "Valid Buyer", "organization": "Valid Org",
        "contact_email": "valid@example.com", "contact_phone": " +1 (555) 123-4567 ",
        "use_case": "warehouse-logistics",
        "raw_input": rawv({"task": {"state": "ANSWERED", "use_case": "warehouse-logistics"}}),
    })
    row = _fetch(req_id)
    assert row.contact_name == "Valid Buyer"
    assert row.organization == "Valid Org"
    assert row.contact_email == "valid@example.com"
    # trimmed, not otherwise reformatted/normalized
    assert row.contact_phone == "+1 (555) 123-4567"


def test_missing_full_name_is_422(client, database_url) -> None:
    before = _req_count()
    resp = client.post("/api/buyer-requirements", json={
        "organization": "Some Org", "contact_email": "someone@example.com",
        "raw_input": rawv(),
    })
    assert resp.status_code == 422, resp.text
    assert _req_count() == before


def test_blank_full_name_is_422(client, database_url) -> None:
    resp = client.post("/api/buyer-requirements", json={
        "contact_name": "   ", "organization": "Some Org",
        "contact_email": "someone@example.com", "raw_input": rawv(),
    })
    assert resp.status_code == 422, resp.text


def test_missing_organization_is_422(client, database_url) -> None:
    before = _req_count()
    resp = client.post("/api/buyer-requirements", json={
        "contact_name": "Someone", "contact_email": "someone@example.com",
        "raw_input": rawv(),
    })
    assert resp.status_code == 422, resp.text
    assert _req_count() == before


def test_blank_organization_is_422(client, database_url) -> None:
    resp = client.post("/api/buyer-requirements", json={
        "contact_name": "Someone", "organization": "   ",
        "contact_email": "someone@example.com", "raw_input": rawv(),
    })
    assert resp.status_code == 422, resp.text


def test_missing_email_is_422(client, database_url) -> None:
    before = _req_count()
    resp = client.post("/api/buyer-requirements", json={
        "contact_name": "Someone", "organization": "Some Org", "raw_input": rawv(),
    })
    assert resp.status_code == 422, resp.text
    assert _req_count() == before


def test_invalid_email_is_422(client, database_url) -> None:
    resp = _post(client, {"contact_email": "not-an-email", "raw_input": rawv()})
    assert resp.status_code == 422, resp.text


def test_telephone_omitted_succeeds(client, database_url) -> None:
    req_id = _created_id(client, {"raw_input": rawv()})
    assert _fetch(req_id).contact_phone is None


def test_telephone_accepts_international_formatting(client, database_url) -> None:
    for phone in ("+44 20 7946 0958", "+1-555-0123", "(020) 7946 0958 ext. 12"):
        req_id = _created_id(client, {"contact_phone": phone, "raw_input": rawv()})
        assert _fetch(req_id).contact_phone == phone


def test_telephone_over_max_length_is_422(client, database_url) -> None:
    resp = _post(client, {"contact_phone": "1" * 41, "raw_input": rawv()})
    assert resp.status_code == 422, resp.text


def test_server_owned_field_is_still_forbidden(client, database_url) -> None:
    """extra="forbid" remains intact — only genuinely-new identity fields were
    added to the schema; a made-up/server-owned field is still rejected."""
    resp = _post(client, {"lead_status": "WON", "raw_input": rawv()})
    assert resp.status_code == 422, resp.text


def test_historical_anonymous_requirement_rows_remain_valid(client, database_url) -> None:
    """A row written before this change (all four identity columns NULL, as the
    API used to allow) must still be a perfectly valid, selectable row — the
    required-field rule is enforced only at the API edge, never by a DB
    constraint that would invalidate history."""
    req_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        conn.execute(
            text(
                "INSERT INTO buyer_requirement (id, contact_name, contact_email, "
                "organization, contact_phone, raw_input) "
                "VALUES (:id, NULL, NULL, NULL, NULL, :raw)"
            ),
            {"id": req_id, "raw": '{"wizard_version": 1, "answers": {}}'},
        )
    try:
        row = _fetch(req_id)
        assert row.contact_name is None
        assert row.contact_email is None
        assert row.organization is None
        assert row.contact_phone is None
        # And the anonymous-era public read still works normally.
        resp = client.get(f"/api/buyer-requirements/{req_id}")
        assert resp.status_code == 200, resp.text
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET search_path TO humanoid, public"))
            conn.execute(text("DELETE FROM buyer_requirement WHERE id=:i"), {"i": req_id})


def test_public_requirement_read_never_exposes_identity(client, database_url) -> None:
    sentinel_email = "identity-leak-probe@example.com"
    sentinel_org = "Sentinel Org Ltd"
    sentinel_phone = "+1-555-0177"
    req_id = _created_id(client, {
        "contact_name": "Sentinel Person", "organization": sentinel_org,
        "contact_email": sentinel_email, "contact_phone": sentinel_phone,
        "raw_input": rawv(),
    })
    # The identity really was captured — otherwise this test proves nothing.
    row = _fetch(req_id)
    assert row.contact_email == sentinel_email

    resp = client.get(f"/api/buyer-requirements/{req_id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    for field in ("contact_name", "contact_email", "organization", "contact_phone"):
        assert f'"{field}"' not in body, f"{field} leaked in RequirementRead"
    assert sentinel_email not in body
    assert sentinel_org not in body
    assert sentinel_phone not in body
    assert "Sentinel Person" not in body


def test_identity_never_appears_in_urls_or_query_strings(client) -> None:
    """POST-only body field, never a query param or path component."""
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        for field in ("contact_name", "contact_email", "organization", "contact_phone"):
            assert field not in path, (path, field)


def test_identity_does_not_affect_matching(client, database_url) -> None:
    """Two otherwise-identical requirements differing ONLY in contact identity
    must produce identical match results — the matcher reads structured
    requirement fields only (app/services/matching), never identity columns."""
    body = {
        "use_case": "warehouse-logistics", "country": "US", "payload_min_kg": 10,
        "preferred_transaction": "RAAS",
        "raw_input": rawv({
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
            "country": {"state": "ANSWERED", "value": "US"},
            "payload": {"state": "ANSWERED", "value": 10},
        }),
    }
    rid_a = _created_id(client, {
        **body, "contact_name": "Buyer A", "organization": "Org A",
        "contact_email": "a@example.com",
    })
    rid_b = _created_id(client, {
        **body, "contact_name": "Someone Completely Different",
        "organization": "A Different Org Entirely",
        "contact_email": "z@example.com", "contact_phone": "+1-555-9999",
    })
    matches_a = client.get(f"/api/buyer-requirements/{rid_a}/matches").json()["matches"]
    matches_b = client.get(f"/api/buyer-requirements/{rid_b}/matches").json()["matches"]
    slugs_a = [(m["robot"]["slug"], m["score"], m["rank"]) for m in matches_a]
    slugs_b = [(m["robot"]["slug"], m["score"], m["rank"]) for m in matches_b]
    assert slugs_a == slugs_b


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
