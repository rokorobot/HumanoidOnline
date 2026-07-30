"""Batch trace + promotion review (DATA-D1 §9/§18, Gate H2/P2/P8).

The bottleneck in clearing a discovery queue is not the database, it is the
human: DATA-D1 P2 requires a *confirmed authoritative trace* for every candidate
and P8 requires a named human to approve every promotion. Doing that one
candidate at a time through `app.cli.promote_candidate` is correct and
unbearable at 43 candidates.

This module makes the same decisions **in a batch, through a reviewable file**,
without weakening a single gate. It adds no new writer: `export_worksheet` reads,
and `apply_worksheet` calls the existing, ratified `record_trace` / `advance` /
`promote` / `reject`.

Two phases, deliberately separated by a file a human edits:

    export  ->  worksheet.json   ->  [human opens each page, decides]  ->  apply

**What the worksheet does and does not do.** It pre-fills `trace_url` from the
candidate's `official_url` LEAD purely to save typing. That prefill is NOT a
confirmation and never becomes one: a row is acted on only when a human has
typed a `decision`, and DATA-D1.2/H2's rule that *a lead is not proof* is
enforced by requiring that explicit word. What the software cannot check is
whether the reviewer actually opened the page — so the worksheet says so, in the
file, next to the field.

Truthful scope: confirming a trace establishes that **this robot exists and this
is its authoritative source**. It establishes nothing about the robot's height,
price or availability, and this module never marks a spec claim VERIFIED
(`confirmed_fields` is deliberately not exposed here — per-field verification is
a per-field decision, not a batch one). A candidate promoted through this path
arrives with every specification UNKNOWN, which is the honest result.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate
from app.services.discovery import DiscoveryError, PromotionError
from app.services.discovery.pipeline import advance, record_trace
from app.services.discovery.promotion import promote, reject

#: Worksheet format version. Bumped when a field changes meaning, so an old
#: worksheet is refused rather than silently misread. v2 added `snapshot_hash`:
#: a v1 worksheet carries decisions that were never bound to what was reviewed,
#: so it is refused rather than upgraded.
WORKSHEET_VERSION = 2

#: Row-level failures that are FINDINGS: a gate refused, or the database refused.
#: They roll back that row's savepoint and become BLOCKED. Everything else — a
#: bug, a dropped connection, a disk error — aborts the whole batch, because a
#: batch that silently downgrades an infrastructure failure into "1 blocked row"
#: reports a clean run that never happened.
ROW_LEVEL_FAILURES = (DiscoveryError, PromotionError, IntegrityError, DataError)

#: The only decisions a reviewer may record. An empty string means "not yet
#: reviewed" and is the default for every exported row.
DECISION_CONFIRM = "confirm"
DECISION_REJECT = "reject"
DECISION_SKIP = "skip"
DECISIONS = frozenset({DECISION_CONFIRM, DECISION_REJECT, DECISION_SKIP, ""})

#: Candidates in these states are finished; they are never exported or acted on.
TERMINAL = frozenset({"PROMOTED", "REJECTED"})

#: `source_type` values that describe an authoritative first-party source. A
#: trace to anything else is recorded honestly but will not satisfy DATA-D1.LIVE
#: Gate W where an official source exists for the entity.
OFFICIAL_SOURCE_TYPES = frozenset(
    {"MANUFACTURER_SITE", "MANUFACTURER_STORE", "PRESS_RELEASE", "DIRECT_QUOTE"}
)

DEFAULT_SOURCE_TYPE = "MANUFACTURER_SITE"


#: The fields whose values the reviewer's decision is ABOUT. Ordered, because the
#: hash is over a deterministic serialization of exactly these.
SNAPSHOT_FIELDS = (
    "candidate_id",
    "external_ref",
    "candidate_name",
    "candidate_manufacturer",
    "identity_status",
    "status",
    "trace_state",
    "official_url_lead",
    "updated_at",
)


def candidate_snapshot(candidate: DiscoveryCandidate) -> dict[str, str | None]:
    """The canonical description of what a reviewer was looking at."""
    updated = candidate.updated_at
    return {
        "candidate_id": str(candidate.id),
        "external_ref": candidate.external_ref,
        "candidate_name": candidate.candidate_name,
        "candidate_manufacturer": candidate.candidate_manufacturer,
        "identity_status": candidate.identity_status,
        "status": candidate.status,
        "trace_state": candidate.trace_state,
        "official_url_lead": (candidate.candidate_data or {}).get("official_url"),
        "updated_at": updated.astimezone(UTC).isoformat() if updated else None,
    }


def snapshot_hash(snapshot: dict[str, str | None]) -> str:
    """SHA-256 over a deterministic JSON serialization of `SNAPSHOT_FIELDS`.

    Deterministic means: the fields in the fixed order above, no whitespace
    variation, explicit `null` rather than an omitted key, and UTF-8 without
    ASCII escaping — so the same candidate always hashes the same way on any
    machine, and a changed candidate never hashes the same way twice.
    """
    ordered = [[k, snapshot.get(k)] for k in SNAPSHOT_FIELDS]
    payload = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class WorksheetRow:
    """One candidate awaiting a human decision.

    `snapshot_hash` binds the decision to the candidate AS REVIEWED. Without it
    the `_*` context is decorative: `candidate_id` alone selects the live record,
    so editing one row's id would land its confirmation on a different robot, and
    a candidate that changed between export and apply would receive a decision
    made about its older self. The hash makes both impossible to do silently.

    The `_*` fields remain context for the reviewer and are never written back —
    the worksheet is integrity evidence, not a source of truth.
    """

    candidate_id: str
    snapshot_hash: str = ""
    decision: str = ""
    trace_url: str = ""
    trace_source_type: str = DEFAULT_SOURCE_TYPE
    reject_reason: str = ""
    # --- context, read-only ---
    _name: str | None = None
    _manufacturer: str | None = None
    _identity_status: str | None = None
    _status: str | None = None
    _trace_state: str | None = None
    _official_url_lead: str | None = None
    _claims: int = 0


@dataclass
class ApplyResult:
    confirmed: list[str] = field(default_factory=list)
    promoted: list[dict[str, str]] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)

    @property
    def acted(self) -> int:
        return len(self.confirmed) + len(self.rejected)


def export_worksheet(session: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Build a review worksheet for every non-terminal candidate. Read-only."""
    stmt = select(DiscoveryCandidate).order_by(
        DiscoveryCandidate.candidate_manufacturer, DiscoveryCandidate.candidate_name
    )
    candidates = [c for c in session.execute(stmt).scalars().all() if c.status not in TERMINAL]
    if limit is not None:
        candidates = candidates[:limit]

    rows = [
        WorksheetRow(
            candidate_id=str(c.id),
            snapshot_hash=snapshot_hash(candidate_snapshot(c)),
            # Prefilled from the LEAD to save typing. This is not a confirmation
            # (H2); the `decision` field is what attests, and only a human writes it.
            trace_url=(c.candidate_data or {}).get("official_url", "") or "",
            _name=c.candidate_name,
            _manufacturer=c.candidate_manufacturer,
            _identity_status=c.identity_status,
            _status=c.status,
            _trace_state=c.trace_state,
            _official_url_lead=(c.candidate_data or {}).get("official_url"),
            _claims=len(c.claims),
        )
        for c in candidates
    ]

    return {
        "worksheet_version": WORKSHEET_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_count": len(rows),
        "instructions": [
            "For each row: OPEN the URL and confirm the page is about THIS robot.",
            "Only then set decision to 'confirm'. A prefilled trace_url is a LEAD,",
            "not proof — the software cannot tell whether you opened the page.",
            "decision: 'confirm' | 'reject' | 'skip' | '' (unreviewed, no action).",
            "Confirming establishes the robot EXISTS and this is its source.",
            "It verifies no specification: promoted robots arrive with specs UNKNOWN.",
            "Fields beginning with '_' are context only and are ignored on apply.",
            "DO NOT edit candidate_id or snapshot_hash. The hash binds your decision",
            "to the candidate as exported; if either is altered, or the candidate",
            "changed since export, the row is refused and must be reviewed again.",
        ],
        "rows": [asdict(r) for r in rows],
    }


