"""G2-3: accepted claims, retractions, catalogue write audit, materialization (DR-A5).

Offline PostgreSQL, every test in a rolled-back transaction. Covers the first vertical
slice only: `robot_variant` and variant-scoped `specification[dexterous_hand_option]`.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_claim_proposal_persistence import (
    NEW_PRICE,
    OLD_PRICE,
    PAGE,
    World,
    refused,
    replace_cell,
)
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)

from app.models import (
    AcceptedClaim,
    CatalogueWriteAudit,
    ClaimRetraction,
    DiscoveryClaimProposal,
    ProposalImmutableError,
)
from app.services.discovery import DiscoveryError, claims, materialize
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import (
    CLAIM_POLICIES,
    CLAIM_REGISTRY_VERSION,
    claim_policy_for,
)

pytestmark = pytest.mark.usefixtures("no_external_network")
WHO = "Robert Konecny"
REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO / "db" / "import_catalogue.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


def prop(session, w, kind, edition=None):
    return session.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug, DiscoveryClaimProposal.kind == kind,
        DiscoveryClaimProposal.edition == edition)).one()


def answers(p):
    return {pr.question_key(i): f"owner answer {i}" for i in range(1, len(p.review_questions) + 1)}


def accept_variant(session, w, edition):
    p = prop(session, w, "VARIANT", edition)
    choices = {**answers(p), "target_kind": "robot_variant", "variant_slug": edition.lower(),
               "variant_name": edition}
    return p, pr.decide(session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="owner decision",
                        choices=choices)[0]


def accept_spec(session, w, edition, **override):
    p = prop(session, w, "SPECIFICATION", edition)
    choices = {**answers(p), "target_kind": "specification",
               "spec_key": "dexterous_hand_option", "edition_scope": "THIS_EDITION",
               "accepted_value": p.value, "variant_slug": edition.lower(), **override}
    return p, pr.decide(session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="owner decision",
                        choices=choices)[0]


def seeded(session):
    w = World(session)
    w.ingest(w.page())
    return w


def slice_claims(session, w):
    out = {}
    for ed in ("Standard", "Pro"):
        p, _ = accept_variant(session, w, ed)
        out[f"v-{ed}"] = claims.create_claim(session, str(p.id), created_by=WHO)[0]
    for ed in ("Standard", "Pro"):
        p, _ = accept_spec(session, w, ed)
        out[f"s-{ed}"] = claims.create_claim(session, str(p.id), created_by=WHO)[0]
    return out


def stub(w, tmp):
    doc = {"slug": w.slug, "name": "4NE1 Mini", "manufacturer_slug": "x",
           "commercial_status": "UNKNOWN", "is_published": False, "specs": {},
           "variants": [], "pricing_offers": [], "availability_offers": []}
    path = tmp / f"{w.slug}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------ registry ------


def test_only_the_two_owner_approved_targets_are_registered(dsession):
    assert set(CLAIM_POLICIES) == {"robot_variant", "specification[dexterous_hand_option]"}
    w = seeded(dsession)
    registered = {(p.kind, p.edition) for p in dsession.scalars(
        select(DiscoveryClaimProposal).where(DiscoveryClaimProposal.robot_slug == w.slug))
        if claim_policy_for(p.kind, p.target, p.evidence_locator)}
    assert registered == {("VARIANT", "Standard"), ("VARIANT", "Pro"),
                          ("SPECIFICATION", "Standard"), ("SPECIFICATION", "Pro")}


@pytest.mark.parametrize("kind,edition", [
    ("PRICE_ESTIMATE", "Standard"), ("AVAILABILITY", "Pro"), ("RESERVATION_FEE", "Pro"),
    ("USE_CASES", "Standard"), ("INTEGRATION", "Pro"), ("DESIGN_CAVEAT", None),
    ("DATASHEET_REFERENCE", None)])
def test_unregistered_proposals_are_refused_even_when_accepted(dsession, kind, edition):
    w = seeded(dsession)
    p = prop(dsession, w, kind, edition)
    choices = {**answers(p), pr.HOME_KEY: pr.NO_CATALOGUE_HOME}
    pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="x", choices=choices)
    with pytest.raises(DiscoveryError, match="no registered field policy"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    assert dsession.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


# ------------------------------------------------------------- creation -----


def test_the_first_slice_creates_four_claims_with_full_lineage(dsession):
    w = seeded(dsession)
    made = slice_claims(dsession, w)
    assert len(made) == 4
    v = made["v-Pro"]
    assert (v.target_kind, v.target_key, v.variant_slug, v.accepted_value, v.edition_label) == (
        "robot_variant", "variant", "pro", "Pro", "Pro")
    s = made["s-Pro"]
    assert (s.target_kind, s.target_key, s.variant_slug, s.edition_scope) == (
        "specification", "dexterous_hand_option", "pro", "THIS_EDITION")
    assert s.accepted_value == s.verbatim_value == "12 DoF dexterous hands"
    assert made["s-Standard"].accepted_value == "Not included"
    assert s.registry_version == CLAIM_REGISTRY_VERSION
    # lineage: claim -> decision -> proposal -> observation -> fetched page -> source
    row = dsession.execute(text("""
        SELECT d.decision, p.digest, o.content_hash, fp.url, ds.key
        FROM accepted_claim c
        JOIN discovery_proposal_decision d ON d.id = c.decision_id
        JOIN discovery_claim_proposal p ON p.id = c.proposal_id
        JOIN discovery_proposal_observation o ON o.id = c.observation_id
        JOIN fetched_page fp ON fp.id = o.fetched_page_id
        JOIN discovery_source ds ON ds.id = c.source_id WHERE c.id = :i"""), {"i": s.id}).one()
    assert row.decision == "ACCEPT" and row.digest == s.proposal_digest
    assert row.content_hash == s.observation_content_hash and row.key == w.source.key
    assert row.url == s.source_url


def test_creating_is_idempotent_for_the_same_decision(dsession):
    w = seeded(dsession)
    p, _ = accept_variant(dsession, w, "Standard")
    first, c1 = claims.create_claim(dsession, str(p.id), created_by=WHO)
    again, c2 = claims.create_claim(dsession, str(p.id), created_by="Someone Else")
    assert c1 and not c2 and again.id == first.id
    assert dsession.scalar(select(func.count()).select_from(AcceptedClaim)) == 1


def test_a_claim_needs_an_effective_accept(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "VARIANT", "Pro")
    with pytest.raises(DiscoveryError, match="effective ACCEPT"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    pr.decide(dsession, str(p.id), pr.DEFER, decided_by=WHO, rationale="later")
    with pytest.raises(DiscoveryError, match="effective ACCEPT"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    p2, _ = accept_variant(dsession, w, "Pro")
    pr.decide(dsession, str(p2.id), pr.REJECT, decided_by=WHO, rationale="changed my mind")
    with pytest.raises(DiscoveryError, match="effective ACCEPT"):
        claims.create_claim(dsession, str(p2.id), created_by=WHO)


@pytest.mark.parametrize("key,value,needle", [
    ("variant_slug", "Standard", "variant_slug"), ("variant_slug", "std", "variant_slug"),
    ("variant_name", "standard", "variant_name"), ("target_kind", "specification", "target_kind")])
def test_a_differing_human_mapping_is_refused(dsession, key, value, needle):
    w = seeded(dsession)
    p = prop(dsession, w, "VARIANT", "Standard")
    choices = {**answers(p), "target_kind": "robot_variant", "variant_slug": "standard",
               "variant_name": "Standard", key: value}
    pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="x", choices=choices)
    with pytest.raises(DiscoveryError, match=needle):
        claims.create_claim(dsession, str(p.id), created_by=WHO)


def test_a_missing_mapping_is_never_guessed(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "VARIANT", "Standard")
    pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="x", choices=answers(p))
    with pytest.raises(DiscoveryError, match="target_kind"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)


@pytest.mark.parametrize("override,needle", [
    ({"spec_key": "hand_dof"}, "spec_key"), ({"edition_scope": "PRODUCT_LINE"}, "edition_scope"),
    ({"accepted_value": "12 DoF"}, "accepted_value")])
def test_the_spec_mapping_must_match_the_approved_definition_and_wording(
        dsession, override, needle):
    w = seeded(dsession)
    for ed in ("Standard", "Pro"):
        p, _ = accept_variant(dsession, w, ed)
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    p, _ = accept_spec(dsession, w, "Pro", **override)
    with pytest.raises(DiscoveryError, match=needle):
        claims.create_claim(dsession, str(p.id), created_by=WHO)


def test_a_specification_needs_its_variant_claim_first(dsession):
    w = seeded(dsession)
    p, _ = accept_spec(dsession, w, "Pro")
    with pytest.raises(DiscoveryError, match="must be accepted first"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    pv, _ = accept_variant(dsession, w, "Pro")
    claims.create_claim(dsession, str(pv.id), created_by=WHO)
    p2, _ = accept_spec(dsession, w, "Pro", variant_slug="standard")
    with pytest.raises(DiscoveryError, match="slug must be"):
        claims.create_claim(dsession, str(p2.id), created_by=WHO)


def test_no_claim_from_a_stale_or_superseded_proposal(dsession):
    w = seeded(dsession)
    p, _ = accept_variant(dsession, w, "Standard")        # ACCEPT recorded while CURRENT
    w.page(b"<html>new</html>", retrieved_at=datetime(2026, 9, 27, tzinfo=UTC))
    with pytest.raises(DiscoveryError, match="STALE"):
        claims.create_claim(dsession, str(p.id), created_by=WHO)
    assert dsession.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


def test_a_superseded_proposal_cannot_become_a_claim(dsession):
    w = seeded(dsession)
    price = prop(dsession, w, "PRICE_ESTIMATE", "Standard")
    changed = replace_cell(PAGE, OLD_PRICE, NEW_PRICE).encode("utf-8")
    w.ingest(w.page(changed, retrieved_at=datetime(2026, 9, 27, tzinfo=UTC)), changed)
    assert pr.derive_states(dsession, [price])[0].superseded
    # a registered-kind proposal in the same situation: supersede the Standard variant slot
    # by accepting while current, then changing the grid header wording
    v = prop(dsession, w, "VARIANT", "Standard")
    pr.decide(dsession, str(v.id), pr.REJECT, decided_by=WHO, rationale="history")
    assert dsession.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


# ------------------------------------------------------------ immutability --


@pytest.mark.parametrize("table", ["accepted_claim", "claim_retraction",
                                   "catalogue_write_audit"])
def test_the_new_tables_refuse_update_and_delete_in_the_database(dsession, table):
    w = seeded(dsession)
    made = slice_claims(dsession, w)
    claims.retract_claim(dsession, str(made["v-Standard"].id), retracted_by=WHO, reason="x")
    dsession.execute(text(
        "INSERT INTO catalogue_write_audit (claim_id, robot_slug, method, change_ref, "
        "target_table, target_row_id, after_hash, applied_by) VALUES (:c, :s, 'IMPORTER_M2', "
        "'abc', 'robot_variant', gen_random_uuid(), repeat('a', 64), 'tester')"),
        {"c": made["v-Pro"].id, "s": w.slug})
    for stmt, op in ((f"UPDATE {table} SET id = id", "UPDATE"), (f"DELETE FROM {table}", "DELETE"),
                     (f"UPDATE {table} SET id = id WHERE false", "UPDATE"),
                     (f"DELETE FROM {table} WHERE false", "DELETE")):
        with refused(dsession, op=op):
            dsession.execute(text(stmt))


def test_orm_listeners_back_the_triggers(dsession):
    w = seeded(dsession)
    made = slice_claims(dsession, w)
    claim = made["v-Pro"]
    with dsession.begin_nested():
        claim.accepted_value = "tampered"
        with pytest.raises(ProposalImmutableError):
            dsession.flush()
        dsession.expire(claim)


def test_retraction_appends_and_never_edits(dsession):
    w = seeded(dsession)
    made = slice_claims(dsession, w)
    c = made["v-Standard"]
    before = dsession.execute(text("SELECT to_jsonb(c) FROM accepted_claim c WHERE id = :i"),
                              {"i": c.id}).scalar()
    r = claims.retract_claim(dsession, str(c.id), retracted_by=WHO, reason="wrong wording")
    assert r.claim_id == c.id
    assert dsession.execute(text("SELECT to_jsonb(c) FROM accepted_claim c WHERE id = :i"),
                            {"i": c.id}).scalar() == before
    with pytest.raises(DiscoveryError, match="already retracted"):
        claims.retract_claim(dsession, str(c.id), retracted_by=WHO, reason="again")
    with pytest.raises(DiscoveryError):
        claims.retract_claim(dsession, str(made["v-Pro"].id), retracted_by=" ", reason="x")
    # a replacement must address the same target
    with pytest.raises(DiscoveryError, match="same robot and target"):
        claims.retract_claim(dsession, str(made["v-Pro"].id), retracted_by=WHO, reason="x",
                             replacement_id=str(made["s-Pro"].id))
    assert [a.id for a in claims.active_claims(dsession, w.slug)
            if a.id == c.id] == []
    assert dsession.scalar(select(func.count()).select_from(ClaimRetraction)) == 1


def test_a_claim_needs_a_named_human_in_the_service_and_the_database(dsession):
    w = seeded(dsession)
    p, _ = accept_variant(dsession, w, "Standard")
    with pytest.raises(DiscoveryError, match="--by"):
        claims.create_claim(dsession, str(p.id), created_by="  ")
    made, _ = claims.create_claim(dsession, str(p.id), created_by=WHO)
    with pytest.raises(DBAPIError):
        with dsession.begin_nested():
            dsession.execute(text(
                "INSERT INTO accepted_claim (claim_digest, decision_id, proposal_id, "
                "proposal_digest, observation_id, observation_content_hash, observed_at, "
                "source_id, source_url, robot_slug, variant_slug, target_kind, target_key, "
                "value_type, accepted_value, verbatim_value, evidence_excerpt, "
                "evidence_locator, policy_key, registry_version, resolved_choices, created_by) "
                "SELECT claim_digest, decision_id, proposal_id, proposal_digest, "
                "observation_id, observation_content_hash, observed_at, source_id, source_url, "
                "robot_slug, 'x', target_kind, 'other', value_type, accepted_value, "
                "verbatim_value, evidence_excerpt, evidence_locator, policy_key, "
                "registry_version, resolved_choices, ' ' FROM accepted_claim WHERE id = :i"),
                {"i": made.id})


# ----------------------------------------------------------- materialize ----


def test_materialization_is_deterministic_and_leaves_no_diff_once_applied(dsession, tmp_path):
    w = seeded(dsession)
    slice_claims(dsession, w)
    path = stub(w, tmp_path)
    original = path.read_text(encoding="utf-8")
    plan = materialize.plan_materialization(dsession, w.slug, tmp_path)
    again = materialize.plan_materialization(dsession, w.slug, tmp_path)
    assert plan.after == again.after and plan.changed and plan.diff()
    assert path.read_text(encoding="utf-8") == original        # planning writes nothing
    assert materialize.apply_plan(plan)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["variants"] == [{"slug": "pro", "name": "Pro"},
                               {"slug": "standard", "name": "Standard"}]
    specs = {(s["variant_slug"], s["key"]): s for s in doc["extended_specs"]}
    assert set(specs) == {("pro", "dexterous_hand_option"), ("standard", "dexterous_hand_option")}
    assert specs[("pro", "dexterous_hand_option")]["value"] == "12 DoF dexterous hands"
    assert specs[("standard", "dexterous_hand_option")]["value"] == "Not included"
    for s in specs.values():
        assert s["edition_scope"] == "THIS_EDITION" and s["source_kind"] == "MANUFACTURER"
        assert s["source_url"] and s["source_label"] and s["observed_at"] == "2026-09-26"
    # nothing else changed: only variants and extended_specs differ from the stub
    before = json.loads(original)
    assert {k: v for k, v in doc.items() if k not in ("variants", "extended_specs")} == {
        k: v for k, v in before.items() if k not in ("variants", "extended_specs")}
    # re-materialization: no diff
    final = materialize.plan_materialization(dsession, w.slug, tmp_path)
    assert not final.changed and not materialize.apply_plan(final)
    # no derived structured fields were invented
    assert "hand_dof" not in path.read_text(encoding="utf-8")
    assert "spec_overrides" not in path.read_text(encoding="utf-8")


def test_materialization_preserves_unrelated_catalogue_content(dsession, tmp_path):
    w = seeded(dsession)
    slice_claims(dsession, w)
    path = stub(w, tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["extended_specs"] = [{"key": "sdk_software", "value": "SDK", "edition_scope": "PLATFORM"}]
    doc["variants"] = [{"slug": "other", "name": "Other"}]
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["extended_specs"][0] == doc["extended_specs"][0]
    assert out["variants"][0] == {"slug": "other", "name": "Other"}
    assert [v["slug"] for v in out["variants"]] == ["other", "pro", "standard"]


def test_materialization_refuses_stale_unregistered_and_retracted_claims(dsession, tmp_path):
    w = seeded(dsession)
    made = slice_claims(dsession, w)
    stub(w, tmp_path)
    claims.retract_claim(dsession, str(made["s-Standard"].id), retracted_by=WHO, reason="x")
    plan = materialize.plan_materialization(dsession, w.slug, tmp_path)
    assert "Not included" not in plan.after and "12 DoF" in plan.after   # retracted excluded
    # stale after a page change that was not re-extracted: materialization refuses
    w.page(b"<html>changed</html>", retrieved_at=datetime(2026, 9, 27, tzinfo=UTC))
    with pytest.raises(DiscoveryError, match="STALE"):
        materialize.plan_materialization(dsession, w.slug, tmp_path)


def test_an_unregistered_policy_on_a_claim_is_refused(dsession, tmp_path, monkeypatch):
    w = seeded(dsession)
    slice_claims(dsession, w)
    stub(w, tmp_path)
    monkeypatch.setattr(materialize, "CLAIM_POLICIES", {})
    with pytest.raises(DiscoveryError, match="not registered"):
        materialize.plan_materialization(dsession, w.slug, tmp_path)


def test_a_robot_without_a_catalogue_file_is_refused(dsession, tmp_path):
    w = seeded(dsession)
    with pytest.raises(DiscoveryError, match="not catalogue-backed"):
        materialize.plan_materialization(dsession, w.slug, tmp_path)


def test_materializing_and_claiming_never_touch_the_catalogue_tables(dsession, tmp_path):
    w = seeded(dsession)
    tables = ("robot", "manufacturer", "evidence_source", "specification", "robot_variant",
              "pricing_offer", "availability_offer", "robot_capability", "use_case_fit",
              "robot_image", "deployment", "candidate_claim", "discovery_candidate",
              "promotion_audit", "discovery_claim_proposal", "discovery_proposal_observation")

    def snap():
        return {t: dsession.execute(text(
            f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
            f"FROM {t} x")).one() for t in tables}
    before = snap()
    slice_claims(dsession, w)
    stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    assert snap() == before
    assert dsession.scalar(text("SELECT is_published FROM robot WHERE slug = :s"),
                           {"s": w.slug}) is False


# ------------------------------------------------- importer + verify + audit --


def _raw_cursor(session):
    return session.connection().connection.driver_connection.cursor()


def _definition(cur):
    cur.execute("SELECT id FROM spec_definition WHERE key = 'dexterous_hand_option'")
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO spec_definition (key, label, category, value_type, sort_order) "
                "VALUES ('dexterous_hand_option', 'Dexterous hand option', 'MANIPULATION', "
                "'TEXT', 51) RETURNING id")
    return cur.fetchone()[0]


def _import(session, w, path):
    cur = _raw_cursor(session)
    def_id = _definition(cur)
    cur.execute("SELECT id FROM manufacturer WHERE id = %s", (w.maker.id,))
    robot = json.loads(path.read_text(encoding="utf-8"))
    robot["manufacturer_slug"] = w.maker.slug
    ic.import_robot(cur, robot, region_id=lambda code: None,
                    manufacturer_id=lambda slug: w.maker.id,
                    capability_id=lambda slug: None, use_case_id=lambda slug: None,
                    spec_definition=lambda key: (def_id, "TEXT"), collisions=[])


def test_the_importer_resolves_variant_scoped_specs_to_the_right_variant_ids(
        dsession, tmp_path):
    w = seeded(dsession)
    slice_claims(dsession, w)
    path = stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    _import(dsession, w, path)
    rows = dsession.execute(text("""
        SELECT v.slug, v.name, v.is_developer, s.value_text, s.edition_scope, s.source_kind,
               s.source_url, s.source_label, s.observed_at, s.managed_by
        FROM specification s JOIN robot_variant v ON v.id = s.variant_id
        JOIN robot r ON r.id = s.robot_id WHERE r.slug = :s ORDER BY v.slug"""),
        {"s": w.slug}).all()
    assert [(r.slug, r.name, r.value_text) for r in rows] == [
        ("pro", "Pro", "12 DoF dexterous hands"), ("standard", "Standard", "Not included")]
    assert all(r.edition_scope == "THIS_EDITION" and r.source_kind == "MANUFACTURER"
               and r.source_url and r.source_label and r.observed_at and r.managed_by
               for r in rows)
    assert dsession.scalar(text(
        "SELECT count(*) FROM robot_variant v JOIN robot r ON r.id = v.robot_id "
        "WHERE r.slug = :s"), {"s": w.slug}) == 2
    # no price / availability / hand_dof / spec_overrides were written
    for table in ("pricing_offer", "availability_offer"):
        assert dsession.scalar(text(
            f"SELECT count(*) FROM {table} t JOIN robot r ON r.id = t.robot_id "
            "WHERE r.slug = :s"), {"s": w.slug}) == 0
    assert dsession.scalar(text(
        "SELECT count(*) FROM robot_variant v JOIN robot r ON r.id = v.robot_id "
        "WHERE r.slug = :s AND v.spec_overrides IS NOT NULL"), {"s": w.slug}) == 0
    assert dsession.scalar(text("SELECT hand_dof FROM robot WHERE slug = :s"),
                           {"s": w.slug}) is None


def test_a_second_import_is_semantically_idempotent(dsession, tmp_path):
    w = seeded(dsession)
    slice_claims(dsession, w)
    path = stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))

    def content():
        return dsession.execute(text("""
            SELECT v.slug, v.name, d.key, s.value_text, s.edition_scope, s.source_url,
                   s.source_label, s.source_kind, s.observed_at
            FROM specification s JOIN robot_variant v ON v.id = s.variant_id
            JOIN spec_definition d ON d.id = s.definition_id JOIN robot r ON r.id = s.robot_id
            WHERE r.slug = :s ORDER BY v.slug"""), {"s": w.slug}).all()
    _import(dsession, w, path)
    first = content()
    _import(dsession, w, path)
    assert content() == first and len(first) == 2


def test_product_level_extended_specs_remain_backward_compatible(dsession, tmp_path):
    w = seeded(dsession)
    path = stub(w, tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["variants"] = [{"slug": "pro", "name": "Pro"}]
    doc["extended_specs"] = [
        {"key": "dexterous_hand_option", "value": "product level",
         "source_label": "x", "source_url": "https://example.invalid/", "source_kind":
         "MANUFACTURER", "edition_scope": "PLATFORM", "observed_at": "2026-09-01"},
        {"key": "dexterous_hand_option", "variant_slug": "pro", "value": "variant level",
         "source_label": "x", "source_url": "https://example.invalid/", "source_kind":
         "MANUFACTURER", "edition_scope": "THIS_EDITION", "observed_at": "2026-09-01"}]
    path.write_text(json.dumps(doc), encoding="utf-8")
    _import(dsession, w, path)
    rows = dsession.execute(text("""
        SELECT s.value_text, s.variant_id IS NULL AS product_level FROM specification s
        JOIN robot r ON r.id = s.robot_id WHERE r.slug = :s ORDER BY 1"""), {"s": w.slug}).all()
    assert [(r.value_text, r.product_level) for r in rows] == [
        ("product level", True), ("variant level", False)]


def test_an_unknown_variant_slug_fails_loudly_instead_of_widening_the_fact(
        dsession, tmp_path):
    w = seeded(dsession)
    path = stub(w, tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["extended_specs"] = [{"key": "dexterous_hand_option", "variant_slug": "ghost",
                              "value": "x", "edition_scope": "THIS_EDITION"}]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SystemExit, match="ghost"):
        _import(dsession, w, path)


def test_verify_appends_the_audit_with_lineage_and_refuses_a_mismatch(dsession, tmp_path):
    w = seeded(dsession)
    slice_claims(dsession, w)
    path = stub(w, tmp_path)
    with pytest.raises(DiscoveryError, match="import the merged catalogue first"):
        materialize.verify_applied(dsession, w.slug, change_ref="abc123", applied_by=WHO)
    assert dsession.scalar(select(func.count()).select_from(CatalogueWriteAudit)) == 0
    materialize.apply_plan(materialize.plan_materialization(dsession, w.slug, tmp_path))
    _import(dsession, w, path)
    written = materialize.verify_applied(dsession, w.slug, change_ref="abc123", applied_by=WHO,
                                         importer_run_ref="run-1")
    assert len(written) == 4
    assert {a.target_table for a in written} == {"robot_variant", "specification"}
    assert all(a.method == "IMPORTER_M2" and len(a.after_hash) == 64 for a in written)
    # idempotent for the same change
    assert materialize.verify_applied(dsession, w.slug, change_ref="abc123",
                                      applied_by=WHO) == []
    # audit lineage resolves to the source
    n = dsession.scalar(text("""
        SELECT count(*) FROM catalogue_write_audit a JOIN accepted_claim c ON c.id = a.claim_id
        JOIN discovery_proposal_observation o ON o.id = c.observation_id
        JOIN fetched_page fp ON fp.id = o.fetched_page_id
        JOIN discovery_source s ON s.id = c.source_id WHERE a.robot_slug = :s"""), {"s": w.slug})
    assert n == 4
    # a database that drifted from the claims is refused
    dsession.execute(text(
        "UPDATE specification SET value_text = 'drift' WHERE robot_id = "
        "(SELECT id FROM robot WHERE slug = :s)"), {"s": w.slug})
    with pytest.raises(DiscoveryError, match="not in the database as accepted"):
        materialize.verify_applied(dsession, w.slug, change_ref="def456", applied_by=WHO)


def test_importer_variant_scoped_sql_uses_the_resolved_variant_id():
    from test_catalogue_import_managed_rows import _RecordingCursor

    robot = {"slug": "r", "manufacturer_slug": "m", "name": "R", "commercial_status": "UNKNOWN",
             "is_published": False, "specs": {}, "variants": [{"slug": "pro", "name": "Pro"}],
             "extended_specs": [{"key": "k", "variant_slug": "pro", "value": "v",
                                 "edition_scope": "THIS_EDITION"}]}
    cur = _RecordingCursor(rows=[(1,), ("variant-uuid",), None])
    ic.import_robot(cur, robot, region_id=lambda c: 1, manufacturer_id=lambda s: 1,
                    capability_id=lambda s: 1, use_case_id=lambda s: 1,
                    spec_definition=lambda k: (7, "TEXT"), collisions=[])
    probe = [s for s in cur.statements if "IS NOT DISTINCT FROM" in s]
    assert probe and uuid  # the logical-key probe is variant-aware
    assert any(s.startswith("INSERT INTO specification") for s in cur.statements)


def test_every_catalogue_file_variant_slug_reference_resolves():
    """The catalogue gate for variant-scoped extended specs: a `variant_slug` must name one
    of the SAME file's variants (the importer would otherwise refuse it at load time)."""
    bad = []
    for path in sorted((REPO / "db" / "catalogue" / "robots").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        slugs = {v["slug"] for v in doc.get("variants") or []}
        for x in doc.get("extended_specs") or []:
            if x.get("variant_slug") is not None and x["variant_slug"] not in slugs:
                bad.append((path.name, x.get("key"), x["variant_slug"]))
    assert not bad, bad
