"""AGENT-02.1f — the UNKNOWN hard-constraint exclusion notice (`docs/20` §9.2/§9.4/§15).

A hard constraint is satisfied only by a *confirmed* value, so a robot whose
constrained fact is UNKNOWN is excluded — correctly, and unchanged by this slice.
What was missing is the notice §15 requires: without it, a caller asking
`has_sdk=true` cannot tell "we checked and it has no SDK" apart from "nobody has
recorded whether it does", and would reasonably read the shorter list as the
former.

The notice is deliberately blunt — one generic code, no counts, no identities.
Its whole job is to say *uncertainty was excluded here*, not to characterise the
robots excluded. What it must never do is imply the robots failed on a recorded
value: that is the difference between `null` and `false`, and this contract exists
to keep those apart.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import HARD_CONSTRAINT_EXCLUDED_UNKNOWN as UNKNOWN_WARNING
from app.services.agent_tools import search_robots
from app.services.agent_tools.pricing import (
    EXCLUDED_ABOVE_LIMIT,
    EXCLUDED_UNPROVABLE,
)


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def probe():
    """A private manufacturer plus robots under it, and queries scoped to them.

    Every query in this file is scoped by `manufacturer=<this fixture's slug>`,
    which matters more than it looks. The seeded catalogue is full of legitimate
    NULLs, so an unscoped `has_sdk=true` warns because of *seed* robots — which
    would make the negative cases fail and, worse, let the positive cases pass
    without the fixture proving anything. `manufacturer` is a relational
    constraint on a NOT NULL column, so the detector never relaxes it and it
    isolates these tests exactly.
    """
    mfr_slug = f"unknown-probe-mfr-{uuid.uuid4().hex[:10]}"
    mfr_id = _exec(
        "INSERT INTO manufacturer (slug, name) VALUES (:s, :n) RETURNING id",
        s=mfr_slug, n=mfr_slug.upper(),
    ).scalar_one()
    created: list = []

    class Probe:
        manufacturer = mfr_slug

        @staticmethod
        def robot(*, published: bool = True, prices=None, **cols) -> str:
            slug = f"unknown-probe-{uuid.uuid4().hex[:10]}"
            extra_cols = "".join(f", {k}" for k in cols)
            extra_vals = "".join(f", :{k}" for k in cols)
            rid = _exec(
                f"INSERT INTO robot (slug, manufacturer_id, name, is_published"
                f"{extra_cols}) VALUES (:s, :m, :n, :p{extra_vals}) RETURNING id",
                s=slug, m=mfr_id, n=slug.upper(), p=published, **cols,
            ).scalar_one()
            created.append(rid)
            for price_type, currency, amount in prices or []:
                _exec(
                    "INSERT INTO pricing_offer (robot_id, transaction_type,"
                    " price_type, currency, price, is_current) VALUES (:r,"
                    " 'PURCHASE', CAST(:pt AS price_type), :c, :a, TRUE)",
                    r=rid, pt=price_type, c=currency, a=amount,
                )
            return slug

        @staticmethod
        def result(**kw):
            with SessionLocal() as s:
                return search_robots(s, manufacturer=mfr_slug, limit=100, **kw)

        @staticmethod
        def warned(**kw) -> bool:
            return UNKNOWN_WARNING in Probe.result(**kw).warnings

    yield Probe
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)
    _exec("DELETE FROM manufacturer WHERE id = :i", i=mfr_id)


# --------------------------------------------------------------------------
# UNKNOWN vs a known negative — the distinction the notice exists to preserve
# --------------------------------------------------------------------------


def test_unknown_flag_on_an_otherwise_eligible_robot_warns(probe, database_url):
    slug = probe.robot()  # has_sdk NULL
    res = probe.result(has_sdk=True)
    assert slug not in {i.slug for i in res.items}, "UNKNOWN must not satisfy"
    assert UNKNOWN_WARNING in res.warnings


def test_a_known_false_value_is_not_an_unknown_exclusion(probe, database_url):
    """`false` is a recorded fact. Excluding it is an answer, not uncertainty."""
    probe.robot(has_sdk=False)
    assert not probe.warned(has_sdk=True)


def test_a_negative_requirement_also_excludes_unknown(probe, database_url):
    """`has_sdk=false` asks for a confirmed absence. NULL satisfies neither
    explicit boolean requirement, so it is excluded — and reported."""
    slug = probe.robot()  # has_sdk NULL
    res = probe.result(has_sdk=False)
    assert slug not in {i.slug for i in res.items}
    assert UNKNOWN_WARNING in res.warnings


def test_an_excluded_robot_still_reports_null_never_false(probe, database_url):
    """The result set is unchanged and the value is never rewritten (§9.2)."""
    slug = probe.robot()
    item = next(i for i in probe.result().items if i.slug == slug)
    assert item.payload_kg is None
    assert item.payload_kg is not False and item.payload_kg != 0
    assert item.mobility is None


# --------------------------------------------------------------------------
# EVERY NULLABLE CONSTRAINED FIELD
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "known_good"),
    [
        ({"payload_min": 5}, {"payload_kg": 50}),
        ({"height_min": 100}, {"height_cm": 150}),
        ({"height_max": 200}, {"height_cm": 150}),
        ({"mobility": "BIPEDAL"}, {"mobility": "BIPEDAL"}),
        ({"autonomy_min": "ASSISTED"}, {"autonomy": "HIGHLY_AUTONOMOUS"}),
        ({"has_sdk": True}, {"has_sdk": True}),
        ({"ros_support": True}, {"ros_support": True}),
        ({"developer_edition": True}, {"developer_edition": True}),
        ({"has_manipulation": True}, {"has_manipulation": True}),
    ],
    ids=["payload_min", "height_min", "height_max", "mobility", "autonomy_min",
         "has_sdk", "ros_support", "developer_edition", "has_manipulation"],
)
def test_each_nullable_constrained_field_reports_its_unknowns(
    probe, database_url, query, known_good
):
    unknown = probe.robot()            # the constrained field is NULL
    confirmed = probe.robot(**known_good)

    res = probe.result(**query)
    found = {i.slug for i in res.items}
    assert confirmed in found, "a confirmed value must still qualify"
    assert unknown not in found, "UNKNOWN must not satisfy a hard constraint"
    assert UNKNOWN_WARNING in res.warnings


@pytest.mark.parametrize(
    ("query", "known_bad"),
    [
        ({"payload_min": 50}, {"payload_kg": 1}),
        ({"height_min": 200}, {"height_cm": 100}),
        ({"height_max": 100}, {"height_cm": 200}),
        ({"mobility": "BIPEDAL"}, {"mobility": "WHEELED"}),
        ({"autonomy_min": "TASK_AUTONOMOUS"}, {"autonomy": "TELEOPERATED"}),
        ({"ros_support": True}, {"ros_support": False}),
    ],
    ids=["payload_min", "height_min", "height_max", "mobility", "autonomy_min",
         "ros_support"],
)
def test_a_known_value_that_fails_is_never_reported_as_unknown(
    probe, database_url, query, known_bad
):
    """Recorded values that simply don't qualify are answers, not uncertainty."""
    probe.robot(**known_bad)
    assert not probe.warned(**query)


