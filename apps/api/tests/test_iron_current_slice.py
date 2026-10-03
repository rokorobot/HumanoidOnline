"""IRON current-configuration slice (owner decisions 2026-10-03).

Hand DoF (owner decision, option A): `robot.hand_dof` is PER HAND; XPENG states 21 "in each hand"
for the 2026 production configuration, taken as the manufacturer's own figure (actuated vs
passive is not stated and is recorded as a caveat). The 2022-style 22 (2025 / product page)
stays historical, unregistered evidence.

The 2026 production configuration is IRON's CURRENT one. Its whole-body DoF goes to the robot's
`degrees_of_freedom` column and its compute goes to the existing long-tail `compute_ai` TEXT
spec (a verbatim fragment), through proposal -> ACCEPT -> accepted claim -> deterministic
materialization -> importer -> verification. Everything else (hand DoF, the 2025 and 2024
figures, plans, morphology) stays an unregistered proposal.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from test_claim_proposal_persistence import refused
from test_xpeng_iron import (
    EXPECTED_COUNTS,
    NEWS_2025,
    NEWS_2026,
    PAGES,
    Site,
    body_of,
)
from test_xpeng_iron import dsession as dsession  # noqa: F401 (fixture)
from test_xpeng_iron import site as site  # noqa: F401 (fixture)

from app.models import AcceptedClaim, CatalogueWriteAudit, DiscoveryClaimProposal
from app.services.discovery import DiscoveryError, claims, materialize
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import CLAIM_POLICIES, IRON_CURRENT_CONFIGURATION

pytestmark = pytest.mark.usefixtures("no_external_network")
REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO / "db" / "import_catalogue.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)
WHO = "Robert Konecny"
FRAGMENT = "three Turing AI chips delivering up to 2,250 TOPS of effective computing power"


def ingest_all(site: Site):
    for url in PAGES:
        site.ingest(site.observe(url), body_of(url))


def proposal(site, url, kind):
    [p] = [p for p in site.all_proposals() if p.source_url == url and p.kind == kind]
    return p


def answers(p):
    return {pr.question_key(i): "Owner decision 2026-10-03: the 2026 production configuration is "
            "current" for i in range(1, len(p.review_questions) + 1)}


def body_choices(p, **over):
    return {**answers(p), "target_kind": "robot_spec", "spec_key": "degrees_of_freedom",
            "configuration": IRON_CURRENT_CONFIGURATION, "accepted_value": "76", **over}


def hand_choices(p, **over):
    return {**answers(p), "target_kind": "robot_spec", "spec_key": "hand_dof",
            "configuration": IRON_CURRENT_CONFIGURATION, "convention": "per hand",
            "accepted_value": "21", **over}


def compute_choices(p, **over):
    return {**answers(p), "target_kind": "specification", "spec_key": "compute_ai",
            "edition_scope": "THIS_EDITION", "configuration": IRON_CURRENT_CONFIGURATION,
            "accepted_value": FRAGMENT, **over}


def accept(site, p, choices):
    return pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO,
                     rationale="owner decision", choices=choices)[0]


def make_claims(site):
    body = proposal(site, NEWS_2026, "BODY_DOF")
    compute = proposal(site, NEWS_2026, "COMPUTE")
    hand = proposal(site, NEWS_2026, "HAND_DOF")
    accept(site, body, body_choices(body))
    accept(site, hand, hand_choices(hand))
    accept(site, compute, compute_choices(compute))
    return (claims.create_claim(site.session, str(body.id), created_by=WHO)[0],
            claims.create_claim(site.session, str(compute.id), created_by=WHO)[0],
            claims.create_claim(site.session, str(hand.id), created_by=WHO)[0])


def materialize_date(site) -> str:
    return site.session.scalar(select(AcceptedClaim.observed_at).where(
        AcceptedClaim.robot_slug == site.slug).limit(1)).date().isoformat()


def stub(site, tmp_path) -> Path:
    doc = json.loads((REPO / "db" / "catalogue" / "robots" / "xpeng-iron.json").read_text(
        encoding="utf-8"))
    doc["slug"], doc["manufacturer_slug"] = site.slug, site.maker.slug
    path = tmp_path / f"{site.slug}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def do_import(site, path):
    cur = site.session.connection().connection.driver_connection.cursor()
    cur.execute("SELECT id FROM spec_definition WHERE key = 'compute_ai'")
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO spec_definition (key, label, category, value_type, sort_order) "
                    "VALUES ('compute_ai', 'AI compute', 'AI_AUTONOMY', 'TEXT', 31) RETURNING id")
        row = cur.fetchone()
    robot = json.loads(path.read_text(encoding="utf-8"))
    ic.import_robot(cur, robot, region_id=lambda c: None,
                    manufacturer_id=lambda s: site.maker.id, capability_id=lambda s: None,
                    use_case_id=lambda s: None, spec_definition=lambda k: (row[0], "TEXT"),
                    collisions=[])


# ------------------------------------------------------------------ policies ---


def test_exactly_the_three_current_configuration_proposals_have_policies(site):
    ingest_all(site)
    assert {"robot_spec[degrees_of_freedom]", "robot_spec[hand_dof]",
            "specification[compute_ai]"} <= set(CLAIM_POLICIES)
    registered = [p for p in site.all_proposals()
                  if claims.claim_policy_for(p.kind, p.target, p.evidence_locator, p.structured)]
    current = [p for p in registered
               if claims.claim_policy_for(p.kind, p.target, p.evidence_locator,
                                          p.structured).target_kind != "NO_CATALOGUE_HOME"]
    assert {(p.source_url, p.kind) for p in current} == {
        (NEWS_2026, "BODY_DOF"), (NEWS_2026, "HAND_DOF"), (NEWS_2026, "COMPUTE")}
    assert len(registered) == 3 + 8                    # + the eight historical figures
    assert len(site.all_proposals()) == sum(EXPECTED_COUNTS.values())


@pytest.mark.parametrize("url,kind", [
    (NEWS_2026, "LAUNCH_PLAN"), (NEWS_2026, "MANUFACTURING_STATE"),
    (NEWS_2026, "MASS_PRODUCTION_PLAN"), (NEWS_2025, "MASS_PRODUCTION_PLAN"),
    (NEWS_2025, "GENERATION_HISTORY"), (NEWS_2025, "SDK_PLAN"), (NEWS_2025, "MORPHOLOGY")])
def test_plans_state_and_descriptions_stay_unregistered(site, url, kind):
    ingest_all(site)
    for p in site.all_proposals():
        if p.source_url == url and p.kind == kind:
            choices = {**answers(p), pr.HOME_KEY: pr.NO_CATALOGUE_HOME}
            pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="x",
                      choices=choices)
            with pytest.raises(DiscoveryError, match="no registered field policy"):
                claims.create_claim(site.session, str(p.id), created_by=WHO)
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


def historical(site):
    page = [u for u in PAGES if u not in (NEWS_2025, NEWS_2026) and "ai_robot_iron" in u]
    return [p for p in site.all_proposals()
            if p.source_url in (NEWS_2025, *page)
            and p.kind in ("BODY_DOF", "HAND_DOF", "COMPUTE", "BATTERY")]


def historical_choices(p):
    cfg = (p.structured or {}).get("configuration") or "Next-Gen IRON (product page)"
    return {**answers(p), pr.HOME_KEY: pr.NO_CATALOGUE_HOME, "target_kind": "NO_CATALOGUE_HOME",
            "configuration": cfg,
            "accepted_value": p.value}


def test_exactly_the_eight_historical_figures_are_no_catalogue_home_policies(site):
    ingest_all(site)
    hist = historical(site)
    assert len(hist) == 8 and sorted(p.kind for p in hist) == sorted(
        ["BODY_DOF", "HAND_DOF", "HAND_DOF", "HAND_DOF", "COMPUTE", "COMPUTE", "BATTERY",
         "BATTERY"])
    for p in hist:
        pol = claims.claim_policy_for(p.kind, p.target, p.evidence_locator, p.structured)
        assert pol is not None and pol.target_kind == "NO_CATALOGUE_HOME"
        assert pol.target_key.startswith("historical_")


def test_historical_figures_become_governed_knowledge_and_never_a_catalogue_fact(site, tmp_path):
    ingest_all(site)
    path = stub(site, tmp_path)
    before = path.read_text(encoding="utf-8")
    for p in historical(site):
        accept(site, p, historical_choices(p))
        c, created = claims.create_claim(site.session, str(p.id), created_by=WHO)
        assert created and c.target_kind == "NO_CATALOGUE_HOME"
        assert c.accepted_value == p.value and c.source_url == p.source_url
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 8
    plan = materialize.plan_materialization(site.session, site.slug, tmp_path)
    assert not plan.changed and path.read_text(encoding="utf-8") == before   # nothing written


def test_a_historical_figure_cannot_pose_as_the_current_configuration(site):
    ingest_all(site)
    p = proposal(site, NEWS_2025, "BODY_DOF")
    accept(site, p, historical_choices(p) | {"configuration": IRON_CURRENT_CONFIGURATION})
    with pytest.raises(DiscoveryError, match="configuration"):
        claims.create_claim(site.session, str(p.id), created_by=WHO)
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


@pytest.mark.parametrize("which,over,needle", [
    ("hand", {"accepted_value": "22"}, "accepted_value"),
    ("hand", {"accepted_value": "42"}, "accepted_value"),
    ("hand", {"convention": "total"}, "convention"),
    ("hand", {"configuration": "2025 Next-Gen IRON"}, "configuration"),
    ("hand", {"spec_key": "degrees_of_freedom"}, "spec_key"),
    ("body", {"configuration": "2025 Next-Gen IRON"}, "configuration"),
    ("body", {"accepted_value": "82"}, "accepted_value"),
    ("body", {"spec_key": "hand_dof"}, "spec_key"),
    ("body", {"target_kind": "specification"}, "target_kind"),
    ("compute", {"accepted_value": "three Turing AI chips delivering 3000 TOPS"},
     "accepted_value"),
    ("compute", {"configuration": "2025 Next-Gen IRON"}, "configuration"),
    ("compute", {"spec_key": "compute_base"}, "spec_key")])
def test_a_mapping_that_differs_from_the_owner_decision_is_refused(site, which, over, needle):
    ingest_all(site)
    kind = {"body": "BODY_DOF", "hand": "HAND_DOF", "compute": "COMPUTE"}[which]
    p = proposal(site, NEWS_2026, kind)
    choices = {"body": body_choices, "hand": hand_choices, "compute": compute_choices}[which](
        p, **over)
    accept(site, p, choices)
    with pytest.raises(DiscoveryError, match=needle):
        claims.create_claim(site.session, str(p.id), created_by=WHO)
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


def test_the_claims_carry_the_exact_current_values_and_full_lineage(site):
    ingest_all(site)
    body, compute, hand = make_claims(site)
    assert (hand.target_kind, hand.target_key, hand.accepted_value, hand.variant_slug) == (
        "robot_spec", "hand_dof", "21", None)
    assert hand.source_url == NEWS_2026
    assert materialize.logical_target(hand) == f"robot_spec:{site.slug}:hand_dof"
    assert (body.target_kind, body.target_key, body.accepted_value, body.variant_slug) == (
        "robot_spec", "degrees_of_freedom", "76", None)
    assert (compute.target_kind, compute.target_key, compute.accepted_value) == (
        "specification", "compute_ai", FRAGMENT)
    assert compute.variant_slug is None and compute.edition_scope == "THIS_EDITION"
    for c in (body, compute):
        assert c.source_url == NEWS_2026 and c.robot_slug == site.slug
        assert c.accepted_value and c.evidence_excerpt in c.verbatim_value or c.evidence_excerpt
    row = site.session.execute(text("""
        SELECT d.decision, p.digest, o.content_hash, fp.url, ds.key
        FROM accepted_claim c JOIN discovery_proposal_decision d ON d.id = c.decision_id
        JOIN discovery_claim_proposal p ON p.id = c.proposal_id
        JOIN discovery_proposal_observation o ON o.id = c.observation_id
        JOIN fetched_page fp ON fp.id = o.fetched_page_id
        JOIN discovery_source ds ON ds.id = c.source_id WHERE c.id = :i"""),
        {"i": body.id}).one()
    assert row.decision == "ACCEPT" and row.url == NEWS_2026 and row.key == site.source.key
    assert materialize.logical_target(body) == f"robot_spec:{site.slug}:degrees_of_freedom"
    assert materialize.logical_target(compute) == f"specification:{site.slug}:compute_ai"
    again = claims.create_claim(site.session, str(proposal(site, NEWS_2026, "BODY_DOF").id),
                                created_by="x")
    assert again[1] is False                                    # idempotent


# --------------------------------------------------------------- materialize ---


def test_materialization_adds_exactly_three_facts_and_nothing_else(site, tmp_path):
    ingest_all(site)
    make_claims(site)
    path = stub(site, tmp_path)
    before = json.loads(path.read_text(encoding="utf-8"))
    plan = materialize.plan_materialization(site.session, site.slug, tmp_path)
    assert plan.after == materialize.plan_materialization(
        site.session, site.slug, tmp_path).after              # deterministic
    materialize.apply_plan(plan)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["specs"]["degrees_of_freedom"] == 76
    moved = ("degrees_of_freedom", "hand_dof")
    assert {k: v for k, v in after["specs"].items() if k not in moved} == {
        k: v for k, v in before["specs"].items() if k not in moved}
    assert after["specs"]["hand_dof"] == 21                    # per hand, never a 42 total
    assert after["specs"]["hand_type"] is None
    d = materialize_date(site)
    assert after["specs_note"] == (
        f"degrees of freedom (76) as stated by XPENG for its 2026 production IRON ({NEWS_2026}, "
        f"observed {d}); hand dof (21, per hand) as stated by XPENG for its 2026 production IRON "
        f"({NEWS_2026}, observed {d}); whether the hand figure counts only actuated joints is "
        "not stated. All other specifications are not yet verified.")
    [compute] = after["extended_specs"]
    assert compute == {
        "key": "compute_ai", "value": FRAGMENT, "source_label": "XPENG",
        "source_url": NEWS_2026, "source_kind": "MANUFACTURER", "edition_scope": "THIS_EDITION",
        "observed_at": compute["observed_at"]}
    assert "variant_slug" not in compute
    keep = ("commercial_status", "is_published", "official_url", "variants", "pricing_offers",
            "availability_offers", "capabilities", "use_case_fits", "images", "summary",
            "announced_year")
    assert {k: after[k] for k in keep} == {k: before[k] for k in keep}
    assert after["commercial_status"] == "UNKNOWN" and after["is_published"] is False
    assert not materialize.plan_materialization(site.session, site.slug, tmp_path).changed


def test_materialization_refuses_when_the_current_proposal_goes_stale(site, tmp_path):
    ingest_all(site)
    make_claims(site)
    stub(site, tmp_path)
    site.observe(NEWS_2026, b"<html>the page changed</html>")      # newer, not re-extracted
    with pytest.raises(DiscoveryError, match="STALE"):
        materialize.plan_materialization(site.session, site.slug, tmp_path)


def test_the_importer_and_verification_close_the_chain_idempotently(site, tmp_path):
    ingest_all(site)
    make_claims(site)
    path = stub(site, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(site.session, site.slug, tmp_path))
    do_import(site, path)
    row = site.session.execute(text(
        "SELECT degrees_of_freedom, hand_dof, hand_type, autonomy::text, has_sdk, "
        "is_published, commercial_status::text FROM robot WHERE slug = :s"),
        {"s": site.slug}).one()
    assert tuple(row) == (76, 21, None, None, None, False, "UNKNOWN")
    spec = site.session.execute(text(
        "SELECT s.value_text, s.variant_id IS NULL AS product_level, s.edition_scope, "
        "s.source_kind, s.source_url FROM specification s JOIN spec_definition d "
        "ON d.id = s.definition_id JOIN robot r ON r.id = s.robot_id "
        "WHERE r.slug = :s AND d.key = 'compute_ai'"), {"s": site.slug}).one()
    assert (spec.value_text, spec.product_level, spec.edition_scope, spec.source_kind) == (
        FRAGMENT, True, "THIS_EDITION", "MANUFACTURER")
    written = materialize.verify_applied(site.session, site.slug, change_ref="chg-iron",
                                         applied_by=WHO)
    assert {a.target_table for a in written} == {"robot", "specification"} and len(written) == 3
    do_import(site, path)                                          # importer churns the rows
    assert materialize.verify_applied(site.session, site.slug, change_ref="chg-iron",
                                      applied_by=WHO) == []
    site.session.execute(text("UPDATE robot SET degrees_of_freedom = 82 WHERE slug = :s"),
                         {"s": site.slug})
    with pytest.raises(DiscoveryError, match="degrees_of_freedom is not in the database"):
        materialize.verify_applied(site.session, site.slug, change_ref="chg-x", applied_by=WHO)
    with refused(site.session, op="UPDATE"):
        site.session.execute(text("UPDATE catalogue_write_audit SET claim_id = claim_id"))
    assert site.session.scalar(select(func.count()).select_from(CatalogueWriteAudit)) == 3


def test_nothing_else_in_the_catalogue_or_decision_layers_moves(site, tmp_path):
    ingest_all(site)
    tables = ("robot_variant", "pricing_offer", "availability_offer", "robot_capability",
              "use_case_fit", "evidence_source", "promotion_audit")
    before = {t: site.session.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables}
    images_before = site.session.scalar(text("SELECT count(*) FROM robot_image"))
    make_claims(site)
    path = stub(site, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(site.session, site.slug, tmp_path))
    do_import(site, path)
    assert {t: site.session.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables} == before
    # the catalogue file carries IRON's one photograph (2026-10-03): the importer adds exactly it
    assert site.session.scalar(text("SELECT count(*) FROM robot_image")) == images_before + 1
    decisions = site.session.scalar(select(func.count()).select_from(AcceptedClaim))
    assert decisions == 3
    states = pr.derive_states(site.session, site.all_proposals())
    assert all(s.state == pr.CURRENT for s in states)               # no proposal was touched
    assert site.session.scalar(select(func.count()).select_from(DiscoveryClaimProposal)) == 38
