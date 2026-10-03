"""Adapter between the canonical catalogue rows and the single G4 resolver (DR-G4, G4-2).

This module contains NO semantics. It only (a) turns ORM / database rows into the plain inputs of
`services/fact_resolution.py`, (b) calls that pure resolver, and (c) shapes the result for the API.
Every consumer (detail, compare, list filters, the matching inputs and the agent tools) goes
through here, so there is exactly one interpretation of scoped facts.

Resolved values are derived on read. They are never stored and never written back into a robot
column.
"""
from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.robot import Robot, RobotVariant
from app.models.spec import SpecDefinition, Specification
from app.schemas.robot import (
    ProjectionEvidenceRead,
    ResolvedFactRead,
    ResolvedVariantValueRead,
    ScopeNoteRead,
    SourceFactRead,
)
from app.services import fact_resolution as fr
from app.services.fact_resolution import ResolvedFact, ScopedSpec, State

#: The registered properties, in a stable order.
RESOLVED_PROPERTIES: tuple[str, ...] = fr.PROJECTED_PROPERTIES

#: Robot columns the registered properties resolve their product value from.
PRODUCT_COLUMNS: tuple[str, ...] = RESOLVED_PROPERTIES


def resolve_loaded_robot(robot: Robot) -> dict[str, ResolvedFact]:
    """Resolve one robot whose `variants` and `specifications` (with `definition`) are loaded."""
    slug_by_id = {v.id: v.slug for v in robot.variants}
    variants = [(v.slug, v.name) for v in sorted(robot.variants, key=lambda v: v.slug)]
    specs = [
        ScopedSpec(slug_by_id.get(s.variant_id), s.definition.key, s.value_text)
        for s in robot.specifications
    ]
    product = {p: getattr(robot, p) for p in PRODUCT_COLUMNS}
    return fr.resolve_robot(product, variants, specs, RESOLVED_PROPERTIES)


def to_read(
    fact: ResolvedFact, *, source_facts: dict[str, list[SourceFactRead]] | None = None
) -> ResolvedFactRead:
    src = source_facts or {}
    return ResolvedFactRead(
        property=fact.property,
        state=fact.state.value,
        value=fact.value,
        product_value=fact.product_value,
        product_source=fact.product_source,
        variants=[
            ResolvedVariantValueRead(
                slug=v.slug,
                name=v.name,
                value=v.value,
                evidence=[ProjectionEvidenceRead(spec_key=k, token=t) for k, t in v.evidence],
                source_facts=src.get(v.slug, []),
            )
            for v in fact.variants
        ],
        registry_version=fact.registry_version,
        detail=fact.detail,
    )


def resolved_facts_for(robot: Robot) -> list[ResolvedFactRead]:
    """The `resolved_facts` array of the robot detail (properties in stable order).

    Verbatim accepted facts of the registered SINGLE-VALUED keys (e.g. the dexterous hand option)
    travel with their variant, so "Not included" stays visible next to an unknown manipulation.
    """
    facts = resolve_loaded_robot(robot)
    slug_by_id = {v.id: v.slug for v in robot.variants}
    registry_keys: dict[str, set[str]] = {}
    for rule in fr.PROJECTION_REGISTRY:
        if rule.spec_key in fr.SINGLE_VALUED_KEYS:
            registry_keys.setdefault(rule.property, set()).add(rule.spec_key)
    out: list[ResolvedFactRead] = []
    for prop in sorted(facts):
        keys = registry_keys.get(prop, set())
        source: dict[str, list[SourceFactRead]] = {}
        for s in robot.specifications:
            slug = slug_by_id.get(s.variant_id)
            if slug is not None and s.definition.key in keys and s.value_text:
                source.setdefault(slug, []).append(
                    SourceFactRead(key=s.definition.key, label=s.definition.label,
                                   value=s.value_text))
        out.append(to_read(facts[prop], source_facts=source))
    return out