def write_worksheet(path: str | Path, worksheet: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(worksheet, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def read_worksheet(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("worksheet_version")
    if version != WORKSHEET_VERSION:
        raise DiscoveryError(
            f"worksheet version {version!r} is not {WORKSHEET_VERSION} — "
            "re-export rather than editing an old file, so no field is misread"
        )
    if not isinstance(data.get("rows"), list):
        raise DiscoveryError("worksheet has no 'rows' list")
    return data


def validate_worksheet(worksheet: dict[str, Any]) -> None:
    """Refuse a worksheet that cannot be applied truthfully, before touching the DB."""
    seen: set[str] = set()
    for index, raw in enumerate(worksheet["rows"]):
        where = f"row {index} ({raw.get('candidate_id', '?')})"
        cid = str(raw.get("candidate_id") or "")
        if not cid:
            raise DiscoveryError(f"{where}: candidate_id is required")
        if cid in seen:
            raise DiscoveryError(f"{where}: duplicate candidate_id {cid}")
        seen.add(cid)

        decision = (raw.get("decision") or "").strip().lower()
        if decision not in DECISIONS:
            raise DiscoveryError(
                f"{where}: decision {decision!r} is not one of "
                f"{sorted(d for d in DECISIONS if d)} (or empty for unreviewed)"
            )
        if decision and not str(raw.get("snapshot_hash") or "").strip():
            raise DiscoveryError(
                f"{where}: snapshot_hash is missing. A decision must be bound to "
                "the candidate it was made about; re-export the worksheet."
            )
        if decision == DECISION_CONFIRM and not str(raw.get("trace_url") or "").strip():
            raise DiscoveryError(
                f"{where}: 'confirm' requires a trace_url — a confirmed trace "
                "needs an authoritative source (DATA-D1 P2)"
            )
        if decision == DECISION_REJECT and not str(raw.get("reject_reason") or "").strip():
            raise DiscoveryError(f"{where}: 'reject' requires a reject_reason")


def apply_worksheet(
    session: Session,
    worksheet: dict[str, Any],
    *,
    reviewed_by: str,
    promote_confirmed: bool = False,
    dry_run: bool = True,
) -> ApplyResult:
    """Apply reviewer decisions. Does not commit — the caller owns the transaction.

    `reviewed_by` is recorded as both the trace verifier (H2) and, when
    `promote_confirmed` is set, the P8 approving human. It is required: an
    unattributed decision is not a decision (DATA-D1.9).

    Idempotent and re-runnable: an already-terminal candidate is reported as
    skipped rather than raising, so a partially applied worksheet can be
    corrected and applied again.

    **Transaction semantics.** Each actionable row runs inside its own SAVEPOINT.
    An expected row-level failure — a gate refusing, or the database refusing —
    rolls back only that savepoint, records the row as BLOCKED, and leaves the
    session usable for the rows that follow. Any other exception aborts the whole
    operation and is not converted into a blocked row. **Each row is validated and
    isolated within the batch transaction; successful rows become durable only at
    the caller's final commit.**
    """
    if not reviewed_by or not reviewed_by.strip():
        raise DiscoveryError(
            "batch review requires an attributed human (reviewed_by) — the trace "
            "verifier (H2) and the promotion approver (P8) are both named people"
        )
    validate_worksheet(worksheet)
    reviewed_by = reviewed_by.strip()
    result = ApplyResult()

    for raw in worksheet["rows"]:
        cid = str(raw["candidate_id"])
        decision = (raw.get("decision") or "").strip().lower()
        label = f"{raw.get('_manufacturer') or '?'} {raw.get('_name') or '?'}".strip()

        if decision == "" or decision == DECISION_SKIP:
            result.skipped.append(
                {"candidate_id": cid, "label": label, "why": decision or "unreviewed"}
            )
            continue

        candidate = session.get(DiscoveryCandidate, cid)
        if candidate is None:
            result.blocked.append(
                {"candidate_id": cid, "label": label, "why": "candidate not found"}
            )
            continue
        # Terminal FIRST, and deliberately before the snapshot check: a candidate
        # that is already PROMOTED/REJECTED has necessarily changed since export,
        # and reporting "you must re-review" for work that is already done would
        # make re-running a partially applied worksheet impossible.
        if candidate.status in TERMINAL:
            result.skipped.append(
                {"candidate_id": cid, "label": label, "why": f"already {candidate.status}"}
            )
            continue

        # The decision must be about THIS candidate, as exported (correction 1).
        current = snapshot_hash(candidate_snapshot(candidate))
        if current != str(raw.get("snapshot_hash") or "").strip():
            result.blocked.append({
                "candidate_id": cid, "label": label,
                "why": "candidate changed since worksheet export; re-export and review again",
            })
            continue

        # Savepoints are per ACTION, not per row. Tracing and promoting are two
        # decisions: when a trace is validly confirmed but promotion is refused by
        # a gate (an ambiguous identity, a claim conflict), the trace is real work
        # and must survive. Sharing one savepoint would discard it and make the
        # operator confirm the same page twice.
        if decision == DECISION_REJECT:
            try:
                with session.begin_nested():
                    reject(session, candidate, reviewed_by, str(raw["reject_reason"]).strip())
                    session.flush()
            except ROW_LEVEL_FAILURES as exc:
                result.blocked.append({"candidate_id": cid, "label": label, "why": str(exc)})
                continue
            result.rejected.append(cid)
            continue

        # DECISION_CONFIRM — savepoint 1: the trace itself.
        try:
            with session.begin_nested():
                record_trace(
                    session,
                    candidate,
                    trace_url=str(raw["trace_url"]).strip(),
                    trace_source_type=(
                        raw.get("trace_source_type") or DEFAULT_SOURCE_TYPE
                    ).strip(),
                    verified_by=reviewed_by,
                    # Deliberately empty: a trace confirms the ENTITY, never its
                    # specifications. Per-field verification is a per-field decision.
                    confirmed_fields=frozenset(),
                )
                advance(session, candidate)
                session.flush()
        except ROW_LEVEL_FAILURES as exc:
            result.blocked.append({"candidate_id": cid, "label": label, "why": str(exc)})
            continue
        result.confirmed.append(cid)

        if not promote_confirmed:
            continue

        # savepoint 2: the promotion, which may be refused while the trace stands.
        try:
            with session.begin_nested():
                robot = promote(session, candidate, reviewed_by)
                session.flush()
        except ROW_LEVEL_FAILURES as exc:
            result.blocked.append(
                {"candidate_id": cid, "label": label, "why": f"promotion blocked: {exc}"}
            )
            continue
        result.promoted.append(
            {"candidate_id": cid, "label": label, "robot_slug": robot.slug,
             "robot_id": str(robot.id)}
        )

    if dry_run:
        session.rollback()
    return result
