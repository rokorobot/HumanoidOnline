"""DATA-D1 admin integrity — the discovery state machine has ONE entrance.

An operational audit proved that SQLAdmin exposed a second, ungoverned path into
the discovery layer. With the framework defaults (create/edit/delete all enabled
and every column rendered in the form) an authenticated operator could:

  * forge `identity_status`, `status`, `trace_state` and `trace_verified_by`
    directly, reaching READY_FOR_PROMOTION without `resolve_identity()`,
    `record_trace()` or `advance()` ever running — after which `check_gates()`
    reported NO failures and the fabricated candidate promoted to canonical; and
  * silently DESTROY evidence: SQLAdmin renders `claims` / `images` as
    relationship fields, so an ordinary field edit that omits them dissociates
    the children (a candidate ingested with claims came back with none).

These tests are the regression. They drive a REAL authenticated admin client
against committed rows, so they fail if the permissions ever regress.

Scope note: this file proves the *boundary*. Governed admin actions (advance,
record trace, reject) are a later slice; promotion stays on the deliberate CLI.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin import (
    CandidateClaimAdmin,
    CandidateImageRefAdmin,
    DiscoveryCandidateAdmin,
    DiscoverySourceAdmin,
    PromotionAuditAdmin,
    mount_admin,
)
from app.config import get_settings
from app.db.session import engine
from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
)
from app.services.discovery.promotion import check_gates

ADMIN_ENV = {
    "ADMIN_USERNAME": "operator",
    "ADMIN_PASSWORD": "correct-horse-battery-staple",
    "ADMIN_SESSION_SECRET": "x" * 48,
}

CANDIDATE_VIEWS = ("discovery-candidate", "candidate-claim", "candidate-image-ref")


@pytest.fixture
def admin_client(monkeypatch):
    """A throwaway app with the admin configured and an authenticated session."""
    for key, value in ADMIN_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    client = TestClient(app, follow_redirects=False)
    resp = client.post(
        "/admin/login",
        data={
            "username": ADMIN_ENV["ADMIN_USERNAME"],
            "password": ADMIN_ENV["ADMIN_PASSWORD"],
        },
    )
    assert resp.status_code in (200, 302), "admin login failed; fixture is unusable"
    assert client.get("/admin/").status_code == 200, "session cookie not established"
    try:
        yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def committed_candidate(database_url):
    """A COMMITTED source + candidate + claim + image.

    The admin runs on its own connection, so a transaction-scoped row would be
    invisible to it. Teardown deletes the source, which cascades.
    """
    tag = uuid.uuid4().hex[:8]
    with Session(engine) as s:
        source = DiscoverySource(
            key=f"admin-integrity-{tag}",
            name="Admin Integrity Fixture",
            source_class="MANUFACTURER",
            homepage_url="https://fixture.test",
            tos_status="ALLOWED",
            robots_status="ALLOWED",
            eligibility_reviewed_at=datetime.now(UTC),
            eligibility_reviewed_by="auditor@test",
            is_enabled=True,
        )
        s.add(source)
        s.flush()
        candidate = DiscoveryCandidate(
            source_id=source.id,
            entity_type="ROBOT",
            candidate_name="Integrity Probe Bot",
            candidate_manufacturer="Fixture Robotics",
            external_ref=f"probe-{tag}",
            discovery_url="https://fixture.test/probe",
            candidate_data={"official_url": "https://fixture-robotics.test/probe"},
        )
        s.add(candidate)
        s.flush()
        s.add(
            CandidateClaim(
                candidate_id=candidate.id, field_key="height_cm", claimed_value="165",
                unit="cm", discovery_source_id=source.id,
            )
        )
        s.add(
            CandidateImageRef(
                candidate_id=candidate.id,
                image_url="https://fixture.test/img/probe.jpg",
                discovery_source_id=source.id, credited_to="Fixture Robotics",
            )
        )
        s.commit()
        ids = {"source": source.id, "candidate": candidate.id}
    try:
        yield ids
    finally:
        with Session(engine) as s:
            # Order matters since DATA-D1.LIVE Slice A: `candidate_claim`
            # .discovery_source_id is NOT NULL with ON DELETE RESTRICT, so a
            # source cannot be deleted while any claim still cites it. Delete the
            # CANDIDATE first — that cascades its claims and images — and only
            # then the source. Deleting the source first now fails, which is the
            # constraint doing its job: provenance is never silently stripped
            # from a claim that has already been made.
            candidate = s.get(DiscoveryCandidate, ids["candidate"])
            if candidate is not None:
                s.delete(candidate)
                s.commit()
            obj = s.get(DiscoverySource, ids["source"])
            if obj is not None:
                s.delete(obj)
                s.commit()


def _candidate_state(candidate_id) -> dict:
    with Session(engine) as s:
        c = s.get(DiscoveryCandidate, candidate_id)
        return {
            "identity_status": c.identity_status,
            "status": c.status,
            "trace_state": c.trace_state,
            "trace_verified_by": c.trace_verified_by,
            "trace_url": c.trace_url,
            "claims": [(cl.field_key, cl.claimed_value, cl.claim_status) for cl in c.claims],
            "images": [(i.image_url, i.media_status) for i in c.images],
        }


# --------------------------------------------------------------------------- #
# Declared permissions
# --------------------------------------------------------------------------- #
def test_research_views_are_read_only() -> None:
    """Candidates, claims and image refs are written ONLY by governed services."""
    for view in (DiscoveryCandidateAdmin, CandidateClaimAdmin, CandidateImageRefAdmin):
        assert view.can_create is False, view.__name__
        assert view.can_edit is False, view.__name__
        assert view.can_delete is False, view.__name__


def test_promotion_audit_stays_read_only() -> None:
    assert PromotionAuditAdmin.can_create is False
    assert PromotionAuditAdmin.can_edit is False
    assert PromotionAuditAdmin.can_delete is False


def test_source_registry_is_writable_but_undeletable() -> None:
    """Operators must register sources and record ToS/robots review; deleting one
    would cascade into its candidates and destroy research history."""
    assert DiscoverySourceAdmin.can_create is True
    assert DiscoverySourceAdmin.can_edit is True
    assert DiscoverySourceAdmin.can_delete is False


def test_source_form_exposes_only_registry_and_review_fields() -> None:
    exposed = {getattr(c, "key", str(c)) for c in DiscoverySourceAdmin.form_columns}
    assert exposed == {
        "key", "name", "source_class", "homepage_url",
        "tos_status", "robots_status",
        "eligibility_reviewed_at", "eligibility_reviewed_by",
        "is_enabled", "notes",
    }
    # Surrogate ids, system timestamps and the children relationship stay out.
    for forbidden in ("id", "created_at", "updated_at", "candidates"):
        assert forbidden not in exposed


# --------------------------------------------------------------------------- #
# Authenticated HTTP surface
# --------------------------------------------------------------------------- #
def test_research_create_forms_are_refused(admin_client) -> None:
    for view in CANDIDATE_VIEWS:
        resp = admin_client.get(f"/admin/{view}/create")
        assert resp.status_code == 403, f"{view} create form is reachable"


def test_research_rows_remain_listable(admin_client, committed_candidate) -> None:
    """Read-only must still mean READ: the operator keeps full visibility."""
    for view in CANDIDATE_VIEWS:
        assert admin_client.get(f"/admin/{view}/list").status_code == 200


def test_candidate_edit_and_delete_are_refused(admin_client, committed_candidate) -> None:
    cid = committed_candidate["candidate"]
    assert admin_client.get(f"/admin/discovery-candidate/edit/{cid}").status_code == 403
    assert admin_client.delete(
        f"/admin/discovery-candidate/delete?pks={cid}"
    ).status_code == 403


def test_forged_candidate_mutation_is_refused_and_changes_nothing(
    admin_client, committed_candidate
) -> None:
    """THE regression: the exact exploit shape the audit demonstrated."""
    cid = committed_candidate["candidate"]
    before = _candidate_state(cid)
    assert before["status"] == "DISCOVERED"
    assert before["identity_status"] == "UNRESOLVED"
    assert before["trace_state"] == "NOT_TRACED"

    stamp = "2026-07-28 12:00:00"
    resp = admin_client.post(
        f"/admin/discovery-candidate/edit/{cid}",
        data={
            "entity_type": "ROBOT",
            "candidate_name": "Integrity Probe Bot",
            "candidate_manufacturer": "Fixture Robotics",
            "external_ref": "forged",
            "identity_status": "NEW_ENTITY",
            "status": "READY_FOR_PROMOTION",
            "trace_state": "TRACE_CONFIRMED",
            "trace_source_type": "MANUFACTURER_SITE",
            "trace_url": "https://attacker.test/not-really-traced",
            "trace_verified_by": "forged@attacker.test",
            "discovered_at": stamp, "last_seen_at": stamp,
            "created_at": stamp, "updated_at": stamp,
            "save": "Save",
        },
    )
    assert resp.status_code == 403, "the forged edit was accepted"
    assert _candidate_state(cid) == before, "a refused edit still changed state"


def test_refused_mutation_does_not_detach_claims_or_images(
    admin_client, committed_candidate
) -> None:
    """The quieter half of the defect: an edit omitting the relationship fields
    used to dissociate (destroy) the candidate's claims and images."""
    cid = committed_candidate["candidate"]
    before = _candidate_state(cid)
    assert len(before["claims"]) == 1 and len(before["images"]) == 1

    admin_client.post(
        f"/admin/discovery-candidate/edit/{cid}",
        data={"entity_type": "ROBOT", "candidate_name": "x", "external_ref": "x",
              "save": "Save"},
    )
    after = _candidate_state(cid)
    assert after["claims"] == before["claims"], "claims were altered or destroyed"
    assert after["images"] == before["images"], "images were altered or destroyed"


