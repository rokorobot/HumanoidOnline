"""Importer Hardening Phase 0: the read-only audit-integrity report.

Offline PostgreSQL, every test in a rolled-back transaction. Reuses the G2-3 vertical slice
(two variants + two variant-scoped specifications) from test_accepted_claims.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from test_accepted_claims import WHO, _import, seeded, slice_claims, stub
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)

from app.models import CatalogueWriteAudit
from app.services.discovery import audit_integrity as ai
from app.services.discovery import claims, materialize

pytestmark = pytest.mark.usefixtures("no_external_network")


def verified(session, tmp_path):
    w = seeded(session)
    made = slice_claims(session, w)
    path = stub(w, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(session, w.slug, tmp_path))
    _import(session, w, path)
    assert len(materialize.verify_applied(session, w.slug, change_ref="chg-1",
                                          applied_by=WHO)) == 4
    return w, made, path


def classes(session, slug):
    return sorted((a.target_table, a.classification, a.target_exists)
                  for a in ai.classify_audits(session) if a.robot_slug == slug)


def test_freshly_verified_audits_are_current(dsession, tmp_path):
    w, _, _ = verified(dsession, tmp_path)
    assert classes(dsession, w.slug) == [("robot_variant", "CURRENT", True)] * 2 + [
        ("specification", "CURRENT", True)] * 2


def test_reimport_makes_every_audit_dangling_but_relinkable(dsession, tmp_path):
    """The importer recreates variant and specification rows under new UUIDs: every audit
    target dangles, and every one is reproduced exactly by one current row."""
    w, _, path = verified(dsession, tmp_path)
    _import(dsession, w, path)
    found = [a for a in ai.classify_audits(dsession) if a.robot_slug == w.slug]
    assert {(a.classification, a.target_exists) for a in found} == {("RELINKABLE", False)}
    assert all(a.current_row_id and a.current_row_id != a.target_row_id for a in found)
    live = {str(r[0]) for r in dsession.execute(text(
        "SELECT v.id FROM robot_variant v JOIN robot r ON r.id = v.robot_id WHERE r.slug = :s "
        "UNION SELECT s.id FROM specification s JOIN robot r ON r.id = s.robot_id "
        "WHERE r.slug = :s"), {"s": w.slug})}
    assert {a.current_row_id for a in found} == live


def test_changed_content_is_unresolved_until_a_later_audit_records_it(dsession, tmp_path):
    w, _, _ = verified(dsession, tmp_path)
    # source_label is part of the audited payload but not of the acceptance check, so the
    # claim still verifies while its content hash changes.
    dsession.execute(text("UPDATE specification SET source_label = 'relabelled' WHERE robot_id ="
                          " (SELECT id FROM robot WHERE slug = :s)"), {"s": w.slug})
    assert classes(dsession, w.slug) == [("robot_variant", "CURRENT", True)] * 2 + [
        ("specification", "UNRESOLVED", True)] * 2
    assert len(materialize.verify_applied(dsession, w.slug, change_ref="chg-2",
                                          applied_by=WHO)) == 4      # one per claim
    by_ref = {(a.change_ref, a.target_table, a.classification)
              for a in ai.classify_audits(dsession) if a.robot_slug == w.slug}
    assert by_ref == {("chg-1", "robot_variant", "CURRENT"),
                      ("chg-1", "specification", "SUPERSEDED"),
                      ("chg-2", "robot_variant", "CURRENT"),
                      ("chg-2", "specification", "CURRENT")}


def test_a_claim_that_no_longer_verifies_is_unresolved_with_its_reason(dsession, tmp_path):
    w, _, _ = verified(dsession, tmp_path)
    dsession.execute(text("UPDATE specification SET value_text = 'drift' WHERE robot_id ="
                          " (SELECT id FROM robot WHERE slug = :s)"), {"s": w.slug})
    spec = [a for a in ai.classify_audits(dsession)
            if a.robot_slug == w.slug and a.target_table == "specification"]
    assert {a.classification for a in spec} == {"UNRESOLVED"}
    assert all("no longer verifies" in a.reason for a in spec)


def test_retracted_claims_are_historical(dsession, tmp_path):
    w, made, _ = verified(dsession, tmp_path)
    claims.retract_claim(dsession, str(made["s-Standard"].id), retracted_by=WHO, reason="x")
    found = {a.claim_id: a.classification for a in ai.classify_audits(dsession)
             if a.robot_slug == w.slug}
    assert found[str(made["s-Standard"].id)] == "RETRACTED"
    assert sorted(found.values()).count("CURRENT") == 3


def test_a_robot_that_cannot_be_materialized_does_not_stop_the_report(dsession, tmp_path):
    w, _, _ = verified(dsession, tmp_path)
    w.page(b"<html>changed</html>", retrieved_at=datetime(2026, 9, 27, tzinfo=UTC))
    found = [a for a in ai.classify_audits(dsession) if a.robot_slug == w.slug]
    assert len(found) == 4 and {a.classification for a in found} == {"UNRESOLVED"}
    assert all("STALE" in a.reason for a in found)


def test_evidence_orphans_and_unmanaged_variant_specs_are_listed(dsession, tmp_path):
    w, _, _ = verified(dsession, tmp_path)
    ghost = uuid.uuid4()
    dsession.execute(text(
        "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type) "
        "VALUES ('ROBOT_VARIANT', :g, 'https://example.test/x', 'MANUFACTURER_SITE')"),
        {"g": ghost})
    dsession.execute(text("UPDATE specification SET managed_by = NULL WHERE robot_id ="
                          " (SELECT id FROM robot WHERE slug = :s)"), {"s": w.slug})
    report = ai.build_report(dsession)
    assert [o["subject_id"] for o in report.evidence_orphans
            if o["source_url"] == "https://example.test/x"] == [str(ghost)]
    mine = [s for s in report.unmanaged_variant_specs if s["robot"] == w.slug]
    assert sorted(s["variant"] for s in mine) == ["pro", "standard"]


def test_the_report_writes_nothing(dsession, tmp_path):
    w, _, path = verified(dsession, tmp_path)
    _import(dsession, w, path)

    def snapshot():
        return [dsession.scalar(select(func.count()).select_from(CatalogueWriteAudit)),
                *dsession.execute(text(
                    "SELECT (SELECT count(*) FROM specification), "
                    "(SELECT count(*) FROM robot_variant), "
                    "(SELECT count(*) FROM evidence_source)")).one()]
    before = snapshot()
    ai.build_report(dsession)
    assert snapshot() == before
