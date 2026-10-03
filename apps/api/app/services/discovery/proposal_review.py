"""G2-2 governed human review of claim proposals — DR-A5 B-prime, sections 5, 9 and 16.

Reads proposals (immutable) and appends human decisions (append-only). It writes ONLY
`discovery_proposal_decision` rows: no accepted claim, no catalogue row, no proposal,
no `is_published`. Every state shown here is derived on read and never stored:

* SUPERSEDED: a newer proposal exists in the same slot (`slot_key`).
* STALE (fail closed): the proposal is not currently supported by the evidence we hold.
  It is stale when ANY of these holds (the reasons are listed, never guessed away):
    - the extractor key/version that produced it is no longer a live extractor;
    - the identity gate fails (the robot slug is missing, or is not the named robot);
    - no observation of its source page can be found, the latest one did not retrieve
      the page (error, block, non-2xx), or no retrieved content can be established;
    - the latest retrieved content hash is not one the proposal was actually sighted on,
      i.e. the page changed (or at least changed bytes we cannot prove were re-extracted)
      since the proposal was last confirmed.
  Currentness is never inferred from missing data.

ACCEPT is allowed only for a CURRENT, non-stale proposal, by a named human, with a
rationale, with every review question explicitly resolved (or `NO_CATALOGUE_HOME`
explicitly chosen). Nothing is guessed: unknown resolved-choice keys, blank values and
unresolved questions are refused. A repeat of the effective decision with identical
resolved choices is a no-op; anything else appends a new row. ACCEPT creates no claim.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.acquisition import FetchedPage
from app.models.claim_proposal import (
    DiscoveryClaimProposal,
    DiscoveryProposalDecision,
    DiscoveryProposalObservation,
)
from app.models.discovery import DiscoverySource
from app.models.robot import Robot
from app.services.discovery import DiscoveryError
from app.services.discovery.field_policy import MAPPING_KEYS
from app.services.discovery.sources import neura_mini_proposals as mini
from app.services.discovery.sources import xpeng_iron_proposals as xpeng
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

ACCEPT, REJECT, DEFER = "ACCEPT", "REJECT", "DEFER"
DECISIONS = (ACCEPT, REJECT, DEFER)
NO_CATALOGUE_HOME = "NO_CATALOGUE_HOME"
HOME_KEY = "catalogue_home"
CURRENT, SUPERSEDED, STALE = "CURRENT", "SUPERSEDED", "STALE"

#: Extractors whose output is still trusted. Retiring one makes its proposals stale.
LIVE_EXTRACTORS = frozenset({(mini.EXTRACTOR_KEY, mini.EXTRACTOR_VERSION),
                             (xpeng.EXTRACTOR_KEY, xpeng.EXTRACTOR_VERSION)})
#: Identity gate: the catalogue name a live extractor's proposals must attach to.
EXTRACTOR_ROBOT_NAME = {mini.EXTRACTOR_KEY: mini.ROBOT_NAME,
                        xpeng.EXTRACTOR_KEY: xpeng.ROBOT_NAME}

_UNCHANGED = {"NOT_MODIFIED", "SKIPPED_UNCHANGED"}


def question_key(index: int) -> str:
    """The explicit key of the Nth (1-based) review question."""
    return f"q{index}"


@dataclass
class ProposalState:
    proposal: DiscoveryClaimProposal
    superseded: bool
    stale_reasons: list[str] = field(default_factory=list)
    effective: DiscoveryProposalDecision | None = None
    sightings: list[DiscoveryProposalObservation] = field(default_factory=list)

    @property
    def stale(self) -> bool:
        return bool(self.stale_reasons)

    @property
    def state(self) -> str:
        return SUPERSEDED if self.superseded else (STALE if self.stale else CURRENT)

    @property
    def acceptable(self) -> bool:
        return not self.superseded and not self.stale

    @property
    def needs_review(self) -> bool:
        return self.effective is None or self.effective.decision == DEFER


def _page_urls_match(page: FetchedPage, source_url: str) -> bool:
    for raw in (page.url, page.final_url):
        if not raw:
            continue
        try:
            if normalize_url(raw) == source_url:
                return True
        except UnsupportedUrl:
            continue
    return False


def _stale_reasons(session: Session, p: DiscoveryClaimProposal,
                   sighted_hashes: set[str]) -> list[str]:
    reasons: list[str] = []
    if (p.extractor_key, p.extractor_version) not in LIVE_EXTRACTORS:
        reasons.append(f"extractor {p.extractor_key}@{p.extractor_version} is not a live extractor")
    expected = EXTRACTOR_ROBOT_NAME.get(p.extractor_key)
    robot_name = session.scalar(select(Robot.name).where(Robot.slug == p.robot_slug))
    if robot_name is None or (expected is not None and robot_name != expected):
        reasons.append(f"identity gate fails for robot {p.robot_slug!r}")
    try:
        source_url = normalize_url(p.source_url)
    except UnsupportedUrl:
        return [*reasons, "the proposal's source URL is not a usable URL"]
    pages = [pg for pg in session.scalars(
        select(FetchedPage).where(FetchedPage.source_id == p.source_id)
        .order_by(FetchedPage.retrieved_at.desc(), FetchedPage.created_at.desc()))
        if _page_urls_match(pg, source_url)]
    if not pages:
        return [*reasons, "no observation of the source page was found"]
    latest = pages[0]
    if latest.outcome in ("BLOCKED_BY_ROBOTS", "BLOCKED_BY_SOURCE", "ERROR"):
        return [*reasons, f"the latest observation did not retrieve the page ({latest.outcome})"]
    if latest.http_status is not None and not (
            200 <= latest.http_status < 300 or latest.http_status == 304):
        return [*reasons, f"the latest observation of the source page returned "
                          f"HTTP {latest.http_status}"]
    # The newest observation that actually carries content is the current state of the page
    # (an unchanged / not-modified answer confirms the previous content, it adds none).
    content = next((pg for pg in pages if pg.content_hash), None)
    if content is None:
        return [*reasons, "no retrieved content could be established for the source page"]
    if content.content_hash not in sighted_hashes:
        reasons.append(
            "the page's latest retrieved content (hash "
            f"{content.content_hash[:12]}, observation {content.id}) is not content this "
            "proposal was sighted on; it has not been re-extracted")
    return reasons


def latest_content_page_for(session: Session, source_id, source_url: str) -> FetchedPage | None:
    """The newest observation of `source_url` (for one source) that carries content."""
    try:
        wanted = normalize_url(source_url)
    except UnsupportedUrl:
        return None
    pages = (pg for pg in session.scalars(
        select(FetchedPage).where(FetchedPage.source_id == source_id)
        .order_by(FetchedPage.retrieved_at.desc(), FetchedPage.created_at.desc()))
        if _page_urls_match(pg, wanted))
    return next((pg for pg in pages if pg.content_hash), None)


def latest_content_page(session: Session, p: DiscoveryClaimProposal) -> FetchedPage | None:
    """The newest observation of the proposal's source page that carries content."""
    return latest_content_page_for(session, p.source_id, p.source_url)


