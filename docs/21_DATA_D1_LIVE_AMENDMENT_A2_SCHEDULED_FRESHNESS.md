# DATA-D1.LIVE — Amendment A2: `SCHEDULED_FRESHNESS`

> **STATUS: RATIFIED — 2026-08-25, Robert Konecny (product owner).**
> Laws and definitions in this document are **FROZEN**. See §11.
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`
> (RATIFIED v0.1, 2026-07-29) specifically at **LIVE.4 — Manual local execution
> only**. It also narrows the open question left by `docs/11` §15 (discovery
> frequency) for one specific purpose.
>
> **Ratification changes what is *permitted in principle*. It authorizes no
> fetch, approves no source, enables no scheduler, and authorizes no
> implementation.** Schema, models, migrations, adapters, CI/CD configuration
> and application code are untouched and remain so until a **separate
> implementation contract** is ratified. This document is governance only.
>
> **This amendment does not reopen new-discovery crawling.** LIVE.4 remains
> fully authoritative — manual, local, human-triggered only — for every purpose
> other than the one narrow exception defined in §2.

---

## 0. Why this exists

The Catalogue Freshness Scanner v0.1 investigation (2026-08-24/25) found that
every primitive a freshness scanner needs already exists and works:
`DiscoverySource.radar_eligible` implements DATA-D1.9 in one place;
`pipeline.flag_recheck()` raises `RECHECK_REQUIRED` as workflow metadata with
no canonical mutation, exactly as `docs/11` §12 already permits; the P1–P8
promotion gates are unchanged and authoritative; `adapters.ingest()` dedups
idempotently. The one missing piece was never technical — it is that
`LIVE.4` names **exactly one** `crawl_trigger` value, `'MANUAL'`, and states
plainly: *"There is no scheduler, no cron entry, no queue, no worker, no
crawler VPS, and no code path by which the production stack initiates a
fetch."* `docs/11` §15 (discovery frequency) was left deliberately
unimplemented pending "a later, separately ratified slice." This is that
slice — narrowed to exactly the case it was written for.

**The failure this amendment exists to prevent** is not "the catalogue goes
stale." It is the same failure DATA-D1 has guarded against from the start,
restated for a scheduler instead of a crawler: *an automated trigger, once it
exists at all, quietly grows scope* — one more domain, one more page, one more
"while we're at it" link followed — until the platform is running an
unattended crawler in production without ever having decided to. Every rule
below is chosen against that outcome specifically, not against freshness
monitoring in general.

## 1. The current problem

`LIVE.4`'s prohibition is a single, undifferentiated rule: no automated
trigger, for any purpose, ever, in v0.1. That rule was correct against its
target — unattended discovery crawling turning "radar" into "production
scraper" — and nothing here weakens it for that target.

But it also blocks something categorically different: **re-checking a URL the
platform already knows about, already has permission to fetch, and already
has attached to an existing canonical robot** — to see whether anything
changed. That is not discovery. It expands no source list, resolves no new
identity, follows no link. It is the freshness half of `docs/11` §12
("`last_checked_at`... DATA-D1 may raise `RECHECK_REQUIRED` when the
underlying source changes") with no way to run it, because §12's own
`RECHECK_REQUIRED` machinery presumes *something* checked the source, and
under `LIVE.4` that something must be a human, by hand, one URL at a time,
forever.

## 2. Definition

**`SCHEDULED_FRESHNESS`** is a narrow, additional value on top of `LIVE.4`'s
manual-only rule. It does not replace `LIVE.4`; it carves out one specific
kind of fetch from it.

> A production scheduler **may** run **at most once every 7 days**
> (`FRESHNESS_INTERVAL_DAYS = 7`, default) to re-check a **known freshness
> target** — an exact, individually registered URL, already linked to an
> existing canonical robot, whose source already holds a current affirmative
> DATA-D1.9 eligibility decision — for the sole purpose of detecting whether
> its content changed since last checked.

Every one of the following ten conditions must hold for a given target on a
given run, or the run for that target does not happen:

| # | Requirement |
|---|---|
| **1** | The **exact URL** is already registered in HumanoidOnline (§4 — a `FreshnessTarget` record, or equivalent, exists before any fetch is considered). |
| **2** | The target is **linked to an existing canonical robot** (`robot_id` is set and resolves to a published, canonical row). |
| **3** | The target's source has a **current affirmative DATA-D1.9 eligibility decision** — `tos_status = ALLOWED`, `robots_status` in `(ALLOWED, NOT_APPLICABLE)`, an attributed, timestamped, unexpired review (`radar_eligible`, unchanged). |
| **4** | The fetch's **sole purpose** is freshness / change detection — never identity resolution, never new-entity discovery, never claim extraction beyond what §6 permits. |
| **5** | **No recursive crawling or link-following** beyond the exact registered target URL. One page, the one that was registered — never a page it links to. |
| **6** | **Conservative, per-host rate limiting** — stricter than, never looser than, whatever `docs/11` §14 and any per-source declared `Crawl-delay` already require. |
| **7** | **No authentication bypass, no CAPTCHA bypass, no defeat of any technical access control** (`LIVE.3`, restated — unchanged). |
| **8** | **No automatic canonical mutation.** A scheduled run may never write to a canonical table, directly or indirectly, under any outcome. |
| **9** | A **detected change** creates or reuses governed DATA-D1 work — `RECHECK_REQUIRED` (§12) on the linked discovery-layer record — and nothing more. It does not assert a new value, does not touch the canonical row, and does not skip TRACE/VERIFY. |
| **10** | **P1–P8 remain fully authoritative for promotion.** Nothing about this amendment shortens, bypasses, or auto-satisfies any promotion gate. |

**If DATA-D1.9 (requirement 3) is missing, stale, ambiguous, or negative for a
target's source: no network fetch occurs, under any circumstances, on any
schedule.** The target's execution mode is `MANUAL_CHECK` or
`ELIGIBILITY_REVIEW_REQUIRED` (§5) instead — queued for a human, exactly as
before this amendment. A scheduler discovering a target lacks eligibility does
not itself request a review, does not disable anything, and does not touch the
source's eligibility record — it simply does not fetch, and the target stays
in its non-`AUTO_CHECK` mode until a human resolves it.

## 3. What this amendment does **not** authorize

Stated first, because it is the part most likely to be misread later.

- **It does not reopen new-discovery crawling.** `LIVE.4` remains fully
  authoritative for RADAR (finding robots/manufacturers not yet in the
  catalogue). A `SCHEDULED_FRESHNESS` run may never create a *new* candidate
  entity, resolve a *new* identity, or add a source URL to a robot's freshness
  targets on its own initiative.
- **No autonomous competitor radar crawl.** Competitor directories and
  aggregators are unaffected; nothing about freshness-checking a manufacturer's
  own product page touches DATA-D1's competitor-radar posture.
- **No sitemap crawl, no recursive discovery, no general web crawler.** The
  target set is a closed, individually registered list. A scheduler that
  discovers *anything* not already on that list — a new page, a redirect
  target, a linked spec sheet — does not follow it, does not register it, and
  does not fetch it.
- **No autonomous expansion of source scope.** Adding a new `FreshnessTarget`,
  or registering a new `DiscoverySource`, remains a human, out-of-band act.
  The scheduler consumes the registry; it never writes new entries into it.
- **No canonical mutation, ever, under any outcome** (requirement 8, restated
  because it is the one a future "just this once" would erode first).
- **No change to DATA-D1.9.** A source still needs its own affirmative,
  attributed, unexpired eligibility decision. Weekly cadence is a *ceiling* on
  how often an eligible target may be re-checked; it is not, and never becomes,
  a substitute for eligibility.
- **No change to Gate W, Gate S, Gate T, Gate X, or P1–P8.** Promotion
  authority is completely untouched — see §7 of the base contract, unaffected.
- **No change to `crawl_trigger`'s existing `'MANUAL'` value or its meaning
  for every other purpose.** This amendment proposes a **new**, additional
  enum value (`SCHEDULED_FRESHNESS` — see §8) for the implementation slice to
  add; it does not redefine `MANUAL`, and every non-freshness crawl trigger
  remains exactly as constrained as before.

## 4. The `FreshnessTarget` concept (documented here, not implemented)

This section records the **semantic boundary** this amendment requires of any
future implementation. Exact field names, types, and table structure are
implementation design and are **not frozen** by this document — only the
boundary is.

**A `FreshnessTarget` is an operational scheduling record, not a research
object.** It is deliberately *not* a `DiscoveryCandidate`: `DiscoveryCandidate`
represents *"here is a lead on something that might become, or might already
be, a robot"* — a research/change-work object with its own identity-resolution
state machine (`docs/11` §6). A `FreshnessTarget` represents *"here is a page
we already trust, for a robot we already have, that we re-check on a
schedule."* Conflating the two would make `DiscoveryCandidate` a shadow mirror
of the canonical catalogue — the exact thing Decision B (§9) refuses.

Conceptual shape:

```
FreshnessTarget
  id
  robot_id              -> canonical robot (required, §2 req. 2)
  discovery_source_id   -> existing DiscoverySource registry (required, §2 req. 3)
  url                   -> the exact registered target (required, §2 req. 1)
  purpose / type        -> e.g. SPEC, PRICE, AVAILABILITY, STATUS, OFFICIAL_EVIDENCE
  execution_mode        -> AUTO_CHECK | MANUAL_CHECK | ELIGIBILITY_REVIEW_REQUIRED | INACTIVE
  interval_days         -> default 7 (FRESHNESS_INTERVAL_DAYS)
  last_checked_at
  last_result           -> e.g. UNCHANGED, CHANGE_DETECTED, ERROR, SOURCE_UNAVAILABLE
  etag
  last_modified
  content_fingerprint
  last_change_detected_at
  active
