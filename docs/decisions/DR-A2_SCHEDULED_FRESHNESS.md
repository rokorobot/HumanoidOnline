# DR-A2 — A narrow scheduled-trigger exception to LIVE.4: `SCHEDULED_FRESHNESS`

| | |
|---|---|
| **Status** | **DECIDED — ADOPTED, 2026-08-25, Robert Konecny (product owner)** |
| **Raised** | 2026-08-25 |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Amends** | `docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md` §"LIVE.4" (RATIFIED v0.1, 2026-07-29) |
| **Normative text** | `docs/21_DATA_D1_LIVE_AMENDMENT_A2_SCHEDULED_FRESHNESS.md` |
| **Evidence** | Catalogue Freshness Scanner v0.1 infrastructure audit (2026-08-24/25): 47 tracked robots, 28 with source URLs, 35 unique URLs, 17 unique domains; existing `flag_recheck()`/`radar_eligible`/P1–P8 machinery fully built and reusable; zero linkage between the 47 published robots and `discovery_candidate` |

This record captures **why the decision was asked for and what turns on it**.
The amendment document carries the normative text; nothing here is binding.

## 1. Context

The product owner's next roadmap priority (after the compare-performance work)
was a weekly Catalogue Freshness Scanner: periodically re-check the sources
already cited as evidence for the 47 tracked robots, and surface what may have
changed — without ever silently overwriting canonical truth.

An infrastructure audit found the governed pipeline (RADAR → CANDIDATE →
TRACE → VERIFY → PROMOTE), the DATA-D1.9 eligibility model
(`DiscoverySource.radar_eligible`), the `RECHECK_REQUIRED` workflow-metadata
mechanism (`pipeline.flag_recheck()`), and the P1–P8 promotion gates all
already exist, are already tested, and require no new law to reuse for this
purpose. **The one actual blocker was `LIVE.4`**: *"Every v0.1 crawl is
started by a named human on a local machine... no code path by which the
production stack initiates a fetch."* `crawl_trigger` is a database enum with
exactly one value, `'MANUAL'`, by design — "so that adding an automated
trigger is a visible schema change, not a config flag." `docs/11` §15
(discovery frequency) states cadence is "implementation policy, not frozen,"
but was explicitly left unimplemented "until a later, separately ratified
slice" — precisely because of `LIVE.4`.

So the scanner as originally scoped (Phase 7: "runs weekly," a production
scheduler) was not a maturity gap. It was something the project had already,
deliberately, decided not to allow — for a reason (unattended discovery
crawling silently expanding scope) that does not describe what a freshness
re-check of an already-known, already-eligible page actually does.

## 2. The decision

**Should `LIVE.4` gain one narrow, additional trigger value —
`SCHEDULED_FRESHNESS` — permitting a production scheduler to re-check
already-registered, already-eligible, already-canonically-linked URLs at most
once per week, while leaving every other automated-trigger prohibition
(new-discovery crawling, competitor radar, sitemap/recursive crawling, source
scope expansion) exactly as `LIVE.4` already forbids it?**

The question is narrower than "should DATA-D1 get a scheduler." It is whether
one blanket rule — *no automated trigger, for anything, ever* — should
continue to answer two different questions with one word:

| Question | Nature |
|---|---|
| May the platform *discover* something it does not already have permission to look at? | About scope expansion — the risk `LIVE.4` was written against |
| May the platform *re-check* a page it already trusts, for a robot it already has, on a fixed weekly ceiling? | About staleness of an existing, bounded, already-approved fact |

## 3. Options considered

### Option 1 — Change nothing; keep the scanner human-run only

A named human runs a local CLI at whatever cadence they choose. Fully
compliant with `LIVE.4` today, no amendment needed.

*For:* zero new surface, zero risk of scope creep, ships today.

*Against:* does not scale — 12+ freshness-candidate domains checked by hand
weekly is real, recurring human time, and it is exactly the "produces work for
a person instead of doing the person's job" pattern the discovery layer was
built to reduce. It does not become more attractive as the catalogue grows.

