"""G4-3: the INTEGRITY gate and the non-blocking COVERAGE audit (DR-G4 sections 7-8).

    Incomplete is publishable. Misleading is not.

The first half is pure (no database): it pins what may block and, as importantly, what never may.
The
second half exercises the database loader, the current-versus-historical identity rule, the
importer's
publication transition and the CLI exit codes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.robot_image import RobotImage
from app.services import fact_resolution as fr
from app.services import readiness as rd
from app.services.readiness import (
    AvailabilityRow,
    ClaimRow,
    ImageRow,
    PricingRow,
    RobotRecord,
    SpecRow,
)
from app.services.readiness_loader import load_records

REPO = Path(__file__).resolve().parents[3]
BASELINE = REPO / "db" / "catalogue" / "legacy_readiness_baseline.json"
LEGACY = rd.load_legacy_baseline(BASELINE.read_text(encoding="utf-8"))


def blocks(findings):
    return [f for f in findings if f.severity == rd.BLOCK]


def codes(findings):
    return sorted({f.code for f in blocks(findings)})


def sparse(**over) -> RobotRecord:
    """A newly announced humanoid: identity, one authoritative source, a summary, honest maturity,
    ONE technical fact, and everything else UNKNOWN. No price, no availability."""
    base = dict(
        slug="robot-x",
        name="Robot X",
        manufacturer_slug="maker-x",
        is_published=False,
        summary=(
            "Maker X's newly announced humanoid robot. The manufacturer states 80 body DoF and "
            "plans market launch in 2028. Other specifications have not yet been verified."
        ),
        commercial_status="ANNOUNCED",
        official_url="https://maker-x.example/robot-x",
        core={"degrees_of_freedom": 80},
        status_evidence=1,
        source_count=1,
    )
    base.update(over)
    return RobotRecord(**base)


MINI_VARIANTS = (("pro", "Pro"), ("standard", "Standard"))
MINI_SPECS = (
    SpecRow("standard", "dexterous_hand_option", "Dexterous hand option", "Not included"),
    SpecRow("pro", "dexterous_hand_option", "Dexterous hand option", "12 DoF dexterous hands"),
    SpecRow(
        "standard",
        "common_interfaces",
        "Common interfaces",
        "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync",
    ),
    SpecRow(
        "pro",
        "common_interfaces",
        "Common interfaces",
        "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync",
    ),
    SpecRow(
        "pro",
        "additional_interfaces",
        "Additional interfaces",
        "C++ SDK, digital twin access, teleoperation, ready for Neura Gym training",
    ),
)


def mini(**over) -> RobotRecord:
    base = dict(
        slug="mini-like",
        name="Mini",
        manufacturer_slug="neura",
        is_published=True,
        summary="NEURA Robotics' compact humanoid, offered in Standard and Pro configurations.",
        variants=MINI_VARIANTS,
        specs=MINI_SPECS,
        status_evidence=0,
        commercial_status="UNKNOWN",
    )
    base.update(over)
    return RobotRecord(**base)


# ------------------------------------------------------------------------ the golden cases ---


def test_a_fresh_sparse_announcement_is_publishable():
    """THE business case (owner 2026-10-03): newly announced, ~10% known, 90% UNKNOWN, no price, no
    availability. publication_integrity = PASS, coverage = LOW, and it publishes."""
    rec = sparse()
    assert blocks(rd.integrity_check(rec, transition=True)) == []
    assert rd.publication_check(rec) == []
    assert rd.fresh_announcement_ready(rec) is True
    cov = rd.coverage_audit(rec)
    assert cov.band == "LOW"
    assert {f.code for f in cov.findings} >= {
        "NO_PRICE",
        "NO_AVAILABILITY",
        "UNKNOWN_DENSITY",
        "NO_SDK_EVIDENCE",
        "NO_DEPLOYMENT_EVIDENCE",
    }
    assert all(f.severity != rd.BLOCK for f in cov.findings)  # coverage never blocks


def test_a_robot_that_is_ninety_percent_unknown_publishes_when_the_known_part_is_truthful():
    rec = sparse(
        core={"degrees_of_freedom": 80, "payload_kg": 20.0},
        specs=(SpecRow(None, "compute_ai", "AI compute", "new AI processor"),),
    )
    cov = rd.coverage_audit(rec)
    assert cov.known_buyer_fields < cov.total_buyer_fields / 2  # mostly UNKNOWN
    assert rd.publication_check(rec) == []  # and still publishable


@pytest.mark.parametrize(
    "name,rec",
    [
        ("everything UNKNOWN", sparse(core={}, commercial_status="UNKNOWN", status_evidence=0)),
        ("no price / availability / deployment", sparse()),
        ("detail-only tokens", sparse(variants=MINI_VARIANTS, specs=MINI_SPECS)),
        (
            "unmapped manufacturer wording",
            sparse(
                specs=(
                    SpecRow(
                        None,
                        "common_interfaces",
                        "Common interfaces",
                        "a brand new feature, 5G modem",
                    ),
                )
            ),
        ),
        (
            "no-catalogue-home claims",
            sparse(
                claims=(
                    ClaimRow("c1", "NO_CATALOGUE_HOME", "reservation_fee", None, "EUR 100"),
                    ClaimRow("c2", "NO_CATALOGUE_HOME", "historical_body_dof", None, "82"),
                )
            ),
        ),
        ("pending proposals", sparse(not_yet_reviewed=12)),
    ],
)
def test_completeness_conditions_never_block(name, rec):
    assert blocks(rd.integrity_check(rec, transition=True)) == [], name
    cov = rd.coverage_audit(rec)
    assert cov.band in {"LOW", "PARTIAL", "GOOD"} and all(
        f.severity != rd.BLOCK for f in cov.findings
    )


def test_coverage_has_no_failing_outcome_even_for_a_broken_record():
    broken = sparse(name="", manufacturer_slug=None, summary=None)
    cov = rd.coverage_audit(broken)  # returns a report; it cannot raise or block
    assert all(f.severity != rd.BLOCK for f in cov.findings)
    assert blocks(rd.integrity_check(broken, transition=True))  # integrity is where it blocks


# ------------------------------------------------------------------------ what blocks ---


def test_identity_blockers():
    assert "IDENTITY_MISSING_NAME" in codes(rd.integrity_check(sparse(name="  ")))
    assert "IDENTITY_MISSING_MANUFACTURER" in codes(
        rd.integrity_check(sparse(manufacturer_slug=None))
    )
    assert "IDENTITY_INVALID_SLUG" in codes(rd.integrity_check(sparse(slug="Robot X!")))
    amb = sparse(open_identity=("candidate 'Robot X' is POSSIBLE_DUPLICATE (POSSIBLE_DUPLICATE)",))
    assert "IDENTITY_AMBIGUOUS" in codes(rd.integrity_check(amb))
    assert "IDENTITY_AMBIGUOUS" in codes(rd.integrity_check(amb, transition=True))


def test_a_canonical_conflict_blocks_a_published_robot_but_never_picks_a_side():
    pro_sdk = SpecRow("pro", "common_interfaces", "Common interfaces", "Python SDK")
    rec = mini(core={"has_sdk": False}, specs=(pro_sdk,))
    assert "CANONICAL_CONFLICT" in codes(rd.integrity_check(rec))
    assert rd.resolve(rec)["has_sdk"].state is fr.State.CONFLICT
    two = mini(
        claims=(
            ClaimRow("1", "robot_spec", "degrees_of_freedom", None, "76"),
            ClaimRow("2", "robot_spec", "degrees_of_freedom", None, "82"),
        ),
        core={"degrees_of_freedom": 76},
    )
    assert "CANONICAL_CONFLICT" in codes(rd.integrity_check(two))


def test_fabricated_year_level_date_blocks():
    year = AvailabilityRow(None, "WAITLIST", "2027-01-01", "Expected in 2027", None, True)
    assert "FABRICATED_DATE" in codes(
        rd.integrity_check(sparse(is_published=True, availability=(year,)))
    )
    ok = AvailabilityRow(None, "WAITLIST", None, "Expected in 2027", None, True)
    assert "FABRICATED_DATE" not in codes(
        rd.integrity_check(sparse(is_published=True, availability=(ok,)))
    )
    exact = AvailabilityRow(None, "AVAILABLE", "2026-11-03", "Ships 3 November 2026", None, True)
    assert "FABRICATED_DATE" not in codes(
        rd.integrity_check(sparse(is_published=True, availability=(exact,)))
    )


def test_an_estimate_published_as_a_public_price_blocks():
    claim = ClaimRow(
        "p",
        "pricing_offer",
        "purchase.manufacturer_estimate",
        "pro",
        json.dumps({"price_type": "MANUFACTURER_ESTIMATE", "price": "29999"}),
    )
    msrp = PricingRow("pro", "PUBLIC", 29999.0, True)
    honest = PricingRow("pro", "MANUFACTURER_ESTIMATE", 29999.0, True)
    base = dict(is_published=True, variants=MINI_VARIANTS, claims=(claim,))
    assert "FABRICATED_PRICE_TYPE" in codes(rd.integrity_check(sparse(pricing=(msrp,), **base)))
    assert "FABRICATED_PRICE_TYPE" not in codes(
        rd.integrity_check(sparse(pricing=(honest,), **base))
    )


def test_a_historical_figure_with_a_catalogue_home_blocks():
    bad = ClaimRow("h", "robot_spec", "historical_body_dof", None, "82")
    assert "HISTORICAL_AS_CURRENT" in codes(rd.integrity_check(sparse(claims=(bad,))))
    ok = ClaimRow("h", "NO_CATALOGUE_HOME", "historical_body_dof", None, "82")
    assert "HISTORICAL_AS_CURRENT" not in codes(rd.integrity_check(sparse(claims=(ok,))))


def test_a_variant_flattened_to_product_scope_blocks():
    claim = ClaimRow("v", "specification", "dexterous_hand_option", "pro", "12 DoF dexterous hands")
    flat = (
        SpecRow(None, "dexterous_hand_option", "Dexterous hand option", "12 DoF dexterous hands"),
    )
    assert "VARIANT_FLATTENED" in codes(rd.integrity_check(mini(specs=flat, claims=(claim,))))


def test_required_provenance_blocks_for_published_robots_only():
    unevidenced = sparse(is_published=True, status_evidence=0)
    assert "PROVENANCE_MISSING" in codes(rd.integrity_check(unevidenced))
    assert "PROVENANCE_MISSING" in codes(
        rd.integrity_check(sparse(status_evidence=0), transition=True)
    )
    # an UNPUBLISHED stub is not a public assertion: a coverage warning, never a block
    stub = rd.integrity_check(sparse(status_evidence=0))
    assert blocks(stub) == []
    assert any(f.concept == rd.COVERAGE and f.code == "PROVENANCE_MISSING" for f in stub)
    for rec in (
        sparse(is_published=True, pricing=(PricingRow(None, "PUBLIC", 1.0, False),)),
        sparse(
            is_published=True,
            availability=(AvailabilityRow(None, "AVAILABLE", None, None, None, False),),
        ),
        sparse(is_published=True, deployments=(False,)),
    ):
        assert "PROVENANCE_MISSING" in codes(rd.integrity_check(rec))
    sourceless = ImageRow(
        "/x.webp", None, None, "VERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", None
    )
    assert "IMAGE_PROVENANCE_MISSING" in codes(
        rd.integrity_check(sparse(is_published=True, images=(sourceless,)))
    )
    # no image at all is simply IMAGE_UNAVAILABLE: fine
    assert blocks(rd.integrity_check(sparse(is_published=True, images=()))) == []


# ------------------------------------------------------------------------ new vs legacy false ---


def test_a_new_unexplained_false_is_an_integrity_failure_and_a_legacy_one_is_not():
    new = sparse(is_published=True, core={"has_sdk": False})
    assert "UNEXPLAINED_NEGATIVE" in codes(rd.integrity_check(new, legacy=LEGACY))
    legacy_rec = RobotRecord(**{**new.__dict__, "slug": "unitree-h2"})
    assert "UNEXPLAINED_NEGATIVE" not in codes(rd.integrity_check(legacy_rec, legacy=LEGACY))
    cov = rd.coverage_audit(legacy_rec, legacy=LEGACY)
    assert any(f.code == "LEGACY_UNEXPLAINED_FALSE" and f.severity == rd.WARN for f in cov.findings)
    zero = sparse(is_published=True, core={"weight_kg": 0})
    assert "UNEXPLAINED_NEGATIVE" in codes(rd.integrity_check(zero, legacy=LEGACY))  # NULL -> 0
    # spec_caveats is explanatory metadata ONLY: it can never establish a false (owner ruling)
    caveated = sparse(
        is_published=True,
        core={"has_sdk": False},
        spec_caveats=({"field": "has_sdk", "kind": "EXPLICIT_NEGATIVE", "text": "Maker: no SDK."},),
    )
    assert "UNEXPLAINED_NEGATIVE" in codes(rd.integrity_check(caveated, legacy=LEGACY))
    assert not hasattr(rd, "EXPLICIT_NEGATIVE")


def test_a_negative_is_never_inferred_from_wording_that_has_no_ratified_mapping():
    """The governed chain: wording is preserved verbatim as a scoped specification; a separately
    ratified negative projection may resolve false. The initial registry has none, so an explicit
    negative statement stays a projection candidate (UNMAPPED_KNOWLEDGE) and the property stays
    UNKNOWN: never false, and never a publication blocker."""
    specs = (
        SpecRow("pro", "common_interfaces", "Common interfaces", "SDK not supported"),
        SpecRow(
            "standard", "additional_interfaces", "Additional interfaces", "No teleoperation support"
        ),
    )
    rec = mini(specs=specs)
    res = rd.resolve(rec)
    assert res["has_sdk"].state is fr.State.UNKNOWN and res["has_sdk"].value is None
    assert res["has_teleoperation"].state is fr.State.UNKNOWN
    assert all(v.value is not False for f in res.values() for v in f.variants)
    acc = rd.account_facts(rec)
    assert "common_interfaces/SDK not supported" in acc.unmapped_candidates
    assert "additional_interfaces/No teleoperation support" in acc.unmapped_candidates
    assert blocks(rd.integrity_check(rec)) == []
    # once an owner ratifies the exact mapping, the SAME chain yields false (G4-1 resolver contract)
    neg = (*fr.PROJECTION_REGISTRY, fr.ProjectionRule("common_interfaces", "SDK not supported",
                                                      "has_sdk", False))
    only_pro = [fr.ScopedSpec("pro", "common_interfaces", "SDK not supported")]
    got = fr.resolve_property("has_sdk", None, [("pro", "Pro")], only_pro, registry=neg)
    assert got.state is fr.State.UNIFORM_VARIANTS and got.value is False


def test_the_legacy_baseline_matches_the_catalogue_and_can_only_shrink():
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert len([e for e in entries if e["field"] != "summary"]) == 8
    assert {e["slug"] for e in entries if e["field"] == "summary"} == {
        "honda-asimo",
        "rainbow-hubo",
        "softbank-nao",
        "softbank-pepper",
    }
    robots = {}
    for p in sorted((REPO / "db" / "catalogue" / "robots").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        robots[d["slug"]] = d
    for e in entries:  # every entry is still true: remove fixed ones
        d = robots[e["slug"]]
        if e["field"] == "summary":
            assert not (d.get("summary") or "").strip(), (
                f"{e['slug']} now has a summary: drop the entry"
            )
        else:
            assert (d.get("specs") or {}).get(e["field"]) in (False, 0), (
                f"{e['slug']}.{e['field']} was fixed: drop the baseline entry"
            )
    listed = {(e["slug"], e["field"]) for e in entries}
    for slug, d in robots.items():  # and nothing new has appeared at the source
        for f in rd.BOOLEAN_FIELDS:
            if (d.get("specs") or {}).get(f) is False:
                assert (slug, f) in listed, f"new unexplained false: {slug}.{f}"
        for f in rd.IMPLAUSIBLE_ZERO_FIELDS:
            v = (d.get("specs") or {}).get(f)
            if v is not None and float(v) == 0.0:
                assert (slug, f) in listed, f"new unexplained zero: {slug}.{f}"


# ------------------------------------------------------------------------ summary at publication
# ---


def test_a_summary_is_required_only_when_a_robot_becomes_published():
    none = sparse(summary=None)
    assert "SUMMARY_MISSING" in codes(rd.integrity_check(none, transition=True))
    assert "SUMMARY_MISSING" not in codes(
        rd.integrity_check(RobotRecord(**{**none.__dict__, "is_published": True}))
    )
    for bad in ("TBD", "N/A", "Robot X", "lorem ipsum dolor sit amet consectetur adipiscing"):
        assert "SUMMARY_NOT_USEFUL" in codes(
            rd.integrity_check(sparse(summary=bad), transition=True)
        ), bad
    # legacy published robots that predate the rule are a coverage warning, never a failure
    legacy_rec = RobotRecord(**{**none.__dict__, "slug": "honda-asimo", "is_published": True})
    assert blocks(rd.integrity_check(legacy_rec, legacy=LEGACY)) == []
    assert blocks(rd.integrity_check(legacy_rec, legacy=LEGACY, transition=True)) == []
    assert any(
        f.code == "SUMMARY_MISSING" and f.severity == rd.WARN
        for f in rd.coverage_audit(legacy_rec, legacy=LEGACY).findings
    )
    # a sparse summary is enough: it does not have to summarize every field
    assert "SUMMARY_NOT_USEFUL" not in codes(rd.integrity_check(sparse(), transition=True))


# ------------------------------------------------------------------------ loss and accounting ---


def test_accepted_knowledge_lost_from_the_public_chain_blocks_only_what_is_public():
    claim = ClaimRow("c", "specification", "common_interfaces", "pro", "Python SDK")
    lost = mini(specs=(), claims=(claim,))
    assert "UNACCOUNTED_LOSS" in codes(rd.integrity_check(lost))  # published
    unpub = rd.integrity_check(RobotRecord(**{**lost.__dict__, "is_published": False}))
    assert blocks(unpub) == [] and any(f.code == "UNACCOUNTED_LOSS" for f in unpub)  # warning
    assert "UNACCOUNTED_LOSS" in codes(
        rd.integrity_check(RobotRecord(**{**lost.__dict__, "is_published": False}), transition=True)
    )
    present = mini(
        claims=(
            ClaimRow(
                "c",
                "specification",
                "common_interfaces",
                "pro",
                "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync",
            ),
        )
    )
    assert "UNACCOUNTED_LOSS" not in codes(rd.integrity_check(present))


def test_a_registered_projection_that_the_resolver_loses_is_a_loss(monkeypatch):
    """Token drift of the dangerous kind: the fact is registered but the resolved output lost it."""
    real = fr.resolve_robot

    def lossy(product, variants, specs, properties=fr.PROJECTED_PROPERTIES, registry=None):
        out = real(product, variants, specs, properties)
        f = out["has_sdk"]
        out["has_sdk"] = fr.ResolvedFact(
            "has_sdk",
            fr.State.UNKNOWN,
            None,
            None,
            None,
            tuple(fr.VariantValue(v.slug, v.name, None) for v in f.variants),
        )
        return out

    monkeypatch.setattr(rd.fr, "resolve_robot", lossy)
    got = rd.integrity_check(mini())
    assert "UNACCOUNTED_LOSS" in codes(got) or "PUBLIC_CONTRADICTS_CANONICAL" in codes(got)


def test_fact_accounting_classifies_every_unit_and_unmapped_is_not_a_blocker():
    rec = mini(
        core={"payload_kg": 5.0},
        claims=(ClaimRow("n", "NO_CATALOGUE_HOME", "reservation_fee", None, "EUR 100"),),
        specs=MINI_SPECS
        + (SpecRow("pro", "additional_interfaces", "Additional interfaces", "5G modem"),),
        not_yet_reviewed=3,
    )
    acc = rd.account_facts(rec)
    assert acc.canonical_projected >= 6  # Python SDK x2, ROS x2, C++ SDK, teleop, manip
    assert "dexterous_hand_option/Not included" in acc.detail_only_reasons
    assert "additional_interfaces/digital twin access" in acc.detail_only_reasons
    assert acc.unmapped_candidates == ["additional_interfaces/5G modem"]
    assert acc.unmapped_knowledge == 1 and acc.no_catalogue_home == 1
    assert acc.not_yet_reviewed == 3 and acc.unaccounted_loss == 0 and acc.conflicts == 0
    assert (
        blocks(rd.integrity_check(rec)) == []
    )  # UNMAPPED / DETAIL_ONLY / NO_HOME / pending: allowed
    assert "UNMAPPED_KNOWLEDGE" in {f.code for f in rd.coverage_audit(rec).findings}


def test_the_mini_and_a_product_value_robot_pass_integrity():
    assert blocks(rd.integrity_check(mini())) == []
    res = rd.resolve(mini())
    assert res["has_sdk"].state is fr.State.UNIFORM_VARIANTS
    assert res["has_manipulation"].state is fr.State.PARTIAL_VARIANTS


# ------------------------------------------------------------------------ MEDIA-01 equivalence ---


@pytest.mark.parametrize("identity", ["VERIFIED", "UNVERIFIED"])
@pytest.mark.parametrize("rights", ["PERMITTED", "ATTRIBUTION_REQUIRED", "UNKNOWN", "RESTRICTED"])
@pytest.mark.parametrize("usage", ["NONE", "OFFICIAL_MANUFACTURER_MEDIA", "OWNER_APPROVED_DISPLAY"])
@pytest.mark.parametrize("rep", [False, True])
@pytest.mark.parametrize("note", [None, "caption"])
@pytest.mark.parametrize("attribution", [None, "(c) Maker"])
def test_the_readiness_image_rule_equals_the_ratified_model(
    identity, rights, usage, rep, note, attribution
):
    row = ImageRow("/x.webp", "https://s", "Maker", identity, rights, usage, attribution, rep, note)
    model = RobotImage(
        image_url="/x.webp",
        source_url="https://s",
        source_name="Maker",
        source_type="MANUFACTURER",
        image_type="FRONT",
        identity_status=identity,
        rights_status=rights,
        usage_basis=usage,
        is_official=True,
        is_primary=True,
        attribution=attribution,
        is_representative=rep,
        representative_note=note,
    )
    assert rd._display_eligible(row) == model.is_display_eligible()


# ------------------------------------------------------------------------ database-backed ---


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def world(database_url):
    made: list = []
    mfr = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()

    def robot(tag, **cols) -> tuple[str, object]:
        slug = f"g43-{tag}-{uuid.uuid4().hex[:8]}"
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) VALUES "
            "(:s, :m, :n, FALSE) RETURNING id",
            s=slug,
            m=mfr,
            n=slug.upper(),
        ).scalar_one()
        made.append(rid)
        for col, v in cols.items():
            _exec(f"UPDATE robot SET {col} = :v WHERE id = :i", v=v, i=rid)
        return slug, rid

    ctx = {"robot": robot, "made": made}
    yield ctx
    for rid in made:
        _exec(
            "DELETE FROM discovery_candidate WHERE possible_robot_id = :i "
            "OR promoted_robot_id = :i",
            i=rid,
        )
        _exec("DELETE FROM robot WHERE id = :i", i=rid)
    _exec("DELETE FROM discovery_source WHERE key LIKE 'g43-src-%'")


def records(slugs):
    with SessionLocal() as s:
        cur = s.connection().connection.cursor()
        return {r.slug: r for r in load_records(cur, set(slugs))}


def candidate(rid, *, identity, status, name="Probe"):
    src = _exec(
        "INSERT INTO discovery_source (key, name, source_class) VALUES "
        "(:k, 'g43', 'MANUFACTURER') RETURNING id",
        k=f"g43-src-{uuid.uuid4().hex[:8]}",
    ).scalar_one()
    _exec(
        "INSERT INTO discovery_candidate (source_id, external_ref, candidate_name, "
        "identity_status, status, possible_robot_id) VALUES (:s, :e, :n, "
        "CAST(:i AS candidate_identity_status), CAST(:t AS candidate_status), :r)",
        s=src,
        e=uuid.uuid4().hex,
        n=name,
        i=identity,
        t=status,
        r=rid,
    )


def test_the_loader_reads_a_published_sparse_robot_as_publishable(world):
    slug, rid = world["robot"](
        "sparse", summary=sparse().summary, degrees_of_freedom=80, commercial_status="UNKNOWN"
    )
    rec = records([slug])[slug]
    assert rec.core["degrees_of_freedom"] == 80 and rec.manufacturer_slug
    assert rd.publication_check(rec, legacy=LEGACY) == []


def test_only_a_CURRENT_unresolved_identity_ambiguity_blocks(world):
    slug, rid = world["robot"]("ident", summary=sparse().summary)
    candidate(rid, identity="POSSIBLE_DUPLICATE", status="POSSIBLE_DUPLICATE")  # active
    assert "IDENTITY_AMBIGUOUS" in codes(rd.publication_check(records([slug])[slug], legacy=LEGACY))
    # the ambiguity was RESOLVED (the candidate is terminal): the historical row must not block
    _exec("UPDATE discovery_candidate SET status = 'REJECTED' WHERE possible_robot_id = :i", i=rid)
    resolved = records([slug])[slug]
    assert resolved.open_identity == []
    assert rd.publication_check(resolved, legacy=LEGACY) == []
    # resolved to MATCHED_EXISTING (SAME_ENTITY decided): also not an open ambiguity
    _exec(
        "UPDATE discovery_candidate SET status = 'SOURCE_TRACE', identity_status = "
        "'MATCHED_EXISTING' WHERE possible_robot_id = :i",
        i=rid,
    )
    assert records([slug])[slug].open_identity == []


def load_importer():
    spec = importlib.util.spec_from_file_location(
        "import_catalogue_g43", REPO / "db" / "import_catalogue.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_importer_transition_refuses_a_misleading_publication_and_allows_a_sparse_one(
    world, capsys
):
    ic = load_importer()
    good, _ = world["robot"]("good", summary=sparse().summary, degrees_of_freedom=80)
    bad, _ = world["robot"]("bad", degrees_of_freedom=80)  # no summary
    with SessionLocal() as s:
        cur = s.connection().connection.cursor()
        cur.execute("SET search_path TO humanoid, public")
        # sparse + truthful: publishable, with non-blocking coverage warnings printed
        ic._check_publication_transitions(
            cur, [{"slug": good, "is_published": True}], {good: False}
        )
        out = capsys.readouterr().out
        assert f"PUBLICATION CHECK {good}: integrity PASS" in out and "coverage" in out
        # a misleading one is refused (and nothing about coverage can refuse it)
        with pytest.raises(SystemExit, match="PUBLICATION REFUSED"):
            ic._check_publication_transitions(
                cur, [{"slug": bad, "is_published": True}], {bad: False}
            )
        assert "SUMMARY_MISSING" in capsys.readouterr().out
        # an already-published robot is not a transition: no check, no refusal
        ic._check_publication_transitions(cur, [{"slug": bad, "is_published": True}], {bad: True})
        assert capsys.readouterr().out == ""


def run_cli(url, *args):
    return subprocess.run(
        [sys.executable, str(REPO / "db" / "readiness_check.py"), *args, "--database-url", url],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_the_cli_integrity_gate_fails_only_for_integrity_and_coverage_always_exits_zero(
    world, database_url
):
    ok, _ = world["robot"]("cli-ok", summary=sparse().summary)
    bad, bad_id = world["robot"]("cli-bad", is_published=True)
    _exec("UPDATE robot SET name = '   ' WHERE id = :i", i=bad_id)  # identity: blank name
    good = run_cli(database_url, "integrity", "--slug", ok)
    assert good.returncode == 0 and "Integrity gate: PASS" in good.stdout, good.stdout + good.stderr
    failing = run_cli(database_url, "integrity", "--slug", bad)
    assert failing.returncode == 1 and "IDENTITY_MISSING_NAME" in failing.stdout
    for slug in (ok, bad):  # coverage never fails, even for a broken robot
        cov = run_cli(database_url, "coverage", "--slug", slug)
        assert cov.returncode == 0 and "never blocks" in cov.stdout, cov.stdout + cov.stderr
    pub = run_cli(database_url, "publish", "--slug", ok)
    assert pub.returncode == 0 and "PUBLISHABLE" in pub.stdout


def test_the_real_catalogue_inputs_pass_integrity_in_the_unit_harness():
    """Every real catalogue record, taken straight from the committed JSON, passes the integrity
    check as a PUBLISHED robot: the detectors raise no false alarm on the legacy catalogue."""
    for path in sorted((REPO / "db" / "catalogue" / "robots").glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if not d.get("is_published"):
            continue
        spec_rows = tuple(
            SpecRow(
                e.get("variant_slug"),
                e["key"],
                e.get("label"),
                e["value"] if isinstance(e.get("value"), str) else None,
            )
            for e in d.get("extended_specs", [])
        )
        rec = RobotRecord(
            slug=d["slug"],
            name=d["name"],
            manufacturer_slug=d["manufacturer_slug"],
            is_published=True,
            summary=d.get("summary"),
            commercial_status=d["commercial_status"],
            official_url=d.get("official_url"),
            core=d.get("specs") or {},
            spec_caveats=d.get("spec_caveats", []),
            variants=tuple((v["slug"], v["name"]) for v in d.get("variants", [])),
            specs=spec_rows,
            status_evidence=len(d.get("commercial_status_evidence", [])),
            pricing=tuple(
                PricingRow(
                    p.get("variant_slug"), p["price_type"], p.get("price"), bool(p.get("evidence"))
                )
                for p in d.get("pricing_offers", [])
            ),
            availability=tuple(
                AvailabilityRow(
                    a.get("variant_slug"),
                    a["availability_status"],
                    a.get("available_from"),
                    a.get("delivery_estimate_label"),
                    a.get("seller_wording"),
                    bool(a.get("evidence")),
                )
                for a in d.get("availability_offers", [])
            ),
            deployments=tuple(bool(x.get("evidence")) for x in d.get("deployments", [])),
        )
        assert blocks(rd.integrity_check(rec, legacy=LEGACY)) == [], path.name
