"""G2-4: 4NE1 Mini commercial and interface semantics (owner decisions, DR-A5).

Covers the MANUFACTURER_ESTIMATE price type (additive migration, old ESTIMATED unchanged),
the new claim policies (manufacturer-estimate price, WAITLIST availability with year-level
wording, verbatim interface specs, NO_CATALOGUE_HOME statements), deterministic
materialization, the importer, and the audit across importer UUID churn.
Offline PostgreSQL; every test runs in a rolled-back transaction.
"""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_accepted_claims import WHO, accept_variant, answers, seeded, stub
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)
from test_claim_proposal_persistence import refused

from app.models import AcceptedClaim, CatalogueWriteAudit, DiscoveryClaimProposal
from app.services.discovery import DiscoveryError, claims, materialize
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import (
    CLAIM_POLICIES,
    NO_CATALOGUE_HOME,
    claim_policy_for,
)

pytestmark = pytest.mark.usefixtures("no_external_network")
REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO / "db" / "import_catalogue.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)
_vspec = importlib.util.spec_from_file_location(
    "validate_catalogue", REPO / "db" / "validate_catalogue.py")
vc = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(vc)

YEAR_SENTENCE = ("Both 4NE1 Mini Standard and 4NE1 Mini Pro are expected to be available "
                 "in 2026.")


# ----------------------------------------------------------------- helpers ---


def one(session, w, kind, edition=None, *, row=None):
    rows = [p for p in session.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug, DiscoveryClaimProposal.kind == kind,
        DiscoveryClaimProposal.edition == edition))
        if row is None or (p.structured or {}).get("row") == row]
    assert len(rows) == 1, (kind, edition, row, len(rows))
    return rows[0]


def price_choices(p, **over):
    return {**answers(p), "target_kind": "pricing_offer", "variant_slug": p.edition.lower(),
            "price_type": "MANUFACTURER_ESTIMATE", "transaction_type": "PURCHASE",
            "billing_period": "ONE_TIME", "region": "UNSPECIFIED", "provider": "NONE",
            "edition_confirmed": "true", "currency": p.structured["currency"],
            "price": p.structured["amount"], **over}


def avail_choices(p, **over):
    return {**answers(p), "target_kind": "availability_offer", "variant_slug": p.edition.lower(),
            "availability_status": "WAITLIST", "transaction_type": "PURCHASE",
            "available_from": "NULL", "region": "UNSPECIFIED", "provider": "NONE",
            "delivery_estimate_label": "Expected in 2026", **over}


def iface_choices(p, key, **over):
    return {**answers(p), "target_kind": "specification", "spec_key": key,
            "edition_scope": "THIS_EDITION", "accepted_value": p.value,
            "variant_slug": p.edition.lower(), **over}


def home_choices(p, **over):
    return {**answers(p), "target_kind": NO_CATALOGUE_HOME, HOME_KEY: NO_CATALOGUE_HOME,
            "accepted_value": p.value, **over}


HOME_KEY = pr.HOME_KEY


def accept(session, p, choices, why="owner decision"):
    return pr.decide(session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=why,
                     choices=choices)[0]


def make(session, p):
    return claims.create_claim(session, str(p.id), created_by=WHO)[0]


def full_slice(session, w, *, earlier_defers=False):
    """The owner-approved G2-4 slice: variants, prices, WAITLIST, interfaces, no-home facts."""
    out = {}
    for ed in ("Standard", "Pro"):
        p, _ = accept_variant(session, w, ed)
        out[f"v-{ed}"] = make(session, p)
    terms = one(session, w, "RESERVATION_TERMS")
    accept(session, terms, home_choices(terms))
    out["terms"] = make(session, terms)
    for ed in ("Standard", "Pro"):
        price = one(session, w, "PRICE_ESTIMATE", ed)
        av = one(session, w, "AVAILABILITY", ed)
        if earlier_defers:
            for p in (price, av):
                pr.decide(session, str(p.id), pr.DEFER, decided_by=WHO, rationale="deferred")
        accept(session, price, price_choices(price))
        out[f"price-{ed}"] = make(session, price)
        accept(session, av, avail_choices(av))
        out[f"avail-{ed}"] = make(session, av)
        fee = one(session, w, "RESERVATION_FEE", ed)
        accept(session, fee, home_choices(fee))
        out[f"fee-{ed}"] = make(session, fee)
        uc = one(session, w, "USE_CASES", ed)
        accept(session, uc, home_choices(uc))
        out[f"uc-{ed}"] = make(session, uc)
    for ed, row, key in (("Standard", "Common interfaces", "common_interfaces"),
                         ("Pro", "Common interfaces", "common_interfaces"),
                         ("Pro", "Additional interfaces", "additional_interfaces")):
        p = one(session, w, "INTERFACES", ed, row=row)
        accept(session, p, iface_choices(p, key))
        out[f"if-{ed}-{key}"] = make(session, p)
    return out