### Option 2 — Broaden `LIVE.4` generally (allow any scheduled DATA-D1 work)

Remove the manual-only restriction entirely, or add a generic
"scheduled work" trigger not scoped to freshness.

*For:* maximum flexibility; solves this and future scheduling needs at once.

*Against:* exactly the failure mode `LIVE.4` exists to prevent — a general
scheduled trigger is a standing invitation for scope to creep from "re-check a
known page" to "discover a bit more while we're at it." Rejected without
further analysis, consistent with how the base contract already rejects
"crawl anything not technically blocked."

### Option 3 — `SCHEDULED_FRESHNESS`, narrowly bounded *(the proposal)*

One additive trigger value, usable only when all ten requirements of `docs/21`
§2 hold simultaneously: exact registered URL, linked to an existing canonical
robot, source already DATA-D1.9-eligible, freshness-only purpose, no
recursion, conservative rate, no access-control bypass, no canonical
mutation, `RECHECK_REQUIRED`-only on change, P1–P8 unchanged.

*For:* unblocks the actual bottleneck (human time spent on rote re-checks of
pages already known to be fine) without touching the guarantee that makes
DATA-D1 trustworthy — nothing here can expand source scope, discover a new
entity, or write canonical data. Every authorized path still ends either in
"nothing changed" (bookkeeping only) or in a human-reviewed `RECHECK_REQUIRED`
item, exactly as manual re-checking already would.

*Against:* it is the first automated trigger of any kind this project has
authorized. The discipline that has made every prior DATA-D1 decision correct
came partly from the rule being simple ("no scheduler" has zero edge cases).
A scoped exception is a scoped exception, and the place it will fail is not
the first implementation — it is the point where someone extends a
freshness-check adapter to also grab "just the linked spec page while it's
already fetching."

### Option 4 — Allow scheduling only for MANUAL_BOOTSTRAP-class sources

Restrict the exception to sources already reviewed under the no-network
`MANUAL_BOOTSTRAP` posture, sidestepping DATA-D1.9 network-eligibility
questions entirely.

*For:* avoids any live-fetch eligibility question.

*Against:* doesn't solve the actual problem — `MANUAL_BOOTSTRAP` sources are
by definition never fetched automatically at all (that's the whole point of
that mode), so this option authorizes nothing a scheduler could do that isn't
already just a human reading a page. Rejected as not actually responsive to
the freshness-scanner goal.

## 4. Recommendation

**Adopt Option 3.** It is the only option that reduces the actual bottleneck
(recurring human time on rote re-checks) without reopening any of the
guarantees DATA-D1 exists to protect. The ten requirements in `docs/21` §2 are
written so that every one of them, independently, blocks the failure mode
that would matter if it were missing — there is no "spirit of the rule"
gap left for an implementation to quietly widen.

**Decision B is adopted alongside it, not separately debated**: no
`DiscoveryCandidate` backfill for the 47 existing canonical robots.
`DiscoveryCandidate` stays a research/change-work object; a `FreshnessTarget`
concept (linking directly to `robot_id`) is the right shape for "recheck an
existing fact," and a discovery-layer candidate is created only at the moment
a change is actually detected — never speculatively, never
one-per-catalogue-robot.

## 5. Consequences if adopted

| | |
|---|---|
| **Immediately** | Nothing. Zero sources approved, zero targets registered, zero code changed. Each of the 12 freshness-candidate domains still needs its own recorded `DiscoverySource` row and DATA-D1.9 review — 3 of which (Unitree store, Agility Robotics, Engineered Arts) carry a **prior negative** finding that must be re-confirmed, not assumed to still hold, and not assumed to have lapsed either. |
| **Implementation** | A separately authorized slice: `crawl_trigger` enum gains one additive value; a `FreshnessTarget`-equivalent table/model (naming is implementation design); a scheduler mechanism (smallest existing option — GitHub Actions `schedule:` is already present in this repo for CI); rate policy at least as conservative as existing DATA-D1 etiquette. |
| **New-discovery / competitor radar** | Unchanged. Still `LIVE.4` manual-only, no exception, no narrowing. |
| **DATA-D1.9** | Unchanged and fully binding. Weekly cadence is a ceiling on an already-eligible target, never a substitute for eligibility. |
| **Canonical truth** | Unchanged. No path from a scheduled fetch to a canonical write; P1–P8 remain the only route, exactly as today. |
| **`robotshop.com` / `eu.robotshop.com`** | Hard `MANUAL_CHECK` override, independent of DATA-D1.9 — this project's own tooling cannot safely open that domain, so no eligibility outcome changes its mode. |

