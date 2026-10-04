"""G4-3 readiness (DR-G4 sections 7-8): an INTEGRITY check and a separate COVERAGE audit.

    Incomplete is publishable. Misleading is not.

* `integrity_check` returns BLOCK findings: only conditions that would make the public record
  materially
  false, self-contradictory or unverifiable. It is the ONLY thing that may fail the integrity gate
  or
  stop an `is_published` false -> true transition.
* `coverage_audit` returns non-blocking findings and the fact accounting. It NEVER blocks: it has no
  failing outcome at all. Its findings feed the enrichment queue.

Both operate on a plain `RobotRecord` (the canonical facts of one robot as stored) so they are pure
and
independent of any database, ORM or web framework (stdlib + the G4 resolver only). The same
functions are
used by the importer's publication transition, the CI gate, the audit CLI and the tests.

Scope of the fabrication detector (owner ruling 2026-10-03): it inspects SYSTEM TRANSFORMATIONS and
governed output paths (projection, scoped resolution, materializer/importer output, read model,
variant
flattening, year-level statements turned into exact dates, price-type changes, NULL -> false/0,
historical -> current). It does NOT try to re-justify every legacy hand-entered value: those are
coverage
review findings, never integrity failures. A NEW or CHANGED unexplained `false` is an integrity
failure.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services import fact_resolution as fr

BLOCK = "BLOCK"
WARN = "WARN"
INFO = "INFO"

INTEGRITY = "INTEGRITY"
COVERAGE = "COVERAGE"

# ------------------------------------------------------------------------------------------------
# Plain input records
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecRow:
    variant_slug: str | None
    key: str
    label: str | None
    value_text: str | None
    value_number: float | None = None
    value_bool: bool | None = None


@dataclass(frozen=True)
class PricingRow:
    variant_slug: str | None
    price_type: str | None
    price: float | None
    has_evidence: bool


@dataclass(frozen=True)
class AvailabilityRow:
    variant_slug: str | None
    status: str | None
    available_from: str | None
    delivery_estimate_label: str | None
    seller_wording: str | None
    has_evidence: bool


@dataclass(frozen=True)
class ImageRow:
    image_url: str | None
    source_url: str | None
    source_name: str | None
    identity_status: str | None
    rights_status: str | None
    usage_basis: str | None
    attribution: str | None
    is_representative: bool = False
    representative_note: str | None = None


@dataclass(frozen=True)
class ClaimRow:
    """A CURRENT (not retracted) accepted claim."""

    claim_id: str
    target_kind: str
    target_key: str
    variant_slug: str | None
    accepted_value: str | None


@dataclass
class RobotRecord:
    slug: str
    name: str | None
    manufacturer_slug: str | None
    is_published: bool
    summary: str | None = None
    commercial_status: str = "UNKNOWN"
    official_url: str | None = None
    core: Mapping[str, Any] = field(default_factory=dict)  # the robot columns
    spec_caveats: Sequence[Mapping[str, Any]] = ()
    variants: Sequence[tuple[str, str]] = ()
    specs: Sequence[SpecRow] = ()
    status_evidence: int = 0
    pricing: Sequence[PricingRow] = ()
    availability: Sequence[AvailabilityRow] = ()
    deployments: Sequence[bool] = ()  # has_evidence per deployment
    images: Sequence[ImageRow] = ()
    claims: Sequence[ClaimRow] = ()
    open_identity: Sequence[str] = ()  # CURRENT unresolved identity items
    not_yet_reviewed: int = 0  # CURRENT proposals with no decision
    source_count: int = 0  # authoritative-source indicators


@dataclass(frozen=True)
class Finding:
    concept: str  # INTEGRITY | COVERAGE
    severity: str  # BLOCK | WARN | INFO
    code: str
    message: str
    subject: str | None = None


# ------------------------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
YEAR_LEVEL_RE = re.compile(
    r"^\s*(expected|planned|available|launch|delivery)[^0-9]{0,40}"
    r"((19|20)\d\d)\s*\.?\s*$",
    re.I,
)
PLACEHOLDER_RE = re.compile(r"\b(todo|tbd|lorem|ipsum|placeholder|n/?a)\b|^\W*$", re.I)
MIN_SUMMARY_CHARS = 30

#: Core boolean columns whose `false` is a negative assertion (a missing basis must never create
#: one).
BOOLEAN_FIELDS = (
    "has_manipulation",
    "has_teleoperation",
    "has_vision",
    "has_language_ui",
    "has_sdk",
    "has_api",
    "ros_support",
    "developer_edition",
    "simulation_support",
)
#: Numeric columns where `0` is physically implausible, so a zero is a NULL -> 0 suspect.
IMPLAUSIBLE_ZERO_FIELDS = (
    "height_cm",
    "weight_kg",
    "arm_span_cm",
    "reach_cm",
    "walk_speed_ms",
    "runtime_minutes",
    "battery_wh",
    "degrees_of_freedom",
)
# A NEGATIVE (`false`) is a factual assertion, established ONLY by the governed provenance chain
# (owner ruling 2026-10-03): source statement -> proposal -> ACCEPT -> accepted claim -> a
# provenance-bearing product- or variant-scoped `specification` carrying the source's own wording ->
# an owner-ratified negative projection -> resolved `false`. Never by writing a core
# column and never by `spec_caveats`, which is explanatory metadata only (why a field is UNKNOWN).

#: Fields counted for the (informational) coverage band: what a buyer typically needs first.
BUYER_FIELDS = (
    "height_cm",
    "weight_kg",
    "payload_kg",
    "runtime_minutes",
    "battery_wh",
    "mobility",
    "degrees_of_freedom",
    "autonomy",
)

#: Tokens ratified as DETAIL_ONLY in DR-G4 4.1 (no canonical property yet), with their recorded
#: reason.
DETAIL_ONLY_TOKENS: dict[tuple[str, str], str] = {
    (
        "dexterous_hand_option",
        "Not included",
    ): "absence of an option is not absence of a capability (DR-G4 4.1)",
    ("common_interfaces", "Wi-Fi 6"): "connectivity: no canonical property yet",
    ("common_interfaces", "Ethernet"): "connectivity: no canonical property yet",
    ("common_interfaces", "NEURA Sync"): "manufacturer software: no canonical property yet",
    ("additional_interfaces", "digital twin access"): "no canonical property yet",
    ("additional_interfaces", "ready for Neura Gym training"): "no canonical property yet",
}

DIRECT_KINDS = {"robot_variant", "robot_spec", "pricing_offer", "availability_offer",
                "commercial_status"}

#: Findings about what the PUBLIC sees. An unpublished catalogue record is not a public assertion,
#: so
#: for it these are reported as coverage warnings ("resolve before publishing") and never block;
#: they
#: block only a robot that is published or is being published. Identity, mechanics, a new
#: unexplained
#: negative, a flattened variant and a historical figure given a home block the canonical record
#: always.
PUBLIC_ONLY_CODES = frozenset(
    {
        "CANONICAL_CONFLICT",
        "PUBLIC_CONTRADICTS_CANONICAL",
        "FABRICATED_DATE",
        "FABRICATED_PRICE_TYPE",
        "PROVENANCE_MISSING",
        "IMAGE_PROVENANCE_MISSING",
    }
)


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def _blank(v: str | None) -> bool:
    return v is None or not str(v).strip()


def load_legacy_baseline(path_text: str | None) -> frozenset[tuple[str, str]]:
    """The committed baseline of PRE-EXISTING weaknesses: (slug, field) pairs for unexplained
    `false`/zero values and for the field "summary" (published robots that predate the summary
    requirement). They are coverage review findings, never integrity failures (owner ruling
    2026-10-03); the baseline may only shrink."""
    if not path_text:
        return frozenset()
    data = json.loads(path_text)
    return frozenset((e["slug"], e["field"]) for e in data.get("entries", []))


def resolution_inputs(rec: RobotRecord) -> tuple[dict, list, list]:
    product = {p: rec.core.get(p) for p in fr.PROJECTED_PROPERTIES}
    variants = sorted(rec.variants)
    specs = [fr.ScopedSpec(s.variant_slug, s.key, s.value_text) for s in rec.specs]
    return product, variants, specs


def resolve(rec: RobotRecord) -> dict[str, fr.ResolvedFact]:
    product, variants, specs = resolution_inputs(rec)
    return fr.resolve_robot(product, variants, specs)


def _display_eligible(img: ImageRow) -> bool:
    """MEDIA-01 display eligibility; equal to RobotImage.is_display_eligible (a test pins it)."""
    note = (img.representative_note or "").strip()
    if img.identity_status != "VERIFIED":
        if not (img.is_representative and img.usage_basis == "OWNER_APPROVED_DISPLAY"):
            return False
        if not note:
            return False
    if img.rights_status == "RESTRICTED":
        return False
    if not (
        img.rights_status in ("PERMITTED", "ATTRIBUTION_REQUIRED")
        or img.usage_basis in ("OFFICIAL_MANUFACTURER_MEDIA", "OWNER_APPROVED_DISPLAY")
    ):
        return False
    if img.is_representative and not note:
        return False
    if img.rights_status == "ATTRIBUTION_REQUIRED":
        return bool((img.attribution or "").strip())
    return True


def unexplained_negatives(rec: RobotRecord) -> list[str]:
    """Core fields holding a `false` (or an implausible zero).

    A core column can never carry a governed negative (see the note above), so every such value is
    unexplained; whether it is blocking or a legacy review finding is decided by the baseline."""
    out = []
    for f in BOOLEAN_FIELDS:
        if rec.core.get(f) is False:
            out.append(f)
    for f in IMPLAUSIBLE_ZERO_FIELDS:
        v = rec.core.get(f)
        if v is not None and float(v) == 0.0:
            out.append(f)
    return out


def _claim_target(c: ClaimRow, slug: str) -> str:
    return f"{c.target_kind}:{slug}:{c.variant_slug or ''}:{c.target_key}"


def _unit_tokens(s: SpecRow) -> tuple[str, ...]:
    return fr.tokens_of(s.key, s.value_text)


# ------------------------------------------------------------------------------------------------
# Integrity
# ------------------------------------------------------------------------------------------------


def integrity_check(
    rec: RobotRecord,
    *,
    legacy: frozenset[tuple[str, str]] = frozenset(),
    transition: bool = False,
) -> list[Finding]:
    """BLOCK findings only. `transition=True` = this robot is going from unpublished to published
    (adds the summary requirement and makes loss blocking for an unpublished robot)."""
    out: list[Finding] = []

    def block(code: str, message: str, subject: str | None = None) -> None:
        out.append(Finding(INTEGRITY, BLOCK, code, message, subject))

    publishing = rec.is_published or transition

    # A. identity ------------------------------------------------------------------------------
    if _blank(rec.name):
        block("IDENTITY_MISSING_NAME", "the robot has no name")
    if _blank(rec.manufacturer_slug):
        block("IDENTITY_MISSING_MANUFACTURER", "the robot has no resolved manufacturer")
    if not SLUG_RE.match(rec.slug or ""):
        block("IDENTITY_INVALID_SLUG", f"slug {rec.slug!r} is not a valid canonical slug")
    for item in rec.open_identity:
        block(
            "IDENTITY_AMBIGUOUS",
            f"an active, unresolved identity ambiguity is attached to this robot: {item}",
        )

    # B. conflict ------------------------------------------------------------------------------
    resolved = resolve(rec)
    for prop, f in resolved.items():
        if f.state is fr.State.CONFLICT:
            block("CANONICAL_CONFLICT", f"{prop} is in CONFLICT: {f.detail}", prop)
    by_target: dict[str, set[str | None]] = {}
    for c in rec.claims:
        if c.target_kind == "NO_CATALOGUE_HOME":
            continue
        by_target.setdefault(_claim_target(c, rec.slug), set()).add(c.accepted_value)
    for target, values in by_target.items():
        if len(values) > 1:
            block(
                "CANONICAL_CONFLICT",
                f"current accepted claims disagree for {target}: {sorted(map(str, values))}",
                target,
            )

    # C. the resolved public output must be consistent with the canonical inputs ---------------
    for prop, f in resolved.items():
        names = {v.slug for v in f.variants}
        if f.value is not None and f.state not in (
            fr.State.PRODUCT_VALUE,
            fr.State.UNIFORM_VARIANTS,
        ):
            block(
                "PUBLIC_CONTRADICTS_CANONICAL",
                f"{prop} publishes a robot-wide value in state {f.state.value}",
                prop,
            )
        if f.state is fr.State.UNIFORM_VARIANTS and any(v.value != f.value for v in f.variants):
            block(
                "PUBLIC_CONTRADICTS_CANONICAL",
                f"{prop} is UNIFORM but its configurations disagree",
                prop,
            )
        if (
            f.state is fr.State.PRODUCT_VALUE
            and f.value != rec.core.get(prop)
            and f.product_source == "core"
        ):
            block(
                "PUBLIC_CONTRADICTS_CANONICAL",
                f"{prop} product value differs from the column",
                prop,
            )
        if f.state is fr.State.UNKNOWN and any(
            s.variant_slug in names
            for s in rec.specs
            if any(
                p == prop
                for p, _, _ in fr.project(fr.ScopedSpec(s.variant_slug, s.key, s.value_text))
            )
        ):
            block(
                "PUBLIC_CONTRADICTS_CANONICAL",
                f"{prop} is UNKNOWN although scoped canonical evidence exists",
                prop,
            )

    # D. fabrication / unsupported inference in governed transformations ------------------------
    for a in rec.availability:
        year_level = any(
            a_text and YEAR_LEVEL_RE.match(a_text)
            for a_text in (a.delivery_estimate_label, a.seller_wording)
        )
        if year_level and a.available_from:
            block(
                "FABRICATED_DATE",
                "a year-level availability statement was turned into an exact date "
                f"({a.available_from})",
                a.variant_slug,
            )
    pricing_claims = {c.variant_slug: c for c in rec.claims if c.target_kind == "pricing_offer"}
    for p in rec.pricing:
        claim = pricing_claims.get(p.variant_slug)
        if claim is not None:
            try:
                claimed_type = json.loads(claim.accepted_value or "{}").get("price_type")
            except ValueError:
                claimed_type = None
            if claimed_type and claimed_type != p.price_type:
                block(
                    "FABRICATED_PRICE_TYPE",
                    f"the accepted price type {claimed_type} was published as {p.price_type}",
                    p.variant_slug,
                )
    for c in rec.claims:
        if c.target_key.startswith("historical_") and c.target_kind != "NO_CATALOGUE_HOME":
            block(
                "HISTORICAL_AS_CURRENT",
                f"historical figure {c.target_key} was given a catalogue home",
                c.target_key,
            )
    for fld in unexplained_negatives(rec):
        if (rec.slug, fld) in legacy:
            continue  # legacy: a coverage review finding, never an integrity failure
        block(
            "UNEXPLAINED_NEGATIVE",
            f"{fld} is {rec.core.get(fld)!r} but a negative must come through the governed "
            "chain (source statement, accepted claim, scoped specification, ratified negative "
            "projection); missing evidence must never create false or 0",
            fld,
        )

    # E. required provenance --------------------------------------------------------------------
    if rec.commercial_status != "UNKNOWN" and rec.status_evidence == 0:
        block(
            "PROVENANCE_MISSING",
            f"commercial status {rec.commercial_status} has no evidence",
            "commercial_status",
        )
    for p in rec.pricing:
        if not p.has_evidence:
            block("PROVENANCE_MISSING", "a pricing offer has no evidence", p.variant_slug)
    for a in rec.availability:
        if not a.has_evidence:
            block("PROVENANCE_MISSING", "an availability offer has no evidence", a.variant_slug)
    if any(not ok for ok in rec.deployments):
        block("PROVENANCE_MISSING", "a deployment has no evidence")
    for img in rec.images:
        if _display_eligible(img):
            if _blank(img.source_url) or _blank(img.source_name):
                block(
                    "IMAGE_PROVENANCE_MISSING",
                    f"display-eligible image {img.image_url} lacks source provenance",
                    img.image_url,
                )
            if _blank(img.attribution) and img.rights_status == "ATTRIBUTION_REQUIRED":
                block(
                    "IMAGE_PROVENANCE_MISSING", "attribution is required but missing", img.image_url
                )

    # F. mechanics ------------------------------------------------------------------------------
    if not isinstance(rec.is_published, bool):
        block("MECHANICS_PUBLICATION_FLAG", "is_published is not a boolean")
    if transition and (rec.slug, "summary") not in legacy:
        s = (rec.summary or "").strip()
        if not s:
            block("SUMMARY_MISSING", "a new publication needs a non-empty summary", "summary")
        elif (
            len(s) < MIN_SUMMARY_CHARS
            or PLACEHOLDER_RE.search(s)
            or s.lower() == (rec.name or "").lower()
        ):
            block(
                "SUMMARY_NOT_USEFUL",
                "the summary is a placeholder or too short to explain what the robot is",
                "summary",
            )

    # G. loss: accepted knowledge missing from the intended public representation --------------
    for loss in loss_findings(rec, resolved):
        severity = BLOCK if publishing else WARN
        out.append(
            Finding(INTEGRITY if publishing else COVERAGE, severity, "UNACCOUNTED_LOSS", loss, None)
        )
    # scope widening is a fabrication, not a loss
    spec_by = {(s.variant_slug, s.key): s for s in rec.specs}
    for c in rec.claims:
        if c.target_kind == "specification" and c.variant_slug:
            row = spec_by.get((c.variant_slug, c.target_key))
            if row is None and (None, c.target_key) in spec_by:
                block(
                    "VARIANT_FLATTENED",
                    f"{c.target_key} was accepted for variant {c.variant_slug!r} but stored "
                    "at product level",
                    c.target_key,
                )
    if publishing:
        return out
    return [
        Finding(
            COVERAGE,
            WARN,
            f.code,
            f.message + " (unpublished: resolve before publishing)",
            f.subject,
        )
        if f.concept == INTEGRITY and f.code in PUBLIC_ONLY_CODES
        else f
        for f in out
    ]


def loss_findings(rec: RobotRecord, resolved: Mapping[str, fr.ResolvedFact]) -> list[str]:
    """Accepted CURRENT knowledge that is missing from the canonical/public chain."""
    lost: list[str] = []
    variants = {s for s, _ in rec.variants}
    spec_by = {(s.variant_slug, s.key): s for s in rec.specs}
    for c in rec.claims:
        if c.target_kind == "robot_variant":
            if c.variant_slug not in variants:
                lost.append(f"accepted variant {c.variant_slug!r} is not in the catalogue")
        elif c.target_kind == "specification":
            row = spec_by.get((c.variant_slug, c.target_key))
            if row is None:
                if (None, c.target_key) not in spec_by or not c.variant_slug:
                    lost.append(
                        f"accepted specification {c.target_key!r} "
                        f"({c.variant_slug or 'product'}) is not in the catalogue"
                    )
            elif row.value_text != c.accepted_value:
                lost.append(f"specification {c.target_key!r} differs from its accepted value")
        elif c.target_kind == "robot_spec":
            col = rec.core.get(c.target_key)
            if col is None or str(int(col)) != str(c.accepted_value):
                lost.append(f"accepted {c.target_key} = {c.accepted_value} is not on the robot")
        elif c.target_kind == "commercial_status":
            if rec.commercial_status != c.accepted_value:
                lost.append(f"accepted commercial status {c.accepted_value} is not on the robot "
                            f"(it is {rec.commercial_status})")
        elif c.target_kind == "pricing_offer":
            if not any(p.variant_slug == c.variant_slug for p in rec.pricing):
                lost.append(f"accepted price for {c.variant_slug!r} is not published")
        elif c.target_kind == "availability_offer":
            if not any(a.variant_slug == c.variant_slug for a in rec.availability):
                lost.append(f"accepted availability for {c.variant_slug!r} is not published")
    # a registered projection that the resolver lost
    for s in rec.specs:
        for prop, _value, token in fr.project(fr.ScopedSpec(s.variant_slug, s.key, s.value_text)):
            f = resolved.get(prop)
            if f is None:
                continue
            have = {(k, t) for v in f.variants for k, t in v.evidence if v.slug == s.variant_slug}
            if (
                s.variant_slug is not None
                and (s.key, token) not in have
                and f.state is not fr.State.CONFLICT
            ):
                lost.append(
                    f"registered projection {prop} from {s.key}/{token!r} "
                    f"({s.variant_slug}) is missing from the resolved output"
                )
    return lost


# ------------------------------------------------------------------------------------------------
# Coverage (NEVER blocks)
# ------------------------------------------------------------------------------------------------


@dataclass
class FactAccounting:
    canonical_direct: int = 0
    canonical_projected: int = 0
    detail_only: int = 0
    no_catalogue_home: int = 0
    unmapped_knowledge: int = 0
    unaccounted_loss: int = 0
    conflicts: int = 0
    not_yet_reviewed: int = 0
    detail_only_reasons: dict[str, str] = field(default_factory=dict)
    unmapped_candidates: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class CoverageReport:
    slug: str
    findings: list[Finding]
    accounting: FactAccounting
    known_buyer_fields: int
    total_buyer_fields: int
    band: str  # LOW | PARTIAL | GOOD (informational)


def account_facts(rec: RobotRecord) -> FactAccounting:
    acc = FactAccounting()
    resolved = resolve(rec)
    for f in BUYER_FIELDS + fr.PROJECTED_PROPERTIES:
        if rec.core.get(f) is not None:
            acc.canonical_direct += 1
    acc.canonical_direct += len(rec.variants) + len(rec.pricing) + len(rec.availability)
    registry_keys = {r.spec_key for r in fr.PROJECTION_REGISTRY}
    for s in rec.specs:
        if s.key not in registry_keys:
            acc.detail_only += 1
            acc.detail_only_reasons[f"{s.key}"] = "long-tail specification, verbatim by design"
            continue
        for token in _unit_tokens(s):
            if fr.project(fr.ScopedSpec(s.variant_slug, s.key, token)):
                acc.canonical_projected += 1
            elif (s.key, token) in DETAIL_ONLY_TOKENS:
                acc.detail_only += 1
                acc.detail_only_reasons[f"{s.key}/{token}"] = DETAIL_ONLY_TOKENS[(s.key, token)]
            else:
                acc.unmapped_knowledge += 1
                acc.unmapped_candidates.append(f"{s.key}/{token}")
    acc.no_catalogue_home = sum(1 for c in rec.claims if c.target_kind == "NO_CATALOGUE_HOME")
    acc.unaccounted_loss = len(loss_findings(rec, resolved))
    acc.conflicts = sum(1 for f in resolved.values() if f.state is fr.State.CONFLICT)
    acc.not_yet_reviewed = rec.not_yet_reviewed
    return acc


def coverage_audit(
    rec: RobotRecord, *, legacy: frozenset[tuple[str, str]] = frozenset()
) -> CoverageReport:
    """Informational findings and counts. There is no failing outcome: this never blocks."""
    out: list[Finding] = []

    def note(sev: str, code: str, message: str, subject: str | None = None) -> None:
        out.append(Finding(COVERAGE, sev, code, message, subject))

    resolved = resolve(rec)
    acc = account_facts(rec)
    # public-assertion issues of an UNPUBLISHED record are reported here, as warnings
    out.extend(f for f in integrity_check(rec, legacy=legacy) if f.concept == COVERAGE)
    if (rec.is_published or (rec.slug, "summary") in legacy) and _blank(rec.summary):
        note(
            WARN, "SUMMARY_MISSING", "published robot without a summary (not an integrity failure)"
        )
    for fld in unexplained_negatives(rec):
        if (rec.slug, fld) in legacy:
            note(
                WARN,
                "LEGACY_UNEXPLAINED_FALSE",
                f"{fld} = {rec.core.get(fld)!r} predates G4-3 and lacks per-field provenance; "
                "review: find the source and record it through the governed chain, else prefer "
                "NULL/UNKNOWN (not an integrity failure)",
                fld,
            )
    known = sum(1 for f in BUYER_FIELDS if rec.core.get(f) is not None)
    known += sum(1 for f in resolved.values() if f.state is not fr.State.UNKNOWN)
    known += 1 if rec.pricing else 0
    known += 1 if rec.availability else 0
    total = len(BUYER_FIELDS) + len(resolved) + 2
    ratio = known / total
    band = "LOW" if ratio < 0.34 else "PARTIAL" if ratio < 0.67 else "GOOD"
    if not rec.pricing:
        note(INFO, "NO_PRICE", "no price on record")
    if not rec.availability:
        note(INFO, "NO_AVAILABILITY", "no availability on record")
    if resolved["has_sdk"].state is fr.State.UNKNOWN:
        note(INFO, "NO_SDK_EVIDENCE", "no SDK evidence at product or variant scope")
    if not rec.deployments:
        note(INFO, "NO_DEPLOYMENT_EVIDENCE", "no deployment evidence")
    unknown = [f for f in BUYER_FIELDS if rec.core.get(f) is None]
    if unknown:
        note(
            INFO,
            "UNKNOWN_DENSITY",
            f"{len(unknown)}/{len(BUYER_FIELDS)} buyer fields UNKNOWN: " + ", ".join(unknown),
        )
    for cand in acc.unmapped_candidates:
        note(
            INFO,
            "UNMAPPED_KNOWLEDGE",
            f"projection candidate / owner mapping required: {cand}",
            cand,
        )
    if acc.detail_only:
        note(INFO, "DETAIL_ONLY", f"{acc.detail_only} fact(s) preserved as detail only")
    if acc.no_catalogue_home:
        note(
            INFO,
            "NO_CATALOGUE_HOME",
            f"{acc.no_catalogue_home} accepted fact(s) with no catalogue home",
        )
    if acc.not_yet_reviewed:
        note(INFO, "NOT_YET_REVIEWED", f"{acc.not_yet_reviewed} proposal(s) await human review")
    return CoverageReport(rec.slug, out, acc, known, total, band)


# ------------------------------------------------------------------------------------------------
# Publication transition and the fresh-announcement readiness concept
# ------------------------------------------------------------------------------------------------


def publication_check(
    rec: RobotRecord, *, legacy: frozenset[tuple[str, str]] = frozenset()
) -> list[Finding]:
    """Findings that would BLOCK an `is_published` false -> true transition (integrity only)."""
    return [f for f in integrity_check(rec, legacy=legacy, transition=True) if f.severity == BLOCK]


def fresh_announcement_ready(
    rec: RobotRecord, *, legacy: frozenset[tuple[str, str]] = frozenset()
) -> bool:
    """The lightweight readiness concept (DR-G4 8.1): "publication integrity passes plus
    the minimum a page needs to explain what the robot is": identity, manufacturer, an authoritative
    source, an honest maturity and a summary. Nothing about completeness."""
    if publication_check(rec, legacy=legacy):
        return False
    has_source = bool(rec.official_url) or rec.status_evidence > 0 or rec.source_count > 0
    return has_source and not _blank(rec.summary)


def summarize(findings: Iterable[Finding]) -> Counter:
    return Counter((f.concept, f.severity, f.code) for f in findings)
