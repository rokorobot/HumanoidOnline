"""Market discovery scope (`docs/20` §12.1) — and its distance from eligibility.

`applicable_region_ids` answers "does this offer apply to a buyer here?" and
walks UPWARD (region + ancestors + GLOBAL). `discovery_region_ids` answers
"whose offers should a buyer browsing this market see?" and additionally walks
DOWNWARD, so an EU browser finds what a German supplier lists.

The whole risk of adding the second walk is that it quietly becomes the first
one — that a `DE` offer surfaced by `offered_in=EU` starts being treated as
evidence of EU-wide applicability. These tests pin the two apart: the downward
step must exist in discovery and must NOT exist in eligibility. The eligibility
half is asserted here too, deliberately duplicating
`test_region_applicability.py`, because the property that matters is the
*difference* between them, and a test that reads only one side cannot see it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.region import Region
from app.services.regions import (
    MARKET_RANK_AGNOSTIC,
    MARKET_RANK_ANCESTOR,
    MARKET_RANK_DESCENDANT,
    MARKET_RANK_EXACT,
    MARKET_RANK_GLOBAL,
    applicable_region_ids,
    discovery_market_rank,
    discovery_region_ids,
)


def _id_of(session, code: str):
    return session.execute(
        select(Region.id).where(Region.code == code)
    ).scalar_one_or_none()


def _require(session, *codes):
    ids = {c: _id_of(session, c) for c in codes}
    missing = [c for c, v in ids.items() if v is None]
    if missing:
        pytest.skip(f"regions not present in this dataset: {', '.join(missing)}")
    return ids


def test_discovery_includes_descendants_where_eligibility_does_not() -> None:
    """The one behavioural difference, stated as one assertion pair.

    A German supplier's offer must be FINDABLE when browsing the EU market, and
    must still not be ELIGIBLE EU-wide. Both halves are the point.
    """
    with SessionLocal() as s:
        ids = _require(s, "DE", "EU")
        assert ids["DE"] in discovery_region_ids(s, code="EU")
        assert ids["DE"] not in applicable_region_ids(s, code="EU")


def test_discovery_still_includes_ancestors_and_global() -> None:
    """Widening downward must not cost the upward walk: an EU-wide offer and a
    worldwide one are both discoverable from DE."""
    with SessionLocal() as s:
        ids = _require(s, "DE", "EU")
        found = discovery_region_ids(s, code="DE")
        assert ids["DE"] in found
        assert ids["EU"] in found
        global_id = _id_of(s, "GLOBAL")
        if global_id is not None:
            assert global_id in found


def test_unknown_code_discovers_nothing() -> None:
    """A typo matches nothing rather than widening to the whole catalogue — the
    same failure direction the eligibility resolver already enforces."""
    with SessionLocal() as s:
        assert discovery_region_ids(s, code="NOT-A-REGION") == set()


def test_market_rank_orders_exact_before_ancestor_before_descendant() -> None:
    """Rank is precedence INSIDE a market, not a quality judgement about offers.

    An EU-scoped offer is a better answer to "browsing the EU" than one scoped
    to a single member state, and both beat worldwide and region-agnostic.
    """
    with SessionLocal() as s:
        _require(s, "DE", "EU")
        ranks = discovery_market_rank(s, code="EU")
        assert ranks["EU"] == MARKET_RANK_EXACT
        assert ranks["DE"] == MARKET_RANK_DESCENDANT
        assert ranks[None] == MARKET_RANK_AGNOSTIC
        assert ranks["EU"] < ranks["DE"] < ranks[None]
        if "GLOBAL" in ranks:
            assert ranks["DE"] < ranks["GLOBAL"] <= MARKET_RANK_GLOBAL

        from_de = discovery_market_rank(s, code="DE")
        assert from_de["DE"] == MARKET_RANK_EXACT
        assert from_de["EU"] == MARKET_RANK_ANCESTOR


def test_market_rank_keys_are_exactly_the_discoverable_regions() -> None:
    """Filtering and ranking must come from ONE interpretation of geography.

    If the rank map could name a region the discovery set excludes (or omit one
    it includes), a caller could rank an offer it must not show, or drop one it
    must. The two are built from the same walk, and this pins that.
    """
    with SessionLocal() as s:
        _require(s, "EU")
        ranked_codes = {c for c in discovery_market_rank(s, code="EU") if c is not None}
        discoverable = discovery_region_ids(s, code="EU")
        codes = {
            code
            for (code,) in s.execute(
                select(Region.code).where(Region.id.in_(discoverable))
            ).all()
        }
        assert ranked_codes == codes


def test_unknown_market_ranks_nothing() -> None:
    with SessionLocal() as s:
        assert discovery_market_rank(s, code="NOT-A-REGION") == {}
