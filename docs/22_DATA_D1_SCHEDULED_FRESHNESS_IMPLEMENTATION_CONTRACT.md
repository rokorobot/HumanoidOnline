# DATA-D1 Scheduled Freshness — Implementation Contract v0.1

> **STATUS: RATIFIED — 2026-08-25, Robert Konecny (product owner).**
>
> This document is the "separate implementation contract" required by
> `docs/21` §11.1 (DATA-D1.LIVE Amendment A2, RATIFIED 2026-08-25,
> main @ `fd631b1e04a369d4ca12d8aaffac3c1c3137d4f9`) before any code, schema,
> or migration for scheduled freshness checking may be written.
>
> **Implementation authorized by this document: none.** No migration, no
> model, no CLI, no workflow, and no DATA-D1.9 eligibility decision exists
> because of this document. It specifies exactly what the next slice would
> build, so that slice has a specification instead of an inference — the same
> discipline `docs/17` §10 and `docs/21` §8 already used for their own later
> slices.
>
> Subordinate to everything already frozen: `docs/21` (A2) governs what this
> contract may authorize in principle; `docs/11` (DATA-D1 base, P1–P8, UNKNOWN
> semantics, G2); `docs/16` (DATA-D1.LIVE, LIVE.1–LIVE.14, Gate W); MEDIA-01;
> AGENT-01.7. Nothing here may loosen any of them, and where this document is
> silent, the stricter reading of those documents governs.

---

## Phase 1 — Inspected conventions (informs every design choice below)

| Area | Finding |
|---|---|
| Migrations | `db/migrations/NNNN_description.sql`, sequential, each wrapped in idempotent `DO $$ ... IF NOT EXISTS ... END $$;` guards against `pg_type`/`pg_attribute`, with a header comment naming the ratifying doc and stating exactly what the slice does and does not add (0003, 0004 are the direct precedent for a discovery-adjacent, structurally-isolated layer). Current head: `0009_add_buyer_requirement_contact_phone.sql`. |
| `DiscoverySource` | `apps/api/app/models/discovery.py:82-93` — `radar_eligible` property is DATA-D1.9's base gate. **Verified by direct inspection: it does NOT check `tos_expires_at` or `last_robots_checked_at` recency at all** — it checks only `is_enabled`, `tos_status == ALLOWED`, `robots_status`, and reviewer attribution. A source whose review expired months ago still reads `radar_eligible = True` today if nothing else touched its row. `adapters.ingest()` has the identical gap (same single check, `apps/api/app/services/discovery/adapters.py:104`). Neither gap has ever been exercised — `FixtureAdapter` never performs a real fetch, so no code path has ever needed the currentness check to actually fire. **`radar_eligible` alone is reused unmodified; freshness composes an ADDITIONAL currentness check on top of it — see Phase 3.** |
| `DiscoveryCandidate` | Own state machine (`pipeline.py`), `UniqueConstraint("source_id", "external_ref")` for dedup, `promoted_robot_id`/`possible_robot_id` point *to* canonical (Gate K: never the reverse). **Not backfilled per Decision B — reused only at the moment a change is detected**, via its existing dedup constraint. |
| `crawl_trigger` / `crawl_run` | DATA-D1.LIVE's live-acquisition run record (migration 0004). `crawl_trigger` has exactly one value, `'MANUAL'`, by design (LIVE.4, restated in a schema comment). `crawl_run` is wired to `fetched_page`/`candidate_claim.crawl_run_id`/`candidate_image_ref.crawl_run_id` — i.e. to the **radar/discovery** ingest path specifically. |
| `pipeline.flag_recheck()` | Fully implemented, tested, terminal-safe (H5), sets `status = RECHECK_REQUIRED` and merges a reason into `candidate_data`. Safe to call again on an already-`RECHECK_REQUIRED` candidate (idempotent in effect — restated in Phase 6). **Reused unmodified.** |
| `promotion.py` (P1–P8) | `check_gates()` + `promote()`. **Untouched by this contract** — freshness work never reaches `READY_FOR_PROMOTION` on its own; a detected change only ever produces a `RECHECK_REQUIRED` candidate that a human later traces/verifies through the existing pipeline. |
| `adapters.py` (`ingest`) | Gated by `source.radar_eligible`, writes via `SourceAdapter.discover()` → `RawCandidate`/`RawClaim`. Built for **discovering candidates from a source**, not for re-checking one known robot's one known URL. **Not reused directly** — see Phase 4 for why. |
| `bootstrap.py` | The exact precedent for "one governed writer, argparse CLI, `--operator` required, `--dry-run` supported, refuses cleanly with `DiscoveryError`." **Freshness CLI follows this shape exactly.** |
| `app/cli/*.py` | `bootstrap_inventory.py`, `promote_candidate.py`, `batch_review.py` — all: `argparse`, open one `SessionLocal()` session, one governed service call, explicit commit, human-readable stdout, non-zero exit on refusal. |
| GitHub Actions | `.github/workflows/ci.yml` only — push/PR-triggered, no `schedule:` anywhere in the repo. Six jobs, each spins up an **ephemeral** Postgres service container and applies schema+seed or schema+catalogue fresh every run; none of them talks to a persistent/production database. |
| Production deployment | `apps/api` is deployed on Vercel (serverless functions) against Neon Postgres — confirmed live in this project's own prior work (Vercel Production checks, `apps/api/.vercel/project.json`). A GitHub Actions **cron** job cannot "call into" a serverless function on a schedule by itself; it can only (a) HTTP-call a deployed endpoint, or (b) run the governed Python CLI directly inside the Action against `DATABASE_URL` pointed at production Neon. **Design choice, Phase 8.** |

