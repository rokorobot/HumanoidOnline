# DR-D1 — HO-DATA Fast Lane and the standing manufacturer-research authorization

| | |
|---|---|
| **Status** | **DECIDED — ADOPTED, 2026-10-22, Robert Konecny (product owner)** |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Applies** | `docs/26` §2.1 (research work order), §6 (human approval gate, path (b) catalogue authoring), §6A (phase authorization) |
| **Unchanged** | `docs/26` §2.2 (standing automated processes), §3 (evidence record), §4 (labelling), §5, §7 (publication), §8; `docs/16` LIVE.2/LIVE.3; AGENTS.md rules 1–10 |
| **Schema** | None. No new tooling, workflow or infrastructure. |

## 1. Standing manufacturer-research authorization (90 days, revocable)

The owner grants a **standing `AGENT_ASSISTED_RESEARCH` work order** under `docs/26` §2.1:

| | |
|---|---|
| **Reference** | `HO-DATA-STANDING 2026-10-22` (cite this in every evidence statement it supports, `docs/26` §3.1) |
| **Valid** | 2026-10-22 to **2027-01-20** inclusive (90 days). Renewal is an explicit owner act. |
| **Revocation** | The owner may revoke or narrow it at any time, in chat or in this file. Revocation takes effect immediately. Evidence retrieved before revocation keeps its provenance. |
| **Research targets** | Every robot record in the catalogue master (`db/catalogue/robots/`), and humanoid models newly discovered by the discovery pipeline or during research. |
| **Source class** | Publicly accessible **manufacturer** material: product pages, specification tables, datasheets, manuals, press releases and technical documentation published on the manufacturer's own hosts (including their CDN and documentation hosts). Relevant manufacturer sources discovered during research are in scope. |
| **Excluded** | Distributor, reseller, marketplace and wiki hosts as a basis for a fact; copies of manufacturer documents hosted by third parties (pending an owner policy); circumvention of any access control, login, paywall or bot block (`docs/16` LIVE.3); archives of withdrawn pages unless the owner rules otherwise. |

Within this scope, routine manufacturer research for existing and newly discovered models **does not need a new
work order per batch**. Retrieval stays read-only and proportionate (`docs/26` §2.1, §6B).

This authorization is **not**:

- an eligibility decision. It enables no `DiscoverySource`, registers no freshness target and adds nothing to the radar
  set (`docs/26` §2.2);
- approval of any catalogue mutation. Every change to `db/catalogue/` still passes the `docs/26` §6 approval gate;
- approval of a new robot record, a publication change, an identity or same-entity decision, a commercial claim (price,
  availability, commercial status) or any proposed semantic policy (HO-DATA-02B D1–D12).

## 2. HO-DATA Fast Lane (catalogue enrichment batches)

Fast Lane is the operating procedure for enrichment batches under `docs/26` §6.1(b). It reduces administrative steps,
not verification standards.

1. **Collect and validate.** Manufacturer evidence → edition matching → deduplication → exact proposed changes. Every
   value is raw-verified against the retrieved source. Values relayed only by a summarizing tool do not count.
2. **One consolidated batch PR**, presenting the `docs/26` §6.2 evidence package: exact robot editions, current values,
   proposed values, source evidence, caveats, held items and why, expected production changes (an expected-change
   manifest for `db/import_preflight.py`), and projected completeness.
3. **One owner approval** of that exact batch, recorded in the PR before merge (`docs/26` §6.5). It covers the merge,
   the rehearsal on a production branch copy, the scoped production import and its verification, run in sequence
   without further approval requests.
4. **Execute and verify.** Merge → rehearsal (`import_catalogue.py --only …` twice, `import_preflight.py` with the
   manifest, `import_identity_check.py`) → retained Neon safety branch → scoped production import → the same checks
   against production → API and page check → one report (added fields, affected robots, unchanged data, updated
   core and P0 completeness).

**Stop conditions.** An unexpected change, a failed safeguard, or a change in scope stops execution. A changed batch
needs a new approval.

**Priorities.** P0: missing height, weight, payload, runtime, walking speed, DoF. P1: other missing core fields.
P2: extended specifications. **Hold:** conflicting facts, ambiguous editions, unsupported claims and claims that
depend on an unapproved policy. These are presented separately for owner decision and never ride in the clean batch.

**Metric.** Core-field UNKNOWN over published robots × the 22 core fields, and P0 UNKNOWN over published robots × the
6 P0 fields, as defined in HO-DATA-02A. Baseline 2026-10-22: 65.4% core, 46.1% P0. First milestone: P0 below 30%.

## 3. Record

- 2026-10-22: Fast Lane adopted; batch 1 (PR #191, 12 P0 values) approved, merged @ `6a725da` and imported.
- 2026-10-22: standing authorization `HO-DATA-STANDING 2026-10-22` granted for 90 days.