def load_resolutions(
    session: Session, robot_ids: Collection[uuid.UUID] | None = None
) -> dict[uuid.UUID, dict[str, ResolvedFact]]:
    """Resolve many robots with THREE queries (robots, variants, specifications): never one per
    property or per variant. `robot_ids=None` resolves every robot."""
    cols = [Robot.id] + [getattr(Robot, p) for p in PRODUCT_COLUMNS]
    q = select(*cols)
    if robot_ids is not None:
        if not robot_ids:
            return {}
        q = q.where(Robot.id.in_(list(robot_ids)))
    rows = session.execute(q).all()
    ids = [r[0] for r in rows]
    products = {r[0]: dict(zip(PRODUCT_COLUMNS, r[1:], strict=True)) for r in rows}

    variants: dict[uuid.UUID, list[tuple[str, str]]] = {i: [] for i in ids}
    slug_by_variant: dict[uuid.UUID, str] = {}
    for rid, vid, slug, name in session.execute(
        select(RobotVariant.robot_id, RobotVariant.id, RobotVariant.slug, RobotVariant.name)
        .where(RobotVariant.robot_id.in_(ids))
        .order_by(RobotVariant.robot_id, RobotVariant.slug)
    ).all():
        variants[rid].append((slug, name))
        slug_by_variant[vid] = slug

    specs: dict[uuid.UUID, list[ScopedSpec]] = {i: [] for i in ids}
    registered_keys = sorted({r.spec_key for r in fr.PROJECTION_REGISTRY})
    for rid, vid, key, value in session.execute(
        select(Specification.robot_id, Specification.variant_id, SpecDefinition.key,
               Specification.value_text)
        .join(SpecDefinition, SpecDefinition.id == Specification.definition_id)
        .where(Specification.robot_id.in_(ids))
        .where(SpecDefinition.key.in_(registered_keys))
    ).all():
        specs[rid].append(ScopedSpec(slug_by_variant.get(vid), key, value))

    return {
        i: fr.resolve_robot(products[i], variants[i], specs[i], RESOLVED_PROPERTIES)
        for i in ids
    }


def resolutions_for_session(
    session: Session,
) -> dict[uuid.UUID, dict[str, ResolvedFact]]:
    """All robots, memoised on the session so one request resolves once (the count, page and
    notice statements of a filtered list share it)."""
    memo = session.info.get("g4_resolutions")
    if memo is None:
        memo = load_resolutions(session)
        session.info["g4_resolutions"] = memo
    return memo


# ----------------------------------------------------------------------------------------
# Filter semantics (DR-G4 section 6): ANY-VARIANT for a positive filter; the id sets feed SQL.
# ----------------------------------------------------------------------------------------


def _satisfies(fact: ResolvedFact, wanted: bool) -> bool:
    if wanted:
        return fr.any_variant_match(fact).matches
    # An explicit "false" requirement is satisfied only when the property is known to be
    # absent on every documented configuration (PRODUCT_VALUE / UNIFORM false). Conservative.
    return fact.state in (State.PRODUCT_VALUE, State.UNIFORM_VARIANTS) and fact.value is False


def _is_unknown(fact: ResolvedFact) -> bool:
    """Excluded for want of knowledge (the docs/20 section 9.4 notice): nothing known, or some
    configuration unknown and none known to satisfy."""
    if fact.state is State.UNKNOWN:
        return True
    return fact.state is State.PARTIAL_VARIANTS and not any(
        v.value is True for v in fact.variants)


def capability_id_sets(
    session: Session, prop: str, wanted: bool
) -> tuple[frozenset[uuid.UUID], frozenset[uuid.UUID]]:
    """(satisfied robot ids, unknown robot ids) for a positive/negative capability filter."""
    satisfied: set[uuid.UUID] = set()
    unknown: set[uuid.UUID] = set()
    for rid, facts in resolutions_for_session(session).items():
        fact = facts[prop]
        if _satisfies(fact, wanted):
            satisfied.add(rid)
        elif _is_unknown(fact):
            unknown.add(rid)
    return frozenset(satisfied), frozenset(unknown)


def scope_notes_for(
    session: Session, robot_ids: Iterable[uuid.UUID], requested: dict[str, bool | None]
) -> dict[uuid.UUID, list[ScopeNoteRead]]:
    """Disclosure notes for robots that matched an active POSITIVE filter on only some
    configurations. Empty for product-wide matches."""
    active = [p for p, v in requested.items() if v is True and p in RESOLVED_PROPERTIES]
    if not active:
        return {}
    res = resolutions_for_session(session)
    out: dict[uuid.UUID, list[ScopeNoteRead]] = {}
    for rid in robot_ids:
        for prop in active:
            fact = res.get(rid, {}).get(prop)
            if fact is None:
                continue
            m = fr.any_variant_match(fact)
            if m.label:
                out.setdefault(rid, []).append(ScopeNoteRead(
                    property=prop, label=m.label, configurations=list(m.configurations)))
    return out


def conservative_boolean(fact: ResolvedFact) -> bool | None:
    """The robot-level boolean the deterministic matching engine may use (DR-G4 section 6):
    `True` only through `satisfies_hard_requirement`; `False` only for a known product-wide
    absence; everything else is unknown (None), never true and never false."""
    if fr.satisfies_hard_requirement(fact):
        return True
    if fact.state in (State.PRODUCT_VALUE, State.UNIFORM_VARIANTS) and fact.value is False:
        return False
    return None
