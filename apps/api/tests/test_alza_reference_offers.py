"""Alza.cz reference offers (owner decision 2026-10-05): provider + governed retail claims.

Alza is an approved Czech commercial provider and a REFERENCE source for evidence-backed offers.
It is NOT approved for automated monitoring. These tests pin that split and the semantics:

- manual capture records retained bytes as a governed observation without enabling the source;
  nothing schedules, polls or fetches Alza (no network at all: the suite's guard is active);
- the extractor proposes only for reviewed items (accessories, quadrupeds, unresolved SKUs and
  unreviewed products produce nothing), keeps NEW and USED apart and fails closed;
- retail price/availability are their own governed claims (never MANUFACTURER_ESTIMATE / WAITLIST),
  every catalogue value is stated by the reviewer, and a NEW and a USED offer of the same robot
  coexist through proposal -> decision -> claim -> materialization -> import -> verification;
- a used unit's stock never makes the new unit obtainable.
Offline PostgreSQL; every DB test runs in a rolled-back transaction.
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from test_accepted_claims import WHO
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)

from app.models import DiscoveryClaimProposal
from app.models.discovery import DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, claims, materialize, proposals
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import (
    CLAIM_POLICIES,
    claim_policy_for,
)
from app.services.discovery.manual_capture import record_manual_capture
from app.services.discovery.source_registry import enable_source, register_source
from app.services.discovery.sources import alza_cz_reference_proposals as alza

pytestmark = pytest.mark.usefixtures("no_external_network")
REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO / "db" / "import_catalogue.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

WALKER = "ubtech-walker-tienkung-embodied-intelligence"
WALKER_NAME = "Walker Tienkung · Embodied Intelligence"
CAPTURED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
PROVENANCE = "AGENT_ASSISTED_RESEARCH: test capture (owner WorkOrder 2026-10-05)"


# ------------------------------------------------------------------- fixtures ---


def tok(text_: str) -> str:
    return f"<span>{text_}</span>"


def item(pid, code, name, price, avail, *, almostnew="false", new_ref=None, discount=False,
         href=None, button="Do košíku"):
    href = href or f"/{name.lower().replace(' ', '-')}-d{pid}.htm"
    parts = ["Doručení na", "prodejnu zdarma", "Přidat do oblíbených", alza._ANCHOR, name,
             "Humanoidní robot - popis, 29 kloubů", *(["-11 % z nového"] if discount else []),
             price, *([f"Nový {new_ref}"] if new_ref else []), "Od 5 290,- měsíčně", button, "-",
             "+", "Přidáno do košíku", avail, "Objednací kód:", code]
    return (f'<div class="box browsingitem js-box canBuy" data-code="{code}" data-id="{pid}" '
            f'data-almostnew="{almostnew}" data-analytics=\'{{"a":">"}}\'>'
            f'<a class="name browsinglink" href="{href}">{name}</a>'
            + "".join(tok(p) for p in parts) + "</div>")


def listing(*items) -> bytes:
    return ("<html><body>" + "".join(items) + "</body></html>").encode("utf-8")


WALKER_NEW = item("13233810", "ubtech2501", "Ubtech Walker Tienkung (embodied intelligence)",
                  "2 491 790,-", "Momentálně nedostupné", button="Hlídat",
                  href="/ubtech-walker-tienkung-embodied-intelligence-d13233810.htm")
WALKER_USED = item("13509114", "ubtech2501", "Ubtech Walker Tienkung (embodied intelligence)",
                   "2 199 990,-", "Použité - skladem 1 ks", almostnew="true",
                   new_ref="2 491 790,-", discount=True,
                   href="/ubtech-walker-tienkung-embodied-intelligence-bazar-d13509114.htm")
R1_U2 = item("13408319", "BUN_R1EDU_U2", "Unitree R1 EDU U2", "425 990,-", "Skladem 1 ks")
G1_U2 = item("13150281", "uni_G1_U2", "Unitree G1 EDU U2", "917 990,-", "Skladem 5 ks")
BATTERY = item("13079625", "uni_bat", "Unitree G1 Baterie", "16 990,-", "Skladem > 5 ks")
GO2_BATTERY = item("13150279", "uni_go2", "Unitree Go2 Baterie", "16 990,-", "Skladem 2 ks")
G1_U4 = item("13150282", "uni_G1_U4", "Unitree G1 EDU U4", "1 242 990,-", "Skladem 3 ks")
G1_U5 = item("13079624", "unitreeG1_EDU", "Unitree G1 EDU U5", "1 242 990,-", "Skladem 2 ks")
G1_U6 = item("13150284", "uni_G1_U6", "Unitree G1 EDU U6", "1 349 990,-", "Skladem 2 ks")
H2_EDU = item("13215768", "uni_H2_EDU", "Unitree H2 EDU", "1 309 990,-", "Skladem 2 ks")
H2_EDU_U2 = item("13501544", "BUN_H2EDU_U2", "Unitree H2 EDU U2", "1 507 990,-", "Skladem 1 ks")
R1_BASIC = item("13408317", "BUN_R1_B", "Unitree R1 Basic", "229 990,-", "Skladem 3 ks")
LISTING = listing(WALKER_NEW, WALKER_USED, R1_U2, G1_U2, BATTERY, GO2_BATTERY, G1_U4, G1_U5,
                  G1_U6, H2_EDU, H2_EDU_U2, R1_BASIC)


def ensure_robot(session, slug, name):
    robot = session.scalar(select(Robot).where(Robot.slug == slug))
    if robot is None:
        maker = Manufacturer(slug=f"m-{slug}"[:40], name=f"Maker {slug}")
        session.add(maker)
        session.flush()
        robot = Robot(slug=slug, manufacturer_id=maker.id, name=name, is_published=False)
        session.add(robot)
        session.flush()
    assert robot.name == name
    return robot


def alza_source(session):
    source = session.scalar(select(DiscoverySource).where(DiscoverySource.key == alza.SOURCE_KEY))
    if source is None:
        source = register_source(session, key=alza.SOURCE_KEY, name="Alza.cz",
                                 source_class="DISTRIBUTOR",
                                 homepage_url="https://www.alza.cz/", registered_by=WHO)
    return source


def capture(session, body=LISTING, url=alza.UBTECH_LISTING_URL, at=CAPTURED):
    alza_source(session)
    page, _ = record_manual_capture(
        session, source_key=alza.SOURCE_KEY, url=url, body=body, content_type="text/html",
        retrieved_at=at, captured_by=WHO, provenance=PROVENANCE)
    return page


def ingest(session, slug=WALKER, name=WALKER_NAME, body=LISTING, page=None):
    ensure_robot(session, slug, name)
    page = page or capture(session, body)
    return page, proposals.ingest_alza_reference_proposals(
        session, source_key=alza.SOURCE_KEY, robot_slug=slug, fetched_page_id=page.id,
        body=body, ingested_by=WHO)


def props(session, slug=WALKER):
    return {(p.kind, (p.structured or {}).get("condition")): p for p in session.scalars(
        select(DiscoveryClaimProposal).where(DiscoveryClaimProposal.robot_slug == slug))}


def answers(p):
    return {pr.question_key(i): "reviewed" for i in range(1, len(p.review_questions) + 1)}


def price_choices(p, **over):
    s = p.structured
    return {**answers(p), "target_kind": "pricing_offer", "provider": s["provider"],
            "region": s["market"], "condition": s["condition"], "transaction_type": "PURCHASE",
            "edition_confirmed": "true", "price_type": "PUBLIC", "billing_period": "ONE_TIME",
            "currency": s["currency"], "price": s["amount"], **over}


def avail_choices(p, status, **over):
    s = p.structured
    return {**answers(p), "target_kind": "availability_offer", "provider": s["provider"],
            "region": s["market"], "condition": s["condition"], "transaction_type": "PURCHASE",
            "edition_confirmed": "true", "availability_status": status, **over}


def accept(session, p, choices):
    return pr.decide(session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="reference offer",
                     choices=choices)[0]


def claim_for(session, p):
    return claims.create_claim(session, str(p.id), created_by=WHO)[0]


# ----------------------------------------------------- source governance ---------


def test_alza_is_a_manual_provider_never_a_scheduled_source(dsession):
    source = alza_source(dsession)
    assert source.is_enabled is False and source.tos_status != "ALLOWED"
    assert source.observation_interval_hours is None          # no cadence: never scheduled
    with pytest.raises(DiscoveryError, match="cannot enable"):
        enable_source(dsession, alza.SOURCE_KEY, by=WHO)
    from app.services.discovery.g2_ingest import G2_INGESTS
    from app.services.discovery.sources import ADAPTERS
    assert alza.SOURCE_KEY not in G2_INGESTS                   # not in the observe cycle
    assert alza.SOURCE_KEY not in ADAPTERS and "alza" not in " ".join(map(str, ADAPTERS)).lower()
    workflows = " ".join(p.read_text(encoding="utf-8").lower()
                         for p in (REPO / ".github" / "workflows").glob("*.yml"))
    assert "alza" not in workflows                             # no schedule, watcher or dispatch
    assert alza.EXTRACTOR_KEY not in {s.key for s in []}       # structural: extractor is manual


def test_the_extractor_result_declares_no_write_and_no_fetch():
    result = alza.propose_alza_reference_claims(LISTING, alza.UBTECH_LISTING_URL,
                                                robot_slug=WALKER)
    assert result.writes_catalogue is False and result.fetches is False


def test_manual_capture_records_an_observation_without_enabling_the_source(dsession):
    source = alza_source(dsession)
    page, created = record_manual_capture(
        dsession, source_key=alza.SOURCE_KEY, url=alza.UBTECH_LISTING_URL, body=LISTING,
        content_type="text/html", retrieved_at=CAPTURED, captured_by=WHO,
        provenance=PROVENANCE)
    assert created and page.outcome == "FETCHED" and page.retrieved_at == CAPTURED
    again, created_again = record_manual_capture(
        dsession, source_key=alza.SOURCE_KEY, url=alza.UBTECH_LISTING_URL, body=LISTING,
        content_type="text/html", retrieved_at=CAPTURED, captured_by=WHO,
        provenance=PROVENANCE)
    assert not created_again and again.id == page.id           # idempotent
    dsession.refresh(source)
    assert source.is_enabled is False and source.last_crawled_at is None


@pytest.mark.parametrize("kw,match", [
    (dict(url="https://evil.example/ubtech/v6390.htm"), "own host"),
    (dict(url="https://www.alza.sk/ubtech/v6390.htm"), "own host"),
    (dict(provenance=" "), "provenance"),
    (dict(captured_by=" "), "who captured"),
    (dict(retrieved_at=datetime(2999, 1, 1, tzinfo=UTC)), "future"),
    (dict(retrieved_at=datetime(2026, 10, 5, 12, 0)), "timezone-aware"),
    (dict(body=b""), "retrieved bytes"),
])
def test_manual_capture_fails_closed(dsession, kw, match):
    alza_source(dsession)
    args = dict(source_key=alza.SOURCE_KEY, url=alza.UBTECH_LISTING_URL, body=LISTING,
                content_type="text/html", retrieved_at=CAPTURED, captured_by=WHO,
                provenance=PROVENANCE)
    args.update(kw)
    with pytest.raises(DiscoveryError, match=match):
        record_manual_capture(dsession, **args)


# ------------------------------------------------------------------ parsing -------


def parsed(*items):
    return {i.product_id: i for i in alza.parse_listing(listing(*items))}


def test_stock_quantities_availability_and_prices_are_read_as_displayed():
    got = parsed(G1_U2, BATTERY, WALKER_NEW,
                 item("900", "x", "Unitree X", "1 000,-", "Předobjednávka"))
    assert (got["13150281"].price, got["13150281"].signal, got["13150281"].stock_quantity,
            got["13150281"].condition) == ("917 990,-", alza.IN_STOCK, "5", "NEW")
    assert got["13079625"].stock_quantity == ">5"              # "> 5 ks" kept as displayed
    assert got["13233810"].signal == alza.UNAVAILABLE and got["13233810"].stock_quantity is None
    assert got["900"].signal == alza.PREORDER
    assert alza.price_amount("2 491 790,-") == "2491790"
    assert alza.price_amount("917 990,-") == "917990"


def test_new_and_used_listings_stay_distinct_and_the_used_one_carries_no_second_price():
    got = parsed(WALKER_NEW, WALKER_USED)
    new, used = got["13233810"], got["13509114"]
    assert (new.condition, new.price, new.signal) == ("NEW", "2 491 790,-", alza.UNAVAILABLE)
    assert (used.condition, used.price, used.signal, used.stock_quantity) == (
        "USED", "2 199 990,-", alza.IN_STOCK, "1")
    assert used.new_reference_price == "2 491 790,-"           # reference text, never an offer


@pytest.mark.parametrize("bad,why", [
    (item("1", "c", "Unitree R1 EDU U2", "425 990,-", "Použité - skladem 1 ks"),
     "markers disagree"),                                      # wording says used, flag says new
    (item("1", "c", "Unitree R1 EDU U2", "425 990,-", "Skladem 1 ks", almostnew="true"),
     "markers disagree"),
    (item("1", "c", "Unitree R1 EDU U2", "425 990,-", "Brzy skladem"), "availability"),
    (item("1", "c", "Unitree R1 EDU U2", "cena na dotaz", "Skladem 1 ks"), "price"),
    (item("1", "c", "Unitree R1 EDU U2", "425 990,-", "Skladem 1 ks", almostnew=""),
     "condition markers missing"),
])
def test_an_unrecognised_or_contradictory_listing_item_fails_closed(bad, why):
    [li] = alza.parse_listing(listing(bad))
    assert li.problems and any(why in p for p in li.problems)


def test_only_reviewed_items_are_proposed_and_everything_else_is_reported():
    page = alza.propose_alza_reference_claims(LISTING, alza.UBTECH_LISTING_URL,
                                              robot_slug="unitree-r1-edu-u2")
    assert {p.kind for p in page.proposals} == {alza.PRICE_KIND, alza.AVAILABILITY_KIND}
    assert {p.robot_name for p in page.proposals} == {"R1 EDU U2"}
    reasons = dict(page.rejected)
    assert any("OUT_OF_SCOPE" in r and "Baterie" in k for k, r in reasons.items())  # accessory
    assert any(k.startswith("13150279") and "OUT_OF_SCOPE" in r
               for k, r in reasons.items())                    # quadruped accessory
    assert any(k.startswith("13150282") and "IDENTITY_UNRESOLVED" in r and "no new robot row" in r
               for k, r in reasons.items())                    # a retailer SKU is not a robot
    # nothing was proposed for any other robot's item
    other = alza.propose_alza_reference_claims(LISTING, alza.UBTECH_LISTING_URL,
                                               robot_slug="not-reviewed")
    assert other.status == alza.NO_PROPOSALS and not other.proposals


def test_a_listing_condition_that_differs_from_the_reviewed_one_is_refused():
    swapped = listing(item("13233810", "ubtech2501", "Ubtech Walker Tienkung (x)", "2 491 790,-",
                           "Použité - skladem 1 ks", almostnew="true"))
    page = alza.propose_alza_reference_claims(swapped, alza.UBTECH_LISTING_URL, robot_slug=WALKER)
    assert not page.proposals and any("differs from the reviewed" in r for _, r in page.rejected)


def test_walker_tienkung_is_never_mapped_to_walker_s1_or_s2():
    slugs = {i.robot_slug for i in alza.REFERENCE_ITEMS.values()}
    assert not slugs & {"ubtech-walker-s1", "ubtech-walker-s2"}
    assert {i.robot_slug for i in alza.REFERENCE_ITEMS.values()
            if i.product_id in ("13233810", "13509114")} == {WALKER}


# ------------------------------------------------ ingest, review, identity --------


def test_ingest_creates_unverified_reviewable_proposals_and_is_idempotent(dsession):
    page, report = ingest(dsession)
    assert report.status == "PROPOSED" and report.proposals_created == 4   # NEW+USED x price+avail
    rows = props(dsession)
    assert set(rows) == {("RETAIL_PRICE", "NEW"), ("RETAIL_PRICE", "USED"),
                         ("RETAIL_AVAILABILITY", "NEW"), ("RETAIL_AVAILABILITY", "USED")}
    for p in rows.values():
        assert p.claim_status == "NOT_VERIFIED" and p.review_questions
        assert p.source_url == alza.UBTECH_LISTING_URL and p.origin_fetched_page_id == page.id
        assert p.structured["capture_class"] == "AGENT_ASSISTED_RESEARCH"
        assert p.structured["vat_stated"] is False and p.structured["currency"] == "CZK"
        assert p.structured["market"] == "CZ"
    # re-ingesting the same capture creates nothing
    again = proposals.ingest_alza_reference_proposals(
        dsession, source_key=alza.SOURCE_KEY, robot_slug=WALKER, fetched_page_id=page.id,
        body=LISTING, ingested_by=WHO)
    assert again.proposals_created == 0 and again.observations_created == 0
    assert again.unchanged == 4


def test_a_changed_price_supersedes_and_an_unreviewed_robot_gets_nothing(dsession):
    page, _ = ingest(dsession)
    old = props(dsession)[("RETAIL_PRICE", "NEW")]
    cheaper = listing(WALKER_NEW.replace("2 491 790,-", "2 391 790,-"), WALKER_USED)
    page2 = capture(dsession, cheaper, at=CAPTURED + timedelta(minutes=1))
    report = proposals.ingest_alza_reference_proposals(
        dsession, source_key=alza.SOURCE_KEY, robot_slug=WALKER, fetched_page_id=page2.id,
        body=cheaper, ingested_by=WHO)
    assert report.proposals_created == 1                       # only the changed price
    [state] = pr.derive_states(dsession, [old])
    assert state.superseded
    with pytest.raises(DiscoveryError, match="no reviewed Alza reference mapping"):
        proposals.ingest_alza_reference_proposals(
            dsession, source_key=alza.SOURCE_KEY, robot_slug="unitree-g1-edu-u4",
            fetched_page_id=page2.id, body=cheaper, ingested_by=WHO)
    with pytest.raises(DiscoveryError, match="source only"):
        proposals.ingest_alza_reference_proposals(
            dsession, source_key="some-other", robot_slug=WALKER, fetched_page_id=page2.id,
            body=cheaper, ingested_by=WHO)


def test_the_identity_gate_refuses_a_robot_with_the_wrong_name(dsession):
    capture(dsession)
    ensure_robot(dsession, "unitree-r1-edu-u2", "R1 EDU U2")
    robot = dsession.scalar(select(Robot).where(Robot.slug == "unitree-r1-edu-u2"))
    robot.name = "Some Other Robot"
    dsession.flush()
    page = capture(dsession)
    with pytest.raises(DiscoveryError, match="is not the catalogue's"):
        proposals.ingest_alza_reference_proposals(
            dsession, source_key=alza.SOURCE_KEY, robot_slug="unitree-r1-edu-u2",
            fetched_page_id=page.id, body=LISTING, ingested_by=WHO)


# ----------------------------------------------------- registry & claim rules -----


def test_retail_claims_are_their_own_semantics_not_manufacturer_estimate_or_waitlist(dsession):
    price = CLAIM_POLICIES["pricing_offer[retail]"]
    avail = CLAIM_POLICIES["availability_offer[retail]"]
    assert (price.target_key, price.requires_variant) == ("purchase.retail", False)
    assert (avail.target_key, avail.requires_variant) == ("purchase.retail", False)
    assert price.target_key != CLAIM_POLICIES["pricing_offer[variant]"].target_key
    assert avail.target_key != CLAIM_POLICIES["availability_offer[variant]"].target_key
    ingest(dsession)
    rows = props(dsession)
    p = rows[("RETAIL_PRICE", "NEW")]
    assert claim_policy_for(p.kind, p.target, p.evidence_locator, p.structured) is price
    # the manufacturer-estimate and waitlist locators do NOT resolve for retail kinds
    assert claim_policy_for("RETAIL_PRICE", "pricing_offer[variant]",
                            "feature-grid/row[Estimated price]/x", {}) is None


@pytest.mark.parametrize("over", [
    {"price_type": "MANUFACTURER_ESTIMATE"}, {"price_type": "ESTIMATED"},
    {"currency": "EUR"}, {"price": "1"}, {"region": "SK"}, {"region": "EU"}, {"region": "HU"},
    {"provider": "unitree-store"}, {"condition": "USED"}, {"transaction_type": "RENTAL"},
    {"billing_period": "MONTHLY"}, {"edition_confirmed": "false"},
])
def test_a_price_decision_that_departs_from_the_source_is_refused(dsession, over):
    ingest(dsession)
    p = props(dsession)[("RETAIL_PRICE", "NEW")]
    accept(dsession, p, price_choices(p, **over))
    with pytest.raises(DiscoveryError):
        claim_for(dsession, p)


@pytest.mark.parametrize("cond,status,ok", [
    ("NEW", "NOT_AVAILABLE", True), ("NEW", "AVAILABLE", False), ("NEW", "WAITLIST", False),
    ("NEW", "PREORDER", False), ("NEW", "ON_REQUEST", False), ("USED", "AVAILABLE", True),
    ("USED", "NOT_AVAILABLE", False), ("USED", "LIMITED", False),
])
def test_availability_maps_only_to_the_status_the_wording_supports(dsession, cond, status, ok):
    ingest(dsession)
    p = props(dsession)[("RETAIL_AVAILABILITY", cond)]
    accept(dsession, p, avail_choices(p, status))
    if ok:
        c = claim_for(dsession, p)
        assert json.loads(c.accepted_value)["availability_status"] == status
    else:
        with pytest.raises(DiscoveryError):
            claim_for(dsession, p)


def test_stock_wording_is_preserved_but_quantity_is_not_a_canonical_field(dsession):
    ingest(dsession)
    p = props(dsession)[("RETAIL_AVAILABILITY", "USED")]
    assert p.structured["stock_quantity"] == "1"               # the extracted observation
    with pytest.raises(DiscoveryError, match="unknown resolved-choice key"):
        accept(dsession, p, avail_choices(p, "AVAILABLE", stock_quantity="1"))
    accept(dsession, p, avail_choices(p, "AVAILABLE"))
    o = json.loads(claim_for(dsession, p).accepted_value)
    assert "stock_quantity" not in o and o["seller_wording"] == "Použité - skladem 1 ks"
    assert o["condition"] == "USED" and o["region"] == "CZ" and o["provider"] == "alza-cz"


# ------------------------------------------- NEW vs USED, end to end --------------


def stub_doc(tmp_path, slug, name):
    doc = {"slug": slug, "name": name, "manufacturer_slug": "x", "commercial_status": "UNKNOWN",
           "is_published": False, "specs": {}, "variants": [], "pricing_offers": [],
           "availability_offers": []}
    path = tmp_path / f"{slug}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def raw(session):
    return session.connection().connection.driver_connection.cursor()


def seed_refs(session):
    session.execute(text(
        "INSERT INTO provider (slug, type, name) VALUES ('alza-cz', 'DISTRIBUTOR', 'Alza.cz') "
        "ON CONFLICT (slug) DO NOTHING"))
    session.execute(text(
        "INSERT INTO region (type, code, name, iso_country) "
        "VALUES ('COUNTRY', 'CZ', 'Czechia', 'CZ') ON CONFLICT (code) DO NOTHING"))
    return session.scalar(text("SELECT id FROM region WHERE code = 'CZ'"))


def accept_all(session):
    made = {}
    rows = props(session)
    for (kind, cond), status in (
            (("RETAIL_PRICE", "NEW"), None), (("RETAIL_PRICE", "USED"), None),
            (("RETAIL_AVAILABILITY", "NEW"), "NOT_AVAILABLE"),
            (("RETAIL_AVAILABILITY", "USED"), "AVAILABLE")):
        p = rows[(kind, cond)]
        accept(session, p, price_choices(p) if status is None else avail_choices(p, status))
        made[(kind, cond)] = claim_for(session, p)
    return made


def do_import(session, path, robot_row):
    cur = raw(session)
    robot = json.loads(path.read_text(encoding="utf-8"))
    robot["manufacturer_slug"] = "x"
    cz = seed_refs(session)
    ic.import_robot(cur, robot, region_id=lambda code: cz if code == "CZ" else None,
                    manufacturer_id=lambda slug: robot_row.manufacturer_id,
                    capability_id=lambda slug: None, use_case_id=lambda slug: None,
                    spec_definition=lambda key: None, collisions=[])


def test_new_and_used_walker_offers_travel_the_whole_chain_as_separate_offers(dsession, tmp_path):
    ingest(dsession)
    made = accept_all(dsession)
    assert len({c.id for c in made.values()}) == 4

    path = stub_doc(tmp_path, WALKER, WALKER_NAME)
    plan = materialize.plan_materialization(dsession, WALKER, tmp_path)
    assert plan.after == materialize.plan_materialization(dsession, WALKER, tmp_path).after
    materialize.apply_plan(plan)
    assert not materialize.plan_materialization(dsession, WALKER, tmp_path).changed
    doc = json.loads(path.read_text(encoding="utf-8"))

    prices = {o["condition"]: o for o in doc["pricing_offers"]}
    assert set(prices) == {"NEW", "USED"}
    assert (prices["NEW"]["price"], prices["USED"]["price"]) == (2491790.0, 2199990.0)
    for o in prices.values():
        assert (o["provider_slug"], o["region_code"], o["currency"], o["price_type"]) == (
            "alza-cz", "CZ", "CZK", "PUBLIC")
        assert "price_basis" not in o                          # VAT basis is not stated
        assert "not an MSRP" in o["note"] and "not a live price" in o["note"]
    avail = {o["condition"]: o for o in doc["availability_offers"]}
    assert avail["NEW"]["availability_status"] == "NOT_AVAILABLE"
    assert avail["USED"]["availability_status"] == "AVAILABLE"
    assert "Použité - skladem 1 ks" in avail["USED"]["note"]       # raw wording, not a field
    assert "durable inventory" in avail["USED"]["note"]
    assert all("stock_quantity" not in o for o in avail.values())
    for o in (*prices.values(), *avail.values()):
        [ev] = o["evidence"]
        assert ev["source_url"] == alza.UBTECH_LISTING_URL and ev["verified_at"] is None
        assert ev["confidence"] == "MEDIUM" and ev["source_type"] == "OTHER"
        assert "AGENT_ASSISTED_RESEARCH" in ev["note"] and PROVENANCE in ev["note"]
        assert ev["observed_at"] == "2026-10-05"

    # the importer carries `condition`; both rows coexist; verification passes per claim
    robot = dsession.scalar(select(Robot).where(Robot.slug == WALKER))
    do_import(dsession, path, robot)
    rows = dsession.execute(text(
        "SELECT a.condition::text, a.availability_status::text FROM availability_offer a "
        "JOIN robot r ON r.id = a.robot_id WHERE r.slug = :s ORDER BY 1"), {"s": WALKER}).all()
    assert [tuple(r) for r in rows] == [("NEW", "NOT_AVAILABLE"), ("USED", "AVAILABLE")]
    audits = materialize.verify_applied(dsession, WALKER, change_ref="chg-alza", applied_by=WHO)
    assert len(audits) == 4 and {a.target_table for a in audits} == {
        "pricing_offer", "availability_offer"}
    assert len({materialize.logical_target(c) for c in made.values()}) == 4
    do_import(dsession, path, robot)                           # importer churn: idempotent
    assert materialize.verify_applied(dsession, WALKER, change_ref="chg-alza",
                                      applied_by=WHO) == []

    # a used unit's stock never makes the new unit obtainable (snapshot view)
    assert dsession.scalar(text(
        "SELECT is_obtainable FROM robot_commercial_snapshot WHERE slug = :s"),
        {"s": WALKER}) is False
    # the lowest-price cache is the NEW price only (importer rule, migration 0024)
    cache = dsession.execute(text("SELECT lowest_purchase_price FROM robot WHERE slug = :s"),
                             {"s": WALKER}).scalar()
    assert cache is None or float(cache) == 2491790.0


def test_a_retail_claim_never_overwrites_a_hand_authored_offer(dsession, tmp_path):
    ingest(dsession)
    accept_all(dsession)
    path = stub_doc(tmp_path, WALKER, WALKER_NAME)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["pricing_offers"] = [{"provider_slug": "alza-cz", "region_code": "CZ",
                              "transaction_type": "PURCHASE", "price_type": "PUBLIC",
                              "currency": "CZK", "price": 1.0, "condition": "NEW",
                              "evidence": [{"source_url": "https://www.alza.cz/x",
                                            "note": "hand written"}]}]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DiscoveryError, match="hand-authored"):
        materialize.plan_materialization(dsession, WALKER, tmp_path)


def test_conflicting_new_prices_refuse_but_new_and_used_never_conflict(dsession, tmp_path):
    ingest(dsession)
    accept_all(dsession)                                       # NEW and USED price: no conflict
    stub_doc(tmp_path, WALKER, WALKER_NAME)
    assert materialize.plan_materialization(dsession, WALKER, tmp_path).changed


# ------------------------------------------------------------- catalogue data -----


def catalogue_json(name):
    return json.loads((REPO / "db" / "catalogue" / name).read_text(encoding="utf-8"))


def test_alza_is_a_czech_distributor_provider_not_a_manufacturer():
    provider = {p["slug"]: p for p in catalogue_json("providers.json")["providers"]}["alza-cz"]
    assert provider["type"] == "DISTRIBUTOR" and provider["manufacturer_slug"] is None
    assert provider["country_region_code"] == "CZ"
    assert provider["website_url"] == "https://www.alza.cz"
    assert "NOT approved for automated monitoring" in provider["description"]
    assert "no Slovak, Hungarian or EU-wide offer" in provider["description"]
    manufacturers = {m["slug"] for m in catalogue_json("manufacturers.json")["manufacturers"]}
    assert "alza-cz" not in manufacturers and "alza" not in manufacturers


def test_czechia_exists_once_and_no_alza_offer_is_filed_outside_it():
    codes = [r["code"] for r in catalogue_json("regions.json")["regions"]]
    assert codes.count("CZ") == 1
    for path in (REPO / "db" / "catalogue" / "robots").glob("*.json"):
        robot = json.loads(path.read_text(encoding="utf-8"))
        for kind in ("pricing_offers", "availability_offers"):
            for offer in robot.get(kind, []):
                if offer.get("provider_slug") == "alza-cz":
                    assert offer.get("region_code") == "CZ", path.name
                    assert offer.get("condition") in ("NEW", "USED", "OPEN_BOX", "REFURBISHED")


@pytest.mark.parametrize("slug,code,dof", [
    ("ubtech-walker-tienkung-embodied-intelligence", "TK2301", 42),
    ("ubtech-walker-tienkung-voice-vision", "TK2201", 21),
    ("ubtech-walker-tienkung", "TK2101", 20),
])
def test_walker_tienkung_models_are_separate_unpublished_governed_entities(slug, code, dof):
    robot = catalogue_json(f"robots/{slug}.json")
    assert robot["is_published"] is False and robot["commercial_status"] == "UNKNOWN"
    assert (robot["model_code"], robot["specs"]["degrees_of_freedom"]) == (code, dof)
    assert robot["manufacturer_slug"] == "ubtech-robotics"
    assert "AGENT_ASSISTED_RESEARCH" in robot["specs_note"]
    assert "docs.ubtrobot.com" in robot["official_url"]
    assert robot["pricing_offers"] == robot["availability_offers"] == []   # none materialized
    s1, s2 = (catalogue_json(f"robots/ubtech-walker-{x}.json") for x in ("s1", "s2"))
    assert robot["slug"] not in (s1["slug"], s2["slug"])
    assert robot["model_code"] not in (s1.get("model_code"), s2.get("model_code"))


def test_the_alza_extractor_is_a_live_extractor_but_has_no_identity_gate_name_collision():
    assert (alza.EXTRACTOR_KEY, alza.EXTRACTOR_VERSION) in pr.LIVE_EXTRACTORS
    names = {i.robot_name for i in alza.REFERENCE_ITEMS.values()}
    assert re.search(r"Embodied Intelligence", " ".join(names))


# ------------------------------------- owner identity decisions (2026-10-05) -------


def test_g1_edu_u4_u5_u6_and_r1_basic_get_no_proposals_and_no_robot_rows(dsession):
    """Retailer configurations are not canonical robots: nothing is proposed or created."""
    unresolved = {"13150282", "13079624", "13150284", "13408317"}
    assert unresolved <= set(alza.UNRESOLVED_ITEMS)
    assert not unresolved & set(alza.REFERENCE_ITEMS)
    before = dsession.scalar(text("SELECT count(*) FROM robot"))
    for slug in ("unitree-g1-edu-plus-u2", "unitree-r1", "unitree-h2", "unitree-h2-edu",
                 "unitree-r1-edu-u2"):
        result = alza.propose_alza_reference_claims(LISTING, alza.UNITREE_LISTING_URL,
                                                    robot_slug=slug)
        ids = {dict(p.structured)["product_id"] for p in result.proposals}
        assert not ids & unresolved, slug
        rejected = {k.split()[0]: why for k, why in result.rejected}
        for pid in unresolved:
            assert "IDENTITY_UNRESOLVED" in rejected[pid]
    assert "UNMATCHED" in alza.UNRESOLVED_ITEMS["13408317"]
    assert "no new robot row" in alza.UNRESOLVED_ITEMS["13150282"]
    assert dsession.scalar(text("SELECT count(*) FROM robot")) == before
    for slug in ("unitree-g1-edu-u4", "unitree-g1-edu-u5", "unitree-g1-edu-u6",
                 "unitree-h2-edu-u2", "unitree-r1-basic"):
        assert slug not in {i.robot_slug for i in alza.REFERENCE_ITEMS.values()}
        assert not (REPO / "db" / "catalogue" / "robots" / f"{slug}.json").exists()


def test_h2_basic_and_h2_edu_u2_map_to_the_official_h2_family():
    assert alza.REFERENCE_ITEMS["13215767"].robot_slug == "unitree-h2"
    assert alza.REFERENCE_ITEMS["13215767"].identity_confidence == "MEDIUM"
    u2 = alza.REFERENCE_ITEMS["13501544"]
    assert (u2.robot_slug, u2.configuration[0]) == ("unitree-h2-edu", "u2")
    result = alza.propose_alza_reference_claims(LISTING, alza.UNITREE_LISTING_URL,
                                                robot_slug="unitree-h2-edu")
    by_pid = {}
    for p in result.proposals:
        by_pid.setdefault(dict(p.structured)["product_id"], dict(p.structured))
    assert set(by_pid) == {"13215768", "13501544"}
    assert "configuration_label" not in by_pid["13215768"]
    assert by_pid["13501544"]["configuration_label"] == "U2"
    assert by_pid["13501544"]["order_code"] == "BUN_H2EDU_U2"


def test_h2_edu_and_its_u2_bundle_are_two_offers_of_one_robot_without_a_new_robot(
        dsession, tmp_path):
    slug, name = "unitree-h2-edu", "H2 EDU"
    ensure_robot(dsession, slug, name)
    page = capture(dsession, LISTING, url=alza.UNITREE_LISTING_URL)
    proposals.ingest_alza_reference_proposals(
        dsession, source_key=alza.SOURCE_KEY, robot_slug=slug, fetched_page_id=page.id,
        body=LISTING, ingested_by=WHO)
    rows = list(dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == slug)))
    assert len(rows) == 4
    bundle_price = next(p for p in rows if p.kind == "RETAIL_PRICE"
                        and p.structured.get("configuration_label"))
    # a bundle offer without the stated configuration is refused
    accept(dsession, bundle_price, price_choices(bundle_price))
    with pytest.raises(DiscoveryError):
        claims.create_claim(dsession, str(bundle_price.id), created_by=WHO)
    for p in rows:
        s = p.structured
        extra = ({"variant_slug": "u2", "variant_name": s["configuration_name"]}
                 if s.get("configuration_label") else {})
        if p.kind == "RETAIL_PRICE":
            accept(dsession, p, price_choices(p, **extra))
        else:
            accept(dsession, p, avail_choices(p, "AVAILABLE", **extra))
        claim_for(dsession, p)

    path = stub_doc(tmp_path, slug, name)
    materialize.apply_plan(materialize.plan_materialization(dsession, slug, tmp_path))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert [v["slug"] for v in doc["variants"]] == ["u2"]
    prices = {o.get("variant_slug"): o["price"] for o in doc["pricing_offers"]}
    assert prices == {None: 1309990.0, "u2": 1507990.0}
    avail = {o.get("variant_slug"): o["availability_status"] for o in doc["availability_offers"]}
    assert avail == {None: "AVAILABLE", "u2": "AVAILABLE"}
    robot = dsession.scalar(select(Robot).where(Robot.slug == slug))
    before = dsession.scalar(text("SELECT count(*) FROM robot"))
    do_import(dsession, path, robot)
    assert dsession.scalar(text("SELECT count(*) FROM robot")) == before   # no new robot
    audits = materialize.verify_applied(dsession, slug, change_ref="chg-h2", applied_by=WHO)
    assert len(audits) == 4
    do_import(dsession, path, robot)
    assert materialize.verify_applied(dsession, slug, change_ref="chg-h2", applied_by=WHO) == []