def raw(session):
    return session.connection().connection.driver_connection.cursor()


def definition_ids(cur):
    ids = {}
    for key, label, cat in (("dexterous_hand_option", "Dexterous hand option", "MANIPULATION"),
                            ("common_interfaces", "Common interfaces", "SOFTWARE"),
                            ("additional_interfaces", "Additional interfaces", "SOFTWARE")):
        cur.execute("SELECT id FROM spec_definition WHERE key = %s", (key,))
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO spec_definition (key, label, category, value_type, "
                        "sort_order) VALUES (%s, %s, %s, 'TEXT', 70) RETURNING id",
                        (key, label, cat))
            row = cur.fetchone()
        ids[key] = row[0]
    return ids


def do_import(session, w, path):
    cur = raw(session)
    ids = definition_ids(cur)
    robot = json.loads(path.read_text(encoding="utf-8"))
    robot["manufacturer_slug"] = w.maker.slug
    ic.import_robot(cur, robot, region_id=lambda code: None,
                    manufacturer_id=lambda slug: w.maker.id,
                    capability_id=lambda slug: None, use_case_id=lambda slug: None,
                    spec_definition=lambda key: (ids[key], "TEXT"), collisions=[])


def materialize_and_import(session, w, tmp_path):
    path = stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(session, w.slug, tmp_path))
    do_import(session, w, path)
    return path


# -------------------------------------------------- migration / enum / shape --


def test_manufacturer_estimate_is_a_distinct_additive_price_type(dsession):
    labels = [r[0] for r in dsession.execute(text(
        "SELECT unnest(enum_range(NULL::price_type))::text"))]
    assert labels == ["PUBLIC", "ESTIMATED", "MANUFACTURER_ESTIMATE", "QUOTE_ONLY", "FROM",
                      "RANGE"]            # existing values untouched, the new one after ESTIMATED


def _offer(session, w, price_type, **kw):
    cols = {"price": "1000.00", "price_min": None, "price_max": None, **kw}
    session.execute(text(
        "INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, price, "
        "price_min, price_max) VALUES (:r, 'PURCHASE', :t, 'EUR', :p, :lo, :hi)"),
        {"r": w.robot.id, "t": price_type, "p": cols["price"], "lo": cols["price_min"],
         "hi": cols["price_max"]})