## 6. Risks and their mitigations

| Risk | Mitigation |
|---|---|
| A freshness fetch follows a link "just this once" | `docs/21` §2 req. 5 and §6.2 make this an absolute, non-negotiable prohibition, with adversarial example 1 stated explicitly against it. |
| A scheduler registers a new target it discovered | Explicitly out of scope (§3, §6.2) — a scheduler consumes the registry, never writes to it. |
| An expired eligibility review is treated as "still probably fine" | §2 req. 3 plus adversarial example 2: fail-closed, no exception for recency, mirrors `docs/17` §7.1's existing expiry discipline exactly. |
| A detected change gets asserted straight into canonical data | §2 req. 8/9, §6.2, adversarial example 4: a change only ever raises `RECHECK_REQUIRED`; P1–P8 remain the sole promotion path. |
| Cadence quietly loosens from weekly to something tighter over time | `FRESHNESS_INTERVAL_DAYS = 7` frozen at this amendment; loosening it requires a further amendment (adversarial example 6), matching `LIVE.4`'s own "visible schema change, not a config flag" principle. |
| `DiscoveryCandidate` becomes a shadow mirror of the catalogue via backfill | Decision B explicitly refuses backfill; `FreshnessTarget` links `robot_id` directly instead. |
| A missing/errored fetch gets read as a negative canonical fact | §6.2: `SOURCE_UNAVAILABLE`/`UNKNOWN` on the freshness record only, never `FALSE`/`0`/`NOT_AVAILABLE` on any canonical field. |

## 7. What was explicitly not asked

This record did not ask for approval to fetch anything, to enable any source,
to write any code, to backfill `discovery_candidate`, or to loosen `LIVE.4`
for anything other than the one narrow purpose defined in `docs/21` §2. It
asked one thing: whether that one narrow trigger exception should exist.
**The decision below answers that question and nothing wider.**

## 8. Decision

```
DECISION:            ADOPT
Decided by:          Robert Konecny (product owner)
Date:                2026-08-25
Decided at:          docs/21 (this amendment) — governance-only turn,
                     no code/schema/migration change

Adopted with:        FRESHNESS_INTERVAL_DAYS = 7 (weekly ceiling)
                     Ten-requirement gate (docs/21 §2), all must hold
                     No DiscoveryCandidate backfill (Decision B)
                     robotshop.com / eu.robotshop.com hard MANUAL_CHECK
                       override, independent of DATA-D1.9

Notes:               New-discovery / competitor-radar crawling is UNCHANGED
                     and remains LIVE.4 manual-only, with no exception. DATA-
                     D1.9 is unchanged and fully binding — weekly cadence
                     never substitutes for eligibility. Canonical mutation
                     remains impossible from this path under any outcome;
                     P1-P8 remain the sole promotion route. No source is
                     approved and no implementation is authorized by this
                     decision — a separate implementation contract is
                     required before any code is written (docs/21 §11.1).
```

**Authorized sequence following adoption** (see `docs/21` §11.1): a separate
implementation contract (enum, `FreshnessTarget`-equivalent schema, scheduler
mechanism, rate policy, run reporting) → per-source DATA-D1.9 reviews for the
12 freshness-candidate domains identified in `docs/21` §5 → registration of
individual targets an operator actually wants tracked → `AUTO_CHECK`
enablement only for targets whose source passes review. **Scanner
implementation remains paused** until that sequence is reached, in order.
