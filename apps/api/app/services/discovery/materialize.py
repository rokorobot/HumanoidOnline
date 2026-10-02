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
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.claim_proposal import AcceptedClaim, CatalogueWriteAudit, DiscoveryClaimProposal
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery import proposal_review as pr
from app.services.discovery.claims import _active_claim, active_claims
from app.services.discovery.field_policy import CLAIM_POLICIES

CATALOGUE_ROBOTS = Path(__file__).resolve().parents[5] / "db" / "catalogue" / "robots"
_SOURCE_KIND = {"MANUFACTURER": "MANUFACTURER"}
_EVIDENCE_TYPE = {"MANUFACTURER": "MANUFACTURER_SITE"}
#: Deterministic, owner-decided wording of what these two offers ARE (G2-4). It states the
#: source's own semantics and the owner's mapping; it asserts nothing the source did not say.
PRICE_NOTE = ("Estimate published by the manufacturer itself on its official product page "
              "(stated there as an 'Estimated price'). Not an MSRP or public selling price, "
              "and not a HumanoidOnline estimate.")
WAITLIST_NOTE = ("WAITLIST: the manufacturer states that a reservation secures a place in the "
                 "delivery queue; this is not a purchase order. No date is stated: 'Expected in "
                 "2026' is year-level seller wording, not a date.")


def _evidence(claim: AcceptedClaim, source: DiscoverySource) -> dict:
    """The catalogue evidence block, built only from the accepted claim's own chain."""
    if source.source_class not in _EVIDENCE_TYPE:
        raise DiscoveryError(f"source {source.key} is not a manufacturer source")
    return {
        "source_url": claim.source_url, "source_type": _EVIDENCE_TYPE[source.source_class],
        "source_title": f"{source.name} \u2014 official product page",
        "excerpt": claim.evidence_excerpt, "published_at": None,
        "observed_at": claim.observed_at.date().isoformat(), "verified_at": None,
        "confidence": "HIGH",
        "note": (f"Governed extraction (DR-A5): proposal {claim.proposal_digest[:12]} at "
                 f"{claim.evidence_locator}, sighted on page content hash "
                 f"{claim.observation_content_hash[:12]}; accepted claim "
                 f"{claim.claim_digest[:12]}; owner ACCEPT decision. Retrieved by the "
                 "governed observation; not human-verified on the page itself.")}


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
    offer_claims = [c for c in claims if c.target_kind in ("pricing_offer", "availability_offer")]
    if offer_claims:
        osources = {x.id: x for x in session.scalars(select(DiscoverySource).where(
            DiscoverySource.id.in_({c.source_id for c in offer_claims})))}
        prices = {}
        for c in (c for c in offer_claims if c.target_kind == "pricing_offer"):
            o = json.loads(c.accepted_value)
            prices[c.variant_slug] = {
                "variant_slug": c.variant_slug, "transaction_type": o["transaction_type"],
                "price_type": o["price_type"], "currency": o["currency"],
                "price": float(Decimal(o["price"])), "billing_period": o["billing_period"],
                "note": PRICE_NOTE,
                "price_basis": f"{o['price_basis']} (as stated by the manufacturer)",
                "edition_confirmed": o["edition_confirmed"],
                "evidence": [_evidence(c, osources[c.source_id])]}
        if prices:
            doc["pricing_offers"] = _merge_offers(
                doc.get("pricing_offers", []), prices, "MANUFACTURER_ESTIMATE", "price_type")
        avail = {}
        terms = None
        for c in (c for c in offer_claims if c.target_kind == "availability_offer"):
            if terms is None:
                terms = _reservation_terms(session, robot_slug)
            o = json.loads(c.accepted_value)
            avail[c.variant_slug] = {
                "variant_slug": c.variant_slug, "transaction_type": o["transaction_type"],
                "availability_status": o["availability_status"],
                "delivery_estimate_label": o["delivery_estimate_label"],
                "seller_wording": o["seller_wording"], "note": WAITLIST_NOTE,
                "evidence": [_evidence(c, osources[c.source_id]),
                             _evidence(terms, osources.get(terms.source_id)
                                       or session.get(DiscoverySource, terms.source_id))]}
        if avail:
            doc["availability_offers"] = _merge_offers(
                doc.get("availability_offers", []), avail, "WAITLIST", "availability_status")
    return MaterializationPlan(robot_slug, path, before, _dump(doc), claims)