def test_claim_verification_state_cannot_be_set_from_admin(
    admin_client, committed_candidate
) -> None:
    with Session(engine) as s:
        claim = s.execute(
            select(CandidateClaim).where(
                CandidateClaim.candidate_id == committed_candidate["candidate"]
            )
        ).scalar_one()
        claim_id, before_status = claim.id, claim.claim_status
    assert before_status == "NOT_VERIFIED"

    assert admin_client.get(f"/admin/candidate-claim/edit/{claim_id}").status_code == 403
    resp = admin_client.post(
        f"/admin/candidate-claim/edit/{claim_id}",
        data={"field_key": "height_cm", "claimed_value": "165",
              "claim_status": "VERIFIED", "save": "Save"},
    )
    assert resp.status_code == 403
    with Session(engine) as s:
        assert s.get(CandidateClaim, claim_id).claim_status == before_status


def test_candidate_image_cannot_be_created_or_deleted(
    admin_client, committed_candidate
) -> None:
    with Session(engine) as s:
        image = s.execute(
            select(CandidateImageRef).where(
                CandidateImageRef.candidate_id == committed_candidate["candidate"]
            )
        ).scalar_one()
        image_id = image.id
    assert admin_client.get(f"/admin/candidate-image-ref/edit/{image_id}").status_code == 403
    assert admin_client.delete(
        f"/admin/candidate-image-ref/delete?pks={image_id}"
    ).status_code == 403
    with Session(engine) as s:
        assert s.get(CandidateImageRef, image_id) is not None