def test_the_price_shape_check_treats_it_as_a_point_price_and_old_types_are_unchanged(dsession):
    w = seeded(dsession)
    for t in ("PUBLIC", "FROM", "ESTIMATED", "MANUFACTURER_ESTIMATE"):
        _offer(dsession, w, t)                                           # a point price: ok
        with pytest.raises(DBAPIError), dsession.begin_nested():
            _offer(dsession, w, t, price=None)                           # needs its number
        with pytest.raises(DBAPIError), dsession.begin_nested():
            _offer(dsession, w, t, price_min="1.00", price_max="2.00")   # never a range
    _offer(dsession, w, "RANGE", price=None, price_min="1.00", price_max="2.00")
    with pytest.raises(DBAPIError), dsession.begin_nested():
        _offer(dsession, w, "QUOTE_ONLY")                                # unchanged arm
    # ESTIMATED still means a HumanoidOnline estimate: the schema documents both separately
    schema = (REPO / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "'ESTIMATED',   -- HumanoidOnline estimate" in schema
    assert "'MANUFACTURER_ESTIMATE'" in schema


def test_application_surfaces_know_the_new_type_without_changing_the_old_ones():
    from app.schemas.robot import PricingOfferRead
    from app.services import pricing, reads

    assert "MANUFACTURER_ESTIMATE" in pricing.POINT_TYPES and "ESTIMATED" in pricing.POINT_TYPES
    rank = reads._PRICE_TYPE_RANK
    order = ["PUBLIC", "FROM", "MANUFACTURER_ESTIMATE", "ESTIMATED", "RANGE", "QUOTE_ONLY"]
    assert [rank[k] for k in order] == sorted(rank[k] for k in order)
    fields = PricingOfferRead.model_fields
    assert "price_type" in fields
    offer = PricingOfferRead(transaction_type="PURCHASE", price_type="MANUFACTURER_ESTIMATE",
                             price=19999.0, currency="EUR", billing_period="ONE_TIME")
    assert offer.model_dump()["price_type"] == "MANUFACTURER_ESTIMATE"


def test_matching_treats_a_manufacturer_estimate_as_an_unconfirmed_point_price():
    src = (REPO / "apps" / "api" / "app" / "services" / "matching" / "engine.py").read_text(
        encoding="utf-8")
    assert '"MANUFACTURER_ESTIMATE"' in src and "manufacturer's estimate" in src


def test_a_manufacturer_estimate_without_manufacturer_evidence_is_a_catalogue_violation(
        dsession):
    w = seeded(dsession)
    _offer(dsession, w, "MANUFACTURER_ESTIMATE")
    gap = vc.GAP_QUERIES["pricing_offer (MANUFACTURER_ESTIMATE needs manufacturer evidence)"]
    assert (w.robot.slug,) in dsession.execute(text(gap)).all()          # unpublished: still gated
    pid = dsession.scalar(text("SELECT id FROM pricing_offer WHERE robot_id = :r "
                               "AND price_type = 'MANUFACTURER_ESTIMATE'"), {"r": w.robot.id})
    dsession.execute(text(
        "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
        "excerpt) VALUES ('PRICING_OFFER', :i, 'https://m.example/p', 'MANUFACTURER_SITE', 'x')"),
        {"i": pid})
    assert (w.robot.slug,) not in dsession.execute(text(gap)).all()


# ------------------------------------------------------------- policy matrix --


def test_the_registry_contains_exactly_the_approved_targets_and_nothing_commercial_else():
    assert set(CLAIM_POLICIES) == {
        "robot_variant", "specification[dexterous_hand_option]",
        "specification[common_interfaces]", "specification[additional_interfaces]",
        "pricing_offer[variant]", "availability_offer[variant]",
        "no_catalogue_home[reservation_fee]", "no_catalogue_home[reservation_terms]",
        "no_catalogue_home[use_cases]"}


def test_proposals_resolve_to_the_expected_policies_and_the_rest_stay_unregistered(dsession):
    w = seeded(dsession)
    got = {}
    for p in dsession.scalars(select(DiscoveryClaimProposal).where(
            DiscoveryClaimProposal.robot_slug == w.slug)):
        pol = claim_policy_for(p.kind, p.target, p.evidence_locator, p.structured)
        got.setdefault(p.kind, set()).add(pol.key if pol else None)
    assert got["PRICE_ESTIMATE"] == {"pricing_offer[variant]"}
    assert got["AVAILABILITY"] == {"availability_offer[variant]"}
    assert got["INTERFACES"] == {"specification[common_interfaces]",
                                 "specification[additional_interfaces]"}
    assert got["RESERVATION_FEE"] == {"no_catalogue_home[reservation_fee]"}
    assert got["RESERVATION_TERMS"] == {"no_catalogue_home[reservation_terms]"}
    assert got["USE_CASES"] == {"no_catalogue_home[use_cases]"}
    for kind in ("INTEGRATION", "DESIGN_CAVEAT", "DATASHEET_REFERENCE"):
        assert got[kind] == {None}                                       # not materialized


def test_the_placeholder_row_produces_no_proposal_and_so_no_claim(dsession):
    w = seeded(dsession)
    std_additional = [p for p in dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug, DiscoveryClaimProposal.kind == "INTERFACES",
        DiscoveryClaimProposal.edition == "Standard"))
        if (p.structured or {}).get("row") == "Additional interfaces"]
    assert std_additional == []                                          # "/" is not a value


# ------------------------------------------------------------ claim creation --