```

**No full third-party page body is retained** — only the minimum observation
metadata above (etag, last-modified, a content fingerprint, a result state).
This mirrors DATA-D1.10's minimal-retention discipline, applied to freshness
observation instead of candidate data.

**A unique constraint prevents duplicate target registration** for the same
`(robot_id, url)` pair — one target per robot per exact page, not one per
robot-and-domain.

## 5. Execution modes and the source-universe classification

Every registered target resolves to exactly one of:

| Mode | Meaning |
|---|---|
| `AUTO_CHECK` | Requirements 1–10 (§2) all currently hold. Eligible for the weekly scheduler. |
| `MANUAL_CHECK` | A real freshness target (manufacturer/commercial page relevant to price, availability, spec, or status), but not currently `AUTO_CHECK` — queued for a human, with the exact URL, the robot(s) affected, and the facts due for recheck. **No automated fetch is made.** |
| `ELIGIBILITY_REVIEW_REQUIRED` | No current affirmative DATA-D1.9 decision exists for the source (missing, stale, or ambiguous). No automated fetch is made. This is the same state a source is in before *any* DATA-D1 use, not something new to this amendment. |
| `INACTIVE` | Not a freshness target at all — archival/editorial evidence, a one-time press release, or a source explicitly excluded from automated access on operational grounds independent of DATA-D1.9. |

**Classification of the current 17 evidence domains** (measured 2026-08-25;
see the freshness-scanner audit turn for the source counts), applying the
guidance that manufacturer/commercial pages are the primary candidates and
static editorial/archival sources normally are not:

| Domain | Robots | Class | Notes |
|---|---:|---|---|
| pal-robotics.com | 3 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed under DATA-D1.9. |
| shop.unitree.com | 2 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Prior 2026-07-29 assessment found Unitree's **store** terms prohibit automation; per this amendment's own rule (§2 req. 3, and "do not assume an old rejection is permanently correct"), that finding must be **re-confirmed as a recorded, current `DiscoverySource` row**, not carried forward informally. Last known finding: negative. |
| unitree.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Distinct domain from the store; requires its own review, not inherited from `shop.unitree.com`. |
| agilityrobotics.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Prior assessment: Agility Robotics' terms prohibit automation. Re-review required to act, not assumed permanent. |
| engineeredarts.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Prior assessment: prohibits automation. Re-review required. |
| apptronik.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed. |
| astribot.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed. |
| figure.ai | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed. |
| robotera.com | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed. |
| 1x.tech | 1 | freshness-candidate → `ELIGIBILITY_REVIEW_REQUIRED` | Never assessed. |
| eu.robotshop.com | 4 | freshness-candidate (commercial, price/availability) → `MANUAL_CHECK` (hard override) | Independent of any DATA-D1.9 outcome: this domain crashes the Claude/Claude-Code browser tooling this project's operator uses. Never fetched by any of this project's automated *or agent-driven* tooling — a human checks it directly, outside this stack, regardless of eligibility. |
| robotshop.com | 1 | freshness-candidate (commercial) → `MANUAL_CHECK` (hard override) | Same rule as above. |
| commons.wikimedia.org | 5 | `INACTIVE` (archival/image evidence) | Static historical reference; not a specification/price/availability/status source. No freshness reason identified. |
| humanoid.guide | 4 | `INACTIVE` (archival/editorial) | Editorial/news coverage, not an authoritative source for facts that change. |
| robotsguide.com | 3 | `INACTIVE` (archival, and already disqualified) | Prior assessment: `robots.txt` names `ClaudeBot` with `Disallow: /`, Article 4 rights reservation, `403` on all other paths. Editorial content regardless. Never `AUTO_CHECK`. |
| prnewswire.com | 1 | `INACTIVE` (point-in-time press release) | A press release does not get "fresher" — it is a historical record of one announcement. |
| therobotreport.com | 1 | `INACTIVE` (archival/editorial) | Same reasoning as humanoid.guide. |

**Totals**: 17 domains → **12** freshness-candidate (manufacturer/commercial)
→ **5** archival/non-freshness (`INACTIVE`). Of the 12 candidates, **0** are
currently `AUTO_CHECK` (all 12 lack a current, recorded, affirmative
DATA-D1.9 decision in `discovery_source`; 3 carry a **known prior negative**
finding that predates this amendment and is not treated as automatically
current). **12 are `ELIGIBILITY_REVIEW_REQUIRED`** in the strict sense
("no current affirmative decision exists"), of which 2 domains (robotshop.com
/ eu.robotshop.com, both distributor pages) additionally carry a **hard
`MANUAL_CHECK` override** independent of eligibility, because this project's
own tooling cannot safely open that domain at all. `robotsguide.com`
(archival/`INACTIVE`) already carries a recorded **negative** DATA-D1.9
finding from prior work, separate from the "review required" domains that
have simply never been assessed.

**This table is a classification exercise, not a set of approvals.** Ratifying
this amendment approves **zero** sources and enables **zero** scheduled
fetches. Every domain above still needs its own recorded `DiscoverySource` row
and its own current, attributed DATA-D1.9 review before it can ever become
`AUTO_CHECK` — this amendment only defines the narrow *trigger* exception that
would let an already-eligible target be checked on a schedule once that
review exists.

## 6. What a `SCHEDULED_FRESHNESS` fetch may and may not do

### 6.1 Authorized

| Capability | Bound |
|---|---|
| One conditional GET of the exact registered URL | `If-None-Match`/`If-Modified-Since` where the source supports it (LIVE.14 conditional-request discipline, restated). |
| Content fingerprinting | A hash of the fetched body (or the relevant portion), stored so an unchanged page produces zero downstream work. |
| Freshness bookkeeping update | `last_checked_at`, `last_result`, `etag`, `last_modified` on the `FreshnessTarget` record — never a canonical write. |
| Raising `RECHECK_REQUIRED` on a change | Exactly the existing `pipeline.flag_recheck()` semantics (`docs/11` §12): workflow metadata, no canonical mutation, no P8 gate. |
| A best-effort, non-binding change-type guess | e.g. `PRICE`, `AVAILABILITY`, `SPECIFICATION` — informational only, never itself a canonical assertion, never itself `VERIFIED`. |

### 6.2 Prohibited, absolutely

| Prohibited | Note |
|---|---|
| Canonical mutation of any kind | Requirement 8, restated — no publish/unpublish, no price/availability/spec write, ever, from this path. |
| Treating missing content as a negative fact | A page returning `404`, an empty field, or a fetch error is `SOURCE_UNAVAILABLE` / `UNKNOWN` on the freshness record — never translated to `FALSE`, `0`, or `NOT_AVAILABLE` on any canonical field (`docs/11` §5, UNKNOWN semantics, unchanged). |
| Recursive or unbounded crawling | Requirement 5. One URL, the registered one. |
| Registering a new target | A scheduler consumes the `FreshnessTarget` registry; it never adds to it. |
| Auto-unpublishing a robot | A source going quiet, erroring, or disappearing is a signal for human review, never an automated unpublish. |
| Auto-asserting the new value as canonical | A detected change is a lead for verification, exactly as `docs/13` (change detection) already states: *"change detected ≠ canonical change accepted."* |
| Image downloading | Out of scope entirely — MEDIA-01 is untouched and this amendment does not create a media-acquisition path. |
| Bypassing DATA-D1.9 because the target "used to be eligible" | An expired or stale review is treated exactly as `docs/17` §7.1 already treats an expired `NO_EXPRESS_PROHIBITION` review: fail-closed, starts nothing, requires a fresh human review. |

## 7. Adversarial examples

| # | Situation | Correct outcome |
|---|---|---|
| 1 | A weekly run for `unitree.com/g1/` finds a link on that page to a new `unitree.com/r2/` announcement. | The link is **not followed**. Requirement 5. Only a human, acting outside this amendment, may register a new target or open a new discovery lead. |
| 2 | A `FreshnessTarget`'s source review expires mid-week, between two scheduled runs. | The next run finds `radar_eligible = false` (requirement 3 fails) and **does not fetch**. The target's mode becomes `ELIGIBILITY_REVIEW_REQUIRED` / `MANUAL_CHECK` for that cycle. No exception for "it was fine last week." |
| 3 | A registered target's page now redirects to a different URL entirely (e.g. a product line renamed). | The redirect target is **not** treated as the same freshness target. The fetch records `SOURCE_UNAVAILABLE`/changed-location as a result; a human decides whether to register the new URL. No automatic re-pointing. |
| 4 | A scheduled fetch detects the price changed from $13,500 to $14,200. | `RECHECK_REQUIRED` is raised (or an existing discovery-layer record for that robot/source is reused), change-type guessed as `PRICE`. **The canonical `pricing_offer` row is untouched** until a human traces, verifies, and promotes through P1–P8. |
| 5 | An operator argues one AUTO_CHECK run "obviously" found nothing wrong on a `MANUAL_CHECK` source, so it should count as checked. | Refused. `MANUAL_CHECK` means no automated fetch occurs, full stop (§2, "If D1.9 is missing... no network fetch"). A human must record `CHECKED_UNCHANGED` themselves. |
| 6 | Someone proposes adding a second scheduled run per week "just to be safer." | Refused without a new amendment. `FRESHNESS_INTERVAL_DAYS = 7` is the ceiling this amendment ratifies; loosening it is a cadence change, not an implementation detail, given `docs/16` LIVE.4's own "visible schema change, not a config flag" principle (§8). |
| 7 | A target's source is `eu.robotshop.com`, which later somehow passes a DATA-D1.9 review. | **Still `MANUAL_CHECK`.** The hard override in §5 is independent of DATA-D1.9 — it exists because this project's own tooling cannot safely open that domain, not because of the source's terms. Eligibility alone does not clear it. |

## 8. Implementation consequences (not authorized by this document)

Recorded so the later, separately ratified implementation slice has a
specification, exactly as `docs/17` §10 did for A1.

| Area | Consequence |
|---|---|
| `crawl_trigger` enum | Gains one additive value, e.g. `SCHEDULED_FRESHNESS`, alongside the existing `MANUAL`. Every existing value and its meaning is retained verbatim — this is the "visible schema change, not a config flag" `LIVE.4` was written to require. |
| New `FreshnessTarget`-equivalent table/model | Per §4's semantic boundary. Exact naming, columns, and migration are implementation design. |
| `discovery_candidate` | **Unchanged.** No backfill (Decision B, §9). `RECHECK_REQUIRED` work created from a freshness change either reuses an existing candidate linked to the robot (if one exists) or creates a new, minimal one at the moment a change is actually detected — never in advance, never speculatively, never one-per-catalogue-robot. |
| Scheduler mechanism | Not selected by this document. The implementation slice chooses the smallest existing mechanism (`docs/` freshness-scanner audit turn recommended GitHub Actions `schedule:` as the smallest already-present option) and must satisfy: idempotent, safe to rerun, one failing source does not abort the run, no duplicate `RECHECK_REQUIRED` work for the same unchanged observation. |
| Rate policy | Per-host limits at least as conservative as any existing DATA-D1 crawler-etiquette ceiling (`docs/11` §14); a declared `Crawl-delay` is a floor, never a target. |
| Run reporting | A scheduled run's report must state, per target: mode, result, and (if applicable) the `RECHECK_REQUIRED` work item created/reused — mirroring the manual-run report `docs/16` §18 already requires. |
| Public/API/MCP surfaces | No change. Freshness bookkeeping is invisible to every public and machine surface, exactly as the discovery layer already is (AGENT-01.7, Gate O/I). |

## 9. Relationship to Decision B (no candidate backfill)

This amendment is **conditioned on** Decision B: `DiscoveryCandidate` is not
backfilled one-per-existing-robot. A `FreshnessTarget` referencing
`robot_id` directly is what makes that possible — the freshness layer does not
need every canonical robot to already have a discovery-layer shadow, because
it links to the canonical robot, not to a candidate. A `DiscoveryCandidate` (or
a reused existing one) is created **only at the moment a change is actually
detected**, which is exactly when DATA-D1's research/change-work object
becomes the right tool. This keeps `discovery_candidate`'s meaning intact:
*"there is something here that needs human judgment,"* never *"this table
mirrors the catalogue."*

## 10. Non-goals

This amendment explicitly does **not**:

- authorize any fetch, of any source, official or otherwise — zero sources are
  approved by this document;
- reopen or relax new-discovery / competitor-radar crawling in any way;
- change `DATA-D1.9`, `radar_eligible`, or any existing eligibility state or
  its evidence requirements;
- change Gate W, Gate S, Gate T, Gate X, or P1–P8;
- change `LIVE.4`'s meaning for any trigger other than the one narrow
  exception defined in §2 — every other automated trigger remains prohibited;
- authorize backfilling `discovery_candidate` for existing canonical robots
  (Decision B, §9);
- select a scheduler mechanism, a migration, or any implementation detail —
  those are a separately authorized slice (§8);
- change `FRESHNESS_INTERVAL_DAYS` from 7, or authorize any cadence other than
  weekly, without a further amendment;
- create any path by which a detected change becomes a canonical mutation
  without P1–P8;
- weaken UNKNOWN semantics, G2 ("no commercial fact without evidence"), or
  MEDIA-01 in any way;
- override the `robotshop.com` / `eu.robotshop.com` operational exclusion —
  that exclusion is independent of, and not superseded by, any DATA-D1.9
  outcome for those domains.

## 11. Ratification record

```
STATUS:                      RATIFIED
Proposed:                    2026-08-25
Amends:                      docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md
                             §"LIVE.4 — Manual local execution only"
                             (RATIFIED v0.1, 2026-07-29)
