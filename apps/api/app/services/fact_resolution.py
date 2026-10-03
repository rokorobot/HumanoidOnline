"""Canonical scoped fact resolution (DR-G4, phase G4-1): the pure resolver and projection registry.

`UNKNOWN` means "no accepted canonical knowledge at product or variant scope" — never "known at
variant scope but not exposed". This module is the ONE place that turns scoped canonical facts into
a resolved fact:

    resolved_fact = f(product core value, scoped canonical facts, projection registry version)

It is a pure function: no I/O, no randomness, no LLM, no database. Identical input and registry
give identical output. A resolved value is derived, never stored, and never written back into a
robot-level column. The verbatim accepted facts are untouched (a projection is additive).

Projection is EXACT: a registered specification key plus a registered, whitespace-normalized,
case-sensitive token. There is no substring search, no stemming and no fuzzy matching. Absence of a
token is never `false`; a negative value can come only from a separately ratified negative token
(none exist in the initial registry). Unregistered wording is simply not projected: it stays a
detail fact (DR-G4 section 4.2).

Consumers (detail, filters, matching, compare, agent tools) are integrated in G4-2; this module
does not touch them.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

REGISTRY_VERSION = "0.1.0-g4-initial"


class State(StrEnum):
    PRODUCT_VALUE = "PRODUCT_VALUE"
    UNIFORM_VARIANTS = "UNIFORM_VARIANTS"
    VARIES_BY_VARIANT = "VARIES_BY_VARIANT"
    PARTIAL_VARIANTS = "PARTIAL_VARIANTS"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"      # an integrity failure: it must fail readiness / publication


@dataclass(frozen=True)
class ProjectionRule:
    spec_key: str
    token: str
    property: str
    value: bool


# The initial registry, ratified by the owner on 2026-10-03 (DR-G4 section 4.1). Every addition
# is an owner decision and bumps REGISTRY_VERSION. It must equal
# tests/fixtures/g4/initial_registry.json.
#
# Deliberately NOT mapped: "Not included" (absence of an option is not absence of a capability),
# "12 DoF dexterous hands" -> hand_dof (convention and scope do not permit it), "ROS 2 interface" ->
# has_api, and every detail-only token (Wi-Fi 6, Ethernet, NEURA Sync, digital twin access, ...).
PROJECTION_REGISTRY: tuple[ProjectionRule, ...] = (
    ProjectionRule("common_interfaces", "Python SDK", "has_sdk", True),
    ProjectionRule("additional_interfaces", "C++ SDK", "has_sdk", True),
    ProjectionRule("common_interfaces", "ROS 2 interface", "ros_support", True),
    ProjectionRule("additional_interfaces", "teleoperation", "has_teleoperation", True),
    ProjectionRule("dexterous_hand_option", "12 DoF dexterous hands", "has_manipulation", True),
)

# A single-valued specification key is ONE token (its whole value); every other registered key is a
# comma-separated list of tokens.
SINGLE_VALUED_KEYS = frozenset({"dexterous_hand_option"})

# The canonical properties the registry can project. Others resolve from product scope only.
PROJECTED_PROPERTIES = tuple(sorted({r.property for r in PROJECTION_REGISTRY}))


class ResolutionError(ValueError):
    """The input itself is inconsistent (a scoped fact names a variant the robot does not have)."""


@dataclass(frozen=True)
class ScopedSpec:
    """One canonical `specification` row: product level (`variant_slug` None) or variant-scoped."""
    variant_slug: str | None
    spec_key: str
    value: str | None


@dataclass(frozen=True)
class VariantValue:
    slug: str
    name: str
    value: bool | None                 # None = unknown for this configuration
    evidence: tuple[tuple[str, str], ...] = ()      # (spec_key, token) pairs that established it


@dataclass(frozen=True)
class ResolvedFact:
    property: str
    state: State
    value: bool | None                 # the one value for PRODUCT_VALUE / UNIFORM, else None
    product_value: bool | None         # the product-scope value, if any
    product_source: str | None         # "core" | "projection" | None
    variants: tuple[VariantValue, ...]
    registry_version: str = REGISTRY_VERSION
    detail: str | None = None          # why, for CONFLICT


def normalize_token(token: str) -> str:
    """Whitespace-normalize only. Case is preserved: matching is exact."""
    return " ".join(token.split())


def tokens_of(spec_key: str, value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if spec_key in SINGLE_VALUED_KEYS:
        t = normalize_token(value)
        return (t,) if t else ()
    return tuple(t for t in (normalize_token(p) for p in value.split(",")) if t)


def project(
    spec: ScopedSpec, registry: Sequence[ProjectionRule] = PROJECTION_REGISTRY
) -> tuple[tuple[str, bool, str], ...]:
    """The registered projections of ONE specification row: (property, value, token) triples."""
    out: list[tuple[str, bool, str]] = []
    for token in tokens_of(spec.spec_key, spec.value):
        for rule in registry:
            if rule.spec_key == spec.spec_key and rule.token == token:
                out.append((rule.property, rule.value, token))
    return tuple(out)


def _scope_value(
    prop: str, specs: Iterable[ScopedSpec], registry: Sequence[ProjectionRule]
) -> tuple[bool | None, tuple[tuple[str, str], ...], bool]:
    """(value, evidence, self_conflicting) for one scope's rows and one property."""
    values: set[bool] = set()
    evidence: list[tuple[str, str]] = []
    for spec in specs:
        for p, v, token in project(spec, registry):
            if p == prop:
                values.add(v)
                evidence.append((spec.spec_key, token))
    ev = tuple(sorted(set(evidence)))
    if len(values) > 1:
        return None, ev, True
    return (next(iter(values)) if values else None), ev, False