def _reservation_terms(session: Session, robot_slug: str) -> AcceptedClaim:
    """The accepted RESERVATION_TERMS claim that the WAITLIST status rests on (it must exist
    and its proposal must still be current)."""
    terms = _active_claim(session, robot_slug, target_kind="NO_CATALOGUE_HOME",
                          target_key="reservation_terms")
    if terms is None:
        raise DiscoveryError("WAITLIST needs the accepted RESERVATION_TERMS claim (its basis)")
    [state] = pr.derive_states(session, [session.get(DiscoveryClaimProposal, terms.proposal_id)])
    if not state.acceptable:
        raise DiscoveryError("the RESERVATION_TERMS proposal is no longer current; "
                             "materialization refuses")
    return terms


def _merge_offers(existing: list, new: dict, kind_value: str, kind_field: str) -> list:
    """Replace this slice's own offers (same variant, PURCHASE, no provider/region, same
    status/type) in place, keep everything else, append new ones ordered by variant slug."""
    merged, placed = [], set()
    for entry in existing:
        slug = entry.get("variant_slug")
        if (slug in new and entry.get(kind_field) == kind_value
                and entry.get("transaction_type") == "PURCHASE"
                and not entry.get("provider_slug") and not entry.get("region_code")):
            merged.append(new[slug])
            placed.add(slug)
        else:
            merged.append(entry)
    merged += [new[slug] for slug in sorted(new) if slug not in placed]
    return merged


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


def logical_target(claim: AcceptedClaim) -> str:
    """The durable identity of what a claim materializes, derived from the claim itself:
    `robot_variant:<robot>:<variant>` or `specification:<robot>:<variant>:<target_key>`.
    Never a database row id (the importer recreates those)."""
    if claim.target_kind == "robot_variant":
        return f"robot_variant:{claim.robot_slug}:{claim.variant_slug}"
    if claim.target_kind in ("specification", "pricing_offer", "availability_offer"):
        return (f"{claim.target_kind}:{claim.robot_slug}:{claim.variant_slug}:"
                f"{claim.target_key}")
    raise DiscoveryError(f"{claim.target_kind!r} has no catalogue target")


def _offer_evidence(session: Session, subject: str, subject_id, source_url: str) -> list:
    """The offer's evidence excerpts (sorted), requiring a manufacturer row with our URL."""
    if subject_id is None:
        return []
    rows = session.execute(text(
        "SELECT source_url, source_type, excerpt FROM evidence_source "
        "WHERE subject_type = :t AND subject_id = :i ORDER BY source_url, excerpt"),
        {"t": subject, "i": subject_id}).all()
    ours = [r for r in rows if r.source_url == source_url
            and r.source_type in ("MANUFACTURER_SITE", "MANUFACTURER_STORE") and r.excerpt]
    return [[r.source_url, r.source_type, r.excerpt] for r in rows] if ours else []


