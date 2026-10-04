"""G2-5 — scheduled proposal ingestion for the approved NEURA 4NE1 Mini source (DR-A5).

After a governed observation run (the SAME `_run_one` path for the scheduler, a manual
dispatch and `--run-now`), this step looks at the newest retrieved content of the one
registered page. If that observation has not yet been turned into proposal sightings and
its body is retained, it runs the deterministic G1 extractor over the retained bytes and
persists the result through the G2-1 ingest (`proposals.ingest_neura_mini_proposals`):

    observation -> immutable proposal / sighting -> human review queue      (and stops)

It writes `discovery_claim_proposal` and `discovery_proposal_observation` rows ONLY. It
never records a decision, creates a claim, retraction or audit row, touches a catalogue
table or JSON, or changes `is_published`; every provenance check of the G2-1 ingest
(source ownership, URL, recorded content hash vs the body, identity gate) still applies.

Idempotent and self-healing: the newest content observation is processed once (a re-run
creates nothing), and an earlier failure is retried on the next cycle because the newest
content observation still has no sighting. An unchanged page (a 304 answer) adds no
content, so nothing is re-ingested and the proposals stay CURRENT. Failures are never
swallowed: they are returned for the cycle result to surface for an operator, while the
observation itself stays preserved.

Deliberately NOT generalized: each source is listed explicitly with its approved page(s), robot
and extractor (`G2_INGESTS`): NEURA's 4NE1 Mini page, and XPENG's four reviewed IRON pages.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim_proposal import DiscoveryProposalObservation
from app.models.discovery import DiscoverySource
from app.services.discovery import cache as body_cache
from app.services.discovery.proposal_review import latest_content_page_for
from app.services.discovery.proposals import (
    ingest_neura_mini_datasheet_proposals,
    ingest_neura_mini_proposals,
    ingest_xpeng_iron_proposals,
)
from app.services.discovery.sources import neura_mini_datasheet_proposals as mini_ds
from app.services.discovery.sources import neura_mini_proposals as mini
from app.services.discovery.sources import xpeng_iron_proposals as xpeng

#: A "/" cell is a placeholder, deliberately not read as a value: a standing, benign rejection.
BENIGN_REJECTION = "placeholder '/'"
UP_TO_DATE, NO_OBSERVATION, INGESTED, FAILED = (
    "UP_TO_DATE", "NO_OBSERVATION", "INGESTED", "FAILED")


@dataclass(frozen=True)
class G2Ingest:
    """The approved page(s) of one approved source, its robot and its extractor."""

    page_url: str
    robot_slug: str
    ingest: Callable = ingest_neura_mini_proposals
    #: Further approved pages of the same source (read by the same extractor), if any.
    more_page_urls: tuple[str, ...] = ()

    @property
    def page_urls(self) -> tuple[str, ...]:
        return (self.page_url, *self.more_page_urls)


#: The ONLY wiring. Another page, source or manufacturer needs its own approval and entry.
G2_INGESTS: Mapping[str, G2Ingest] = {
    "neura-robotics-official": G2Ingest(page_url=mini.MINI_URL, robot_slug="4ne1-mini"),
    # G5-2 (owner source decision 2026-10-04): the Mini datasheet on the approved document host.
    "neura-documents-official": G2Ingest(
        page_url=mini_ds.DATASHEET_URL, robot_slug="4ne1-mini",
        ingest=ingest_neura_mini_datasheet_proposals),
    # XPENG IRON (owner source approval 2026-10-03): the four reviewed xpeng.com pages only.
    "xpeng-official": G2Ingest(
        page_url=xpeng.PAGE_URLS[0], robot_slug="xpeng-iron", ingest=ingest_xpeng_iron_proposals,
        more_page_urls=tuple(xpeng.PAGE_URLS[1:])),
}


@dataclass
class G2Result:
    status: str
    detail: str = ""
    fetched_page_id: str | None = None
    proposals_seen: int = 0
    proposals_created: int = 0
    sightings_created: int = 0
    rejected: list = field(default_factory=list)

    @property
    def attention(self) -> bool:
        """A human must look: an ingest failure, a fail-safe rejection (the page no longer
        reads as expected), or new proposals (new slot or changed value: re-review)."""
        return (self.status == FAILED or bool(self.unexpected_rejections)
                or self.proposals_created > 0)

    @property
    def unexpected_rejections(self) -> list:
        """Fail-safe rejections other than the page's standing "/" placeholder (the real
        page has one by design, e.g. 'Additional interfaces / Standard'): any other one
        means the page no longer reads as the extractor expects."""
        return [r for r in self.rejected if not str(r[1]).startswith(BENIGN_REJECTION)]

    def summary(self) -> str:
        if self.status == FAILED:
            return f"G2 INGEST FAILED: {self.detail}"
        if self.status in (UP_TO_DATE, NO_OBSERVATION):
            return f"G2 proposals {self.status.lower().replace('_', ' ')}"
        text = (f"G2 proposals ingested: {self.proposals_created} new / "
                f"{self.sightings_created} sighting(s) / {self.proposals_seen} seen")
        if self.unexpected_rejections:
            text += (f" / {len(self.unexpected_rejections)} UNEXPECTED item(s) rejected by "
                     "fail-safe rules (the page may have changed shape)")
        if self.proposals_created:
            text += " (new proposals need human review)"
        return text

    def as_dict(self) -> dict:
        return {"status": self.status, "detail": self.detail,
                "fetched_page_id": self.fetched_page_id,
                "proposals_seen": self.proposals_seen,
                "proposals_created": self.proposals_created,
                "sightings_created": self.sightings_created,
                "rejected": [list(r) for r in self.rejected],
                "unexpected_rejections": [list(r) for r in self.unexpected_rejections],
                "attention": self.attention,
                "writes_decisions": False, "writes_claims": False, "writes_catalogue": False}


def _ingest_page(session: Session, source: DiscoverySource, cfg: G2Ingest, page_url: str,
                 cache_dir: Path, operator: str,
                 checkpoint: Callable[[], None] | None) -> G2Result:
    """One registered page: ingest its newest retrieved content if it has no sighting yet."""
    page = latest_content_page_for(session, source.id, page_url)
    if page is None:
        return G2Result(NO_OBSERVATION, f"no retrieved content for {page_url} yet")
    already = session.scalar(
        select(DiscoveryProposalObservation.id).where(
            DiscoveryProposalObservation.fetched_page_id == page.id).limit(1))
    if already is not None:
        return G2Result(UP_TO_DATE, fetched_page_id=str(page.id))
    body = body_cache.read_observed_body(cache_dir, str(page.id))
    if body is None:
        return G2Result(
            FAILED, f"the body of observation {page.id} ({page_url}) is not retained in the "
            "cache; proposals cannot be extracted from it (provenance is never reconstructed)",
            fetched_page_id=str(page.id))
    with session.begin_nested():      # a failed ingest leaves no partial rows
        report = cfg.ingest(session, source_key=source.key, robot_slug=cfg.robot_slug,
                            fetched_page_id=page.id, body=body, ingested_by=operator)
    if report.status != "PROPOSED":
        return G2Result(
            FAILED, f"extraction produced no proposals from {page_url} ({report.status}): "
            + "; ".join(report.notes), fetched_page_id=str(page.id))
    if checkpoint is not None:
        checkpoint()
    return G2Result(INGESTED, fetched_page_id=str(page.id),
                    proposals_seen=report.proposals_seen,
                    proposals_created=report.proposals_created,
                    sightings_created=report.observations_created,
                    rejected=list(report.rejected))


def _combine(results: list[G2Result]) -> G2Result:
    """One result for a multi-page source: any failure fails the whole (and is listed)."""
    if len(results) == 1:
        return results[0]
    failed = [r for r in results if r.status == FAILED]
    if failed:
        return G2Result(FAILED, "; ".join(r.detail for r in failed),
                        proposals_seen=sum(r.proposals_seen for r in results),
                        proposals_created=sum(r.proposals_created for r in results),
                        sightings_created=sum(r.sightings_created for r in results),
                        rejected=[x for r in results for x in r.rejected])
    ingested = [r for r in results if r.status == INGESTED]
    if not ingested:
        status = NO_OBSERVATION if all(r.status == NO_OBSERVATION for r in results) else UP_TO_DATE
        return G2Result(status, "; ".join(r.detail for r in results if r.detail))
    return G2Result(INGESTED, f"{len(ingested)} of {len(results)} pages ingested",
                    proposals_seen=sum(r.proposals_seen for r in results),
                    proposals_created=sum(r.proposals_created for r in results),
                    sightings_created=sum(r.sightings_created for r in results),
                    rejected=[x for r in results for x in r.rejected])


def ingest_for_source(session: Session, source: DiscoverySource, *, cache_dir: Path,
                      operator: str, checkpoint: Callable[[], None] | None = None,
                      registry: Mapping[str, G2Ingest] = G2_INGESTS) -> G2Result | None:
    """Ingest proposals for `source` if it is a registered G2 source; None otherwise.

    Never raises: any problem becomes a FAILED result for the cycle to surface."""
    cfg = registry.get(source.key)
    if cfg is None:
        return None
    results: list[G2Result] = []
    for page_url in cfg.page_urls:
        try:
            results.append(_ingest_page(session, source, cfg, page_url, cache_dir, operator,
                                        checkpoint))
        except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
            results.append(G2Result(FAILED, f"{page_url}: {type(exc).__name__}: {exc}"))
    return _combine(results)
