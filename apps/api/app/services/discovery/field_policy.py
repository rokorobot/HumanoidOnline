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

from app.services.discovery import DiscoveryError
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
CLAIM_REGISTRY_VERSION = "0.8.0-retail-offers"

# The resolved-choice keys that carry the human's explicit catalogue mapping.
MAPPING_KEYS = ("target_kind", "variant_slug", "variant_name", "spec_key", "edition_scope",
                "accepted_value",
                # G2-4 offer mapping (owner decisions): every value is stated, none defaulted.
                "price_type", "transaction_type", "billing_period", "currency", "price",
                "region", "provider", "edition_confirmed", "availability_status",
                "available_from", "delivery_estimate_label",
                # XPENG IRON (owner decision 2026-10-03): which configuration is current.
                "configuration",
                # Retailer reference offers (owner decision 2026-10-05): the reviewer states the
                # offer's condition; nothing is defaulted. (Displayed stock stays in the seller's
                # wording and the evidence: no canonical claim or column for it.)
                "condition",
                # hand DoF convention (owner decision 2026-10-03): "per hand".
                "convention")

NO_CATALOGUE_HOME = "NO_CATALOGUE_HOME"

#: Retailer / distributor reference offers (owner decision 2026-10-05). Two governed semantics,
#: deliberately NOT the manufacturer-estimate price and NOT the WAITLIST availability: a retail
#: price is the seller's own offer price (price_type PUBLIC, never an MSRP, manufacturer price or
#: EU price), and retail availability is the seller's stated state for ONE condition (NEW, USED,
#: ...) in ONE market. Displayed stock quantity is a fact about the listing at observation time,
#: kept with the offer's own wording, never a product specification.
RETAIL_PRICE_KIND = "RETAIL_PRICE"
RETAIL_AVAILABILITY_KIND = "RETAIL_AVAILABILITY"
RETAIL_PRICE_TARGET = "pricing_offer[retail]"
RETAIL_AVAILABILITY_TARGET = "availability_offer[retail]"
RETAIL_TARGET_KEY = "purchase.retail"
RETAIL_LOCATOR_ROOT = "listing/item["
OFFER_CONDITIONS = ("NEW", "USED", "OPEN_BOX", "REFURBISHED")
#: What a seller's availability wording OBSERVATION may be mapped to by the reviewer. The existing
#: availability vocabulary is reused; no Czech-specific state is invented, and a page's mere
#: existence is never availability.
RETAIL_ALLOWED_STATUS = {"IN_STOCK": ("AVAILABLE",), "UNAVAILABLE": ("NOT_AVAILABLE",),
                         "PREORDER": ("PREORDER",)}

#: G5 (owner ruling 2026-10-04): commercial maturity is its own governed semantic dimension.
#: The proposal (kind COMMERCIAL_MATURITY) preserves wording and explicit factual clues only; the
#: reviewer alone chooses the frozen HumanoidOnline status, and the registry never defaults,
#: infers or suggests one. UNKNOWN is deliberately NOT acceptable: it means "no accepted current
#: maturity claim exists", so it is the absence of a claim, never a claim.
COMMERCIAL_MATURITY_KIND = "COMMERCIAL_MATURITY"
COMMERCIAL_STATUS_TARGET = "commercial_status"
MATURITY_LOCATOR_PREFIX = "text[maturity]/"
ACCEPTABLE_COMMERCIAL_STATUSES = (
    "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS", "LIMITED_COMMERCIAL",
    "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED")

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


# XPENG IRON historical factual figures (owner decision 2026-10-03, option B): the 2025 Next-Gen
# release and the product page state BODY_DOF / HAND_DOF / COMPUTE / BATTERY figures for
# configurations that are NOT the current one. They are accepted as governed knowledge with
# provenance (NO_CATALOGUE_HOME): never materialized, never a catalogue fact, never maturity.
HISTORICAL_NO_HOME_KINDS = {"BODY_DOF": "historical_body_dof", "HAND_DOF": "historical_hand_dof",
                            "COMPUTE": "historical_compute", "BATTERY": "historical_battery"}
