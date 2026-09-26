"""Stage E — exception-only human review of discovery candidates (docs/16 §17.1).

CLI-first. The queue lists only what needs a human, in a deterministic order;
decisions are attributed and append-only, and each one is applied immediately by
re-running the existing deterministic pipeline on the candidates it touches.

- Candidate <-> candidate identity: `candidate_identity_decision` (SAME_ENTITY /
  NOT_SAME_ENTITY). A decided pair is never flagged as a duplicate again, and
  nothing is merged: both candidates keep their rows, claims and evidence.
- Out of scope: the existing rejection path (`promotion.reject`) with reason
  code OUT_OF_SCOPE. A rejected candidate is terminal and stops causing
  duplicate review.
- Candidate <-> catalogue identity: the confirmed alias register only. This
  module can PRINT a proposal for it; it never writes the register and never
  decides that two names are one robot.

No confidence scores, no fuzzy/embedding/LLM matching, no variant folding.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.acquisition import (
    CandidateCommercialSignal,
    DiscoveryEvidenceExcerpt,
    ExtractionResult,
    FetchedPage,
)
from app.models.discovery import (
    CandidateIdentityDecision,
    DiscoveryCandidate,
    DiscoverySource,
    PromotionAudit,
)
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError
from app.services.discovery.eligibility import _path_within, approved_host, approved_prefixes
from app.services.discovery.identity import (
    ALIASES_PATH,
    _model_key,
    load_confirmed_aliases,
    normalize,
)
from app.services.discovery.identity_decisions import (
    NOT_SAME_ENTITY,
    SAME_ENTITY,
    effective_decisions,
    record_identity_decision,
)
from app.services.discovery.pipeline import _TERMINAL, advance, record_trace
from app.services.discovery.promotion import reject
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

#: Queue item kinds, in display order (most blocking first).
KINDS = (
    "DUPLICATE_PAIR", "AMBIGUOUS", "CONFLICT", "RECHECK_REQUIRED", "ALIAS_PROPOSAL_PENDING",
    "INSUFFICIENT_EVIDENCE", "READY_FOR_PROMOTION", "AWAITING_TRACE",
)


@dataclass(frozen=True)
class QueueItem:
    kind: str
    candidate_ids: tuple[uuid.UUID, ...]
    summary: str


def _key(candidate: DiscoveryCandidate) -> tuple[str, str]:
    mfr = normalize(candidate.candidate_manufacturer)
    return mfr, _model_key(candidate.candidate_name, mfr)


def _label(c: DiscoveryCandidate) -> str:
    return f"{c.candidate_manufacturer or '?'} / {c.candidate_name or '?'} <{c.external_ref}>"


def _alias_proposals(path: Path) -> list[dict]:
    """Register entries awaiting confirmation (confirmed_by/at still null)."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("aliases", [])
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("confirmed_by") is None]


def review_queue(session: Session, aliases_path: Path = ALIASES_PATH) -> list[QueueItem]:
    """Every non-terminal candidate situation that needs a human. Deterministic."""
    open_ = sorted(
        session.scalars(select(DiscoveryCandidate).where(
            DiscoveryCandidate.status.not_in(_TERMINAL))).all(),
        key=lambda c: (_label(c), str(c.id)),
    )
    items: list[QueueItem] = []

    groups: dict[tuple[str, str], list[DiscoveryCandidate]] = {}
    for c in open_:
        mfr, model = _key(c)
        if mfr and model:
            groups.setdefault((mfr, model), []).append(c)
    for members in groups.values():
        for a, b in combinations(members, 2):
            if b.id in effective_decisions(session, a.id):
                continue  # a human already decided this pair
            items.append(QueueItem("DUPLICATE_PAIR", (a.id, b.id),
                                   f"{_label(a)}  <->  {_label(b)}"))

    robots = {r.slug: (r, m) for r, m in session.execute(
        select(Robot, Manufacturer).join(Manufacturer, Manufacturer.id == Robot.manufacturer_id))}
    proposals = _alias_proposals(aliases_path)
    for c in open_:
        mfr, model = _key(c)
        if c.identity_status == "AMBIGUOUS":
            items.append(QueueItem("AMBIGUOUS", (c.id,), _label(c)))
        if c.status in ("CONFLICT", "RECHECK_REQUIRED", "INSUFFICIENT_EVIDENCE",
                        "READY_FOR_PROMOTION"):
            traced = f"  [traced: {c.trace_url}]" if c.trace_state == "TRACE_CONFIRMED" else ""
            items.append(QueueItem(c.status, (c.id,), _label(c) + traced))
        if c.status == "SOURCE_TRACE" and c.identity_status in ("NEW_ENTITY", "MATCHED_EXISTING"):
            items.append(QueueItem("AWAITING_TRACE", (c.id,),
                                   f"{_label(c)}  [{c.identity_status}; {c.trace_state}]"))
        for entry in proposals:
            robot_mfr = robots.get(entry.get("robot_slug"))
            if (robot_mfr and normalize(robot_mfr[1].name) == mfr and model
                    and _model_key(entry.get("alias"), mfr) == model):
                items.append(QueueItem("ALIAS_PROPOSAL_PENDING", (c.id,),
                                       f"{_label(c)}  ->  catalogue {entry['robot_slug']!r} "
                                       "(proposed, awaiting confirmation)"))
    return sorted(items, key=lambda i: (KINDS.index(i.kind), i.summary,
                                        tuple(str(x) for x in i.candidate_ids)))