# --------------------------------------------------------------------------
# PRECISION — the notice must not fire for the wrong reason
# --------------------------------------------------------------------------


def test_a_robot_failing_another_constraint_on_a_known_value_does_not_warn(
    probe, database_url
):
    """The case a careless implementation gets wrong.

    This robot has `has_sdk` UNKNOWN, but its payload is *recorded* and below the
    floor. It was excluded by a known fact, not by uncertainty, so it must not
    make the response claim uncertainty was excluded.
    """
    probe.robot(payload_kg=2)  # has_sdk NULL
    assert not probe.warned(has_sdk=True, payload_min=10)


def test_the_same_robot_does_warn_once_the_known_value_qualifies(
    probe, database_url
):
    """The mirror of the previous case — same UNKNOWN, qualifying payload."""
    probe.robot(payload_kg=20)  # has_sdk NULL
    assert probe.warned(has_sdk=True, payload_min=10)


def test_unrelated_unknowns_are_not_reported(probe, database_url):
    """A NULL on a field nobody constrained is not an exclusion."""
    probe.robot(has_sdk=True)  # payload/height/mobility NULL but unconstrained
    assert not probe.warned(has_sdk=True)


def test_no_warning_when_no_nullable_fact_is_constrained(probe, database_url):
    probe.robot()
    assert not probe.warned()
    assert not probe.warned(commercial_status=["COMMERCIAL"])


def test_multiple_unknown_fields_produce_exactly_one_warning(probe, database_url):
    probe.robot()  # has_sdk, ros_support and payload_kg all NULL
    res = probe.result(has_sdk=True, ros_support=True, payload_min=1)
    assert res.warnings.count(UNKNOWN_WARNING) == 1


def test_a_robot_excluded_by_a_relational_constraint_does_not_warn(
    probe, database_url
):
    """Region/availability exclusions are not nullable-fact exclusions."""
    probe.robot()  # has_sdk NULL, and no availability offer at all
    assert not probe.warned(has_sdk=True, region="US")


# --------------------------------------------------------------------------
# PUBLICATION (AGENT-01.7)
# --------------------------------------------------------------------------


def test_an_unpublished_unknown_robot_cannot_trigger_the_warning(
    probe, database_url
):
    """The notice must not become a side channel revealing withheld records."""
    probe.robot(published=False)  # has_sdk NULL
    assert not probe.warned(has_sdk=True)


def test_the_warning_carries_no_identities_or_counts(probe, database_url):
    probe.robot()
    probe.robot()
    res = probe.result(has_sdk=True)
    assert UNKNOWN_WARNING in res.warnings
    for w in res.warnings:
        assert not any(ch.isdigit() for ch in w)
        assert "unknown-probe" not in w


# --------------------------------------------------------------------------
# commercial_status is NOT a nullable fact (docs/20 §9.1)
# --------------------------------------------------------------------------


