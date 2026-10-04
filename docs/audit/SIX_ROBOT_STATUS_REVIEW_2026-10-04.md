# Six-robot commercial-status review — implementation record (2026-10-04)

Owner decisions of 2026-10-04, implemented as one governed WorkOrder. Evidence rows live in the catalogue JSON
(`commercial_status_evidence`, AGENT_ASSISTED_RESEARCH, `verified_at` NULL). No robot is published by this change.

| Robot | Before | After | Basis |
|---|---|---|---|
| agibot-a2 -> **agibot-a2-ultra** | UNKNOWN | COMMERCIAL | A2 Ultra-specific first-party statements only (1000+ units deployed; 20+ enterprises; store listing is inquiry-only) |
| **agibot-a2-lite** (new stub) | n/a | UNKNOWN | separate product; no A2 Ultra claim is transferred |
| booster-t1 | UNKNOWN | COMMERCIAL | "now shipping worldwide" (news, 2025-01-23) + institutional customers; not marked DISCONTINUED for being absent from the store |
| fourier-intelligence-gr-1 | UNKNOWN | UNKNOWN | evidence gap (below) |
| galbot-g1 | UNKNOWN | COMMERCIAL | external deployments + public purchase link (distinct from Unitree G1) |
| ubtech-walker-s2 | UNKNOWN | COMMERCIAL | mass production, first-batch delivery, orders, named customers; RAAS/limited-commercial not inferred |
| figure-03 | UNKNOWN | PILOT | Figure 03 at BMW Spartanburg; Catalyst Brands deployment agreement |

## Identity remediation

The generic `agibot-a2` stub was ambiguous between A2 Ultra and A2 Lite. It is renamed in place (row id preserved)
to `agibot-a2-ultra`; `agibot-a2-lite` is a new unpublished UNKNOWN stub. No claims, proposals, candidates, aliases
or evidence referenced the old slug. The radar bootstrap seed entry `agibot/a2` is left as written (history).

## EVIDENCE GAP — fourier-intelligence-gr-1 (open)

Stays UNKNOWN. Still required: a **first-party historical GR-1 product page, datasheet, announcement or archived
capture** stating GR-1's commercial status. Current fftai.com describes GR-1 only as "the first humanoid robot
developed by Fourier" within the GRx lineup (GR-3 series, GR-2 current); old GR-1 product pages return 404 and the
newsroom is empty. Third-party reports are not substitutes.
