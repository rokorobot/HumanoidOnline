"""Importer Hardening Phase 0 (docs/IMPORTER_HARDENING_PLAN_2026-10-19.md): a read-only
integrity report over catalogue_write_audit, evidence_source and variant-scoped rows.

It writes nothing. The CLI runs it in a READ ONLY transaction and rolls back.

Audit rows are classified by whether their `after_hash` is reproducible from the rows in the
database now, using the materializer's own verification (`materialize._verify_claim`, the same
payloads and `_hash`). The recomputation looks the row up by the claim's logical target and
yields at most one row, so a hash match is a unique, exact match:

  CURRENT     target_row_id is the current row and the recomputed hash equals after_hash.
  RELINKABLE  the recomputed hash equals after_hash but the current row has another id (the
              importer recreated an identical row). Candidate for an append-only relink.
  SUPERSEDED  the hash differs, and another audit row of the same claim holds the current hash
              (a later verification recorded the change). Historical; not a repair target.
  RETRACTED   the claim has been retracted. Historical; nothing to recompute.
  UNRESOLVED  anything else: the hash differs and no audit holds the current hash, the claim no
              longer verifies, or the robot's claims cannot be materialized. Human review.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import Session

from app.models.claim_proposal import CatalogueWriteAudit, ClaimRetraction
from app.services.discovery import DiscoveryError, materialize

CLASSES = ("CURRENT", "RELINKABLE", "SUPERSEDED", "RETRACTED", "UNRESOLVED")

# evidence_source.subject_type -> the table its subject_id points at.
# COMMERCIAL_STATUS evidence is keyed by robot.id (materialize._verify_claim).
EVIDENCE_SUBJECT_TABLE = {
    "MANUFACTURER": "manufacturer",
    "ROBOT": "robot",
    "ROBOT_VARIANT": "robot_variant",
    "SPECIFICATION": "specification",
    "CAPABILITY": "capability",
    "COMMERCIAL_STATUS": "robot",
    "PRICING_OFFER": "pricing_offer",
    "AVAILABILITY_OFFER": "availability_offer",
    "DEPLOYMENT": "deployment",
    "PROVIDER": "provider",
}
AUDIT_TABLES = ("robot_variant", "specification", "pricing_offer", "availability_offer", "robot")


@dataclass(frozen=True)
class AuditFinding:
    audit_seq: int
    robot_slug: str
    claim_id: str
    target_table: str
    target_row_id: str
    change_ref: str
    target_exists: bool
    classification: str
    current_row_id: str | None = None
    reason: str = ""


@dataclass
class IntegrityReport:
    audits: list[AuditFinding] = field(default_factory=list)
    evidence_orphans: list[dict] = field(default_factory=list)
    unmanaged_variant_specs: list[dict] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(CLASSES, 0)
        for a in self.audits:
            out[a.classification] += 1
        return out

    @property
    def dangling(self) -> list[AuditFinding]:
        return [a for a in self.audits if not a.target_exists]


def _exists(session: Session, table: str, row_id) -> bool:
    assert table in AUDIT_TABLES or table in EVIDENCE_SUBJECT_TABLE.values(), table
    return session.execute(text(f"SELECT 1 FROM {table} WHERE id = :i"),
                           {"i": row_id}).first() is not None


def _recompute(session: Session, robot_slug: str) -> tuple[dict, str | None]:
    """claim_id -> (table, row_id, after_hash) or an error string, for the robot's
    materializable claims; or ({}, reason) when the robot cannot be materialized at all."""
    try:
        claims = materialize._materializable(session, robot_slug)
    except DiscoveryError as exc:
        return {}, f"robot not materializable: {exc}"
    robot_id = session.execute(text("SELECT id FROM robot WHERE slug = :s"),
                               {"s": robot_slug}).scalar()
    if robot_id is None:
        return {}, f"robot {robot_slug!r} is not in the database"
    out: dict = {}
    for c in claims:
        try:
            _, table, row_id, after = materialize._verify_claim(session, c, robot_id, robot_slug)
            out[c.id] = (table, row_id, after)
        except DiscoveryError as exc:
            out[c.id] = f"claim no longer verifies: {exc}"
        except MultipleResultsFound:
            out[c.id] = "ambiguous: more than one current row matches the claim's logical target"
    return out, None


def classify_audits(session: Session) -> list[AuditFinding]:
    audits = list(session.scalars(select(CatalogueWriteAudit)
                                  .order_by(CatalogueWriteAudit.audit_seq)))
    retracted = set(session.scalars(select(ClaimRetraction.claim_id)))
    hashes_by_claim: dict = defaultdict(set)
    for a in audits:
        hashes_by_claim[a.claim_id].add(a.after_hash)
    by_robot: dict[str, list[CatalogueWriteAudit]] = defaultdict(list)
    for a in audits:
        by_robot[a.robot_slug].append(a)
    findings = []
    for slug in sorted(by_robot):
        current, robot_error = _recompute(session, slug)
        for a in by_robot[slug]:
            base = dict(audit_seq=a.audit_seq, robot_slug=slug, claim_id=str(a.claim_id),
                        target_table=a.target_table, target_row_id=str(a.target_row_id),
                        change_ref=a.change_ref,
                        target_exists=_exists(session, a.target_table, a.target_row_id))
            if a.claim_id in retracted:
                findings.append(AuditFinding(**base, classification="RETRACTED"))
                continue
            if robot_error:
                findings.append(AuditFinding(**base, classification="UNRESOLVED",
                                             reason=robot_error))
                continue
            now = current.get(a.claim_id)
            if now is None:
                findings.append(AuditFinding(
                    **base, classification="UNRESOLVED",
                    reason="claim is active but not materializable (no catalogue target)"))
                continue
            if isinstance(now, str):
                findings.append(AuditFinding(**base, classification="UNRESOLVED", reason=now))
                continue
            table, row_id, after = now
            if table != a.target_table:
                findings.append(AuditFinding(
                    **base, classification="UNRESOLVED", current_row_id=str(row_id),
                    reason=f"claim now targets {table}, audit recorded {a.target_table}"))
            elif after == a.after_hash:
                cls = "CURRENT" if row_id == a.target_row_id else "RELINKABLE"
                findings.append(AuditFinding(**base, classification=cls,
                                             current_row_id=str(row_id)))
            elif after in hashes_by_claim[a.claim_id]:
                findings.append(AuditFinding(
                    **base, classification="SUPERSEDED", current_row_id=str(row_id),
                    reason="a later audit of this claim records the current content"))
            else:
                findings.append(AuditFinding(
                    **base, classification="UNRESOLVED", current_row_id=str(row_id),
                    reason="content changed since verification; no audit records the "
                           "current content"))
    return findings


def evidence_orphans(session: Session) -> list[dict]:
    """evidence_source rows whose subject row does not exist."""
    out = []
    for subject, table in EVIDENCE_SUBJECT_TABLE.items():
        rows = session.execute(text(
            f"SELECT e.id, e.subject_id, e.source_url, e.managed_by FROM evidence_source e "
            f"WHERE e.subject_type = CAST(:s AS evidence_subject) AND NOT EXISTS "
            f"(SELECT 1 FROM {table} t WHERE t.id = e.subject_id) ORDER BY e.id"),
            {"s": subject}).all()
        out += [{"subject_type": subject, "evidence_id": str(r.id),
                 "subject_id": str(r.subject_id), "source_url": r.source_url,
                 "managed_by": r.managed_by} for r in rows]
    return out


def unmanaged_variant_specs(session: Session) -> list[dict]:
    """Variant-scoped specification rows the importer does not own. Deleting their variant
    (the importer recreates variants) cascades them away, so each is a data-loss risk."""
    rows = session.execute(text(
        "SELECT s.id, r.slug AS robot, v.slug AS variant, d.key, s.managed_by "
        "FROM specification s JOIN robot r ON r.id = s.robot_id "
        "JOIN robot_variant v ON v.id = s.variant_id "
        "JOIN spec_definition d ON d.id = s.definition_id "
        "WHERE s.managed_by IS DISTINCT FROM 'CATALOGUE_IMPORT' "
        "ORDER BY r.slug, v.slug, d.key")).all()
    return [{"spec_id": str(r.id), "robot": r.robot, "variant": r.variant, "key": r.key,
             "managed_by": r.managed_by} for r in rows]


def build_report(session: Session) -> IntegrityReport:
    """Read-only. The caller owns the transaction (the CLI makes it READ ONLY)."""
    return IntegrityReport(audits=classify_audits(session),
                           evidence_orphans=evidence_orphans(session),
                           unmanaged_variant_specs=unmanaged_variant_specs(session))