def _candidate(session: Session, candidate_id: uuid.UUID) -> DiscoveryCandidate:
    candidate = session.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise DiscoveryError(f"no discovery candidate {candidate_id}")
    return candidate


def _readvance(session: Session, candidates) -> None:
    """Apply a decision now: re-run the deterministic pipeline on non-terminal
    candidates sharing the decided candidates' identity key."""
    keys = {_key(c) for c in candidates}
    for other in session.scalars(select(DiscoveryCandidate).where(
            DiscoveryCandidate.status.not_in(_TERMINAL))).all():
        if _key(other) in keys:
            advance(session, other)
    session.flush()


def decide_pair(session: Session, a: uuid.UUID, b: uuid.UUID, decision: str, *,
                decided_by: str, reason: str) -> tuple[CandidateIdentityDecision, bool]:
    first, second = _candidate(session, a), _candidate(session, b)
    row, created = record_identity_decision(session, a, b, decision,
                                            decided_by=decided_by, reason=reason)
    _readvance(session, (first, second))
    return row, created


def reject_candidate(session: Session, candidate_id: uuid.UUID, *, by: str, reason: str,
                     reason_code: str | None) -> DiscoveryCandidate:
    """The existing rejection path; afterwards the candidate stops causing
    duplicate review for anyone sharing its identity key."""
    candidate = _candidate(session, candidate_id)
    reject(session, candidate, by, reason, reason_code=reason_code)
    _readvance(session, (candidate,))
    return candidate


#: Source classes that can be an authoritative trace (docs/16 §11.1 / Gate W),
#: mapped onto the existing `trace_source_type` vocabulary. Aggregators,
#: marketplaces and editorial sources are never an authoritative trace here.
TRACE_SOURCE_TYPES = {"MANUFACTURER": "MANUFACTURER_SITE", "OFFICIAL_STORE": "MANUFACTURER_STORE"}


def _source(session: Session, key_or_id: str) -> DiscoverySource:
    try:
        source = session.get(DiscoverySource, uuid.UUID(key_or_id))
    except ValueError:
        source = session.scalars(select(DiscoverySource).where(
            DiscoverySource.key == key_or_id)).first()
    if source is None:
        raise DiscoveryError(f"no discovery source {key_or_id!r}")
    return source


