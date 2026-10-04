# DR-G5 — Commercial maturity joins the governed claim pipeline

Status: implemented (owner ruling 2026-10-04). Migration `0023`.

**Automation discovers and preserves the evidence. A human decides which frozen HumanoidOnline
maturity state, if any, the evidence establishes.**

## Chain

```
first-party page -> observation -> COMMERCIAL_MATURITY proposal (verbatim wording + clues)
  -> human ACCEPT with an explicit frozen status -> accepted claim (commercial_status)
  -> deterministic materialization: commercial_status + commercial_status_evidence[]
  -> importer -> catalogue_write_audit (verify)
```

PR #124 (six-robot review) was the last manual maturity path; it is not rewritten.

## Rules

* **Proposal** (`maturity-clues@0.1.0`): the sentence verbatim, source URL, locator, an explicit date
  only if the sentence states exactly one, and *clues* (delivery / shipping / pilot / purchase-or-sale /
  selected partner / deployment / internal deployment / service contract / production / future launch /
  discontinuation stated). Clues are observations. **No clue maps to a status and the proposal carries no
  suggested status.** A shared-page sentence must name the robot.
* **Decision**: ACCEPT must state `target_kind=commercial_status`, answer the review question and give
  `accepted_value` from ANNOUNCED, DEVELOPMENT, PROTOTYPE, PILOT, EARLY_ACCESS, LIMITED_COMMERCIAL,
  COMMERCIAL, RAAS_DEPLOYMENT, DISCONTINUED. No default; `UNKNOWN` is refused (it means *no accepted
  current claim*, so REJECT/DEFER and leave `commercial_status = UNKNOWN`).
* **Claim target** `commercial_status` / key `commercial_status`, policy `commercial_status[current]`.
* **Currentness**: two active claims with different values are a CONFLICT; materialization refuses until
  one is retracted (naming its replacement). Older evidence rows stay in the catalogue as history.
* **Retraction**: only the governed retraction mechanism. If every maturity claim of a robot is retracted
  with no active replacement, materialization writes `commercial_status = UNKNOWN` (explicit outcome;
  evidence rows are kept).
* **Disappearing wording**: never retracts, downgrades or blocks materialization. An active claim whose
  proposal's source wording no longer stands is reported `REVIEW REQUIRED`
  (`materialize.maturity_review_required`); a human decides the consequence.
* **Origin**: every proposal carries `origin` = `NEW_MODEL` | `CATALOGUE_ENRICHMENT` (operational
  metadata; identical truth semantics and the same review/claim pipeline).
* **Lane B in the source cycle**: for a registered approved source, each cycle also extracts maturity
  proposals about the registered *existing* robot from the newest retained page (`G2Ingest.
  maturity_robot_name`). Unchanged wording has the same digest, so it creates nothing and alerts nobody;
  changed wording creates a new proposal. No candidate is created for a known robot.
* **Never**: a scan, proposal, claim or materialization changes `is_published`; coverage or priority is a
  publication threshold; a status is chosen by automation.