def verify_applied(session: Session, robot_slug: str, *, change_ref: str, applied_by: str,
                   importer_run_ref: str | None = None) -> list[CatalogueWriteAudit]:
    """Compare the imported rows with the active claims and append one audit row per
    claim. Refuses (writing nothing) on any mismatch. Idempotent per (claim, content hash,
    change_ref): a later importer run that recreates an identical row under a new UUID
    appends nothing, and old audit rows are never touched. `target_row_id` records the
    physical row observed at verification time (forensic only, not an identity)."""
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
        elif c.target_kind == "pricing_offer":
            o = json.loads(c.accepted_value)
            r = session.execute(text(
                "SELECT p.id, p.price, p.currency, p.billing_period, p.price_type, "
                "p.transaction_type, p.edition_confirmed, p.price_basis, p.provider_id, "
                "p.region_id, p.is_current FROM pricing_offer p JOIN robot_variant v "
                "ON v.id = p.variant_id WHERE p.robot_id = :r AND v.slug = :v "
                "AND p.price_type = 'MANUFACTURER_ESTIMATE' AND p.transaction_type = 'PURCHASE'"),
                {"r": robot_id, "v": c.variant_slug}).one_or_none()
            ev = _offer_evidence(session, "PRICING_OFFER", r.id if r else None, c.source_url)
            if (r is None or r.price != Decimal(o["price"]) or r.currency != o["currency"]
                    or r.billing_period != o["billing_period"] or r.edition_confirmed is not True
                    or r.provider_id is not None or r.region_id is not None
                    or not r.is_current or not ev
                    or not (r.price_basis or "").startswith(o["price_basis"])):
                raise DiscoveryError(
                    f"pricing offer for variant {c.variant_slug!r} is not in the database as "
                    "accepted (or lacks its manufacturer evidence); import the merged "
                    "catalogue first")
            payload = {"robot_slug": robot_slug, "table": "pricing_offer",
                       "variant_slug": c.variant_slug, "price_type": r.price_type,
                       "transaction_type": r.transaction_type, "price": str(r.price),
                       "currency": r.currency, "billing_period": r.billing_period,
                       "price_basis": r.price_basis, "evidence": ev}
            rows.append((c, "pricing_offer", r.id, _hash(payload)))
        elif c.target_kind == "availability_offer":
            o = json.loads(c.accepted_value)
            r = session.execute(text(
                "SELECT a.id, a.availability_status, a.available_from, a.region_id, "
                "a.provider_id, a.delivery_estimate_label, a.seller_wording, a.is_current, "
                "a.transaction_type FROM availability_offer a JOIN robot_variant v "
                "ON v.id = a.variant_id WHERE a.robot_id = :r AND v.slug = :v "
                "AND a.transaction_type = 'PURCHASE'"),
                {"r": robot_id, "v": c.variant_slug}).one_or_none()
            ev = _offer_evidence(session, "AVAILABILITY_OFFER", r.id if r else None, c.source_url)
            if (r is None or r.availability_status != o["availability_status"]
                    or r.available_from is not None or r.provider_id is not None
                    or r.region_id is not None or not r.is_current
                    or r.delivery_estimate_label != o["delivery_estimate_label"]
                    or r.seller_wording != o["seller_wording"] or not ev):
                raise DiscoveryError(
                    f"availability offer for variant {c.variant_slug!r} is not in the database "
                    "as accepted (or lacks its manufacturer evidence); import the merged "
                    "catalogue first")
            payload = {"robot_slug": robot_slug, "table": "availability_offer",
                       "variant_slug": c.variant_slug, "transaction_type": r.transaction_type,
                       "availability_status": r.availability_status,
                       "available_from": None,
                       "delivery_estimate_label": r.delivery_estimate_label,
                       "seller_wording": r.seller_wording, "evidence": ev}
            rows.append((c, "availability_offer", r.id, _hash(payload)))
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
        # The materialization identity is (claim, logical target, content hash, change_ref).
        # The physical row UUID is deliberately NOT part of it: the importer recreates
        # variant and importer-owned specification rows (new UUIDs) on every run, so a
        # row id is forensic metadata, never a durable identity. The logical target is
        # derived from the claim (`logical_target`), the content from `after_hash`.
        dup = session.scalar(select(CatalogueWriteAudit).where(
            CatalogueWriteAudit.claim_id == c.id, CatalogueWriteAudit.after_hash == after,
            CatalogueWriteAudit.change_ref == change_ref.strip()))
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