def test_the_whole_slice_becomes_accepted_claims_over_the_earlier_defers(dsession):
    w = seeded(dsession)
    made = full_slice(dsession, w, earlier_defers=True)
    assert len(made) == 2 + 1 + 2 * 4 + 3
    price = made["price-Standard"]
    body = json.loads(price.accepted_value)
    assert body == {"billing_period": "ONE_TIME", "currency": "EUR", "edition_confirmed": True,
                    "price": "19999.00", "price_basis": "excluding taxes and shipping",
                    "price_type": "MANUFACTURER_ESTIMATE", "transaction_type": "PURCHASE"}
    assert json.loads(made["price-Pro"].accepted_value)["price"] == "29999.00"
    av = json.loads(made["avail-Pro"].accepted_value)
    assert av == {"availability_status": "WAITLIST", "available_from": None,
                  "delivery_estimate_label": "Expected in 2026", "seller_wording": YEAR_SENTENCE,
                  "transaction_type": "PURCHASE"}
    for k in ("fee-Standard", "fee-Pro", "uc-Standard", "uc-Pro", "terms"):
        assert made[k].target_kind == NO_CATALOGUE_HOME
    assert made["fee-Pro"].accepted_value == "100€"
    # the earlier DEFER decisions stay as history; the later ACCEPT is the effective decision
    p = one(dsession, w, "PRICE_ESTIMATE", "Standard")
    hist = pr.decision_history(dsession, p)
    assert [h.decision for h in hist] == ["DEFER", "ACCEPT"]
    assert pr.derive_states(dsession, [p])[0].effective.decision == "ACCEPT"


@pytest.mark.parametrize("over,needle", [
    ({"price_type": "ESTIMATED"}, "price_type"), ({"price_type": "PUBLIC"}, "price_type"),
    ({"price_type": "FROM"}, "price_type"), ({"transaction_type": "RENTAL"}, "transaction_type"),
    ({"billing_period": "MONTHLY"}, "billing_period"), ({"region": "DE"}, "region"),
    ({"provider": "unitree-store"}, "provider"), ({"edition_confirmed": "false"}, "edition"),
    ({"currency": "USD"}, "currency"), ({"price": "20000.00"}, "price")])
def test_a_price_mapping_that_differs_from_the_owner_decision_is_refused(dsession, over, needle):
    w = seeded(dsession)
    accept_variant(dsession, w, "Standard")
    make(dsession, one(dsession, w, "VARIANT", "Standard"))
    p = one(dsession, w, "PRICE_ESTIMATE", "Standard")
    accept(dsession, p, price_choices(p, **over))
    with pytest.raises(DiscoveryError, match=needle):
        make(dsession, p)


@pytest.mark.parametrize("over,needle", [
    ({"availability_status": "PREORDER"}, "availability_status"),
    ({"availability_status": "AVAILABLE"}, "availability_status"),
    ({"available_from": "2026-01-01"}, "available_from"),
    ({"available_from": "2026-12-31"}, "available_from"),
    ({"delivery_estimate_label": "2026-06-30"}, "delivery_estimate_label"),
    ({"transaction_type": "RENTAL"}, "transaction_type")])
def test_an_availability_mapping_that_differs_is_refused_and_no_date_is_invented(
        dsession, over, needle):
    w = seeded(dsession)
    for ed in ("Standard",):
        p, _ = accept_variant(dsession, w, ed)
        make(dsession, p)
    terms = one(dsession, w, "RESERVATION_TERMS")
    accept(dsession, terms, home_choices(terms))
    make(dsession, terms)
    av = one(dsession, w, "AVAILABILITY", "Standard")
    accept(dsession, av, avail_choices(av, **over))
    with pytest.raises(DiscoveryError, match=needle):
        make(dsession, av)


def test_waitlist_needs_its_stated_basis_and_offers_need_their_variant_first(dsession):
    w = seeded(dsession)
    price = one(dsession, w, "PRICE_ESTIMATE", "Standard")
    accept(dsession, price, price_choices(price))
    with pytest.raises(DiscoveryError, match="must be accepted first"):
        make(dsession, price)                                            # no variant claim
    p, _ = accept_variant(dsession, w, "Standard")
    make(dsession, p)
    av = one(dsession, w, "AVAILABILITY", "Standard")
    accept(dsession, av, avail_choices(av))
    with pytest.raises(DiscoveryError, match="RESERVATION_TERMS"):
        make(dsession, av)                                               # basis not accepted
    assert make(dsession, price).target_kind == "pricing_offer"