def derive_states(session: Session, proposals: list[DiscoveryClaimProposal]
                  ) -> list[ProposalState]:
    out: list[ProposalState] = []
    for p in proposals:
        newer = session.scalar(
            select(func.count()).select_from(DiscoveryClaimProposal).where(
                DiscoveryClaimProposal.slot_key == p.slot_key,
                DiscoveryClaimProposal.proposal_seq > p.proposal_seq))
        sightings = list(session.scalars(
            select(DiscoveryProposalObservation).where(
                DiscoveryProposalObservation.proposal_id == p.id)
            .order_by(DiscoveryProposalObservation.observation_seq)))
        effective = session.scalar(
            select(DiscoveryProposalDecision).where(DiscoveryProposalDecision.proposal_id == p.id)
            .order_by(DiscoveryProposalDecision.decision_seq.desc()).limit(1))
        out.append(ProposalState(
            proposal=p, superseded=bool(newer),
            stale_reasons=_stale_reasons(session, p, {s.content_hash for s in sightings}),
            effective=effective, sightings=sightings))
    return out


def list_proposals(session: Session, *, robot_slug: str | None = None,
                   source_key: str | None = None, edition: str | None = None,
                   kind: str | None = None, include_all: bool = False) -> list[ProposalState]:
    """Proposals in stable order. Default: those still needing a human (no effective
    decision, or an effective DEFER). `edition` 'none' selects whole-product proposals."""
    stmt = select(DiscoveryClaimProposal).order_by(DiscoveryClaimProposal.proposal_seq)
    if robot_slug:
        stmt = stmt.where(DiscoveryClaimProposal.robot_slug == robot_slug)
    if source_key:
        stmt = stmt.join(DiscoverySource, DiscoverySource.id == DiscoveryClaimProposal.source_id
                         ).where(DiscoverySource.key == source_key)
    if edition:
        stmt = stmt.where(DiscoveryClaimProposal.edition.is_(None) if edition.lower() == "none"
                          else DiscoveryClaimProposal.edition == edition)
    if kind:
        stmt = stmt.where(DiscoveryClaimProposal.kind == kind.upper())
    states = derive_states(session, list(session.scalars(stmt)))
    return states if include_all else [s for s in states if s.needs_review]


