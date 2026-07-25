"""Source adapters + candidate ingest (DATA-D1 §25-A/B).

A `SourceAdapter` turns a discovery source into raw candidates. v0.1 ships only
`FixtureAdapter` (local JSON, NO network) because no radar source has passed the
DATA-D1.9 ToS/robots eligibility review yet; live network adapters are a later,
separately-gated step. Ingest is the only writer here, and it writes ONLY to the
discovery layer (never canonical — Gate H), with minimal retention (DATA-D1.10).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
)
from app.services.discovery import DiscoveryError


@dataclass
class RawClaim:
    field_key: str
    claimed_value: str | None = None
    unit: str | None = None
    evidence_url: str | None = None


@dataclass
class RawImageRef:
    image_url: str
    credited_to: str | None = None


@dataclass
class RawCandidate:
    external_ref: str
    entity_type: str = "ROBOT"
    name: str | None = None
    manufacturer: str | None = None
    discovery_url: str | None = None
    # A source may EXPOSE an official-URL lead; it is a trace lead, not proof.
    data: dict = field(default_factory=dict)
    claims: list[RawClaim] = field(default_factory=list)
    images: list[RawImageRef] = field(default_factory=list)


class SourceAdapter(Protocol):
    def discover(self, source: DiscoverySource) -> list[RawCandidate]: ...


class FixtureAdapter:
    """Deterministic, offline adapter. Reads candidates from an in-memory list or
    a local JSON file — no HTTP, no competitor extraction."""

    def __init__(
        self, records: list[dict] | None = None, path: str | Path | None = None
    ) -> None:
        if records is None and path is not None:
            records = json.loads(Path(path).read_text(encoding="utf-8"))
        self._records = records or []

    def discover(self, source: DiscoverySource) -> list[RawCandidate]:
        out: list[RawCandidate] = []
        for rec in self._records:
            out.append(
                RawCandidate(
                    external_ref=str(rec["external_ref"]),
                    entity_type=rec.get("entity_type", "ROBOT"),
                    name=rec.get("name"),
                    manufacturer=rec.get("manufacturer"),
                    discovery_url=rec.get("discovery_url"),
                    data=rec.get("data", {}),
                    claims=[RawClaim(**c) for c in rec.get("claims", [])],
                    images=[RawImageRef(**i) for i in rec.get("images", [])],
                )
            )
        return out


def ingest(
    session: Session, source: DiscoverySource, adapter: SourceAdapter
) -> list[DiscoveryCandidate]:
    """Run `adapter` against `source` and upsert candidates into the discovery
    layer. Refuses ineligible sources (DATA-D1.9). Dedups by (source, external_ref):
    a re-seen candidate only refreshes `last_seen_at` (no duplicate row, §21).

    Writes ONLY discovery tables — never canonical (Gate H). Does not commit; the
    caller owns the transaction.
    """
    if not source.radar_eligible:
        raise DiscoveryError(
            f"source {source.key!r} is not radar-eligible: ToS/robots review + "
            "enablement required before crawling (DATA-D1.9)"
        )

    created: list[DiscoveryCandidate] = []
    for raw in adapter.discover(source):
        existing = session.execute(
            select(DiscoveryCandidate).where(
                DiscoveryCandidate.source_id == source.id,
                DiscoveryCandidate.external_ref == raw.external_ref,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.last_seen_at = _now(session)
            continue

        cand = DiscoveryCandidate(
            source_id=source.id,
            entity_type=raw.entity_type,
            candidate_name=raw.name,
            candidate_manufacturer=raw.manufacturer,
            discovery_url=raw.discovery_url,
            external_ref=raw.external_ref,
            candidate_data=raw.data or None,
        )
        for c in raw.claims:
            cand.claims.append(
                CandidateClaim(
                    field_key=c.field_key,
                    claimed_value=c.claimed_value,
                    unit=c.unit,
                    evidence_url=c.evidence_url,
                    discovery_source_id=source.id,
                )
            )
        for im in raw.images:
            cand.images.append(
                CandidateImageRef(
                    image_url=im.image_url,
                    credited_to=im.credited_to,
                    discovery_source_id=source.id,
                )
            )
        session.add(cand)
        created.append(cand)

    session.flush()
    return created


def _now(session: Session):
    """DB clock, so `last_seen_at` is consistent with server_default timestamps."""
    from sqlalchemy import func

    return session.execute(select(func.now())).scalar_one()