def test_no_catalogue_home_claims_need_the_explicit_home_and_verbatim_text(dsession):
    w = seeded(dsession)
    fee = one(dsession, w, "RESERVATION_FEE", "Pro")
    accept(dsession, fee, {**answers(fee), HOME_KEY: NO_CATALOGUE_HOME,
                           "accepted_value": fee.value})
    with pytest.raises(DiscoveryError, match="target_kind"):
        make(dsession, fee)                                              # kind not stated
    uc = one(dsession, w, "USE_CASES", "Standard")
    accept(dsession, uc, home_choices(uc, accepted_value="Education"))
    with pytest.raises(DiscoveryError, match="accepted_value"):
        make(dsession, uc)                                               # not verbatim


@pytest.mark.parametrize("kind,edition", [("INTEGRATION", "Pro"), ("DESIGN_CAVEAT", None),
                                          ("DATASHEET_REFERENCE", None)])
def test_other_mini_proposals_remain_unregistered_even_when_accepted(dsession, kind, edition):
    w = seeded(dsession)
    p = one(dsession, w, kind, edition)
    accept(dsession, p, {**answers(p), HOME_KEY: NO_CATALOGUE_HOME})
    with pytest.raises(DiscoveryError, match="no registered field policy"):
        make(dsession, p)


# ------------------------------------------------------------ materialization --


def test_the_materialized_delta_is_exactly_the_approved_one_and_deterministic(
        dsession, tmp_path):
    w = seeded(dsession)
    full_slice(dsession, w)
    path = stub(w, tmp_path)
    plan = materialize.plan_materialization(dsession, w.slug, tmp_path)
    assert plan.after == materialize.plan_materialization(dsession, w.slug, tmp_path).after
    materialize.apply_plan(plan)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert [v["slug"] for v in doc["variants"]] == ["pro", "standard"]
    prices = {o["variant_slug"]: o for o in doc["pricing_offers"]}
    assert set(prices) == {"standard", "pro"} and len(doc["pricing_offers"]) == 2
    for slug, amount in (("standard", 19999.0), ("pro", 29999.0)):
        o = prices[slug]
        assert (o["price_type"], o["price"], o["currency"], o["transaction_type"],
                o["billing_period"], o["edition_confirmed"]) == (
            "MANUFACTURER_ESTIMATE", amount, "EUR", "PURCHASE", "ONE_TIME", True)
        assert "excluding taxes and shipping" in o["price_basis"]
        assert "provider_slug" not in o and "region_code" not in o
        assert o["evidence"][0]["source_type"] == "MANUFACTURER_SITE"
        assert o["evidence"][0]["excerpt"] and o["evidence"][0]["source_url"]
        assert "MSRP" in o["note"] and "not a HumanoidOnline estimate" in o["note"]
    avail = {o["variant_slug"]: o for o in doc["availability_offers"]}
    assert set(avail) == {"standard", "pro"} and len(doc["availability_offers"]) == 2
    for o in avail.values():
        assert (o["availability_status"], o["transaction_type"],
                o["delivery_estimate_label"], o["seller_wording"]) == (
            "WAITLIST", "PURCHASE", "Expected in 2026", YEAR_SENTENCE)
        facts = {k: v for k, v in o.items() if k != "evidence"}
        assert "available_from" not in o and "2026-" not in json.dumps(facts)  # no invented date
        assert len(o["evidence"]) == 2                                      # year + queue wording
        assert any("secures your place in the delivery queue" in e["excerpt"]
                   for e in o["evidence"])
    specs = {(x["variant_slug"], x["key"]): x["value"] for x in doc["extended_specs"]}
    common = "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync"
    assert specs[("standard", "common_interfaces")] == common
    assert specs[("pro", "common_interfaces")] == common
    assert specs[("pro", "additional_interfaces")] == (
        "C++ SDK, digital twin access, teleoperation, ready for Neura Gym training")
    assert ("standard", "additional_interfaces") not in specs               # "/" is nothing
    assert not any(k[1] == "dexterous_hand_option" for k in specs)          # not in this slice
    # nothing was derived or invented, and nothing deferred was materialized
    text_out = path.read_text(encoding="utf-8")
    for forbidden in ("has_sdk", "ros_support", "has_api", "has_teleoperation",
                      "capability_slug", "spec_overrides", "hand_dof"):
        assert forbidden not in text_out, forbidden

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)
    assert not [k for k in keys(doc) if "fee" in k or "deposit" in k]      # fee has no home
    assert all(o["price"] > 1000 for o in doc["pricing_offers"])           # fee is not a price
    assert doc["commercial_status"] == "UNKNOWN" and doc["is_published"] is False
    assert doc.get("capabilities", []) == [] and doc.get("use_case_fits", []) == []
    assert not materialize.plan_materialization(dsession, w.slug, tmp_path).changed