def resolve_proposal(session: Session, ref: str) -> DiscoveryClaimProposal:
    """A proposal by full id, or by a unique id / digest prefix of at least 8 characters."""
    ref = ref.strip().lower()
    try:
        row = session.get(DiscoveryClaimProposal, uuid.UUID(ref))
        if row is not None:
            return row
    except ValueError:
        pass
    if len(ref) < 8 or not all(c in "0123456789abcdef-" for c in ref):
        raise DiscoveryError(f"no proposal matches {ref!r}")
    rows = list(session.scalars(select(DiscoveryClaimProposal).where(
        (DiscoveryClaimProposal.digest.like(ref + "%"))
        | (text("id::text LIKE :p").bindparams(p=ref + "%")))))
    if len(rows) != 1:
        raise DiscoveryError(
            f"{ref!r} matches {len(rows)} proposals; use a longer prefix or the full id")
    return rows[0]


def canonical_choices(choices: dict[str, str] | None) -> dict[str, str]:
    """Deterministic, explicit form of resolved choices: stripped strings, sorted keys."""
    out: dict[str, str] = {}
    for key, value in (choices or {}).items():
        if not isinstance(key, str) or not key.strip():
            raise DiscoveryError("a resolved choice needs an explicit key")
        if not isinstance(value, str) or not value.strip():
            raise DiscoveryError(f"resolved choice {key!r} is blank; nothing is defaulted")
        out[key.strip()] = value.strip()
    return dict(sorted(out.items()))


