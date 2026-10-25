# Catalogue promotion: 2026-10-25-ho-data-32-agibot-x2

**Robots:** agibot-x2, agibot-x2-ultra  
**Classification:** ROUTINE  
**Evidence:** AGENT_ASSISTED_RESEARCH (not human-verified)  
**Digest:** `ac601ac3f4de1ad392ef06a8245a123edf82e80d78cef3f881b735bcb1bb91bd`  
**Base commit:** `03ef40b18d1111e7a153f9146f45e1c449ed66a5`  
**Execution:** not by `promotion execute` (version 2); scoped import gated by `db/import_preflight.py` after the owner's approval

## Core specifications (UNKNOWN -> value)

- **agibot-x2** `runtime_minutes` (X2, THIS_EDITION): UNKNOWN -> 120 min  [ROUTINE]
  - verbatim: 'Operating Time | At 0.5 m/s walking | Approx. 2 hours'
  - conversion: 2 h = 120 min
  - qualifiers: approximately
  - measurement condition: At 0.5 m/s walking
  - caveat: AgiBot X2 product page states 'Operating Time | At 0.5 m/s walking | Approx. 2 hours'; the figure is stated as approximate; 120 min is a unit conversion; stated measurement condition: At 0.5 m/s walking; evidence AGENT_ASSISTED_RESEARCH, not human-verified.
- **agibot-x2-ultra** `has_vision` (X2 Ultra, THIS_EDITION): UNKNOWN -> yes  [ROUTINE]
  - verbatim: 'X2 Ultra is equipped with LiDAR and RGB-D cameras, enabling precise environmental perception'
  - caveat: AgiBot X2 product page states 'X2 Ultra is equipped with LiDAR and RGB-D cameras, enabling precise environmental perception'; evidence AGENT_ASSISTED_RESEARCH, not human-verified.
- **agibot-x2-ultra** `runtime_minutes` (X2 Ultra, THIS_EDITION): UNKNOWN -> 120 min  [ROUTINE]
  - verbatim: 'Operating Time | At 0.5 m/s walking | Approx. 2 hours'
  - conversion: 2 h = 120 min
  - qualifiers: approximately
  - measurement condition: At 0.5 m/s walking
  - caveat: AgiBot X2 product page states 'Operating Time | At 0.5 m/s walking | Approx. 2 hours'; the figure is stated as approximate; 120 min is a unit conversion; stated measurement condition: At 0.5 m/s walking; evidence AGENT_ASSISTED_RESEARCH, not human-verified.

## Evidence

- agibot-x2 runtime_minutes: AgiBot X2 product page https://www.agibot.com/products/X2 (retrieved 2026-10-25T19:45:12Z by Claude (Opus 5.5, orchestrator) via curl; work order HO-DATA-STANDING 2026-10-22; initiated by Robert Konecny; sha256 `96d0c53acd6c5ff4`; observation EVIDENCE_PACKAGE; evidence `research-52ad3c3b41981c68`)
  - locator: specification table, row Operating Time, column X2
- agibot-x2-ultra has_vision: AgiBot X2 product page https://www.agibot.com/products/X2 (retrieved 2026-10-25T19:45:12Z by Claude (Opus 5.5, orchestrator) via curl; work order HO-DATA-STANDING 2026-10-22; initiated by Robert Konecny; sha256 `96d0c53acd6c5ff4`; observation EVIDENCE_PACKAGE; evidence `research-fa1adccb62bd3aa0`)
  - locator: feature text, LiDAR + RGB-D section; also specification table row RGB-D Camera (X2 Not equipped / X2 Ultra Equipped)
- agibot-x2-ultra runtime_minutes: AgiBot X2 product page https://www.agibot.com/products/X2 (retrieved 2026-10-25T19:45:12Z by Claude (Opus 5.5, orchestrator) via curl; work order HO-DATA-STANDING 2026-10-22; initiated by Robert Konecny; sha256 `96d0c53acd6c5ff4`; observation EVIDENCE_PACKAGE; evidence `research-b51c76614390c88a`)
  - locator: specification table, row Operating Time, column X2 Ultra

## Impact

3 core values filled from UNKNOWN on existing robots, with caveats and the docs/26 provenance statement in specs_note; no change to known values, offers, evidence rows, images, publication or commercial status.


## Decision

APPROVE (merge, then the named scoped import) / REJECT / DEFER (close PR with label)