def test_existing_variants_and_hand_specs_stay_intact_when_the_slice_is_added(
        dsession, tmp_path):
    w = seeded(dsession)
    for ed in ("Standard", "Pro"):
        p, _ = accept_variant(dsession, w, ed)
        make(dsession, p)
        sp = one(dsession, w, "SPECIFICATION", ed)
        accept(dsession, sp, {**answers(sp), "target_kind": "specification",
                              "spec_key": "dexterous_hand_option",
                              "edition_scope": "THIS_EDITION", "accepted_value": sp.value,
                              "variant_slug": ed.lower()})
        make(dsession, sp)
    path = stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    first = json.loads(path.read_text(encoding="utf-8"))
    full_slice(dsession, w)
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    second = json.loads(path.read_text(encoding="utf-8"))
    assert second["variants"] == first["variants"]
    hands = [x for x in second["extended_specs"] if x["key"] == "dexterous_hand_option"]
    assert hands == first["extended_specs"]
    assert len(second["extended_specs"]) == 2 + 3


def test_waitlist_materialization_refuses_when_its_basis_is_retracted(dsession, tmp_path):
    w = seeded(dsession)
    made = full_slice(dsession, w)
    stub(w, tmp_path)
    claims.retract_claim(dsession, str(made["terms"].id), retracted_by=WHO, reason="x")
    with pytest.raises(DiscoveryError, match="RESERVATION_TERMS"):
        materialize.plan_materialization(dsession, w.slug, tmp_path)


# ---------------------------------------------- importer, DB state, audit -----


def _counts(session, w):
    q = lambda sql: session.scalar(text(sql), {"s": w.slug})  # noqa: E731
    return {
        "variants": q("SELECT count(*) FROM robot_variant v JOIN robot r ON r.id = v.robot_id "
                      "WHERE r.slug = :s"),
        "prices": q("SELECT count(*) FROM pricing_offer p JOIN robot r ON r.id = p.robot_id "
                    "WHERE r.slug = :s"),
        "waitlist": q("SELECT count(*) FROM availability_offer a JOIN robot r ON r.id = "
                      "a.robot_id WHERE r.slug = :s AND a.availability_status = 'WAITLIST'"),
        "avail": q("SELECT count(*) FROM availability_offer a JOIN robot r ON r.id = a.robot_id "
                   "WHERE r.slug = :s"),
        "specs": q("SELECT count(*) FROM specification s JOIN robot r ON r.id = s.robot_id "
                   "WHERE r.slug = :s"),
        "capabilities": q("SELECT count(*) FROM robot_capability c JOIN robot r ON r.id = "
                          "c.robot_id WHERE r.slug = :s"),
        "use_cases": q("SELECT count(*) FROM use_case_fit u JOIN robot r ON r.id = u.robot_id "
                       "WHERE r.slug = :s"),
        "published": q("SELECT is_published FROM robot WHERE slug = :s"),
        "status": q("SELECT commercial_status::text FROM robot WHERE slug = :s"),
        "lowest": q("SELECT lowest_purchase_price FROM robot WHERE slug = :s"),
    }