def record_source_trace(session: Session, candidate_id: uuid.UUID, *, source: str, url: str,
                        by: str) -> tuple[DiscoveryCandidate, bool]:
    """Governed CLI path onto the EXISTING `pipeline.record_trace` (H2).

    Validates what the service leaves to its caller: the source exists, is an
    official class, and approves the URL's host and path. It records the trace
    exactly as the batch review does (the entity only, no field confirmation),
    audits it in promotion_audit (TRACE_CONFIRMED) and re-runs the pipeline.
    Tracing never promotes and never writes a canonical table.

    Returns (candidate, recorded?). Re-recording the identical trace is a no-op.
    A different trace on an already-traced candidate is refused: the candidate's
    trace columns hold one value, so replacing it would silently rewrite history.
    """
    candidate = _candidate(session, candidate_id)
    if not (by or "").strip():
        raise DiscoveryError("--by is required (an unattributed trace is not a trace)")
    src = _source(session, source)
    source_type = TRACE_SOURCE_TYPES.get(src.source_class)
    if source_type is None:
        raise DiscoveryError(
            f"source {src.key!r} is {src.source_class}; an authoritative trace needs one of "
            f"{sorted(TRACE_SOURCE_TYPES)} (docs/16 §11.1)")
    try:
        trace_url = normalize_url(url)
    except UnsupportedUrl as exc:
        raise DiscoveryError(str(exc)) from exc
    parts = urlsplit(trace_url)
    if approved_host(src) is None or parts.hostname != approved_host(src):
        raise DiscoveryError(f"{trace_url} is not on {src.key}'s approved host "
                             f"({approved_host(src)})")
    prefixes = approved_prefixes(src)
    if not any(_path_within(parts.path or "/", p) for p in prefixes):
        raise DiscoveryError(f"{trace_url} is outside {src.key}'s approved paths {list(prefixes)}")

    if candidate.trace_state == "TRACE_CONFIRMED":
        if candidate.trace_url == trace_url and candidate.trace_source_type == source_type:
            return candidate, False
        raise DiscoveryError(
            f"candidate already has a confirmed trace ({candidate.trace_url}, "
            f"{candidate.trace_source_type}, by {candidate.trace_verified_by}); a different "
            "trace is refused rather than replacing it")
    record_trace(session, candidate, trace_url=trace_url, trace_source_type=source_type,
                 verified_by=by.strip(), confirmed_fields=frozenset())
    session.add(PromotionAudit(
        candidate_id=candidate.id, action="TRACE_CONFIRMED", approved_by=by.strip(),
        detail={"trace_url": trace_url, "trace_source_type": source_type,
                "source_key": src.key, "source_class": src.source_class},
    ))
    advance(session, candidate)
    session.flush()
    return candidate, True


def history(session: Session, candidate_id: uuid.UUID) -> list[str]:
    _candidate(session, candidate_id)
    lines: list[str] = []
    for row in session.scalars(select(PromotionAudit).where(
            PromotionAudit.candidate_id == candidate_id).order_by(PromotionAudit.created_at)):
        lines.append(f"{row.created_at.isoformat()}  {row.action:<22} by {row.approved_by}  "
                     f"{json.dumps(row.detail or {}, sort_keys=True)}")
    for row in session.scalars(select(CandidateIdentityDecision).where(or_(
            CandidateIdentityDecision.candidate_a_id == candidate_id,
            CandidateIdentityDecision.candidate_b_id == candidate_id,
    )).order_by(CandidateIdentityDecision.decision_seq)):
        other = row.candidate_b_id if row.candidate_a_id == candidate_id else row.candidate_a_id
        lines.append(f"{row.created_at.isoformat()}  {row.decision:<22} by {row.decided_by}  "
                     f"with {other} (#{row.decision_seq}): {row.reason}")
    return sorted(lines)


