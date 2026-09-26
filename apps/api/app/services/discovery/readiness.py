"""Read-only foundation prerequisites; not permission or readiness to crawl.

Reports initialization prerequisites only. A source counted here satisfies the
source-level acquisition policy (`eligibility.source_acquisition_eligible`:
radar-eligible, approved host and path prefixes). That never
authorizes network acquisition by itself: a live run additionally needs
robots.txt evaluated for each exact URL at fetch time (docs/16 LIVE.2) and a
separately authorized operator run. ToS expiry and page-hash currency are not
prerequisites (owner decision DR-A4). Passing these checks never makes execution
available.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.services.discovery.bootstrap import bootstrap_source_key, load_dataset, validate_dataset
from app.services.discovery.eligibility import source_acquisition_eligible

BASELINE_DATASET = "humanoid_radar_v1"


@dataclass(frozen=True)
class DiscoveryReadiness:
    baseline_source_present: bool
    expected_lead_count: int
    missing_lead_refs: tuple[str, ...]
    eligible_source_keys: tuple[str, ...]

    @property
    def missing_prerequisites(self) -> tuple[str, ...]:
        missing = []
        if not self.baseline_source_present:
            missing.append("LEAD_BASELINE_SOURCE_MISSING")
        if self.missing_lead_refs:
            missing.append("LEAD_BASELINE_INCOMPLETE")
        if not self.eligible_source_keys:
            missing.append("NO_RADAR_ELIGIBLE_LIVE_SOURCE")
        return tuple(missing)

    @property
    def prerequisites_ready(self) -> bool:
        return not self.missing_prerequisites

    @property
    def execution_ready(self) -> bool:
        return False  # Stage A has no runner, regardless of database contents.


def check_readiness(session: Session) -> DiscoveryReadiness:
    """Inspect the committed baseline's exact refs under its own source.

    No commit, flush, registration or bootstrap. Disable autoflush so inspecting
    readiness cannot persist unrelated pending changes in the caller's session.
    Manual-bootstrap eligibility is explicitly not live-source eligibility.
    """
    records = load_dataset(BASELINE_DATASET)
    validate_dataset(records)
    expected = {str(record["external_ref"]) for record in records}
    with session.no_autoflush:
        sources = session.scalars(select(DiscoverySource)).all()
        baseline = next(
            (s for s in sources if s.key == bootstrap_source_key(BASELINE_DATASET)), None
        )
        present = set() if baseline is None else set(session.scalars(
            select(DiscoveryCandidate.external_ref).where(
                DiscoveryCandidate.source_id == baseline.id,
                DiscoveryCandidate.entity_type == "ROBOT",
            )
        ))
    return DiscoveryReadiness(
        baseline_source_present=baseline is not None,
        expected_lead_count=len(expected),
        missing_lead_refs=tuple(sorted(expected - present)),
        eligible_source_keys=tuple(sorted(
            s.key for s in sources
            if not s.key.startswith("manual-bootstrap:") and source_acquisition_eligible(s)
        )),
    )