def serialize_choices(choices: dict[str, str]) -> str:
    return json.dumps(choices, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _validate_choices(p: DiscoveryClaimProposal, decision: str,
                      choices: dict[str, str]) -> None:
    questions = list(p.review_questions)
    allowed = ({question_key(i) for i in range(1, len(questions) + 1)} | {HOME_KEY}
               | set(MAPPING_KEYS))
    unknown = sorted(set(choices) - allowed)
    if unknown:
        raise DiscoveryError(
            f"unknown resolved-choice key(s) {unknown}; this proposal has questions "
            f"{sorted(allowed - {HOME_KEY} - set(MAPPING_KEYS))}, the optional {HOME_KEY!r} "
            f"and the mapping keys {list(MAPPING_KEYS)}")
    if decision != ACCEPT:
        return
    missing = [f"{question_key(i)}: {q}" for i, q in enumerate(questions, 1)
               if question_key(i) not in choices]
    if missing:
        raise DiscoveryError(
            "ACCEPT needs an explicit resolved choice for every review question; "
            "unresolved: " + "; ".join(missing))
    if choices.get(HOME_KEY, "") not in ("", NO_CATALOGUE_HOME):
        raise DiscoveryError(
            f"{HOME_KEY!r} may only be {NO_CATALOGUE_HOME!r}: G2-2 maps nothing to the "
            "catalogue")
    if p.representability == "UNREPRESENTABLE" and choices.get(HOME_KEY) != NO_CATALOGUE_HOME:
        raise DiscoveryError(
            "this proposal has no catalogue home (UNREPRESENTABLE); ACCEPT must explicitly "
            f"record {HOME_KEY}={NO_CATALOGUE_HOME} (--no-catalogue-home). Nothing is guessed")


def decide(session: Session, ref: str, decision: str, *, decided_by: str, rationale: str,
           choices: dict[str, str] | None = None
           ) -> tuple[DiscoveryProposalDecision, bool]:
    """Record a human decision. Returns (row, created); an identical effective decision
    with identical resolved choices is a no-op that returns the existing row."""
    if decision not in DECISIONS:
        raise DiscoveryError(f"decision must be one of {DECISIONS}")
    if not decided_by or not decided_by.strip():
        raise DiscoveryError("a decision must name the human who made it (--by)")
    if not rationale or not rationale.strip():
        raise DiscoveryError("a decision needs a non-empty rationale (--reason)")
    p = resolve_proposal(session, ref)
    resolved = canonical_choices(choices)
    _validate_choices(p, decision, resolved)

    # Serialize concurrent decisions on one proposal so the no-op check is race-free.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                    {"k": f"proposal-decision:{p.id}"})
    [state] = derive_states(session, [p])
    if decision == ACCEPT:
        if state.superseded:
            raise DiscoveryError("this proposal is SUPERSEDED by a newer proposal in its slot; "
                                 "it cannot be accepted")
        if state.stale:
            raise DiscoveryError("this proposal is STALE and cannot be accepted: "
                                 + "; ".join(state.stale_reasons))
    eff = state.effective
    if eff is not None and eff.decision == decision and dict(eff.resolved_choices) == resolved:
        return eff, False
    row = DiscoveryProposalDecision(
        proposal_id=p.id, decision=decision, decided_by=decided_by.strip(),
        rationale=rationale.strip(), resolved_choices=resolved)
    session.add(row)
    session.flush()
    return row, True


def decision_history(session: Session, p: DiscoveryClaimProposal
                     ) -> list[DiscoveryProposalDecision]:
    return list(session.scalars(
        select(DiscoveryProposalDecision).where(DiscoveryProposalDecision.proposal_id == p.id)
        .order_by(DiscoveryProposalDecision.decision_seq)))


def render_show(session: Session, p: DiscoveryClaimProposal) -> list[str]:
    [st] = derive_states(session, [p])
    src = session.scalar(select(DiscoverySource.key).where(DiscoverySource.id == p.source_id))
    lines = [
        f"PROPOSAL {p.id}",
        f"  state            {st.state}" + ("" if st.acceptable else "  (cannot be accepted)"),
    ]
    lines += [f"    stale: {r}" for r in st.stale_reasons]
    lines += [
        f"  robot            {p.robot_slug}",
        f"  kind             {p.kind}",
        f"  scope            {p.edition or '(whole product / no edition)'}",
        f"  value (verbatim) {p.value}",
        f"  structured       {json.dumps(p.structured, sort_keys=True, ensure_ascii=False)}",
        f"  source           {src} {p.source_url}",
        f"  evidence         {p.evidence_excerpt}",
        f"  locator          {p.evidence_locator}",
        f"  extractor        {p.extractor_key}@{p.extractor_version} "
        f"({p.extraction_method}, confidence {p.extraction_confidence}, {p.claim_status})",
        f"  digest           {p.digest}",
        f"  slot             {p.slot_key}",
        f"  representability {p.representability}  target hint: {p.target}",
        f"  gap              {p.gap or '(none)'}",
        "  review questions " + ("(none)" if not p.review_questions else ""),
    ]
    lines += [f"    {question_key(i)}: {q}" for i, q in enumerate(p.review_questions, 1)]
    lines.append(f"  first seen       page {p.origin_fetched_page_id} run {p.origin_crawl_run_id}"
                 f" at {p.origin_retrieved_at:%Y-%m-%d %H:%M}Z hash {p.origin_content_hash[:16]}")
    lines.append(f"  sightings ({len(st.sightings)})")
    lines += [f"    page {s.fetched_page_id} run {s.crawl_run_id} "
              f"{s.retrieved_at:%Y-%m-%d %H:%M}Z hash {s.content_hash[:16]}" for s in st.sightings]
    history = decision_history(session, p)
    eff = st.effective
    lines.append("  effective decision " + ("(none)" if eff is None else
                 f"#{eff.decision_seq} {eff.decision} by {eff.decided_by}"))
    lines += [f"    #{d.decision_seq} {d.decision} by {d.decided_by} "
              f"{d.created_at:%Y-%m-%d %H:%M}Z: {d.rationale} "
              f"| choices {serialize_choices(dict(d.resolved_choices))}" for d in history]
    return lines