HISTORICAL_PAGES = ("news-2025-11-05", "product-page")
PRODUCT_PAGE_CONFIGURATION = "Next-Gen IRON (product page)"


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
    # Commercial maturity (owner ruling 2026-10-04): the robot's CURRENT status, chosen by the
    # reviewer from the frozen dictionary. Materializes to robot.commercial_status plus its
    # commercial_status_evidence, derived from this claim's own provenance chain.
    "commercial_status[current]": ClaimPolicy(
        key="commercial_status[current]", proposal_kind=COMMERCIAL_MATURITY_KIND,
        target_kind="commercial_status", target_key=COMMERCIAL_STATUS_TARGET),
    # A seller's reference offer for a robot (variant-agnostic: configurations are robots).
    "pricing_offer[retail]": ClaimPolicy(
        key="pricing_offer[retail]", proposal_kind=RETAIL_PRICE_KIND,
        target_kind="pricing_offer", target_key=RETAIL_TARGET_KEY, value_type="JSON"),
    "availability_offer[retail]": ClaimPolicy(
        key="availability_offer[retail]", proposal_kind=RETAIL_AVAILABILITY_KIND,
        target_kind="availability_offer", target_key=RETAIL_TARGET_KEY, value_type="JSON"),
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
    **{f"no_catalogue_home[{name}]": ClaimPolicy(
        key=f"no_catalogue_home[{name}]", proposal_kind=kind, target_kind=NO_CATALOGUE_HOME,
        target_key=name) for kind, name in HISTORICAL_NO_HOME_KINDS.items()},
}


def claim_policy_for(kind: str, target_hint: str, locator: str,
                     structured: dict | None = None) -> ClaimPolicy | None:
    """The registered claim policy for a proposal, or None (unregistered = refused)."""
    if (kind == COMMERCIAL_MATURITY_KIND and target_hint == COMMERCIAL_STATUS_TARGET
            and locator.startswith(MATURITY_LOCATOR_PREFIX)):
        return CLAIM_POLICIES["commercial_status[current]"]
    if (kind == RETAIL_PRICE_KIND and target_hint == RETAIL_PRICE_TARGET
            and locator.startswith(RETAIL_LOCATOR_ROOT) and locator.endswith("]/price")):
        return CLAIM_POLICIES["pricing_offer[retail]"]
    if (kind == RETAIL_AVAILABILITY_KIND and target_hint == RETAIL_AVAILABILITY_TARGET
            and locator.startswith(RETAIL_LOCATOR_ROOT) and locator.endswith("]/availability")):
        return CLAIM_POLICIES["availability_offer[retail]"]
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
    if (kind in HISTORICAL_NO_HOME_KINDS and cfg != IRON_CURRENT_CONFIGURATION
            and any(locator.startswith(f"{page}/") for page in HISTORICAL_PAGES)):
        return CLAIM_POLICIES[f"no_catalogue_home[{HISTORICAL_NO_HOME_KINDS[kind]}]"]
    if kind in NO_HOME_KINDS:
        return CLAIM_POLICIES[f"no_catalogue_home[{NO_HOME_KINDS[kind]}]"]
    return None


def check_maturity_choice(value: str | None) -> str:
    """The reviewer's explicit maturity choice, validated against the frozen dictionary."""
    if value is None or not str(value).strip():
        raise DiscoveryError("ACCEPT of a COMMERCIAL_MATURITY proposal needs the reviewer's "
                             "explicit accepted_value (a frozen status); nothing is inferred")
    value = str(value).strip()
    if value == "UNKNOWN":
        raise DiscoveryError(
            "UNKNOWN is not an accepted maturity claim: it means no accepted current maturity "
            "claim exists. REJECT or DEFER the proposal instead")
    if value not in ACCEPTABLE_COMMERCIAL_STATUSES:
        raise DiscoveryError(f"{value!r} is not a frozen commercial status "
                             f"{list(ACCEPTABLE_COMMERCIAL_STATUSES)}")
    return value