def test_gates_still_report_the_genuine_failures_after_a_refused_forge(
    admin_client, committed_candidate
) -> None:
    """The point of the boundary: the candidate remains honestly unpromotable."""
    cid = committed_candidate["candidate"]
    admin_client.post(
        f"/admin/discovery-candidate/edit/{cid}",
        data={"identity_status": "NEW_ENTITY", "status": "READY_FOR_PROMOTION",
              "trace_state": "TRACE_CONFIRMED", "trace_verified_by": "forged@attacker.test",
              "save": "Save"},
    )
    with Session(engine) as s:
        failures = check_gates(s, s.get(DiscoveryCandidate, cid))
    assert any("P1" in f for f in failures), failures
    assert any("P2" in f for f in failures), failures
    assert any("READY_FOR_PROMOTION" in f for f in failures), failures


def test_source_delete_is_refused_but_registration_remains_available(
    admin_client, committed_candidate
) -> None:
    sid = committed_candidate["source"]
    assert admin_client.delete(f"/admin/discovery-source/delete?pks={sid}").status_code == 403
    with Session(engine) as s:
        assert s.get(DiscoverySource, sid) is not None
    # Registering and reviewing a source is still the operator's job.
    assert admin_client.get("/admin/discovery-source/create").status_code == 200
    assert admin_client.get(f"/admin/discovery-source/edit/{sid}").status_code == 200


def test_promotion_audit_endpoints_stay_refused(admin_client) -> None:
    assert admin_client.get("/admin/promotion-audit/create").status_code == 403


# --------------------------------------------------------------------------- #
# The database remains the authoritative eligibility backstop
# --------------------------------------------------------------------------- #
def test_enabled_source_without_affirmative_review_is_refused_by_the_database(
    database_url,
) -> None:
    """DATA-D1.9 does not depend on the admin form: the CHECK constraint refuses
    to STORE an enabled source that was never affirmatively reviewed."""
    with Session(engine) as s:
        s.add(
            DiscoverySource(
                key=f"unreviewed-{uuid.uuid4().hex[:8]}",
                name="Unreviewed", source_class="COMPETITOR_DIRECTORY",
                tos_status="UNKNOWN", robots_status="UNKNOWN",
                eligibility_reviewed_at=None, eligibility_reviewed_by=None,
                is_enabled=True,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