def test_filtering_out_commercial_status_unknown_is_not_this_warning(
    probe, database_url
):
    """`UNKNOWN` there is an explicit enum member on a NOT NULL column — an
    ordinary enum exclusion, not an unrecorded fact."""
    probe.robot(commercial_status="UNKNOWN")
    assert not probe.warned(commercial_status=["COMMERCIAL"])


# --------------------------------------------------------------------------
# PAGINATION AND RESULT INVARIANCE
# --------------------------------------------------------------------------


def test_warning_state_is_independent_of_page_size(probe, database_url):
    probe.robot()
    for _ in range(3):
        probe.robot(has_sdk=True)
    for extra in ({"limit": 1}, {"limit": 2, "offset": 2}, {"limit": 100}):
        with SessionLocal() as s:
            res = search_robots(
                s, manufacturer=probe.manufacturer, has_sdk=True, **extra
            )
        assert UNKNOWN_WARNING in res.warnings, extra


def test_results_and_total_are_unchanged_by_the_notice(probe, database_url):
    unknown = probe.robot()
    confirmed = probe.robot(has_sdk=True)
    res = probe.result(has_sdk=True)
    assert {i.slug for i in res.items} == {confirmed}
    assert unknown not in {i.slug for i in res.items}
    assert res.total == 1


# --------------------------------------------------------------------------
# COMPOSITION WITH THE PRICE REASON CODES (docs/20 §10.3)
# --------------------------------------------------------------------------


def test_price_and_unknown_warnings_compose_without_changing_meaning(
    probe, database_url
):
    probe.robot(has_sdk=True, prices=[("QUOTE_ONLY", "GBP", None)])  # unprovable
    probe.robot(has_sdk=True, prices=[("PUBLIC", "GBP", 999999)])    # above limit
    probe.robot(prices=[("PUBLIC", "GBP", 1000)])                    # sdk UNKNOWN

    res = probe.result(has_sdk=True, price_max=30000, price_currency="GBP")
    assert UNKNOWN_WARNING in res.warnings
    assert EXCLUDED_UNPROVABLE in res.warnings
    assert EXCLUDED_ABOVE_LIMIT in res.warnings


def test_price_warning_definitions_are_untouched(probe, database_url):
    """A price-only query still reports only price reasons."""
    probe.robot(prices=[("QUOTE_ONLY", "GBP", None)])
    res = probe.result(price_max=30000, price_currency="GBP")
    assert UNKNOWN_WARNING not in res.warnings
    assert EXCLUDED_UNPROVABLE in res.warnings


def test_a_robot_failing_on_a_known_price_does_not_warn_as_unknown(
    probe, database_url
):
    """Composition precision: an above-limit price is a known failure, so this
    robot's UNKNOWN `has_sdk` is not what excluded it."""
    probe.robot(prices=[("PUBLIC", "GBP", 999999)])  # has_sdk NULL, price too high
    assert not probe.warned(has_sdk=True, price_max=30000, price_currency="GBP")


def test_warnings_are_sorted_and_deduplicated(probe, database_url):
    probe.robot(prices=[("PUBLIC", "GBP", 1000)])
    probe.robot(has_sdk=True, prices=[("QUOTE_ONLY", "GBP", None)])
    res = probe.result(has_sdk=True, price_max=30000, price_currency="GBP")
    assert res.warnings == sorted(res.warnings)
    assert len(res.warnings) == len(set(res.warnings))


def test_the_warning_is_not_an_error_code(probe, database_url):
    """§17 — reason codes and error codes are disjoint vocabularies."""
    probe.robot()
    res = probe.result(has_sdk=True)
    assert UNKNOWN_WARNING in res.warnings
    assert UNKNOWN_WARNING not in {
        "INVALID_ARGUMENT", "INVALID_ENUM", "INVALID_PAGINATION",
        "NOT_FOUND", "RATE_LIMITED", "INTERNAL",
    }


# --------------------------------------------------------------------------
# THE DETECTOR IS BOUNDED
# --------------------------------------------------------------------------


def test_detection_never_materialises_excluded_robots(probe, database_url):
    """Structural: the notice is an EXISTS over the query, so no robot-row query
    may run unbounded (`docs/20` §16)."""
    import re

    from sqlalchemy import event

    for _ in range(5):
        probe.robot()
    for _ in range(3):
        probe.robot(has_sdk=True)

    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.split()).lower())

    event.listen(engine, "after_cursor_execute", record)
    try:
        with SessionLocal() as s:
            res = search_robots(
                s, manufacturer=probe.manufacturer, has_sdk=True, limit=2
            )
    finally:
        event.remove(engine, "after_cursor_execute", record)

    assert UNKNOWN_WARNING in res.warnings
    assert res.total > res.limit
    unbounded = [
        q for q in seen
        if re.search(r"\brobot\.slug\b", q) and " limit " not in q
    ]
    assert not unbounded, "unbounded robot-row query:\n" + "\n\n".join(unbounded)
