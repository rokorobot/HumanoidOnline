"""Parity for the canonical region resolver (`services/regions.py`).

The applicability walk — region + ancestors + GLOBAL — previously existed in two
independent copies (`matching/repository.py`, `leads/routing.py`). The canonical
resolver must agree with **both** before any consumer migrates to it, otherwise
consolidation would silently change ratified matching or lead-routing behaviour.

These tests are the safety net for that migration. `search_robots` already uses
the canonical resolver; the other two consumers are follow-up work and are left
untouched deliberately.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.region import Region
from app.services.leads.routing import _applicable_region_ids as leads_resolver
from app.services.matching.repository import (
    _applicable_region_ids as matching_resolver,
)
from app.services.regions import applicable_region_ids


def _code_exists(session, code: str) -> bool:
    return session.execute(
        select(Region.id).where(Region.code == code)
    ).scalar_one_or_none() is not None


def test_matches_the_matching_repository_walk() -> None:
    """Same answer as the ratified matching resolver, for a COUNTRY."""
    with SessionLocal() as s:
        for code in ("US", "DE", "CN"):
            if not _code_exists(s, code):
                continue
            expected = matching_resolver(s, code)
            actual = applicable_region_ids(s, code=code, require_type="COUNTRY")
            assert actual == expected, f"divergence for {code}"


def test_matches_the_lead_routing_walk() -> None:
    """Same answer as the ratified lead-routing resolver, keyed by id."""
    with SessionLocal() as s:
        for code in ("US", "DE", "EU"):
            rid = s.execute(
                select(Region.id).where(Region.code == code)
            ).scalar_one_or_none()
            if rid is None:
                continue
            assert applicable_region_ids(s, region_id=rid) == leads_resolver(s, rid)


def test_global_is_always_applicable() -> None:
    with SessionLocal() as s:
        global_id = s.execute(
            select(Region.id).where(Region.code == "GLOBAL")
        ).scalar_one_or_none()
        if global_id is None:
            pytest.skip("no GLOBAL region in this dataset")
        for code in ("US", "DE", "EU"):
            if _code_exists(s, code):
                assert global_id in applicable_region_ids(s, code=code)


def test_ancestors_are_included_but_descendants_are_not() -> None:
    """DE resolves EU (its ancestor); EU must NOT resolve DE (its descendant) —
    an EU-wide query is not evidence about one member state's offers."""
    with SessionLocal() as s:
        de = s.execute(select(Region.id).where(Region.code == "DE")).scalar_one_or_none()
        eu = s.execute(select(Region.id).where(Region.code == "EU")).scalar_one_or_none()
        if de is None or eu is None:
            pytest.skip("DE/EU regions not present in this dataset")
        assert eu in applicable_region_ids(s, code="DE")
        assert de not in applicable_region_ids(s, code="EU")


def test_unknown_code_resolves_to_nothing() -> None:
    """A typo must match nothing, never silently widen to GLOBAL."""
    with SessionLocal() as s:
        assert applicable_region_ids(s, code="NOT-A-REGION") == set()


def test_requires_exactly_one_addressing_form() -> None:
    with SessionLocal() as s:
        with pytest.raises(ValueError):
            applicable_region_ids(s)
        with pytest.raises(ValueError):
            applicable_region_ids(s, code="US", region_id=object())  # type: ignore[arg-type]