Also narrows:                docs/11_DATA_D1_CONTRACT.md §15 (discovery
                             frequency) for freshness-recheck purposes only —
                             general discovery cadence remains "implementation
                             policy, not frozen," unchanged
Implementation authorized:   NONE — documentation only
Sources approved:            NONE
Scope:                       Freshness re-check of already-registered,
                             already-eligible, already-canonically-linked
                             exact URLs ONLY. New-discovery / competitor-radar
                             crawling is UNCHANGED and remains MANUAL-only
                             under LIVE.4.
Cadence ceiling:             FRESHNESS_INTERVAL_DAYS = 7 (weekly). Loosening
                             requires a further amendment (adversarial
                             example 6).
Candidate-backfill:          NOT AUTHORIZED (Decision B) — DiscoveryCandidate
                             is not backfilled per existing canonical robot;
                             a separate FreshnessTarget concept links directly
                             to robot_id (§4, §9).
Domain classification
  (2026-08-25 inventory):    17 evidence domains -> 12 freshness-candidate /
                             5 archival(INACTIVE). 0 currently AUTO_CHECK.
                             12 ELIGIBILITY_REVIEW_REQUIRED (3 carrying a
                             known PRIOR NEGATIVE finding needing
                             re-confirmation, not assumed current). 2 of the
                             12 additionally hard-overridden to MANUAL_CHECK
                             (robotshop.com / eu.robotshop.com) independent
                             of eligibility.