def test_the_importer_writes_the_approved_rows_and_nothing_inferred(dsession, tmp_path):
    w = seeded(dsession)
    full_slice(dsession, w)
    materialize_and_import(dsession, w, tmp_path)
    c = _counts(dsession, w)
    assert c == {"variants": 2, "prices": 2, "waitlist": 2, "avail": 2, "specs": 3,
                 "capabilities": 0, "use_cases": 0, "published": False, "status": "UNKNOWN",
                 "lowest": None}                  # no fee row, no use_case_fit, no headline
    rows = dsession.execute(text("""
        SELECT v.slug, p.price_type::text, p.price, p.currency, p.billing_period::text,
               p.transaction_type::text, p.edition_confirmed, p.price_basis, p.provider_id,
               p.region_id, p.is_current,
               (SELECT count(*) FROM evidence_source e WHERE e.subject_type = 'PRICING_OFFER'
                  AND e.subject_id = p.id AND e.source_type = 'MANUFACTURER_SITE') AS ev
        FROM pricing_offer p JOIN robot_variant v ON v.id = p.variant_id
        JOIN robot r ON r.id = p.robot_id WHERE r.slug = :s ORDER BY v.slug"""),
        {"s": w.slug}).all()
    assert [(r.slug, r.price_type, r.price, r.currency) for r in rows] == [
        ("pro", "MANUFACTURER_ESTIMATE", Decimal("29999.00"), "EUR"),
        ("standard", "MANUFACTURER_ESTIMATE", Decimal("19999.00"), "EUR")]
    assert all(r.billing_period == "ONE_TIME" and r.transaction_type == "PURCHASE"
               and r.edition_confirmed is True and r.provider_id is None and r.region_id is None
               and r.is_current and r.ev == 1 and "excluding taxes and shipping" in r.price_basis
               for r in rows)
    av = dsession.execute(text("""
        SELECT v.slug, a.availability_status::text, a.available_from, a.delivery_estimate_label,
               a.seller_wording, a.provider_id, a.region_id, a.is_current,
               (SELECT count(*) FROM evidence_source e WHERE e.subject_type = 'AVAILABILITY_OFFER'
                  AND e.subject_id = a.id) AS ev
        FROM availability_offer a JOIN robot_variant v ON v.id = a.variant_id
        JOIN robot r ON r.id = a.robot_id WHERE r.slug = :s ORDER BY v.slug"""),
        {"s": w.slug}).all()
    assert [(a.slug, a.availability_status, a.available_from, a.delivery_estimate_label,
             a.seller_wording) for a in av] == [
        ("pro", "WAITLIST", None, "Expected in 2026", YEAR_SENTENCE),
        ("standard", "WAITLIST", None, "Expected in 2026", YEAR_SENTENCE)]
    assert all(a.provider_id is None and a.region_id is None and a.is_current and a.ev == 2
               for a in av)
    spec = dsession.execute(text("""
        SELECT v.slug, d.key, s.value_text, s.edition_scope, s.source_kind
        FROM specification s JOIN robot_variant v ON v.id = s.variant_id
        JOIN spec_definition d ON d.id = s.definition_id JOIN robot r ON r.id = s.robot_id
        WHERE r.slug = :s ORDER BY v.slug, d.key"""), {"s": w.slug}).all()
    assert [(x.slug, x.key) for x in spec] == [
        ("pro", "additional_interfaces"), ("pro", "common_interfaces"),
        ("standard", "common_interfaces")]
    assert all(x.edition_scope == "THIS_EDITION" and x.source_kind == "MANUFACTURER"
               for x in spec)
    # no boolean / numeric / capability inference from the interface strings
    inferred = dsession.execute(text(
        "SELECT has_sdk, ros_support, has_api, has_teleoperation, autonomy::text, hand_dof "
        "FROM robot WHERE slug = :s"), {"s": w.slug}).one()
    assert tuple(inferred) == (None, None, None, None, None, None)
    # the fee and use cases have no catalogue home: no pricing row carries 100 EUR
    assert dsession.scalar(text(
        "SELECT count(*) FROM pricing_offer p JOIN robot r ON r.id = p.robot_id "
        "WHERE r.slug = :s AND p.price < 1000"), {"s": w.slug}) == 0


