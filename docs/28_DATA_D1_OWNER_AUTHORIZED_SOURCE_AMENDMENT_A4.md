# DATA-D1.LIVE — Amendment A4: `OWNER_AUTHORIZED` source access

> **STATUS: OWNER DIRECTION 2026-10-18 — DRAFT FOR PR REVIEW.**
> Repository-effective only upon merge of the reviewed PR. Ratification changes
> what is permitted in principle; it starts no crawl, enables no source, sets no
> cadence and applies no migration (§7).
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md` at
> **LIVE.2 / §5** and the scope of **DATA-D1.9**: an enabled standing automated
> source needs an *access basis*, which is either the existing affirmative
> owner-recorded terms decision (`SOURCE_PERMISSION`) or a new, attributed,
> source-specific owner business decision (`OWNER_AUTHORIZED`). It clarifies
> `21_DATA_D1_LIVE_AMENDMENT_A2_SCHEDULED_FRESHNESS.md` requirement 3 (§4).
> Everything else in `docs/16`, `docs/17` (A1), `docs/21` (A2), `docs/26` (A3)
> and DR-A4 is unchanged. "A4" here is the amendment series (A1 = docs/17,
> A2 = docs/21, A3 = docs/26); it is unrelated to the decision record DR-A4
> (`docs/decisions/DR-A4_TOS_NOT_TIME_GATED.md`).

## 1. Owner direction

On **2026-10-18** the product owner (Robert Konecny) approved adding six sources
to the discovery monitoring programme: **Unitree Robotics**
(`unitree-robotics-official`), **Booster Robotics** (`booster-robotics-official`),
**AgiBot** (`agibot-official`), **Agility Robotics**
(`agility-robotics-official`), **Figure AI** (`figure-ai-official`) and
**Alza.cz** (`alza-cz`). All six are registered in production, disabled, with
`tos_status = UNKNOWN`, `robots_status = UNKNOWN` and the instruction recorded in
their notes.

For Alza.cz this supersedes the 2026-10-05 limit "approved reference source, NOT
approved for automated monitoring". Its manual-capture path (`manual_capture`,
`alza_cz_reference_proposals`) is unchanged.

## 2. Semantics

**A4.1 — Two bases, never conflated.**

| `access_basis` | Means | Requires |
|---|---|---|
| `SOURCE_PERMISSION` (default; every pre-A4 source) | The owner read the site's terms and recorded that they permit automation. | `tos_status = ALLOWED` (DR-A4: does not expire). |
| `OWNER_AUTHORIZED` | The owner's **internal business decision** to monitor this source. | An attributed, timestamped, reasoned, path-scoped owner decision; `tos_status` not `RESTRICTED`/`PROHIBITED`. |

**A4.2 — Owner authorization is not publisher consent.** It never sets or implies
`tos_status = ALLOWED`. `tos_status` stays the truthful record of what is known
about the publisher's terms. An `UNKNOWN` stays `UNKNOWN`. Run reports, the CLI
(`source show`) and the admin list show the basis, so the two cases are never
confused.

**A4.3 — A recorded restriction wins.** `OWNER_AUTHORIZED` cannot be recorded
for, and does not apply to, a source whose recorded terms decision is
`RESTRICTED` or `PROHIBITED`. A later review that records one stops the source
(it is disabled in the same act).

**A4.4 — Attributed and append-only.** Every authorization and revocation is a
row in `discovery_source_owner_authorization_event` (append-only: UPDATE, DELETE
and TRUNCATE are refused by the database). The `owner_*` columns on
`discovery_source` are the effective projection of the latest event, and all of
them are set exactly when the basis is `OWNER_AUTHORIZED`
(`ck_discovery_owner_authorization`).

**A4.5 — Scope is a ceiling, never a widening.** The owner's path prefixes must
lie inside the attributed review's `allowed_path_prefixes`. At runtime, the
approved paths are the owner's prefixes still covered by the current review, so
a later, narrower review narrows the source too. The host is the registered
`homepage_url` host only. A storefront on another host (`shop.unitree.com`,
`store.agibot.com`) is a different source that needs its own registration,
review and decision.

**A4.6 — Four separate acts.** *Authorizing*, *enabling*, *scheduling* (cadence)
and *executing* are separate, attributed acts. `source authorize-owner` never
enables. `source enable` needs an access basis, a non-disallow robots decision, an
attributed review and approved paths. `source revoke-owner` disables the source
in the same act, so a running cadence stops at the next cycle.

**A4.7 — Nothing else is relaxed.** LIVE.2's robots row (re-read on every run,
24 h ceiling, a new disallow disables the source), LIVE.3 (no circumvention of
any kind), the bounded fetch, the reviewed versioned adapter
(`structural_review`, seeds, patterns, target cap), the observation separation
(no canonical write; proposals, claims, materialization and import stay
separately governed) and DATA-D1's "UNKNOWN stays UNKNOWN" apply identically
under both bases. A block is a finding, never an obstacle.

## 3. What an `OWNER_AUTHORIZED` source still needs before it is monitored

1. A **read-only structural review** of the host under its own owner work order:
   `robots.txt` for our user agent plus the candidate seed pages, recorded as
   `docs/discovery/<SOURCE>_STRUCTURAL_REVIEW_<date>.md`. That review is network
   access, and it is not authorized by this amendment.
2. A **reviewed, versioned adapter** in `apps/api/app/services/discovery/sources/`,
   registered in `ADAPTERS`, with offline fixtures that prove bounded
   enumeration, deterministic identity, change detection and zero canonical
   writes. Each adapter is its own commit and review.
3. `source review` with the **honest** terms decision (normally `UNKNOWN`), the
   observed robots decision and the reviewed path prefixes.
4. `source authorize-owner KEY --by … --reason … --path-prefix …`.
5. `source enable`, then `source cadence`.

Retail evidence keeps its meaning. A distributor's price is a `RETAIL_PRICE` for
that seller, market and condition; it is never an MSRP, and `NEW` is never
`USED`. A reservation deposit is not a price. A global or Chinese announcement is
not EU availability. All of these remain proposals until a human decision and
claim, as before.

## 4. Scheduled freshness (`docs/21`) is not extended

The 2026-10-18 direction covers the **discovery monitoring programme**.
`docs/21` requirement 3 (an affirmative DATA-D1.9 decision for scheduled
freshness re-checks) is therefore satisfied only by `SOURCE_PERMISSION`.
`freshness_auto_check_eligible` refuses an `OWNER_AUTHORIZED` source, and
`mode_reason` says so. Extending owner authorization to scheduled freshness is
a separate owner decision.

## 5. Source registry as version-controlled identity

`db/discovery/source_registry.json` lists the identity (key, name, class, https
origin) of every registered source. `python -m app.cli.discovery source sync`
(plan by default; `--apply --by WHO`) registers a missing source DISABLED with
ToS and robots UNKNOWN, reports `DRIFT` on a differing existing row without
overwriting it, and reports `UNMANAGED` rows without deleting them. It never
reviews, authorizes, enables, schedules or fetches. Adapter readiness is
reported from code (`sources.ADAPTERS`), never from the file. Re-applying it is
a no-op.

## 6. Schema (migration `0025_owner_authorized_source_access.sql`)

Additive and idempotent: `discovery_source.access_basis` (default
`SOURCE_PERMISSION`) and the `owner_*` projection columns;
`ck_discovery_access_basis`, `ck_discovery_owner_authorization`; the replaced
`ck_discovery_source_eligible`; the append-only
`discovery_source_owner_authorization_event` with its index and triggers. Every
existing row keeps its meaning (`SOURCE_PERMISSION`), and nothing is enabled or
authorized by applying it. The least-privilege `discovery_observer` role gains
nothing: it cannot write the basis or the event table.

## 7. Activation order (each step a separate, owner-approved act)

1. Review and approve the PR head.
2. **Apply `0025` to production before merging.** The API refuses to serve a
   database whose migration state differs from the build
   (`app/db/migration_state.py`), so merge-then-migrate would take the API down.
   Take a Neon safety branch first (`pre-0025-YYYYMMDD`), apply, verify the
   ledger and that all 9 rows are unchanged.
3. Merge. Verify CI, deployment and health.
4. `source sync` (plan) against production must report 9 `UNCHANGED`, 0 drift.
5. Per source, under its own work order: §3 steps 1–5. A source is reported
   **actively monitored** only after an observation cycle has completed for it.

Rollback: before step 3, delete nothing and restore from the safety branch if
needed. After it, a forward fix. The migration is additive, so the pre-A4 code
ignores the new columns, but the strict migration check pins code and schema
together. Revoking a single source is `source revoke-owner`.
