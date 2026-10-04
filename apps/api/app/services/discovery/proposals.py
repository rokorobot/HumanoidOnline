"""G2-1 manual / offline ingest of extraction proposals — DR-A5 B-prime.

`ingest_neura_mini_proposals` runs the pure G1 extractor over a retained page body
and persists what it proposed: one immutable `discovery_claim_proposal` per distinct
proposal digest, plus one append-only `discovery_proposal_observation` per page it
was seen on. It is idempotent and writes NOTHING else: no decision, no accepted
claim, no `candidate_claim`, no catalogue row, no `is_published` change.

Provenance is checked, not trusted: the body's normalized fingerprint must equal the
recorded `fetched_page.content_hash`, the page must belong to the named source, and its
URL must be the page the extractor reads. New lineage never depends on an
`evidence_source` row id (the importer replaces those); it uses the source key, the
proposal digest, the observed page and the content hashes.

The effective state of a proposal (CURRENT / SUPERSEDED, and its newest human decision)
is derived on read, never stored.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
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
from app.services.discovery.fingerprint import fingerprint
from app.services.discovery.sources import maturity_proposals as maturity
from app.services.discovery.sources import neura_mini_proposals as mini
from app.services.discovery.sources import xpeng_iron_proposals as xpeng
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

CURRENT, SUPERSEDED = "CURRENT", "SUPERSEDED"

#: Operational origin of a proposal (G5, migration 0023). Metadata only: both origins use the
#: same governed review and accepted-claim pipeline and the same truth semantics.
NEW_MODEL, CATALOGUE_ENRICHMENT = "NEW_MODEL", "CATALOGUE_ENRICHMENT"
ORIGINS = (NEW_MODEL, CATALOGUE_ENRICHMENT)


def slot_key(source_key: str, robot_slug: str, kind: str, edition: str | None,
             locator: str) -> str:
    """Deterministic identity of what a proposal is ABOUT (never its value)."""
    payload = json.dumps([source_key, robot_slug, kind, edition, locator], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class IngestReport:
    status: str
    fetched_page_id: str
    proposals_seen: int = 0
    proposals_created: int = 0
    observations_created: int = 0
    unchanged: int = 0
    notes: list[str] = field(default_factory=list)
    rejected: list = field(default_factory=list)   # (item, why) the extractor refused

    def as_dict(self) -> dict:
        return {"status": self.status, "fetched_page_id": self.fetched_page_id,
                "proposals_seen": self.proposals_seen,
                "proposals_created": self.proposals_created,
                "observations_created": self.observations_created,
                "unchanged": self.unchanged, "notes": list(self.notes),
                "rejected": [list(r) for r in self.rejected],
                "writes_catalogue": False, "writes_decisions": False}


@dataclass(frozen=True)
class ExtractorSpec:
    """One reviewed, deterministic proposal extractor and the identity it may attach to."""

    key: str
    version: str
    robot_name: str              # the catalogue name the robot must carry (identity gate)
    page_urls: tuple[str, ...] | None   # the only normalized page URLs it reads; None = any
                                        # page the governed fetcher already retrieved
    propose: Callable[[bytes, str], Any]
    proposed_status: str = "PROPOSED"


NEURA_MINI_SPEC = ExtractorSpec(
    key=mini.EXTRACTOR_KEY, version=mini.EXTRACTOR_VERSION, robot_name=mini.ROBOT_NAME,
    page_urls=(mini.MINI_URL,),
    propose=lambda body, url: mini.propose_neura_mini_claims(body, url))

XPENG_IRON_SPEC = ExtractorSpec(
    key=xpeng.EXTRACTOR_KEY, version=xpeng.EXTRACTOR_VERSION, robot_name=xpeng.ROBOT_NAME,
    page_urls=tuple(xpeng.PAGE_URLS),
    propose=lambda body, url: xpeng.propose_xpeng_iron_claims(body, url))


def maturity_spec(robot_name: str, page_scope: str = maturity.SHARED_PAGE) -> ExtractorSpec:
    """The COMMERCIAL_MATURITY extractor bound to one robot (identity) and one page scope.

    It reads whatever first-party page the governed fetcher already retrieved for an approved
    source (eligibility was enforced at fetch time), and attaches wording to this robot only."""
    return ExtractorSpec(
        key=maturity.EXTRACTOR_KEY, version=maturity.EXTRACTOR_VERSION, robot_name=robot_name,
        page_urls=None,
        propose=lambda body, url: maturity.propose_maturity_clues(
            body, url, robot_name=robot_name, page_scope=page_scope))


def ingest_neura_mini_proposals(session: Session, **kw) -> IngestReport:
    """Persist the G1 4NE1 Mini proposals read from `body`, observed as `fetched_page_id`."""
    return ingest_proposals(session, spec=NEURA_MINI_SPEC, **kw)


def ingest_xpeng_iron_proposals(session: Session, **kw) -> IngestReport:
    """Persist the XPENG IRON proposals read from `body`, observed as `fetched_page_id`."""
    return ingest_proposals(session, spec=XPENG_IRON_SPEC, **kw)


def ingest_proposals(session: Session, *, spec: ExtractorSpec, source_key: str,
                     robot_slug: str, fetched_page_id, body: bytes,
                     ingested_by: str, origin: str = CATALOGUE_ENRICHMENT) -> IngestReport:
    """Persist the proposals `spec` reads from `body`, observed as `fetched_page_id`."""
    if origin not in ORIGINS:
        raise DiscoveryError(f"proposal origin must be one of {ORIGINS}")
    if not ingested_by or not ingested_by.strip():
        raise DiscoveryError("ingest must name the human who ran it (--by)")
    who = ingested_by.strip()
    source = session.scalar(select(DiscoverySource).where(DiscoverySource.key == source_key))
    if source is None:
        raise DiscoveryError(f"unknown discovery source {source_key!r}")
    page = session.get(FetchedPage, fetched_page_id)
    if page is None:
        raise DiscoveryError(f"unknown fetched page {fetched_page_id!r}")
    if page.source_id != source.id:
        raise DiscoveryError("the fetched page does not belong to the named source")
    try:
        page_url = normalize_url(page.final_url or page.url)
    except UnsupportedUrl as exc:
        raise DiscoveryError(f"fetched page has no usable URL: {exc}") from exc
    if spec.page_urls is not None and page_url not in spec.page_urls:
        raise DiscoveryError(
            f"this ingest reads {' or '.join(spec.page_urls)} only, not {page_url}")
    if not page.content_hash or fingerprint(body, page.content_type) != page.content_hash:
        raise DiscoveryError(
            "the supplied body does not match the observation's recorded content_hash; "
            "refusing to attribute these bytes to that observation")
    robot = session.scalar(select(Robot).where(Robot.slug == robot_slug))
    if robot is None or robot.name != spec.robot_name:
        raise DiscoveryError(
            f"robot {robot_slug!r} is not the catalogue's {spec.robot_name!r}; "
            "proposals attach to one existing robot identity")

    result = spec.propose(body, page_url)
    report = IngestReport(result.status, str(page.id), notes=list(result.notes),
                          rejected=[list(r) for r in result.rejected])
    if result.status != spec.proposed_status:
        return report

    for p in result.proposals:
        report.proposals_seen += 1
        row = session.scalar(
            select(DiscoveryClaimProposal).where(DiscoveryClaimProposal.digest == p.digest))
        if row is not None and row.robot_slug != robot_slug:
            raise DiscoveryError(
                f"identical proposal content already belongs to another robot "
                f"({row.robot_slug!r}); "
                "refusing to attach it to a second identity")
        if row is None:
            row = DiscoveryClaimProposal(
                digest=p.digest,
                slot_key=slot_key(source.key, robot_slug, p.kind, p.edition, p.evidence.locator),
                source_id=source.id, source_url=p.source_url, robot_slug=robot_slug,
                edition=p.edition, kind=p.kind, target=p.target,
                representability=p.representability, value=p.value,
                structured=dict(p.structured), evidence_excerpt=p.evidence.excerpt,
                evidence_locator=p.evidence.locator, extraction_method=p.method,
                extraction_confidence=p.confidence, claim_status=p.claim_status, gap=p.gap,
                review_questions=list(p.review_required),
                extractor_key=spec.key, extractor_version=spec.version,
                origin_fetched_page_id=page.id, origin_crawl_run_id=page.crawl_run_id,
                origin_content_hash=page.content_hash, origin_retrieved_at=page.retrieved_at,
                ingested_by=who, origin=origin)
            session.add(row)
            session.flush()
            report.proposals_created += 1
        seen = session.scalar(
            select(DiscoveryProposalObservation.id).where(
                DiscoveryProposalObservation.proposal_id == row.id,
                DiscoveryProposalObservation.fetched_page_id == page.id))
        if seen is None:
            session.add(DiscoveryProposalObservation(
                proposal_id=row.id, fetched_page_id=page.id, crawl_run_id=page.crawl_run_id,
                content_hash=page.content_hash, retrieved_at=page.retrieved_at,
                observed_by=who))
            session.flush()
            report.observations_created += 1
        else:
            report.unchanged += 1
    return report


def proposal_states(session: Session, robot_slug: str) -> list[dict]:
    """Read-only: each proposal with derived supersession and its newest decision."""
    rows = session.scalars(
        select(DiscoveryClaimProposal).where(DiscoveryClaimProposal.robot_slug == robot_slug)
        .order_by(DiscoveryClaimProposal.proposal_seq)).all()
    newest_in_slot: dict[str, int] = {}
    for r in rows:
        newest_in_slot[r.slot_key] = max(newest_in_slot.get(r.slot_key, 0), r.proposal_seq)
    states = []
    for r in rows:
        decision = session.scalar(
            select(DiscoveryProposalDecision).where(DiscoveryProposalDecision.proposal_id == r.id)
            .order_by(DiscoveryProposalDecision.decision_seq.desc()).limit(1))
        states.append({
            "id": str(r.id), "digest": r.digest, "kind": r.kind, "edition": r.edition,
            "target": r.target, "representability": r.representability, "value": r.value,
            "state": CURRENT if newest_in_slot[r.slot_key] == r.proposal_seq else SUPERSEDED,
            "decision": decision.decision if decision else None,
        })
    return states