def show(session: Session, candidate_id: uuid.UUID) -> list[str]:
    """Everything a reviewer needs to decide, without writing SQL. Read-only."""
    c = _candidate(session, candidate_id)
    source = session.get(DiscoverySource, c.source_id)
    mfr, model = _key(c)
    lines = [
        f"CANDIDATE {c.id}",
        f"  name={c.candidate_name!r}  manufacturer={c.candidate_manufacturer!r}  "
        f"identity key=({mfr!r}, {model!r})",
        f"  source={source.key if source else '?'} ({source.source_class if source else '?'})",
        f"  external_ref={c.external_ref}",
        f"  discovery_url={c.discovery_url}",
        f"  identity_status={c.identity_status}  status={c.status}  trace={c.trace_state}",
        *([f"  trace: {c.trace_url} ({c.trace_source_type}) by {c.trace_verified_by} at "
           f"{c.trace_verified_at.isoformat() if c.trace_verified_at else '-'}"]
          if c.trace_state != "NOT_TRACED" else []),
        f"  discovered_at={c.discovered_at.isoformat()}  last_seen_at={c.last_seen_at.isoformat()}",
    ]
    if c.possible_robot_id:
        robot = session.get(Robot, c.possible_robot_id)
        lines.append(f"  resolver matched catalogue robot: {robot.slug} ({robot.name!r})")
    if c.possible_manufacturer_id:
        manufacturer = session.get(Manufacturer, c.possible_manufacturer_id)
        confirmed = load_confirmed_aliases()
        lines.append(f"  catalogue manufacturer: {manufacturer.name} ({manufacturer.slug}); "
                     "its catalogue robots (exact keys only, no similarity):")
        for robot in session.scalars(select(Robot).where(
                Robot.manufacturer_id == manufacturer.id).order_by(Robot.slug)):
            robot_key = _model_key(robot.name, mfr)
            aliases = confirmed.get(robot.slug, ())
            same = "EXACT KEY MATCH" if robot_key == model else "different key"
            lines.append(f"    {robot.slug:<32} {robot.name!r:<24} key={robot_key!r:<14} "
                         f"{same}; confirmed aliases={list(aliases)} "
                         f"published={robot.is_published}")
    lines.append("  extraction (markers / lineage):")
    for result, page in session.execute(
            select(ExtractionResult, FetchedPage)
            .join(FetchedPage, FetchedPage.id == ExtractionResult.fetched_page_id)
            .where(ExtractionResult.candidate_id == c.id)
            .order_by(FetchedPage.retrieved_at)):
        notes = json.loads(result.notes or "{}")
        lines.append(f"    {page.retrieved_at.isoformat()} run={page.crawl_run_id} "
                     f"page={page.id} {page.outcome} hash={page.content_hash} "
                     f"{result.status} {result.extractor_key}@{result.extractor_version}")
        lines += [f"      note: {n}" for n in notes.get("notes", [])]
    counts = {
        "claims": len(c.claims),
        "signals": len(session.scalars(select(CandidateCommercialSignal.id).where(
            CandidateCommercialSignal.candidate_id == c.id)).all()),
        "images": len(c.images),
        "excerpts": len(session.scalars(select(DiscoveryEvidenceExcerpt.id).where(
            DiscoveryEvidenceExcerpt.subject_id.in_(
                [x.id for x in c.claims] or [uuid.UUID(int=0)]))).all()),
    }
    lines.append(f"  evidence rows: {counts}")
    decided = effective_decisions(session, c.id)
    related = sorted((o for o in session.scalars(select(DiscoveryCandidate).where(
        DiscoveryCandidate.id != c.id)) if _key(o) == (mfr, model) and model),
        key=lambda o: str(o.id))
    lines.append("  related candidates (same identity key):" if related else
                 "  related candidates: none")
    for other in related:
        lines.append(f"    {other.id} {_label(other)} identity={other.identity_status} "
                     f"status={other.status} decision={decided.get(other.id, 'none')}")
    for other_id, decision in sorted(decided.items(), key=lambda kv: str(kv[0])):
        if other_id not in {o.id for o in related}:
            lines.append(f"    {other_id} (different key) decision={decision}")
    lines.append("  history:")
    lines += [f"    {h}" for h in history(session, c.id)] or ["    (none)"]
    return lines


def propose_alias(session: Session, candidate_id: uuid.UUID, robot_slug: str) -> dict:
    """PRINT-ONLY: the register entry that would make this candidate's name a
    confirmed alias of a catalogue robot. Nothing is written, and the entry is a
    proposal until a human sets confirmed_by/confirmed_at in a reviewed change."""
    c = _candidate(session, candidate_id)
    row = session.execute(select(Robot, Manufacturer).join(
        Manufacturer, Manufacturer.id == Robot.manufacturer_id).where(Robot.slug == robot_slug)
    ).first()
    if row is None:
        raise DiscoveryError(f"no catalogue robot {robot_slug!r}")
    robot, manufacturer = row
    if normalize(manufacturer.name) != normalize(c.candidate_manufacturer):
        raise DiscoveryError("the candidate's manufacturer is not the robot's manufacturer")
    if not c.candidate_name:
        raise DiscoveryError("the candidate has no name to propose as an alias")
    return {
        "robot_slug": robot.slug,
        "alias": c.candidate_name,
        "basis": f"Discovery candidate {c.id} ({c.external_ref}) names the robot "
                 f"{c.candidate_name!r}; the catalogue record is {robot.name!r}. "
                 "State here why they are the same product.",
        "proposed_at": None,
        "confirmed_by": None,
        "confirmed_at": None,
    }


__all__ = ["KINDS", "NOT_SAME_ENTITY", "SAME_ENTITY", "TRACE_SOURCE_TYPES", "QueueItem",
           "decide_pair", "history", "propose_alias", "record_source_trace", "reject_candidate",
           "review_queue", "show"]
