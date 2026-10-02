"""G2-3 materialization — the M2 boundary of DR-A5 (section 11.2).

`plan_materialization` renders the ACTIVE accepted claims of one robot, through the
registered claim policies, into a deterministic patch of `db/catalogue/robots/<slug>.json`.
It touches only registered keys (`variants[]` entries for registered variant claims and
`extended_specs[]` entries for the registered variant-scoped specification), preserves
everything else byte for byte, and refuses anything unregistered, stale, superseded,
conflicting or missing its prerequisite. Re-running it once the patch is applied yields
no diff. It never writes the database: the change travels through a normal PR and the
importer loads it. `verify_applied` later compares the imported rows with the claims and
appends `catalogue_write_audit` rows; only that command writes, and only to the audit
table.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.claim_proposal import AcceptedClaim, CatalogueWriteAudit, DiscoveryClaimProposal
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery import proposal_review as pr
from app.services.discovery.claims import active_claims
from app.services.discovery.field_policy import CLAIM_POLICIES

CATALOGUE_ROBOTS = Path(__file__).resolve().parents[5] / "db" / "catalogue" / "robots"
_SOURCE_KIND = {"MANUFACTURER": "MANUFACTURER"}


@dataclass
class MaterializationPlan:
    robot_slug: str
    path: Path
    before: str
    after: str
    claims: list[AcceptedClaim] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def diff(self) -> str:
        return "".join(difflib.unified_diff(
            self.before.splitlines(keepends=True), self.after.splitlines(keepends=True),
            f"a/{self.path.name}", f"b/{self.path.name}"))


def _dump(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _materializable(session: Session, robot_slug: str) -> list[AcceptedClaim]:
    claims = [c for c in active_claims(session, robot_slug)
              if c.target_kind != "NO_CATALOGUE_HOME"]
    for c in claims:
        policy = CLAIM_POLICIES.get(c.policy_key)
        if policy is None or (policy.target_kind, policy.target_key) != (
                c.target_kind, c.target_key):
            raise DiscoveryError(
                f"claim {c.id} targets {c.target_kind}[{c.target_key}] under policy "
                f"{c.policy_key!r}, which is not registered; unregistered claims are refused")
        proposal = session.get(DiscoveryClaimProposal, c.proposal_id)
        [state] = pr.derive_states(session, [proposal])
        if state.superseded:
            raise DiscoveryError(f"claim {c.id}: its proposal is SUPERSEDED; materialization "
                                 "refuses until a current proposal is accepted")
        if state.stale:
            raise DiscoveryError(f"claim {c.id}: its proposal is STALE ("
                                 + "; ".join(state.stale_reasons) + "); materialization refuses")
    seen: dict[tuple, AcceptedClaim] = {}
    for c in claims:
        key = (c.target_kind, c.target_key, c.variant_slug)
        if key in seen and seen[key].accepted_value != c.accepted_value:
            raise DiscoveryError(
                f"two active claims disagree on {key}: retract one before materializing")
        seen[key] = c
    variants = {c.variant_slug for c in seen.values() if c.target_kind == "robot_variant"}
    for c in seen.values():
        if CLAIM_POLICIES[c.policy_key].requires_variant and c.variant_slug not in variants:
            raise DiscoveryError(f"claim {c.id}: its variant {c.variant_slug!r} has no active "
                                 "VARIANT claim (prerequisite)")
    return list(seen.values())


def plan_materialization(session: Session, robot_slug: str,
                         catalogue_dir: Path = CATALOGUE_ROBOTS) -> MaterializationPlan:
    path = catalogue_dir / f"{robot_slug}.json"
    if not path.is_file():
        raise DiscoveryError(f"{robot_slug!r} is not catalogue-backed: {path.name} does not "
                             "exist (a stub must be adopted first, DR-A5 section 11.2)")
    before = path.read_text(encoding="utf-8")
    doc = json.loads(before)
    if doc.get("slug") != robot_slug:
        raise DiscoveryError(f"{path.name} does not describe {robot_slug!r}")
    claims = _materializable(session, robot_slug)

    variants = {c.variant_slug: c for c in claims if c.target_kind == "robot_variant"}
    specs = [c for c in claims if c.target_kind == "specification"]

    if variants:
        merged, placed = [], set()
        for entry in doc.get("variants", []):     # an existing entry keeps its place
            if entry.get("slug") in variants:
                entry = {**entry, "name": variants[entry["slug"]].accepted_value}
                placed.add(entry["slug"])
            merged.append(entry)
        merged += [{"slug": slug, "name": variants[slug].accepted_value}
                   for slug in sorted(variants) if slug not in placed]
        doc["variants"] = merged
    if specs:
        sources = {s.id: s for s in session.scalars(select(DiscoverySource).where(
            DiscoverySource.id.in_({c.source_id for c in specs})))}
        entries = {}
        for c in specs:
            src = sources[c.source_id]
            if src.source_class not in _SOURCE_KIND:
                raise DiscoveryError(f"source {src.key} is not a manufacturer source; "
                                     "a MANUFACTURER attribution cannot be claimed")
            entries[(c.variant_slug, c.target_key)] = {
                "key": c.target_key, "variant_slug": c.variant_slug,
                "value": c.accepted_value, "source_label": src.name,
                "source_url": c.source_url, "source_kind": _SOURCE_KIND[src.source_class],
                "edition_scope": c.edition_scope,
                "observed_at": c.observed_at.date().isoformat()}
        existing = doc.get("extended_specs", [])
        merged = []
        placed = set()
        for entry in existing:
            k = (entry.get("variant_slug"), entry.get("key"))
            if k in entries:
                merged.append(entries[k])
                placed.add(k)
            else:
                merged.append(entry)
        merged += [entries[k] for k in sorted(entries, key=lambda k: (k[0] or "", k[1]))
                   if k not in placed]
        doc["extended_specs"] = merged
    return MaterializationPlan(robot_slug, path, before, _dump(doc), claims)


def apply_plan(plan: MaterializationPlan) -> bool:
    """Write the patch to the catalogue file (the only file written). True if it changed."""
    if not plan.changed:
        return False
    plan.path.write_bytes(plan.after.encode("utf-8"))
    return True


# ----------------------------------------------------------------- verification --


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def verify_applied(session: Session, robot_slug: str, *, change_ref: str, applied_by: str,
                   importer_run_ref: str | None = None) -> list[CatalogueWriteAudit]:
    """Compare the imported rows with the active claims and append one audit row per
    claim. Refuses (writing nothing) on any mismatch. Idempotent per (claim, row, hash)."""
    if not change_ref.strip() or not applied_by.strip():
        raise DiscoveryError("verification needs a change reference and a named human")
    claims = _materializable(session, robot_slug)
    robot_id = session.execute(text("SELECT id FROM robot WHERE slug = :s"),
                               {"s": robot_slug}).scalar()
    if robot_id is None:
        raise DiscoveryError(f"robot {robot_slug!r} is not in the database")
    rows = []
    for c in claims:
        if c.target_kind == "robot_variant":
            r = session.execute(text(
                "SELECT id, slug, name FROM robot_variant WHERE robot_id = :r AND slug = :v"),
                {"r": robot_id, "v": c.variant_slug}).one_or_none()
            if r is None or r.name != c.accepted_value:
                raise DiscoveryError(f"variant {c.variant_slug!r} is not in the database as "
                                     "accepted; import the merged catalogue first")
            payload = {"robot_slug": robot_slug, "table": "robot_variant", "slug": r.slug,
                       "name": r.name}
            rows.append((c, "robot_variant", r.id, _hash(payload)))
        else:
            r = session.execute(text(
                "SELECT s.id, s.value_text, s.value_number, s.value_bool, s.edition_scope, "
                "s.source_url, s.source_label, s.source_kind, s.observed_at, d.key "
                "FROM specification s JOIN spec_definition d ON d.id = s.definition_id "
                "JOIN robot_variant v ON v.id = s.variant_id "
                "WHERE s.robot_id = :r AND v.slug = :v AND d.key = :k"),
                {"r": robot_id, "v": c.variant_slug, "k": c.target_key}).one_or_none()
            if (r is None or r.value_text != c.accepted_value or r.value_number is not None
                    or r.value_bool is not None or r.edition_scope != c.edition_scope
                    or r.source_url != c.source_url
                    or (r.observed_at and r.observed_at.isoformat()
                        != c.observed_at.date().isoformat())):
                raise DiscoveryError(
                    f"specification {c.target_key!r} for variant {c.variant_slug!r} is not in "
                    "the database as accepted; import the merged catalogue first")
            payload = {"robot_slug": robot_slug, "table": "specification",
                       "variant_slug": c.variant_slug, "key": r.key, "value_text": r.value_text,
                       "edition_scope": r.edition_scope, "source_url": r.source_url,
                       "source_label": r.source_label, "source_kind": r.source_kind,
                       "observed_at": r.observed_at.isoformat() if r.observed_at else None}
            rows.append((c, "specification", r.id, _hash(payload)))
    written = []
    for c, table, row_id, after in rows:
        dup = session.scalar(select(CatalogueWriteAudit).where(
            CatalogueWriteAudit.claim_id == c.id, CatalogueWriteAudit.target_row_id == row_id,
            CatalogueWriteAudit.after_hash == after, CatalogueWriteAudit.change_ref == change_ref))
        if dup is not None:
            continue
        audit = CatalogueWriteAudit(
            claim_id=c.id, robot_slug=robot_slug, method="IMPORTER_M2",
            change_ref=change_ref.strip(), importer_run_ref=importer_run_ref,
            target_table=table, target_row_id=row_id, before_hash=None, after_hash=after,
            applied_by=applied_by.strip())
        session.add(audit)
        written.append(audit)
    session.flush()
    return written
