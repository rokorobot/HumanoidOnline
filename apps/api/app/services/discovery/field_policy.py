"""Field-policy registry skeleton — DR-A5 section 8 (G2-1: three columns, no new mapping).

The registry says which catalogue targets a reviewed proposal may ever be mapped to.
In G2-1 it is deliberately a skeleton: it contains exactly the three numeric columns
the existing promotion gate already approves (height_cm, weight_kg, payload_kg), taken
from that gate so the two cannot drift. No other target, and no price, availability,
use-case or interface semantics, is approved here; those are separate owner decisions.
Persisting a proposal never consults or extends this registry.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.discovery.promotion import _APPROVED_FIELDS

REGISTRY_VERSION = "0.1.0-skeleton"


@dataclass(frozen=True)
class FieldPolicy:
    target: str
    unit: str | None


def _build() -> dict[str, FieldPolicy]:
    return {key: FieldPolicy(target=column, unit=unit)
            for key, (column, unit, _tolerance) in _APPROVED_FIELDS.items()}


REGISTRY: dict[str, FieldPolicy] = _build()


def policy_for(target_hint: str) -> FieldPolicy | None:
    """The registered policy for a proposal's target hint, or None (unmapped = UNKNOWN)."""
    return REGISTRY.get(target_hint)


# --------------------------------------------------------------------------------------
# G2-3 first vertical slice: proposal-based claim policies (owner-approved 2026-10-02/03).
#
# Exactly two registered targets, nothing else. Price, availability, reservation, use
# cases, interfaces and every other mapping are NOT registered and are refused.
# --------------------------------------------------------------------------------------
CLAIM_REGISTRY_VERSION = "0.2.0-g2-3-first-slice"

# The resolved-choice keys that carry the human's explicit catalogue mapping.
MAPPING_KEYS = ("target_kind", "variant_slug", "variant_name", "spec_key", "edition_scope",
                "accepted_value")

SPEC_DEFINITION_KEY = "dexterous_hand_option"
SPEC_LOCATOR_PREFIX = "feature-grid/row[Manipulation]/"


@dataclass(frozen=True)
class ClaimPolicy:
    key: str
    proposal_kind: str
    target_kind: str       # robot_variant | specification
    target_key: str        # 'variant' | spec_definition.key
    value_type: str = "TEXT"
    edition_scope: str | None = None
    requires_variant: bool = False


CLAIM_POLICIES: dict[str, ClaimPolicy] = {
    "robot_variant": ClaimPolicy(
        key="robot_variant", proposal_kind="VARIANT", target_kind="robot_variant",
        target_key="variant"),
    f"specification[{SPEC_DEFINITION_KEY}]": ClaimPolicy(
        key=f"specification[{SPEC_DEFINITION_KEY}]", proposal_kind="SPECIFICATION",
        target_kind="specification", target_key=SPEC_DEFINITION_KEY,
        edition_scope="THIS_EDITION", requires_variant=True),
}


def claim_policy_for(kind: str, target_hint: str, locator: str) -> ClaimPolicy | None:
    """The registered claim policy for a proposal, or None (unregistered = refused)."""
    if kind == "VARIANT" and target_hint == "robot_variant":
        return CLAIM_POLICIES["robot_variant"]
    if (kind == "SPECIFICATION" and target_hint == f"specification[{SPEC_DEFINITION_KEY}]"
            and locator.startswith(SPEC_LOCATOR_PREFIX)):
        return CLAIM_POLICIES[f"specification[{SPEC_DEFINITION_KEY}]"]
    return None