**Smallest implementation consistent with A2**: one new, structurally-isolated
migration (new enums + two new tables, no canonical FK, no touch to `crawl_run`/
`crawl_trigger`/`discovery_candidate`'s shape); one new service module reusing
`radar_eligible`, `flag_recheck`, and `DiscoveryCandidate`'s existing dedup
constraint; one CLI with two subcommands (`run` for the scheduler, `manual` for
the human review queue) sharing one internal function; one GitHub Actions
workflow that contains no business logic and cannot bypass eligibility because
it never sees a URL — it only invokes the CLI.

---

## Phase 2 — Freshness data model

### Model choice: **B — `FreshnessTarget` + `FreshnessObservation`**

Rejected **A (FreshnessTarget-only, latest-state)** because:

- **Idempotency proof (test I) needs a per-attempt record.** "The same changed
  fingerprint on a retry is idempotent" is only checkable if there is a record
  of *each* attempt to compare against — a single mutable "latest state" field
  can't distinguish "this is the second time we saw this fingerprint" from
  "this is the first."
- **Failure diagnosis (test K, M) needs history, not a single last-error
  field.** "Did this target fail once or three times in a row" and "did one
  failing target abort the others" are both about a *sequence* of attempts.
- **It already matches the repository's own precedent.** DATA-D1.LIVE already
  splits "one execution" (`crawl_run`) from "one page's outcome within that
  execution" (`fetched_page`) for exactly this reason. `FreshnessObservation`
  is the same shape, reused for a different, structurally-separate purpose
  (Phase 4 explains why it is a *new* table rather than reusing `fetched_page`).
- **Change lineage** ("what changed and when," for a human reviewer) needs an
  append-only trail, not a value that gets overwritten on the next check.

`FreshnessObservation` is deliberately **lightweight** — no page body, ever
(A2 §4, and DATA-D1.10's minimal-retention discipline, applied here). It is
the freshness-domain equivalent of `fetched_page`, and just as small.

### `FreshnessTarget`

One row per **exact URL registered for one canonical robot.** Stores **durable
intent/config only** — never a derived, potentially-stale eligibility verdict
(correction 3: see Phase 3).

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid`, PK | `gen_random_uuid()` default, matching every other table. |
| `robot_id` | `uuid`, FK → `robot.id`, `NOT NULL`, `ON DELETE CASCADE` | Direct link to canonical (A2 §4/§9) — never through `discovery_candidate`. `CASCADE` because a freshness target has no meaning once its robot is gone, and robot deletion is already a rare, deliberate, human-gated act (`authorized_robot_deletion`) — no orphan-cleanup burden is created. |
| `discovery_source_id` | `uuid`, FK → `discovery_source.id`, `NOT NULL`, `ON DELETE RESTRICT` | Same reasoning `CandidateClaim.discovery_source_id` already uses (Gate X): a target's eligibility is only meaningful through its source, and silently orphaning that link would strip auditability. |
| `url` | `text`, `NOT NULL` | The exact page. Never a domain, a prefix, or a pattern (A2 §2 req. 1/5). |
| `purpose` | `freshness_fact_area` enum, `NOT NULL` | What this target helps keep fresh — `SPEC`, `PRICE`, `AVAILABILITY`, `COMMERCIAL_STATUS`, `DEPLOYMENT`, `OFFICIAL_EVIDENCE`, `OTHER`. Informational routing for the human review queue; asserts nothing about canonical truth. |
| `manual_override` | `boolean`, `NOT NULL`, default `false` | Durable config, human-set at registration. When `true`, forces `MANUAL_CHECK` unconditionally — eligibility is never even consulted (Phase 3). This is how the `robotshop.com`/`eu.robotshop.com` rule is enforced. |
| `interval_days` | `integer`, `NOT NULL`, default `7`, `CHECK (interval_days >= 7)` | A2's `FRESHNESS_INTERVAL_DAYS`. The `CHECK` makes "someone quietly sets 1 day" a schema-level impossibility, not a code-review hope (A2 adversarial example 6). |
| `active` | `boolean`, `NOT NULL`, default `true` | Individually deactivatable per A2's requirement, without deleting history. |
| `last_checked_at` | `timestamptz`, nullable | Denormalized from the latest `FreshnessObservation` — factual history-cache (when did we last actually check), not an eligibility verdict, so it carries none of correction 3's staleness risk. |
| `last_result` | `freshness_result` enum, nullable | Denormalized latest result — `UNCHANGED`, `CHANGED`, `FETCH_ERROR`, `SOURCE_REMOVED`. Null until the first observation. Factual history, same reasoning as `last_checked_at`. |
| `etag` | `text`, nullable | Latest conditional-request validator, carried forward for the next check. |
| `last_modified` | `text`, nullable | Latest `Last-Modified` header value, same purpose. |
| `content_fingerprint` | `text`, nullable | Latest content hash (e.g. SHA-256 of the fetched body, or of a declared relevant excerpt — implementation detail of the later slice). Doubles as the deterministic `change_key` input for idempotency (Phase 6). |
| `last_change_detected_at` | `timestamptz`, nullable | Set only when `last_result = CHANGED`; distinct from `last_checked_at` so "checked recently, nothing new" is visibly different from "changed recently." |
| `created_at` / `updated_at` | `timestamptz`, `NOT NULL`, `now()` default | Standard. |

**No `execution_mode` column on this table** (correction 3). What a target's
mode *currently is* depends on `source.radar_eligible` plus the additional
currentness checks in Phase 3, both of which can change without this row ever
being written to — persisting a verdict here would let it silently go stale
the moment an unrelated `DiscoverySource` row's review expires. Mode is always
computed fresh; see Phase 3.

**Uniqueness**: `UNIQUE (robot_id, url)` — prevents duplicate registration of
the same robot/URL pair, exactly as required. (Not `(robot_id, discovery_source_id)`
— one robot may legitimately have several targets on the same source domain,
e.g. a spec page and a price page both on `unitree.com`.)

**Indexes**: `(active, last_checked_at)` — the scheduler's own query is "give
me active targets due for a check" (mode is filtered in application code
*after* this index narrows the candidate set, since mode is not a stored
column to index against). Plus the implicit indexes from the two FKs and the
unique constraint.

### `FreshnessObservation`

One row per **check attempt** (manual or scheduled).

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid`, PK | |
| `freshness_target_id` | `uuid`, FK → `freshness_target.id`, `NOT NULL`, `ON DELETE CASCADE` | An observation has no meaning without its target. |
| `trigger` | `freshness_trigger` enum, `NOT NULL` | `MANUAL` \| `SCHEDULED_FRESHNESS` (Phase 4 — a **new, dedicated** enum, not `crawl_trigger`). |
| `execution_mode_at_check` | `freshness_execution_mode` enum, `NOT NULL` | **Immutable, observation-time snapshot** of what `compute_execution_mode()` returned at the instant this attempt ran (correction 3). This is the *only* place the enum's value is ever stored — never on the mutable `FreshnessTarget` row — so it can never go stale: it is a historical fact ("this is what the mode was, right then"), not a live verdict a reader might mistake for current truth. Answers "why didn't this run fetch" from the audit log without recomputing anything. |
| `result` | `freshness_result` enum, `NOT NULL` | `UNCHANGED` \| `CHANGED` \| `FETCH_ERROR` \| `SOURCE_REMOVED`. |
| `etag` | `text`, nullable | What was returned/observed this attempt. |
| `last_modified` | `text`, nullable | Same. |
| `content_fingerprint` | `text`, nullable | Same — null on `FETCH_ERROR`. This is the `change_key` input (Phase 6). |
| `detected_change_type` | `freshness_fact_area` enum, nullable | Best-effort, non-binding classification (A2 §6.1) — only meaningful when `result = CHANGED`. |
| `http_status` | `integer`, nullable | Diagnostic only. |
| `error_detail` | `text`, nullable | Diagnostic only, bounded length at the application layer (no raw page body, ever — §4). |
| `discovery_candidate_id` | `uuid`, FK → `discovery_candidate.id`, nullable, `ON DELETE SET NULL` | **The explicit lineage FK (correction 2).** Set when this observation created/reused governed DATA-D1 work (Phase 5/6); `NULL` on every `UNCHANGED`/`FETCH_ERROR` observation, by construction — those branches never call the create-or-reuse function at all. `SET NULL` (not `RESTRICT`) because an observation is a historical fact about a check that happened — it must survive even if the discovery-layer candidate it pointed to is later deleted by an unrelated cleanup; the audit trail is the point, not the live pointer. FK lives entirely on this **new** table — `discovery_candidate` itself gains no column (Phase 2's structural-isolation rule, unchanged). |
| `checked_at` | `timestamptz`, `NOT NULL`, `now()` default | |

**Index**: `(freshness_target_id, checked_at DESC)` — "latest observations for
this target," the query every diagnosis and every `last_*` denormalization
update runs. **Second index**: `(discovery_candidate_id)` where not null — the
exact lineage-lookup correction 2 requires ("which observation created this
recheck work"), queryable in both directions: target → observations →
candidate (forward) and candidate → observation (reverse, via this index).

**No update, ever, after insert.** `FreshnessObservation` is append-only by
convention (application-level for v0.1 — the same honest scope
`PromotionAudit`'s ORM-level enforcement already states for itself: it stops
`session.*`, not raw SQL). A future hardening pass could add the same
`before_update`/`before_delete` guard `PromotionAudit` has; not required for
this slice, noted as a follow-up.

### New enums

```
freshness_execution_mode  ('AUTO_CHECK', 'MANUAL_CHECK',
                            'ELIGIBILITY_REVIEW_REQUIRED', 'INACTIVE')
freshness_result          ('UNCHANGED', 'CHANGED', 'FETCH_ERROR', 'SOURCE_REMOVED')
freshness_fact_area       ('SPEC', 'PRICE', 'AVAILABILITY', 'COMMERCIAL_STATUS',
                            'DEPLOYMENT', 'OFFICIAL_EVIDENCE', 'OTHER')
freshness_trigger         ('MANUAL', 'SCHEDULED_FRESHNESS')
```

All four are **new**, own their own `pg_type`, and touch no existing enum.
`freshness_execution_mode` is retained (correction 3 asked whether it should
be) — but its only storage location is `FreshnessObservation.execution_mode_at_check`,
an immutable snapshot column, never a mutable column on `FreshnessTarget`.

### Structural isolation, restated for this layer

Mirroring 0003 §5 / DATA-D1.10 / Gate K exactly: **no canonical table gains a
column or FK because of this migration, and `discovery_candidate` gains no
column either** (correction 2 — the lineage FK lives wholly on the new
`freshness_observation` table, pointing *to* `discovery_candidate.id`, never
the reverse). `robot.id` is referenced *from* `freshness_target`; `robot`
gains nothing. This layer cannot be discovered by walking outward from
`robot` or from `discovery_candidate`; it can only be found by querying
`freshness_target`/`freshness_observation` directly. Same discipline, same
reason: candidate/freshness data must never leak into a canonical read path by
accident.

---

## Phase 3 — Execution modes, and the runtime eligibility rule (corrected)

### 3.1 `radar_eligible` alone is confirmed **insufficient** (correction 3)

Direct inspection of `apps/api/app/models/discovery.py:82-93` (Phase 1) shows
`radar_eligible` checks exactly five conditions — `is_enabled`, `tos_status ==
ALLOWED`, `robots_status`, and reviewer attribution — and **does not check
`tos_expires_at` or `last_robots_checked_at` at all.** It therefore does
**not**, on its own, enforce DATA-D1.LIVE's own already-ratified currentness
requirements:

- **`docs/16` §7, requirement 9 / the 90-day default expiry**: *"the review
  has not expired."* Encoded in the schema as `tos_expires_at`, but never read
  by `radar_eligible`.
- **`docs/16` LIVE.2**: robots policy is re-read at the start of every run and
  **cached at most 24 hours** — a stored `robots_status` from longer ago must
  not be trusted as current. Encoded as `last_robots_checked_at`, likewise
  never read by `radar_eligible`.

**No new expiry period is invented here.** Both numbers above (90 days,
24 hours) are exactly the ones already ratified in `docs/16` §7 and LIVE.2 —
this contract only composes them into one additional check the freshness path
performs, on top of the unmodified `radar_eligible`.

```python
def freshness_auto_check_eligible(source: DiscoverySource, now: datetime) -> bool:
    """DATA-D1.9 (radar_eligible, unmodified) PLUS the currentness
    requirements docs/16 §7 and LIVE.2 already ratify but radar_eligible does
    not itself check. Fails closed on every axis — a missing/None value is
    treated as NOT current, never as "no expiry means forever eligible.\""""
    if not source.radar_eligible:
        return False
    if source.tos_expires_at is None or now > source.tos_expires_at:
        return False  # docs/16 §7 requirement 9 — no verifiable current review
    if (
        source.last_robots_checked_at is None
        or now - source.last_robots_checked_at > timedelta(hours=24)
    ):
        return False  # docs/16 LIVE.2 — robots cache ceiling
    return True
```

**This is a NEW function in the freshness service module — `radar_eligible`
itself is not edited.** `radar_eligible` has other callers (`adapters.ingest()`)
whose own scope this contract does not touch. Flagged as a finding, not
addressed here: `adapters.ingest()` has the **identical** currentness gap
(Phase 1), unexercised only because no live radar adapter exists yet. A future
hardening pass should probably lift `freshness_auto_check_eligible`'s
currentness logic into a shared helper both call — noted as a recommendation
for a later, separate slice, not performed by this contract.

### 3.2 Execution mode is computed, never persisted as target truth (correction 3)

`FreshnessTarget` stores **durable intent/config only** (`active`,
`manual_override`, `purpose`, `interval_days`) — no `execution_mode` column
exists on it (Phase 2). Mode is computed fresh, every time it is needed
(scheduler due-query, manual-queue render, CLI report), by exactly one
function with exactly one call site's worth of logic:

```python
def compute_execution_mode(target: FreshnessTarget, source: DiscoverySource, now: datetime) -> str:
    if not target.active:
        return "INACTIVE"
    if target.manual_override:
        return "MANUAL_CHECK"                              # eligibility never consulted
    if freshness_auto_check_eligible(source, now):
        return "AUTO_CHECK"
    return "ELIGIBILITY_REVIEW_REQUIRED"
```

The **only** place a mode value is ever stored is
`FreshnessObservation.execution_mode_at_check` (Phase 2) — an immutable
snapshot of what this function returned at the moment one specific check ran.
It cannot become stale because it is never read as if it were current; it is
read only as history ("what was the mode when we last looked"). There is no
column anywhere that a future caller could mistakenly treat as live truth
without recomputing it.

**Fail-closed is structural, not a code path that can be forgotten**:
`AUTO_CHECK` is the return value of a chain of boolean expressions, each of
which is independently false-by-default on any missing/stale/negative input —
`radar_eligible`'s five conditions, plus `freshness_auto_check_eligible`'s two
additional currentness checks, plus `manual_override` short-circuiting to
`MANUAL_CHECK` before eligibility is even evaluated. There is no `else` branch
that reaches a network call. **The scheduler run function itself only ever
attempts a fetch when `compute_execution_mode(...) == "AUTO_CHECK"` at the
moment of that specific attempt** (Phase 8) — the eligibility check is not a
gate the fetch code trusts from a stored value; it is the live condition under
which the fetch code is invoked at all, recomputed immediately before use.

---

## Phase 4 — Crawl trigger: a **dedicated** enum, not `crawl_trigger` reused

**Decision: do not reuse `crawl_trigger`. Add `freshness_trigger` as its own,
new, unrelated enum, attached to `FreshnessObservation`, not to `crawl_run`.**

Reasoning against reuse — "prefer the design that makes misuse hardest":

- `crawl_trigger` belongs to `crawl_run`, which is wired (via `crawl_run_id`
  FKs) into `candidate_claim` and `candidate_image_ref` — the **radar/discovery
  ingest path**, `adapters.ingest()`'s domain. Widening `crawl_trigger` to
  include `SCHEDULED_FRESHNESS` would put a freshness-triggered value on the
  *same* enum and, if a future author took a shortcut, the *same* run table
  that new-discovery crawling uses. The risk is not that this contract's own
  code would misuse it — it is that a **later, careless change** finds
  `crawl_run`/`crawl_trigger` already "supports scheduling" and reuses the
  whole `crawl_run` machinery (and therefore `ingest()`, and therefore new
  candidate discovery) for what was meant to be a bounded freshness check.
  DATA-D1.LIVE's own comment on `crawl_trigger` — *"one value means adding an
  automated trigger is a visible schema change"* — is a **misuse-hardening
  design already applied once**, and it works because the enum is small and
  its table has exactly one purpose. Reusing it for a second purpose *removes*
  that hardening rather than extending it.
- A dedicated `freshness_trigger` enum, attached to a table
  (`freshness_observation`) that has **no FK relationship to `crawl_run`,
  `discovery_candidate.claims`, or any adapter-facing structure**, is
  physically incapable of exercising radar/discovery code — there is no
  shared table for a shortcut to reuse.
- Cost of the dedicated enum: one more `pg_type`, no different in kind from
  the other three new enums this slice already adds. Negligible.

**`crawl_trigger` itself is untouched — still exactly `('MANUAL')`.** This
amendment adds zero values to it. New-discovery/competitor-radar crawling
remains governed by the unmodified `crawl_trigger`/`crawl_run`/LIVE.4 as
ratified, with no new capability, no new enum value, and no code path
connecting it to the freshness layer.

---

## Phase 5 — Change detection contract

```
UNCHANGED
  -> FreshnessObservation(result=UNCHANGED, fingerprint=<same as before>)
  -> FreshnessTarget.last_checked_at/last_result/etag/last_modified updated
  -> NO DiscoveryCandidate created or touched
  -> NO canonical write

CHANGED
  -> FreshnessObservation(result=CHANGED, fingerprint=<new>,
                           detected_change_type=<best-effort guess>)
  -> create_or_reuse_recheck() (Phase 6, corrected) -> pipeline.flag_recheck()
     on a DiscoveryCandidate linked to target.robot_id, keyed by a
     deterministic change identity (Phase 6) — NOT by target alone
  -> FreshnessObservation.discovery_candidate_id set (correction 2 rename;
     was recheck_candidate_id in the pre-correction draft)
  -> FreshnessTarget.last_change_detected_at updated
  -> NO canonical write — RECHECK_REQUIRED is workflow metadata (docs/11 §12),
     exactly as flag_recheck() already guarantees

FETCH_ERROR
  -> FreshnessObservation(result=FETCH_ERROR, http_status, bounded error_detail)
  -> FreshnessTarget.last_checked_at/last_result updated;
     etag/last_modified/content_fingerprint left UNCHANGED (carry the last
     known-good validators forward, so the next attempt can still use
     conditional-request semantics)
  -> NO inference of absence, false, or NOT_AVAILABLE on anything —
     UNKNOWN semantics (docs/11 §5) are binding here exactly as everywhere
     else: an error is UNKNOWN-about-this-check, never a negative fact
  -> retried on the NEXT scheduled interval (no in-run retry loop beyond
     Phase 7's max_retries for transient network errors)

SOURCE_REMOVED
  -> a specific FETCH_ERROR shape (e.g. sustained 404/410, or robots.txt now
     disallows what was previously allowed): FreshnessObservation(result=
     SOURCE_REMOVED)
  -> workflow signal only: surfaced in the weekly manual-queue report (Phase
     9) so a human can decide whether to set target.manual_override=true or
     target.active=false — both durable config fields a human sets explicitly
     (Phase 2/3); nothing here mutates them automatically, since that would
     be exactly the kind of persisted-and-possibly-stale verdict correction 3
     removed from execution_mode itself
  -> NO auto-unpublish, NO canonical fact deletion, NO change to
     Robot.is_published or any commercial/pricing/availability row
```

**The one function that may create governed work**
(`create_or_reuse_recheck`) is called from exactly one place — the `CHANGED`
branch — and nowhere else in this contract touches
`discovery_candidate`/`pipeline`/`promotion` at all.

---

## Phase 6 — Idempotency (corrected: deterministic change identity, not target-only)

**The pre-correction draft's key — `external_ref = f"freshness/{target.id}"`
— is withdrawn.** Under `discovery_candidate`'s existing
`UniqueConstraint("source_id", "external_ref")`, that key allows **at most one
candidate for the entire lifetime of a target**, which is wrong: a target
legitimately changes many times over months or years, and each genuinely new,
distinct change deserves its own discovery-layer work item — reusing one
candidate forever would silently merge unrelated changes into a single,
increasingly confused review thread, and would eventually try to `flag_recheck()`
a candidate a human has already resolved (`PROMOTED`/`REJECTED`), which
`pipeline.flag_recheck()` correctly **refuses** (H5: *"re-checking a promoted
robot is a NEW discovery event, not a status flip on the old one"*) — so the
old key would not just be semantically wrong, it would eventually raise.

### Deterministic change identity

```
change_key = normalized(observation.content_fingerprint)
             # or, for results with no page-content fingerprint, one of the
             # fixed, non-random, non-timestamp literals below
base_ref    = f"freshness/{target.id}/{change_key}"
```

| Observation shape | `change_key` |
|---|---|
| `CHANGED`, content fingerprinted | The fingerprint itself (already a stable hash of the page's relevant content — exactly what "a distinct detected change" means operationally). |
| `SOURCE_REMOVED` | The fixed literal `"SOURCE_REMOVED"` — deterministic, not time-based. Repeated weekly observations of the same still-missing page reuse one open thread. If the page later reappears with different content and then disappears again, that later disappearance is a genuinely new observation on a **changed target state**, not a mere repeat — it still resolves to this same literal key, and per the no-resurrection rule below reuses or references the existing `SOURCE_REMOVED` thread rather than opening a second one; distinctness for `SOURCE_REMOVED` is deliberately coarse (v0.1 does not attempt to distinguish "removed the first time" from "removed again later"). |
| Manual `CHANGE_FOUND` with an operator-supplied fingerprint | The supplied fingerprint, same as automated `CHANGED`. |
| Manual `CHANGE_FOUND` with no fingerprint supplied | The fixed literal `"MANUAL_CHANGE"` — deterministic, not the note text or a timestamp. Consistent with the "one open recheck thread per target" simplification below. |

**No random UUID, no timestamp, anywhere in this key** — every input is
either the content fingerprint itself or one of two fixed literal strings.

### Reuse-or-create algorithm — corrected: no generation suffix, ever

**A prior, withdrawn version of this algorithm** opened a generation-suffixed
candidate (`.../r2`) whenever the matched candidate was terminal. **That is
wrong and is removed.** The owner's ratified implementation invariant is
explicit: *"same observation / scheduler retry → same candidate/work... do
not allow a retry to create a new generation solely because an earlier
candidate became terminal between attempts."* A terminal candidate for a
given `change_key` means a human already resolved **exactly this content** —
if the identical content is observed again, there is nothing new to review,
whether or not the earlier candidate happened to become terminal before or
after this particular observation ran. Distinctness is decided **only** by
`change_key` (i.e. by content), never by the target candidate's lifecycle
state:

```python
def create_or_reuse_recheck(session, target, observation, reason) -> DiscoveryCandidate:
    change_key = _change_key(observation)          # table above
    ref = f"freshness/{target.id}/{change_key}"
    existing = _find_candidate(session, source_id=target.discovery_source_id,
                                external_ref=ref)
    if existing is None:
        candidate = _create_minimal_candidate(
            session, source_id=target.discovery_source_id, external_ref=ref,
            possible_robot_id=target.robot_id,
        )
        flag_recheck(session, candidate, reason)
        return candidate
    if existing.status in _TERMINAL:            # PROMOTED / REJECTED
        # This exact change_key was already resolved by a human. NEVER
        # resurrect it and NEVER open a new generation for it — per the
        # ratified invariant, a retry/repeat of the SAME content is not a
        # genuinely later distinct change. Lineage still points here (the
        # observation's discovery_candidate_id is set to `existing`) so an
        # auditor can see "this observation corresponds to already-resolved
        # work," but flag_recheck() is never called and nothing reopens.
        return existing
    flag_recheck(session, existing, reason)      # idempotent in effect
    return existing
```

**A genuinely new, later distinct change is never blocked by this.** It
reaches the `existing is None` branch and creates a fresh candidate normally,
because its `content_fingerprint` — and therefore its `change_key` and its
`external_ref` — is different from any prior one, regardless of what state any
*other* candidate on the same target is in.

### Behavior table

| Case | Behavior |
|---|---|
| Same target, same fingerprint (repeat `UNCHANGED`) | New observation row each time (honest log); no candidate touched. Fully idempotent in effect. |
| **Scheduler retry of the same changed response** (test I) | Identical `content_fingerprint` → identical `change_key` → identical `ref` → the existing, non-terminal candidate is found and reused via `flag_recheck()`. **Same candidate every time.** |
| **Repeated observation of an identical changed fingerprint** across separate runs (not yet resolved) | Same as above — the candidate stays open, `flag_recheck()` re-called (idempotent), context accumulates via its `reason` merge. |
| **Genuinely new, later changed fingerprint** (a real, distinct second change) | Different `content_fingerprint` → different `change_key` → different `ref` → not found → **new** candidate created, regardless of whether an earlier candidate for this same target (different fingerprint) is still open or already resolved. |
| **The exact same fingerprint recurs after its prior candidate was resolved** (`PROMOTED`/`REJECTED`) — e.g. the page reverted to content that was already reviewed once, or a retry landed after a human resolved the candidate in between | **No new work is created.** The lookup finds the terminal candidate, does not call `flag_recheck()` on it, and the observation's `discovery_candidate_id` references it for lineage only. This is the ratified invariant, test I3. |
| Same target, repeated fetch failure | Each attempt logs its own `FreshnessObservation(result=FETCH_ERROR)` (diagnosable sequence — test K, M); `FETCH_ERROR` never calls `create_or_reuse_recheck()` at all, so failures cannot produce candidates, duplicate or otherwise. |
| Concurrent creation attempts for the identical `(source_id, external_ref)` | `discovery_candidate`'s **existing, unmodified** `UniqueConstraint("source_id", "external_ref")` makes a second concurrent creation fail at the database level, not merely in application logic — unchanged from the pre-correction draft, still true under the new key shape. |
| Scheduler retries the same weekly run (workflow re-triggered, or `workflow_dispatch` run manually the same week) | Per-target: if `last_checked_at` is within `interval_days`, the target is simply not due (Phase 3) — the retry naturally re-processes only targets still due, and any repeat check converges per the rows above. No global "run id" gate is needed; idempotency is enforced per-target, per-change, not per-run. |

**Deliberate v0.1 simplification, stated so it is a decision and not an
accident**: a target has **at most one open (non-terminal) recheck thread per
distinct `change_key`**, not an unbounded number — two different *unresolved*
changes with different fingerprints do get two separate open candidates
(corrected from the withdrawn design, which only ever allowed one candidate
total), but the same fingerprint never opens a second thread while its first
is still unresolved.

**Interval enforcement (test N)**: a target is "due" iff
`last_checked_at IS NULL OR last_checked_at <= now() - interval_days`. This is
evaluated at query time by the scheduler's due-target lookup — not cached,
not separately tracked — so it cannot drift from the stored `interval_days`.

---

## Phase 7 — Rate / network policy (v0.1 defaults)

```
per_host_concurrency     = 1        (strictly serial per host — v0.1 has at
                                      most a handful of eligible targets per
                                      host anyway; concurrency is a later
                                      optimization, not a v0.1 need)
request_timeout_seconds  = 10
max_retries              = 1        (one retry on a transient network error
                                      only — connection reset/timeout, never
                                      on a 4xx/5xx HTTP response, which is
                                      recorded as FETCH_ERROR immediately)
retry_backoff            = 5s fixed (not exponential — v0.1 has at most one
                                      retry, so a backoff *schedule* is
                                      over-engineering; revisit if
                                      max_retries ever grows)
max_targets_per_run      = 50       (a hard ceiling far above the current 12
                                      freshness-candidate domains — exists so
                                      a future bulk-registration mistake
                                      cannot turn one scheduled run into an
                                      unbounded fetch spree; the run simply
                                      stops registering more work past this
                                      count and reports the overflow)
```

Also binding, restated from A2 §2/§6 rather than re-derived:

- exact registered URL only, one fetch, no link-following;
- honour any declared `Crawl-delay` as a floor if the source's `robots.txt`
  states one (mirrors `docs/11` §14 and `docs/17` precedent);
- conditional request (`If-None-Match`/`If-Modified-Since`) whenever the
  target carries a prior `etag`/`last_modified`;
- identifiable User-Agent (`HumanoidOnline-FreshnessBot/1.0
  (+https://humanoidonline.com)` or equivalent — exact string is
  implementation detail, not frozen here);
- no images/assets fetched — only the registered page's text/markup;
- no authentication, no CAPTCHA bypass, no access-control circumvention
  (A2 §2 req. 7, restated absolutely);
- **one failing target does not abort the run**: the per-target check runs
  inside its own try/except; a `FETCH_ERROR` on one target is recorded and the
  loop continues to the next target (test M).

---

## Phase 8 — Scheduler authority

**One scheduler authority: GitHub Actions `schedule:`**, invoking the same
governed CLI a human runs manually. No business logic lives in the workflow
YAML — it does exactly two things: check out the repo, then run
`uv run --directory apps/api python -m app.cli.freshness_check run`.

**Why this satisfies "same application/service path as manual run":** both
the scheduled invocation and a human's manual invocation call the identical
`app.cli.freshness_check` entry point, which calls the identical
`freshness.run_due_checks(session, trigger=...)` service function — the only
difference is the `trigger` value passed through (`SCHEDULED_FRESHNESS` vs
`MANUAL`, Phase 4), which is recorded on each `FreshnessObservation` and
otherwise affects nothing about eligibility, fetch behavior, or write paths.
**The scheduler cannot bypass eligibility (test P)** because eligibility is
evaluated inside `run_due_checks()`, not in the workflow YAML — the YAML has
no way to skip a call it never makes to a check it never performs.

**Proposed schedule**: `cron: '17 6 * * 1'` — **Monday 06:17 UTC**. Reasoning:
weekly per `FRESHNESS_INTERVAL_DAYS = 7` (A2); off-peak for both US and EU
business hours, so a slow run or a transient source hiccup is not competing
with active development/on-call attention; a non-round minute (`:17`, not
`:00`) because GitHub's own scheduling guidance notes exact-hour crons are the
most contended slot on their infrastructure and can be delayed — this job has
no latency requirement, so avoiding contention costs nothing and reduces the
chance of a skipped/delayed run during a busy period.

**`workflow_dispatch` is included** for a manual "run the scheduled path
right now" trigger (useful for verifying the workflow itself without waiting
a week) — it invokes the exact same CLI command with `trigger=SCHEDULED_FRESHNESS`,
it does not become a third trigger value, and it still cannot exceed
`max_targets_per_run` or bypass eligibility, because it is calling the same
function.

**No production credential is added by this document.** The eventual
implementation slice will need a `DATABASE_URL` (or equivalent) GitHub Actions
secret pointed at the production database for the scheduled job to write
freshness observations against real data — that is a deliberate, visible
credential-provisioning step for whoever implements this slice, explicitly
flagged here rather than assumed, per this contract's own non-goals.

**No generic crawler workflow is created.** The workflow's one job has one
purpose (its name states so explicitly: e.g. `catalogue-freshness-weekly`),
and it has no parameters that widen its target set beyond what
`freshness_target` already contains — it cannot be pointed at an arbitrary
URL or domain by any input it accepts.

---

## Phase 9 — Manual mode

**One service module, `app/services/freshness/`, two CLI-exposed entry
points, zero separate truth pipelines:**

```
freshness.run_due_checks(session, *, trigger, operator=None, limit=None)
    -> the shared function. Computes execution_mode per due target; for
       AUTO_CHECK targets, performs the bounded fetch (Phase 7) and records
       the observation + change-detection outcome (Phase 5/6); for
       non-AUTO_CHECK targets, does nothing (they are not "run," they are
       reported — see below).

freshness.due_manual_targets(session) -> list[FreshnessTarget]
    -> targets whose current execution_mode is MANUAL_CHECK or
       ELIGIBILITY_REVIEW_REQUIRED and are due (Phase 6's due calculation).
       Returns robot + url + exact reason (manual_override vs no current
       DATA-D1.9 decision) for each.

freshness.record_manual_check(session, target, *, outcome, operator, note=None)
    -> outcome in {CHECKED_UNCHANGED, CHANGE_FOUND, SOURCE_UNAVAILABLE}.
       Writes exactly one FreshnessObservation with trigger=MANUAL and the
       corresponding result (UNCHANGED / CHANGED / FETCH_ERROR), attributed
       to `operator` (required, mirroring bootstrap.py's --operator
       discipline). CHANGE_FOUND runs through the IDENTICAL
       create_or_reuse_recheck() path CHANGED does in the automated flow —
       literally the same function call, not a parallel implementation.
```

CLI (`app/cli/freshness_check.py`, argparse subcommands, following
`bootstrap_inventory.py`'s shape exactly):

```
uv run --directory apps/api python -m app.cli.freshness_check run
    [--limit N] [--trigger MANUAL|SCHEDULED_FRESHNESS] [--dry-run]
    # AUTO_CHECK targets only. --trigger defaults to MANUAL when run by a
    # human at a terminal; the GitHub Actions workflow passes
    # --trigger SCHEDULED_FRESHNESS explicitly (never inferred from context).

uv run --directory apps/api python -m app.cli.freshness_check queue
    # Prints the weekly MANUAL_CHECK / ELIGIBILITY_REVIEW_REQUIRED report
    # (Phase 6 example format from the original scanner design turn):
    #   AUTO_CHECK: N due, M unchanged, K RECHECK_REQUIRED
    #   MANUAL_CHECK: <robot> — <url>
    #   ELIGIBILITY_REVIEW_REQUIRED: <domain> — <reason>

uv run --directory apps/api python -m app.cli.freshness_check mark
    <target-id> --outcome CHECKED_UNCHANGED|CHANGE_FOUND|SOURCE_UNAVAILABLE
    --operator "name@…" [--note "..."]
    # Human records a manual check result. Requires --operator, exactly as
    # every other DATA-D1 writer does.
```

**No canonical writes exist anywhere in this module.** Grep-verifiable in the
eventual implementation: `freshness/` imports `Robot` only to validate a FK on
registration (a separate, not-yet-designed `register` step — deliberately
**not** specified by this contract, since Phase 11 requires zero targets be
seeded by this slice) and never assigns to any of its attributes.

---

## Phase 10 — Source activation

**Zero `AUTO_CHECK` targets is the correct, expected, and required starting
state.** `run_due_checks()`'s due-target query naturally returns an empty set
when no `FreshnessTarget` rows exist at all (none are created by this
contract or its migration — Phase 11) — the system is fully well-defined and
safe with nothing registered, nothing eligible, and nothing running (test Q).

**No bootstrap-as-eligible.** Building the table does not make any of the 12
freshness-candidate domains identified in `docs/21` §5 eligible; eligibility
still requires its own recorded `DiscoverySource` row and DATA-D1.9 review,
exactly as `docs/21` §11.1 sequences it (step 2, after this implementation
contract, step 1).

**`robotshop.com` / `eu.robotshop.com`**: any future `FreshnessTarget` row for
either domain **must** be registered with `manual_override = true` (Phase 3)
at creation time — this is an operational rule for whoever performs that
future registration, not something this contract's schema can enforce by
itself (a `CHECK` constraint keyed on URL substring would be brittle and easy
to defeat by a redirect or a new path; the enforcement point is the human
registration step and the standing operational instruction, restated here so
it is not lost between now and then).

---

## Phase 11 — Migration / rollback

**One migration**, `db/migrations/0010_add_freshness_layer.sql`, following
0003/0004's exact shape:

- Header comment naming this contract and `docs/21`, stating explicitly:
  *"structurally isolated — no canonical table is altered, no FK from
  `robot`/`discovery_candidate` is added; adds no adapter, no HTTP client, no
  scheduler, and nothing in this repository can perform a fetch after
  applying it."*
- `SET search_path TO humanoid, public;`
- 4 new enum types, each guarded by
  `IF NOT EXISTS (SELECT 1 FROM pg_type ...)`.
- 2 new tables (`freshness_target`, `freshness_observation`) with their FKs,
  `CHECK`, and `UNIQUE` constraints, each guarded by
  `IF NOT EXISTS (SELECT 1 FROM pg_class ...)` or `CREATE TABLE IF NOT EXISTS`.
- 3 new indexes (Phase 2: `freshness_target(active, last_checked_at)`,
  `freshness_observation(freshness_target_id, checked_at DESC)`,
  `freshness_observation(discovery_candidate_id)` partial where not null),
  same idempotent-guard convention.
- **No `ALTER` of any existing table.** `crawl_trigger`, `discovery_source`,
  `discovery_candidate` (correction 2 — gains no column, the lineage FK lives
  only on the new `freshness_observation` table), `robot`, and every
  canonical table are untouched by this migration's DDL.
- Mirrored into `db/schema.sql` SECTION 10 (alongside the existing discovery
  layer), per the repository's "DDL is canonical, models mirror it" rule.

**Rollback**: a companion `DROP` script (or the down-migration convention this
repo already uses, if any — confirmed absent for 0001–0009, which are
forward-only; this slice follows that same forward-only convention rather
than introducing a new one). Rollback is low-risk by construction: dropping
`freshness_observation` then `freshness_target` then the 4 enum types removes
the entire layer with **zero effect on any canonical table**, because nothing
outside this layer references it (Gate K, restated).

**Data backfill: NO**, on every axis the contract requires:

| | |
|---|---|
| `DiscoveryCandidate` backfill | **NO** — Decision B, restated. |
| Catalogue facts changed | **NO** — this migration is additive DDL only. |
| Existing discovery rows changed | **NO** — no `UPDATE` statement anywhere in the migration. |
| `FreshnessTarget` rows seeded | **NO**, not even for the 12 identified candidate domains. Seeding is a later, explicit, human-run registration step (not yet designed — see Phase 10) — "the table exists" and "targets are registered" are two separate, separately-authorized events, exactly as `docs/21` §11.1 sequences eligibility review *before* registration. |

---

## Phase 12 — Test contract (planned; not written this turn)

| | Test | Proves |
|---|---|---|
| A | `test_freshness_target_unique_robot_url` | Duplicate `(robot_id, url)` insert fails at the DB constraint. |
| B | `test_freshness_target_robot_fk_integrity` | Insert with a non-existent `robot_id` fails; deleting a robot cascades. |
| C | `test_freshness_target_source_fk_integrity` | Insert with a non-existent `discovery_source_id` fails; deleting a referenced source is restricted. |
| D | `test_compute_execution_mode_fails_closed_on_missing_review` | `compute_execution_mode()` (never a stored column — correction 3) returns `ELIGIBILITY_REVIEW_REQUIRED`, never `AUTO_CHECK`, for a target whose source has no `DiscoverySource` row / no review at all. |
| E | `test_auto_check_requires_current_affirmative_review` | `freshness_auto_check_eligible()` — **not** bare `radar_eligible` — returns `False`, and `compute_execution_mode()` returns `ELIGIBILITY_REVIEW_REQUIRED`, for: `tos_status != ALLOWED`; `robots_status = DISALLOWED`; **and, distinctly, a `radar_eligible = True` source whose `tos_expires_at` has passed**; **and a `radar_eligible = True` source whose `last_robots_checked_at` is more than 24 hours old** — the two currentness cases `radar_eligible` alone does not catch (Phase 3.1 finding), each asserted as its own case so the composed function's extra checks are proven, not assumed. |
| F | `test_manual_check_makes_no_http_request` | `run_due_checks()` never invokes the fetch function for a `MANUAL_CHECK`/`ELIGIBILITY_REVIEW_REQUIRED` target (mock/spy the fetcher, assert zero calls). |
| G | `test_unchanged_fingerprint_creates_no_candidate` | Two `AUTO_CHECK` runs with an identical mocked fingerprint → zero `DiscoveryCandidate` rows created. |
| H | `test_changed_fingerprint_creates_or_reuses_recheck_only` | A changed fingerprint → exactly one `DiscoveryCandidate` in `RECHECK_REQUIRED`, no canonical write, no promotion-gate progression. |
| I | `test_repeated_changed_fingerprint_is_idempotent` | Two `CHANGED` observations for the same target with the **same** fingerprint (scheduler retry) → still exactly one open recheck candidate, found via the deterministic `change_key`-based `external_ref` (Phase 6, corrected). |
| I2 | `test_distinct_new_fingerprint_creates_a_new_candidate` | A **different** later fingerprint on the same target → a **second**, distinct `DiscoveryCandidate` — proves the corrected key is per-change, not per-target (the withdrawn `freshness/{target.id}`-only key would have collapsed these into one). |
| I3 | `test_terminal_candidate_is_never_resurrected` | A candidate for `change_key=X` is `PROMOTED` (or `REJECTED`); a later observation with the **same** fingerprint `X` arrives → the reuse lookup finds the terminal candidate, does **not** call `flag_recheck()` on it, and creates **no new candidate of any kind** — `create_or_reuse_recheck()` returns the terminal candidate for lineage reference only. Directly proves the ratified invariant: no resurrection, and no new generation opened solely because the matched candidate became terminal. |
| J | `test_canonical_unchanged_on_every_scanner_path` | Snapshot every canonical `robot`/`pricing_offer`/`availability_offer` row before and after a full run (unchanged/changed/error/manual) → byte-identical. |
| K | `test_fetch_error_preserves_canonical_state_and_validators` | A mocked network error → `FreshnessObservation(FETCH_ERROR)`, canonical untouched, `etag`/`last_modified`/`content_fingerprint` on the target carried forward unchanged. |
| L | `test_source_removed_does_not_unpublish` | A mocked sustained-404 → `SOURCE_REMOVED` observation, `Robot.is_published` unchanged, `manual_override`/`active` untouched (no automatic config mutation). |
| M | `test_one_failing_target_does_not_abort_others` | Target 1 raises, targets 2–3 still get observations recorded in the same run. |
| N | `test_weekly_interval_enforced` | A target checked 3 days ago is not "due"; one checked 8 days ago is. |
| O | `test_crawl_trigger_untouched_and_unrelated` | `crawl_trigger` enum values are exactly `{'MANUAL'}` after this migration; `freshness_trigger` is a distinct type with no shared table/FK to `crawl_run`. |
| P | `test_scheduler_cannot_bypass_eligibility` | Calling `run_due_checks(trigger=SCHEDULED_FRESHNESS)` against a target whose source is not eligible (including the two currentness-only cases from test E) performs zero fetches — same assertion as F, run under the scheduled trigger specifically. |
| Q | `test_zero_auto_check_targets_is_valid` | `run_due_checks()` against an empty `freshness_target` table returns cleanly, no error, no fetch attempted. |
| R | `test_manual_and_scheduled_share_one_change_path` | A `CHANGE_FOUND` manual mark and a `CHANGED` automated result for equivalent inputs produce identical `DiscoveryCandidate`/`RECHECK_REQUIRED` outcomes (same function, asserted by calling both and diffing the resulting candidate state). |
| S | `test_observation_candidate_lineage_is_queryable` | For a `CHANGED` observation, `observation.discovery_candidate_id` is set and resolves to the exact candidate `flag_recheck()` acted on; for `UNCHANGED`/`FETCH_ERROR` observations, it is `NULL` by construction. Answers "which exact observation created this recheck work" in both directions (correction 2). |
| T | `test_discovery_candidate_gains_no_column` | Schema introspection: `discovery_candidate`'s column set is identical before and after the freshness migration — the lineage FK lives only on `freshness_observation` (correction 2, "do not ALTER `discovery_candidate`"). |

**Planned count: 22** (A through T, plus I2 and I3 inserted by this correction
pass to cover the corrected idempotency design specifically — kept as I2/I3
rather than renumbering the rest of the table), plus the existing, unmodified
discovery-layer test suites (`test_discovery.py`, `test_acquisition_schema.py`,
etc.) continue to pass unchanged, which is itself a required assertion of the
eventual PR (nothing in this layer may perturb existing discovery/promotion
behavior).

---

## Non-goals (restated for this contract specifically)

This document does **not**: implement `app/models/freshness.py`, any
migration file, any CLI, any GitHub Actions workflow, or `freshness_check`'s
actual fetch logic; perform any DATA-D1.9 eligibility review or fetch any
external source; register any `FreshnessTarget` row; change `crawl_trigger`,
`discovery_candidate`, `discovery_source`, or any canonical table; touch
compare-performance work, lead/email work, Netlify, Vercel, MEDIA-01,
AGENT-02, or `.claude/launch.json`/`apps/api/.gitignore`.

## Ratification record

```
STATUS:                      RATIFIED — Robert Konecny (product owner),
                             2026-08-25. Corrections applied before
                             ratification: (1-3) idempotency key,
                             observation->candidate lineage FK, and runtime
                             eligibility currentness (first correction pass);
                             (4) removed generation-suffixing for a terminal
                             candidate match — a retry/repeat of the SAME
                             content_fingerprint now creates NO new work,
                             ever, regardless of the matched candidate's
                             lifecycle state (second correction pass, applied
                             at ratification per the owner's explicit
                             implementation invariant).
Proposed:                    2026-08-25
Implements:                  docs/21 §11.1 step 1 (the "separate
                             implementation contract")
Authorizes:                  NOTHING YET — documentation only. Migration,
                             models, service, CLI, and workflow all remain
                             to be written in a SEPARATE, later slice once
                             this contract itself is ratified.
Model:                       FreshnessTarget (durable config only — no
                             execution_mode column, corrected) +
                             FreshnessObservation (append-only history,
                             carries an immutable execution_mode_at_check
                             snapshot + the discovery_candidate_id lineage
                             FK) — Model B, history required
New enums:                   freshness_execution_mode (stored ONLY as an
                             observation-time snapshot, never on the
                             mutable target row), freshness_result,
                             freshness_fact_area, freshness_trigger — all
                             new, none shared with crawl_trigger
crawl_trigger:                UNCHANGED — still exactly {'MANUAL'}
Idempotency key (corrected): discovery_candidate.external_ref =
                             "freshness/<target_id>/<change_key>", where
                             change_key is the content fingerprint (or a
                             fixed literal for SOURCE_REMOVED/unfingerprinted
                             manual reports) — NOT target-id-only, so a
                             genuinely distinct later change gets its own
                             candidate. A terminal (PROMOTED/REJECTED)
                             candidate for a given change_key is NEVER
                             resurrected AND never triggers a new generation
                             — per the ratified implementation invariant, a
                             retry/repeat observation of the SAME content
                             creates no new work at all, referencing the
                             terminal candidate for lineage only.
Eligibility runtime
  (corrected):                freshness_auto_check_eligible(source, now) =
                             radar_eligible AND tos_expires_at current
                             (docs/16 §7, 90-day default, unchanged) AND
                             last_robots_checked_at within 24h (docs/16
                             LIVE.2, unchanged) — composed in the freshness
                             service, radar_eligible itself NOT modified.
                             FINDING: radar_eligible (and adapters.ingest())
                             do not themselves check either currentness
                             condition today — verified by direct code
                             inspection, unexercised because no live radar
                             adapter exists yet. Flagged for a future,
                             separate hardening slice; not fixed here.
Scheduler:                   GitHub Actions schedule: '17 6 * * 1' (Mon
                             06:17 UTC) + workflow_dispatch, invoking the
                             same governed CLI a human runs manually
Seed data:                   NONE — zero FreshnessTarget rows created by
                             the migration; registration is a later,
                             separate, explicit step
Candidate backfill:          NOT AUTHORIZED (Decision B, unchanged)
robotshop.com /
  eu.robotshop.com:          MANUAL_CHECK via manual_override (durable
                             config, checked before eligibility is even
                             evaluated), independent of DATA-D1.9,
                             unchanged from A2
Test plan:                   22 tests (A-T plus I2/I3) specified, none
                             written
```
