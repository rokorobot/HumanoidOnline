"""AGENT-02 price *contract vocabulary* — a thin adapter, no pricing rules.

The comparable-price semantics moved to `services/pricing.py` (AGENT-02.1c) so
one governed implementation serves every surface. What remains here is the part
that genuinely belongs to the agent contract: the two `warnings[]` reason codes
`docs/20` §10.3 freezes, and the mapping from the service layer's semantic
outcome onto them.

There is deliberately **no SQL, no currency rule and no price-type rule in this
module**. If a price question can be asked of the catalogue, it is answered in
`services/pricing.py`.

These codes are query-result exclusion reasons, NOT transport errors — they
describe a call that SUCCEEDED and explain why particular robots are absent
(`docs/20` §17). A quote-only robot failing a ceiling is not an error.
"""
from __future__ import annotations

from app.services.pricing import CeilingExclusions

#: Excluded because no comparable numeric price in the requested currency could
#: be established — no rows, quote-gated, or priced only in another currency
#: (`docs/20` §10.3 cases C–F). Never a claim that the robot is expensive.
EXCLUDED_UNPROVABLE = "price_max_excluded_unprovable"

#: Excluded because a comparable price *in the requested currency* exceeded the
#: ceiling (`docs/20` §10.3 case B). Only ever reached when a comparison in that
#: currency actually happened.
EXCLUDED_ABOVE_LIMIT = "price_max_excluded_above_limit"


def warning_codes(exclusions: CeilingExclusions) -> list[str]:
    """Contract warning codes for a ceiling-constrained query.

    Sorted for determinism, so a caller diffing two responses sees a change in
    meaning rather than a change in ordering.
    """
    codes = []
    if exclusions.above_limit:
        codes.append(EXCLUDED_ABOVE_LIMIT)
    if exclusions.unprovable:
        codes.append(EXCLUDED_UNPROVABLE)
    return sorted(codes)
