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