def resolve_property(
    prop: str,
    product_value: bool | None,
    variants: Sequence[tuple[str, str]],
    specs: Sequence[ScopedSpec],
    registry: Sequence[ProjectionRule] = PROJECTION_REGISTRY,
) -> ResolvedFact:
    """Resolve ONE property for one robot.

    `variants` are the robot's documented variants as (slug, name); `specs` are its canonical
    specification rows (product level and variant-scoped); `product_value` is the robot's core
    column for the property (None when NULL).
    """
    known = {slug for slug, _ in variants}
    for s in specs:
        if s.variant_slug is not None and s.variant_slug not in known:
            raise ResolutionError(
                f"specification {s.spec_key!r} names variant {s.variant_slug!r}, which is not one "
                f"of the robot's documented variants {sorted(known)}")

    def conflict(detail: str, pv: bool | None, src: str | None,
                 vv: tuple[VariantValue, ...]) -> ResolvedFact:
        return ResolvedFact(prop, State.CONFLICT, None, pv, src, vv, REGISTRY_VERSION, detail)

    # Variant scope.
    vvalues: list[VariantValue] = []
    for slug, name in variants:
        value, ev, selfc = _scope_value(
            prop, [s for s in specs if s.variant_slug == slug], registry)
        vv = VariantValue(slug, name, value, ev)
        if selfc:
            return conflict(f"variant {slug!r} states both true and false", product_value, None,
                            tuple(vvalues) + (vv,))
        vvalues.append(vv)
    vtuple = tuple(vvalues)

    # Product scope: the core column, else a product-level registered projection.
    pvalue, _evidence, pself = _scope_value(
        prop, [s for s in specs if s.variant_slug is None], registry)
    if pself:
        return conflict("product scope states both true and false", product_value, None, vtuple)
    if product_value is not None:
        if pvalue is not None and pvalue != product_value:
            return conflict("the product column and a product-level projection disagree",
                            product_value, "core", vtuple)
        product, source = product_value, "core"
    elif pvalue is not None:
        product, source = pvalue, "projection"
    else:
        product, source = None, None

    # Scoped evidence contradicting the product value is an integrity failure; the product
    # value never silently wins.
    if product is not None:
        for vv in vtuple:
            if vv.value is not None and vv.value != product:
                return conflict(
                    f"variant {vv.slug!r} ({vv.value}) contradicts the product value ({product})",
                    product, source, vtuple)
        return ResolvedFact(prop, State.PRODUCT_VALUE, product, product, source, vtuple)

    known_values = [vv.value for vv in vtuple if vv.value is not None]
    if not known_values:
        return ResolvedFact(prop, State.UNKNOWN, None, None, None, vtuple)
    if len(known_values) < len(vtuple):
        return ResolvedFact(prop, State.PARTIAL_VARIANTS, None, None, None, vtuple)
    if len(set(known_values)) == 1:
        return ResolvedFact(prop, State.UNIFORM_VARIANTS, known_values[0], None, None, vtuple)
    return ResolvedFact(prop, State.VARIES_BY_VARIANT, None, None, None, vtuple)


def resolve_robot(
    product_values: Mapping[str, bool | None],
    variants: Sequence[tuple[str, str]],
    specs: Sequence[ScopedSpec],
    properties: Sequence[str] = PROJECTED_PROPERTIES,
    registry: Sequence[ProjectionRule] = PROJECTION_REGISTRY,
) -> dict[str, ResolvedFact]:
    """Resolve every requested property for one robot (keyed by property, sorted)."""
    return {
        p: resolve_property(p, product_values.get(p), variants, specs, registry)
        for p in sorted(properties)}


# --------------------------------------------------------------------------------------------
# Consumer semantics (DR-G4 section 6). Pure helpers so G4-2 and the tests share one definition.
# --------------------------------------------------------------------------------------------


def satisfies_hard_requirement(fact: ResolvedFact) -> bool:
    """CONSERVATIVE matching: only a PRODUCT_VALUE or UNIFORM_VARIANTS `true` satisfies a required
    boolean capability at robot scope. VARIES_BY_VARIANT, PARTIAL_VARIANTS, UNKNOWN and CONFLICT
    never do (they are unknown/ineligible for a hard requirement, never treated as true)."""
    return fact.state in (State.PRODUCT_VALUE, State.UNIFORM_VARIANTS) and fact.value is True


@dataclass(frozen=True)
class AnyVariantMatch:
    matches: bool
    product_wide: bool                 # True: every configuration has it; False: only some
    configurations: tuple[str, ...]    # the configurations that have it (slugs), for labelling

    @property
    def label(self) -> str | None:
        """Disclosure for a discovery result that is not product-wide."""
        if self.matches and not self.product_wide:
            return "Available on some configurations"
        return None


def any_variant_match(fact: ResolvedFact) -> AnyVariantMatch:
    """ANY-VARIANT filter semantics for a positive capability filter. A search projection only:
    it never mutates the robot column. CONFLICT never matches."""
    if fact.state is State.CONFLICT:
        return AnyVariantMatch(False, False, ())
    if fact.state is State.PRODUCT_VALUE:
        return AnyVariantMatch(fact.value is True, fact.value is True, ())
    have = tuple(vv.slug for vv in fact.variants if vv.value is True)
    if not have:
        return AnyVariantMatch(False, False, ())
    return AnyVariantMatch(True, len(have) == len(fact.variants), have)
