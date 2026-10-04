"""Database loader for the regional availability read model (impure).

Materializes the canonical catalogue into `RegionalSnapshot`. Only PUBLISHED
robots are loaded (defence in depth: the read model also drops unpublished
robots). No aggregation happens here; that is `readmodel.py`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evidence import EvidenceSource
from app.models.region import Region
from app.models.robot import Robot

from .inputs import (
    DeploymentRow,
    EvidenceRow,
    OfferRow,
    PriceRow,
    RegionalSnapshot,
    RegionNode,
    RobotRow,
)


def _day(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _evidence_by_subject(session: Session, subject_type: str, ids: list) -> dict:
    out: dict = defaultdict(list)
    if not ids:
        return out
    rows = session.execute(
        select(EvidenceSource).where(
            EvidenceSource.subject_type == subject_type,
            EvidenceSource.subject_id.in_(ids),
        )
    ).scalars()
    for e in rows:
        if not e.source_url:
            continue  # an evidence row without a URL is not citable provenance
        out[e.subject_id].append(
            EvidenceRow(
                source_url=e.source_url,
                confidence=e.confidence,
                observed_at=_day(e.observed_at),
                verified_at=_day(e.verified_at),
            )
        )
    return out


def load_regional_snapshot(session: Session, snapshot_date: date) -> RegionalSnapshot:
    regions = session.execute(select(Region)).scalars().all()
    code_by_id = {r.id: r.code for r in regions}
    nodes = tuple(
        RegionNode(r.code, r.name, code_by_id.get(r.parent_id)) for r in regions
    )

    robots = (
        session.execute(
            select(Robot)
            .where(Robot.is_published.is_(True))
            .options(
                selectinload(Robot.manufacturer),
                selectinload(Robot.availability_offers),
                selectinload(Robot.pricing_offers),
                selectinload(Robot.deployments),
            )
        )
        .scalars()
        .all()
    )
    offer_ids = [o.id for r in robots for o in r.availability_offers]
    price_ids = [p.id for r in robots for p in r.pricing_offers]
    deployment_ids = [d.id for r in robots for d in r.deployments]
    deployment_ev = _evidence_by_subject(session, "DEPLOYMENT", deployment_ids)
    offer_ev = _evidence_by_subject(session, "AVAILABILITY_OFFER", offer_ids)
    price_ev = _evidence_by_subject(session, "PRICING_OFFER", price_ids)

    rows = []
    for r in robots:
        offers = tuple(
            OfferRow(
                provider_slug=o.provider.slug if o.provider else None,
                provider_type=o.provider.type if o.provider else None,
                region_code=code_by_id.get(o.region_id),
                transaction_type=o.transaction_type,
                availability_status=o.availability_status,
                is_current=o.is_current,
                evidence=tuple(offer_ev.get(o.id, ())),
            )
            for o in r.availability_offers
        )
        prices = tuple(
            PriceRow(
                provider_slug=p.provider.slug if p.provider else None,
                region_code=code_by_id.get(p.region_id),
                transaction_type=p.transaction_type,
                price_type=p.price_type,
                currency=p.currency,
                price=float(p.price) if p.price is not None else None,
                price_min=float(p.price_min) if p.price_min is not None else None,
                price_max=float(p.price_max) if p.price_max is not None else None,
                billing_period=p.billing_period,
                price_basis=p.price_basis,
                is_current=p.is_current,
                evidence=tuple(price_ev.get(p.id, ())),
            )
            for p in r.pricing_offers
        )
        deployments = tuple(
            DeploymentRow(
                region_code=code_by_id.get(d.region_id),
                customer_name=d.customer_name,
                provider_slug=d.provider.slug if d.provider else None,
                transaction_type=d.transaction_type,
                unit_count=d.unit_count,
                started_on=d.started_on,
                status=d.status,
                evidence=tuple(deployment_ev.get(d.id, ())),
            )
            for d in r.deployments
        )
        rows.append(
            RobotRow(
                slug=r.slug,
                name=r.name,
                manufacturer_slug=r.manufacturer.slug,
                manufacturer_name=r.manufacturer.name,
                is_published=r.is_published,
                commercial_status=r.commercial_status,
                offers=offers,
                prices=prices,
                deployments=deployments,
            )
        )
    return RegionalSnapshot(snapshot_date, nodes, tuple(rows))
