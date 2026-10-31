# DR-D2 — Scheduled agent enrichment run (Option B)

| | |
|---|---|
| **Status** | **DECIDED — 2026-10-31, product owner (in chat: "approved option B")** |
| **Builds on** | DR-D1 (`HO-DATA-STANDING 2026-10-22` standing research order and the HO-DATA Fast Lane) |
| **Unchanged** | `docs/26` §2.2, §6 and §7; `docs/16` LIVE.2/LIVE.3; AGENTS.md rules 1–11 |
| **Schema** | None. No new service, workflow or repository tooling. |

## 1. Decision

A recurring **Cloudroom Loop** ("HO-DATA weekly enrichment") starts an agent session every week. Its scope is
**every published robot** in `db/catalogue/robots/`. Each session:

1. researches the robots' **UNKNOWN core fields** on the manufacturers' own hosts, within DR-D1 §1 and
   `HO-DATA-STANDING 2026-10-22`. It works on the robots added or changed since the previous week, plus a rotating
   quarter of the manufacturers, so every manufacturer is rechecked every four weeks;
2. **when it finds at least one clean, raw-verified value**, opens **one Fast Lane batch PR** in the DR-D1 §2 format
   (an evidence package, an expected-change manifest and held items listed separately);
3. otherwise writes a one-line result and archives its thread. It opens no PR and comments nowhere.

## 2. Classification

The session is `AGENT_ASSISTED_RESEARCH` (`docs/26` §2.1) under the standing order. It is **not** an `AUTOMATED_LIVE`
adapter, the discovery radar or a `SCHEDULED_FRESHNESS` run (`docs/26` §2.2). It enables no `DiscoverySource`,
registers no freshness target and writes no discovery or production rows.

## 3. Limits

- **It never merges, imports, publishes or changes `is_published`.** Each batch needs the owner's explicit approval,
  recorded on the PR before merge (`docs/26` §6.5). That approval then covers the DR-D1 §2 execution sequence.
- **Unknown stays UNKNOWN.** Values come only from first-party sources, with the URL and a verbatim excerpt for each.
  Conflicts, ambiguous editions and policy-dependent values are held, never batched.
- **It respects every block.** A login, paywall, bot block or robots.txt disallow is recorded and never circumvented.
- **It doesn't repeat itself.** It skips cells already proposed in an open batch PR and cells the current register
  closes as `CLOSED-UNKNOWN`.
- **It ends with the standing order.** It is valid only while `HO-DATA-STANDING` is valid (to 2027-01-20). Renewing
  that order renews this decision. The owner can pause or delete the Loop at any time.

## 4. Expectation

The 2026-10-25 evidence pass (`HO-DATA-31`, PR #213) found the public first-party evidence for the open cells
exhausted. Most weekly runs are therefore expected to find nothing. The value of this decision is that new
manufacturer pages, datasheets and robots are picked up within a week, without anyone having to ask.