def test_a_second_import_is_idempotent_and_the_audit_survives_uuid_churn(dsession, tmp_path):
    w = seeded(dsession)
    made = full_slice(dsession, w)
    path = materialize_and_import(dsession, w, tmp_path)
    first = materialize.verify_applied(dsession, w.slug, change_ref="chg-g24", applied_by=WHO)
    assert len(first) == 2 + 2 + 2 + 3          # variants, prices, availability, interface specs
    assert {a.target_table for a in first} == {
        "robot_variant", "pricing_offer", "availability_offer", "specification"}
    original = {a.id: (a.target_row_id, a.after_hash, a.claim_id) for a in first}
    snapshot = _counts(dsession, w)
    live_before = {r[0] for r in dsession.execute(text(
        "SELECT p.id FROM pricing_offer p JOIN robot r ON r.id = p.robot_id WHERE r.slug = :s "
        "UNION SELECT a.id FROM availability_offer a JOIN robot r ON r.id = a.robot_id "
        "WHERE r.slug = :s"), {"s": w.slug})}
    do_import(dsession, w, path)                                    # importer churns the UUIDs
    live_after = {r[0] for r in dsession.execute(text(
        "SELECT p.id FROM pricing_offer p JOIN robot r ON r.id = p.robot_id WHERE r.slug = :s "
        "UNION SELECT a.id FROM availability_offer a JOIN robot r ON r.id = a.robot_id "
        "WHERE r.slug = :s"), {"s": w.slug})}
    assert live_before and not (live_before & live_after)
    assert _counts(dsession, w) == snapshot                         # semantically idempotent
    assert materialize.verify_applied(dsession, w.slug, change_ref="chg-g24",
                                      applied_by=WHO) == []         # Part-A semantics hold
    assert dsession.scalar(select(func.count()).select_from(CatalogueWriteAudit)) == 9
    for a in dsession.scalars(select(CatalogueWriteAudit)):
        assert (a.target_row_id, a.after_hash, a.claim_id) == original[a.id]
    targets = {materialize.logical_target(c) for c in made.values()
               if c.target_kind != NO_CATALOGUE_HOME}
    assert f"pricing_offer:{w.slug}:standard:purchase.manufacturer_estimate" in targets
    assert f"availability_offer:{w.slug}:pro:purchase.waitlist" in targets
    assert f"specification:{w.slug}:pro:additional_interfaces" in targets
    with refused(dsession, op="UPDATE"):
        dsession.execute(text("UPDATE catalogue_write_audit SET claim_id = claim_id"))


def test_drift_in_a_materialized_offer_is_detected_by_verification(dsession, tmp_path):
    w = seeded(dsession)
    full_slice(dsession, w)
    materialize_and_import(dsession, w, tmp_path)
    dsession.execute(text(
        "UPDATE pricing_offer SET price = 1.00 WHERE robot_id = "
        "(SELECT id FROM robot WHERE slug = :s)"), {"s": w.slug})
    with pytest.raises(DiscoveryError, match="pricing offer"):
        materialize.verify_applied(dsession, w.slug, change_ref="x", applied_by=WHO)
    dsession.rollback()


def test_publication_and_other_state_are_untouched_by_the_whole_chain(dsession, tmp_path):
    w = seeded(dsession)
    before = dsession.execute(text(
        "SELECT to_jsonb(r) - 'updated_at' - 'lowest_purchase_price' FROM robot r "
        "WHERE slug = :s"), {"s": w.slug}).scalar()
    full_slice(dsession, w)
    materialize_and_import(dsession, w, tmp_path)
    after = dsession.execute(text(
        "SELECT to_jsonb(r) - 'updated_at' - 'lowest_purchase_price' FROM robot r "
        "WHERE slug = :s"), {"s": w.slug}).scalar()
    assert after == before and after["is_published"] is False
    assert after["commercial_status"] == "UNKNOWN"
    # NO_CATALOGUE_HOME claims were never materialized and are still active governed knowledge
    homes = dsession.scalar(select(func.count()).select_from(AcceptedClaim).where(
        AcceptedClaim.target_kind == NO_CATALOGUE_HOME))
    assert homes == 5


def test_the_catalogue_data_dictionary_and_definitions_know_the_new_values():
    defs = json.loads((REPO / "db" / "catalogue" / "spec_definitions.json").read_text(
        encoding="utf-8"))["spec_definitions"]
    by_key = {d["key"]: d for d in defs}
    for key, label in (("common_interfaces", "Common interfaces"),
                       ("additional_interfaces", "Additional interfaces")):
        assert (by_key[key]["label"], by_key[key]["category"], by_key[key]["value_type"]) == (
            label, "SOFTWARE", "TEXT")
    dd = (REPO / "docs" / "03_DATA_DICTIONARY.md").read_text(encoding="utf-8")
    assert "MANUFACTURER_ESTIMATE" in dd and "HumanoidOnline estimate" in dd