D1.9:                        UNCHANGED and fully binding — weekly cadence
                             never substitutes for eligibility (§2 req. 3).
Gate W / P1-P8:              UNCHANGED
Canonical mutation:          NOT POSSIBLE from this path, under any outcome
                             (§2 req. 8, §6.2)

Ratified by:                 Robert Konecny (product owner)
Ratification date:           2026-08-25
```

**This document freezes principles only.** Implementing `SCHEDULED_FRESHNESS`
— the enum value, the `FreshnessTarget`-equivalent table, the scheduler
mechanism, rate policy, and run reporting — requires a **separate
implementation contract**, ratified before any code is written, exactly as
`docs/17` §13.1 required for A1.

### 11.1 Authorized sequence following ratification

1. A separate **implementation contract** covering the schema/model for
   freshness targets, the `crawl_trigger` enum addition, the scheduler
   mechanism, rate policy, and run reporting.
2. **Per-source DATA-D1.9 eligibility reviews** for the 12 freshness-candidate
   domains identified in §5 — each recorded as its own `DiscoverySource` row,
   including a fresh review for the 3 that carry a prior negative finding.
3. **Registration of individual `FreshnessTarget` records** only for robots
   and URLs an operator actually wants tracked — not a bulk registration of
   every evidence URL in the catalogue.
4. **Enablement of `AUTO_CHECK`** only for targets whose source passes step 2.
   Everything else stays `MANUAL_CHECK` or `ELIGIBILITY_REVIEW_REQUIRED`
   indefinitely, and that is a correct, expected steady state — not a gap to
   be closed by relaxing DATA-D1.9.

**Scanner implementation remains paused** until steps 1–4 above are reached in
order.
