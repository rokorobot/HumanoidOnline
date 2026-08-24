"""DATA-D1 Scheduled Freshness — docs/22_DATA_D1_SCHEDULED_FRESHNESS_
IMPLEMENTATION_CONTRACT.md, RATIFIED v0.1 (amends docs/16 LIVE.4 per
docs/21_DATA_D1_LIVE_AMENDMENT_A2_SCHEDULED_FRESHNESS.md, RATIFIED v0.1).

FOUNDATION SLICE. This package contains:

  - eligibility: freshness_auto_check_eligible() + compute_execution_mode()
  - service: due-target queries, observation recording, change detection,
    the deterministic change-identity dedup, and the manual review path

Deliberately absent from this slice (docs/22 non-goals, restated by the
foundation WorkOrder that built this package): no HTTP client, no live
adapter, no GitHub Actions workflow, no DATA-D1.9 eligibility review, no
FreshnessTarget registration/seeding. `run_due_checks()` accepts a pluggable
`FreshnessChecker` so the entire detection/idempotency/lineage pipeline is
testable without contacting any third party — a real HTTP-backed checker is
a later, separately-gated slice.
"""
from __future__ import annotations


class FreshnessError(RuntimeError):
    """Raised when a freshness-layer operation is refused (bad input, missing
    attribution, unknown enum value) — never for a downstream fetch failure,
    which is represented as a FETCH_ERROR observation, not an exception."""
