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
CLAIM_REGISTRY_VERSION = "0.5.0-xpeng-iron-hand-dof"

# The resolved-choice keys that carry the human's explicit catalogue mapping.
MAPPING_KEYS = ("target_kind", "variant_slug", "variant_name", "spec_key", "edition_scope",
                "accepted_value",
                # G2-4 offer mapping (owner decisions): every value is stated, none defaulted.
                "price_type", "transaction_type", "billing_period", "currency", "price",
                "region", "provider", "edition_confirmed", "availability_status",
                "available_from", "delivery_estimate_label",
                # XPENG IRON (owner decision 2026-10-03): which configuration is current.
                "configuration",
                # hand DoF convention (owner decision 2026-10-03): "per hand".
                "convention")

NO_CATALOGUE_HOME = "NO_CATALOGUE_HOME"
#: Owner decision 2026-10-03: the 2026 production configuration is IRON's CURRENT one.
IRON_CURRENT_CONFIGURATION = "2026 production IRON"
IRON_CURRENT_PAGE = "news-2026-09-08"
SPEC_DEFINITION_KEY = "dexterous_hand_option"
SPEC_LOCATOR_PREFIX = "feature-grid/row[Manipulation]/"
#: Source row label -> the long-tail TEXT definition that preserves the maker's own row
#: wording (owner decision, G2-4). Nothing is split, parsed or interpreted.
INTERFACE_ROWS = {"Common interfaces": "common_interfaces",
                  "Additional interfaces": "additional_interfaces"}
PRICE_LOCATOR_PREFIX = "feature-grid/row[Estimated price]/"
AVAILABILITY_LOCATOR = "text-block[availability-year]"
# NO_CATALOGUE_HOME: an accepted statement preserved with its provenance, never materialized.
NO_HOME_KINDS = {"RESERVATION_FEE": "reservation_fee", "RESERVATION_TERMS": "reservation_terms",
                 "USE_CASES": "use_cases"}


@dataclass(frozen=True)
class ClaimPolicy:
    key: str
    proposal_kind: str
    target_kind: str       # robot_variant | specification | pricing_offer | availability_offer
                           # | NO_CATALOGUE_HOME
    target_key: str        # 'variant' | spec_definition.key | offer locator | statement kind
    value_type: str = "TEXT"
    edition_scope: str | None = None
    requires_variant: bool = False


def _spec(key: str, proposal_kind: str) -> ClaimPolicy:
    return ClaimPolicy(key=f"specification[{key}]", proposal_kind=proposal_kind,
                       target_kind="specification", target_key=key,
                       edition_scope="THIS_EDITION", requires_variant=True)


CLAIM_POLICIES: dict[str, ClaimPolicy] = {
    # IRON's current-configuration body DoF -> the first-class robot column (owner decision).
    "robot_spec[degrees_of_freedom]": ClaimPolicy(
        key="robot_spec[degrees_of_freedom]", proposal_kind="BODY_DOF",
        target_kind="robot_spec", target_key="degrees_of_freedom"),
    # IRON's current-configuration hand DoF -> robot.hand_dof, PER HAND (owner decision
    # 2026-10-03, option A): the figure XPENG states "in each hand"; never a two-hand total.
    "robot_spec[hand_dof]": ClaimPolicy(
        key="robot_spec[hand_dof]", proposal_kind="HAND_DOF",
        target_kind="robot_spec", target_key="hand_dof"),
    # IRON's current-configuration compute -> the existing long-tail TEXT spec, verbatim.
    "specification[compute_ai]": ClaimPolicy(
        key="specification[compute_ai]", proposal_kind="COMPUTE",
        target_kind="specification", target_key="compute_ai",
        edition_scope="THIS_EDITION"),
    "robot_variant": ClaimPolicy(
        key="robot_variant", proposal_kind="VARIANT", target_kind="robot_variant",
        target_key="variant"),
    f"specification[{SPEC_DEFINITION_KEY}]": _spec(SPEC_DEFINITION_KEY, "SPECIFICATION"),
    "specification[common_interfaces]": _spec("common_interfaces", "INTERFACES"),
    "specification[additional_interfaces]": _spec("additional_interfaces", "INTERFACES"),
    # A variant-scoped, manufacturer-estimated purchase price (owner decision, G2-4).
    "pricing_offer[variant]": ClaimPolicy(
        key="pricing_offer[variant]", proposal_kind="PRICE_ESTIMATE",
        target_kind="pricing_offer", target_key="purchase.manufacturer_estimate",
        value_type="JSON", requires_variant=True),
    # A variant-scoped WAITLIST availability with year-level seller wording (owner decision).
    "availability_offer[variant]": ClaimPolicy(
        key="availability_offer[variant]", proposal_kind="AVAILABILITY",
        target_kind="availability_offer", target_key="purchase.waitlist",
        value_type="JSON", requires_variant=True),
    **{f"no_catalogue_home[{name}]": ClaimPolicy(
        key=f"no_catalogue_home[{name}]", proposal_kind=kind, target_kind=NO_CATALOGUE_HOME,
        target_key=name) for kind, name in NO_HOME_KINDS.items()},
}


def claim_policy_for(kind: str, target_hint: str, locator: str,
                     structured: dict | None = None) -> ClaimPolicy | None:
    """The registered claim policy for a proposal, or None (unregistered = refused)."""
    if kind == "VARIANT" and target_hint == "robot_variant":
        return CLAIM_POLICIES["robot_variant"]
    if (kind == "SPECIFICATION" and target_hint == f"specification[{SPEC_DEFINITION_KEY}]"
            and locator.startswith(SPEC_LOCATOR_PREFIX)):
        return CLAIM_POLICIES[f"specification[{SPEC_DEFINITION_KEY}]"]
    if kind == "INTERFACES":
        row = (structured or {}).get("row")
        if row in INTERFACE_ROWS and locator.startswith(f"feature-grid/row[{row}]/"):
            return CLAIM_POLICIES[f"specification[{INTERFACE_ROWS[row]}]"]
        return None
    if (kind == "PRICE_ESTIMATE" and target_hint == "pricing_offer[variant]"
            and locator.startswith(PRICE_LOCATOR_PREFIX)):
        return CLAIM_POLICIES["pricing_offer[variant]"]
    if (kind == "AVAILABILITY" and locator == AVAILABILITY_LOCATOR
            and target_hint.startswith("availability_offer.available_from")):
        return CLAIM_POLICIES["availability_offer[variant]"]
    cfg = (structured or {}).get("configuration")
    if (kind == "BODY_DOF" and cfg == IRON_CURRENT_CONFIGURATION
            and locator.startswith(f"{IRON_CURRENT_PAGE}/")):
        return CLAIM_POLICIES["robot_spec[degrees_of_freedom]"]
    if (kind == "HAND_DOF" and cfg == IRON_CURRENT_CONFIGURATION
            and locator.startswith(f"{IRON_CURRENT_PAGE}/")):
        return CLAIM_POLICIES["robot_spec[hand_dof]"]
    if (kind == "COMPUTE" and cfg == IRON_CURRENT_CONFIGURATION
            and locator.startswith(f"{IRON_CURRENT_PAGE}/")):
        return CLAIM_POLICIES["specification[compute_ai]"]
    if kind in NO_HOME_KINDS:
        return CLAIM_POLICIES[f"no_catalogue_home[{NO_HOME_KINDS[kind]}]"]
    return None
