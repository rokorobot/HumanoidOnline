# AI Visibility Measurement — Amendment M1: Baseline Pilot (HO-AEO-00)

> ## STATUS: DRAFT — PROPOSED, NOT RATIFIED (2026-10-24)
>
> This document amends `24_AI_VISIBILITY_AND_CITATION_MEASUREMENT.md`
> (RATIFIED v0.1, 2026-08-28). It **operationalizes** the ratified baseline
> protocol (`docs/24` §9, §15.1 step 2). It does not redesign it: the
> vocabulary (§2), result states (§5), correctness scale (§6), evidence rules
> (§7), metrics and denominators (§8), prompt-steering prohibition (§9.3),
> collection boundary (§10), aggregate firewall (§11) and recording format
> (§12) of `docs/24` apply unchanged. Where this amendment is silent, `docs/24`
> governs; where the two could be read differently, the stricter reading wins.
>
> **Implementation authorized by this document: none.** No tool is installed
> or connected, no paid API is called, no runtime code, schema, catalogue data
> or production surface changes. Ratification would authorize exactly one thing:
> one baseline pilot under §4–§8 below: manual collection by a named human
> reviewer, plus a treg-assisted sweep once its spend is separately approved
> (D2). Depends on PR #209 (removal of the `docs/24` §1.1 collection
> prohibition).
>
> Workstream: HO-AEO-00 (AI SEO / GEO programme, architecture and pilot
> specification). Repository baseline: `main @ fb0a412`.

---

## 1. Why an amendment and not a new framework

The pasted HO-AEO roadmap (2026-10-24) proposed an architecture audit, a tool
integration and a visibility baseline. Most of that already exists:

| Roadmap item | Already governed by |
|---|---|
| Canonical URLs, crawler access, JSON-LD, `llms.txt`, sitemap | `docs/23` CITATION-01, Citation Layer v0.1 (PR #45, production-verified 2026-08-28) |
| Measurement vocabulary, result states, metrics | `docs/24` §2–§8 (ratified) |
| Benchmark registry | `docs/24` §3 (registry v1, 14 queries) |
| Recording format | `docs/24` §12 (`docs/measurements/ai-visibility/`) |
| Citable original content | `docs/27` regional research (Europe, North America, Asia published) |

What does **not** exist is a completed baseline. `docs/24` §15.1 step 2 was
never finished. This amendment closes only that gap. It creates no parallel
SEO/GEO architecture, content store, measurement database or vocabulary.

---

## 2. State of measurement at the time of writing

Found in the owner's local checkout, **not committed to any branch**:

| Run | Surface | Status | Result |
|---|---|---|---|
| `2026-08-28_chatgpt_personalized_pilot` | ChatGPT, personalized session | Pilot; excluded from baseline by its own note | — |
| `2026-09-06_chatgpt_baseline` | ChatGPT, Temporary Chat | IN PROGRESS, 2 of 14 queries | `NOT_CITED` in 2 of 2 observable answers (COMMERCIAL-003, CAPABILITY-001) |

Two facts about these records matter for this pilot:

1. **The 2026-09-06 run appended a suffix** to the frozen text: *"Please cite
   the sources supporting your answer."* The suffix does not name
   HumanoidOnline, so it is not steering under `docs/24` §9.3, but it changes
   the submitted text, which `docs/24` §9.2 requires to be identical to the
   frozen `query_text`. Its observations are therefore not directly comparable
   with an unsuffixed run (decision D3).
2. **The COMMERCIAL-003 observation (2026-09-06) predates publication of the
   Europe research resource (2026-10-05).** It is the only pre-publication
   observation for any regional page. `docs/27` §14 asked for a pre-publication
   baseline per region; North America (published 2026-10-23) and Asia
   (2026-10-24) have none. This pilot is therefore a **post-publication**
   baseline for all three regions, and must say so in its report (§7).

Screenshots referenced by the 2026-09-06 run are not in the repository (its own
note says they remain in the originating ChatGPT conversation).

---

## 3. Collection method — evaluated

### 3.1 Options

| Method | Description | Compatible with `docs/24`? |
|---|---|---|
| **Manual** | Named human reviewer submits frozen queries in each product's normal UI, captures screenshots, records observations per `docs/24` §4 | **Yes.** This is the method `docs/24` §1.1 and §15.1 anticipate. |
| **treg-assisted** | treg's AEO workflow queries engines via the treg gateway | **Yes**, once the §1.1 prohibition is removed (PR #209); recorded as its own `product_surface` (§4) |
| **Hybrid** | Manual collection plus a treg-assisted sweep of the same 10 queries | **Yes** |

**Recommendation: hybrid.** Manual collection is the reference measurement of
what a user sees. A treg-assisted sweep of the same queries runs alongside it,
within the §9 budget, and the two are compared. If they agree, later repeats
can rely mostly on treg.

### 3.2 treg — evaluation (desk review only; nothing installed)

Sources reviewed 2026-10-24: `github.com/superdesigndev/treg` (README and
license summary), `treg.to`, `treg.to/aeo`, and public descriptions of cloro
(`cloro.dev`). These are vendor-published statements and were not tested.

| Question | Finding |
|---|---|
| What it is | A pay-per-call gateway ("OpenRouter for agent tools") brokering third-party APIs through one token, CLI and Claude Code plugin |
| Licensing | Repository: Apache 2.0 *with additional terms* (no redistribution as a competing hosted registry). Use by HumanoidOnline would be through the hosted service, governed by `treg.to/terms` and `treg.to/privacy`, **which were not reviewed** (contents not retrievable during this desk review) |
| How it collects AI answers | AEO step 2 calls `cloro.ai-search.chatgpt.scrape`, `cloro.ai-search.gemini.scrape` and `cloro.google.serp.ai_mode`; Perplexity via a treg endpoint that the site marks as having "no official API". cloro describes itself as a managed scraping API for AI products' web interfaces, handling authentication and Cloudflare bypass |
| Other data sources | SE Ranking and DataForSEO (keywords, intent, SERP), Moz (link metrics), Scrape Creators (Reddit), YouTube search |
| Storage | Local CSV/HTML report files; hosted audit log of every call (`treg calls`); responses up to 8 MiB buffered for billing; anonymous CLI telemetry to PostHog (opt-out `TREG_TELEMETRY=0`). **No retention period stated** |
| API requirements | Account (GitHub, Google or e-mail code), prepaid balance, one treg token; optional own provider keys |
| Credentials risk | `treg upload` scans a `.env` file and registers matched provider keys server-side; a `cli_auth` injector lifts material from CLI keychains. Must never be used against this repository or any machine holding HumanoidOnline secrets |
| Outreach | Drafts only; the AEO workflow states it sends nothing |
| Cost (vendor estimate) | ≈ $0.015 per question per sweep for AI answers; ≈ $0.31 for the full four-step example |

**Conclusion.** The `docs/24` §1.1 collection prohibition is removed by owner
direction (PR #209), so treg-assisted answer collection is permitted. Remaining
conditions for its use in this pilot:

- treg's answers come from provider-run sessions (cloro), not from the
  reviewer's own view, so they are recorded under their own `product_surface`
  (§4) and compared with, not merged into, the manual observations;
- the ChatGPT and Google consumer terms restrict automated extraction; that
  risk sits primarily with the provider and is noted, not treated as a blocker;
- `treg upload`, `treg upload env`/`skills` and the `cli_auth` injector are
  **never** run on any machine holding HumanoidOnline secrets; the CLI runs
  with `TREG_TELEMETRY=0`, and only a dedicated treg token with a prepaid
  balance no larger than the §9 ceiling is used;
- treg's terms and privacy pages are read by the owner before account creation.

Answers obtained through an engine's official developer API (a model API
without the consumer product's search UI) would be yet another
`product_surface` and are out of scope for this pilot.

### 3.3 Non-answer SEO data (keywords, backlinks)

Keyword demand and backlink data are **not** citation measurement and are
outside `docs/24`. If wanted later, they need their own scope: named provider,
named endpoints, data stored, cost ceiling and an owner authorization. They are
not part of this pilot and are not required for the baseline.

---

## 4. Pilot surfaces

Four surfaces, recorded with an explicit `product_surface` (`docs/24` §4.1):

| `engine` | `product_surface` (fixed label) |
|---|---|
| ChatGPT | `ChatGPT web — search answer` |
| Gemini | `Gemini web app` |
| Perplexity | `Perplexity web — default mode` |
| Google | `Google Search — AI Mode` |

treg-assisted observations of the same engines use the label
`<engine> via treg/<provider endpoint>` (for example
`ChatGPT via treg/cloro.ai-search.chatgpt.scrape`) and are reported as separate
surfaces.

If a surface answers without visible search or sources, the observation is
still recorded: `NOT_CITED` if the answer is fully observable, with
`citation_context` noting "no sources displayed".

**Out of pilot scope (disclosed, not measured):** Microsoft Copilot and Google
AI Overviews, both listed in `docs/24` §9.1. They are recorded in the report as
*not in pilot scope*, not as `UNOBSERVABLE` and not as `NOT_CITED`, and the
report does not describe the pilot as covering all `docs/24` surfaces.

---

## 5. Pilot benchmark set — 10 queries

`docs/24` §3.1: wording is frozen, queries are added by owner decision, never
edited. The pilot uses **eight registry v1 queries unchanged** and proposes
**two new IDs** for the regional resources. Ratifying this amendment creates
**registry v2** = v1 + `COMMERCIAL-004` + `COMMERCIAL-005`; nothing is retired.

| # | `query_id` | Frozen `query_text` | Registry | Primary HumanoidOnline citation target |
|---|---|---|---|---|
| 1 | `COMMERCIAL-003` | Which humanoid robots can be purchased in Europe? | v1 | `/research/humanoid-availability/europe` |
| 2 | `COMMERCIAL-004` | Which humanoid robots can be purchased in North America? | **v2 (proposed)** | `/research/humanoid-availability/north-america` |
| 3 | `COMMERCIAL-005` | Which humanoid robots can be purchased in Asia? | **v2 (proposed)** | `/research/humanoid-availability/asia` |
| 4 | `COMMERCIAL-002` | Which humanoid robots are commercially available? | v1 | `/research`, `/robots` |
| 5 | `COMMERCIAL-001` | How much does the Unitree G1 cost? | v1 | `/robots/unitree-g1` |
| 6 | `CAPABILITY-001` | Which humanoid robots have SDK access? | v1 | `/robots`, robot profiles |
| 7 | `CAPABILITY-003` | Which humanoid robots are suitable for research? | v1 | `/use-cases/<research use case>` |
| 8 | `COMPARE-002` | Unitree G1 vs Booster K1. | v1 | `/compare`, both robot profiles |
| 9 | `ENTITY-003` | How tall is the Unitree G1? | v1 | `/robots/unitree-g1` |
| 10 | `MARKET-002` | How many commercial humanoid robots exist? | v1 | none — see note |

Selection rationale: the three regional queries come first because the
regional resources are HumanoidOnline's most distinctive evidence-backed
answers (`docs/27`). Queries 4–7 cover the commercial and capability questions
those resources and the catalogue answer. Queries 8–9 are controls where
manufacturer and retailer pages are expected to dominate. Query 10 is a market
control.

- **Primary citation target** is an analysis label for `citation_rate_by_url`
  (`docs/24` §8.2). It is not a prediction, and a citation of any other
  HumanoidOnline URL still counts as `CITED`.
- **Query 10 carries the `docs/24` §3 Family E caveat and the §11 firewall.**
  It records what engines answer; HumanoidOnline publishes no count of its own
  because of it.
- **Query wording never names HumanoidOnline** (`docs/24` §9.3). The two
  proposed queries reuse the COMMERCIAL-003 form verbatim apart from the region
  name, so the three regions are comparable.
- Not chosen from v1: `ENTITY-001/002`, `CAPABILITY-002`, `COMPARE-001`,
  `MARKET-001/003`. They stay in the registry for a later full run.

---

## 6. Run protocol

Applies `docs/24` §9.2 with these fixed choices:

| Item | Rule |
|---|---|
| Collector | Manual: one named human reviewer (default: the product owner). treg sweep: run by the owner or an agent on owner instruction; every observation still human-reviewed (`reviewed_by`) |
| Text submitted | Frozen `query_text` exactly, no suffix (unless D3 decides otherwise) |
| Session | New chat or search per query; temporary/incognito mode where the product offers it |
| Locale | `en` language; region recorded as observed (expected `CZ`); no VPN |
| Authentication | Recorded honestly per observation (`anonymous` / `signed-in` / `unknown`) |
| Window | Run R1 within one 48-hour window; all 40 observations |
| Evidence | Full-answer screenshots including the sources area, per `docs/24` §7 |
| Correctness | Scored per `docs/24` §6 against governed facts current at `observed_at` |

**Size:** 10 queries × 4 surfaces = **40 observations per run**.

### 6.1 Repeatability

Answer engines are non-deterministic, so one sweep is not a baseline.

- **R2:** repeat the identical 40 observations 5–9 days after R1, same
  protocol, same reviewer where possible.
- **Stability per surface:**
  `pairs (query, surface) with the same result state in R1 and R2`
  ÷ `pairs observable in both R1 and R2`. Pairs with `UNOBSERVABLE`,
  `ENGINE_ERROR` or `AMBIGUOUS` in either run are excluded from the denominator
  and reported as coverage.
- **Baseline value:** each metric is reported for R1 and R2 separately, never
  averaged into a single percentage. A finding counts as stable only where R1
  and R2 agree.
- An optional R3 is a later owner decision, not part of this pilot.

---

## 7. Baseline report format

One report per pilot (R1 + R2), committed beside its data. Required sections,
in order:

1. **Disclosure block** (`docs/24` §8): window(s), surfaces included and
   excluded, registry version (v2), reviewer, observation counts by result
   state, observability coverage.
2. **Headline table** — every metric as *N of D*, not as a bare percentage:
   `citation_rate`, `linked_source_rate`, `first_source_rate`,
   `correct_answer_with_citation_rate`. `citation_correctness_rate` only
   alongside its `CITED` count (`docs/24` §8.2.1).
3. **By surface** and **by query**, each with its own denominator.
4. **Regional resources** — results for queries 1–3, the URL cited (if any),
   and the competing sources cited instead. States that this is a
   post-publication baseline (§2).
5. **By URL** — `citation_rate_by_url`, labelled with its denominator.
6. **Competitor sources** — `competitor_citation_frequency` for the most
   frequent sources, each as *N of D*.
7. **Repeatability** — stability per surface (§6.1).
8. **Catalogue findings** — answers where the engine appears right and
   HumanoidOnline appears stale (`docs/24` §6.1). Listed for the ordinary
   governed correction path; nothing is changed by the report.
9. **Deviations** — anything that departed from §6.

**Inline denominator rule.** The rule `docs/24` §11.1 proposes for `docs/25`
(every aggregate shows its denominator inline) is **applied voluntarily to
this report**. Doing so ratifies nothing in `docs/25`; it is simply the
stricter reading.

The report makes **no** external claim. It is an internal measurement record.

---

## 8. Data and provenance

| Artefact | Location |
|---|---|
| Run data | `docs/measurements/ai-visibility/<run_id>/observations.json` — schema exactly `docs/24` §4/§12 |
| Evidence | `docs/measurements/ai-visibility/<run_id>/evidence/<query_id>__<surface>.png` |
| Report | `docs/measurements/ai-visibility/<run_id>/REPORT.md` |

`run_id` values: `aeo-pilot-2026-11-r1`, `aeo-pilot-2026-11-r2` (month as
actually run).

Additional provenance, compatible with the `docs/24` §4 schema:

- every evidence file's **SHA-256** is recorded in that observation's `notes`
  as `sha256:<hex>`, so a later reader can confirm the screenshot is the one
  reviewed;
- `reviewed_by` is a real name; agent-assisted transcription, if any, is
  disclosed in `notes` and does not replace human review;
- observation files are append-only after the report is committed; corrections
  are new commits with the reason stated.

Nothing is written to a database, the catalogue or any runtime path
(`docs/24` §12).

---

## 9. Budget

| Item | Ceiling |
|---|---|
| Pilot maximum external spend | **$10.00 USD** |
| Spend authorized by this amendment | **$0.00** |

The manual part needs no paid API. A treg sweep of 10 queries × 4 engines is
estimated by the vendor at ≈ $0.15–0.60 per run (≈ $0.015 per question per
engine; unverified), so R1 + R2 fit well inside $10. **Any** paid call still
needs a separate, explicit owner authorization naming the provider,
endpoints, data stored and amount (D2).

---

## 10. Non-goals

This amendment does not:

- install, connect or create an account with treg, cloro or any other vendor;
- authorize any paid API call or any stored credential;
- add runtime code, schema, migrations, crawler-policy or `robots.txt` changes;
- change catalogue facts, regional pages or editorial content;
- automate or schedule collection;
- authorize outreach, posting or publication of any metric;
- ratify `docs/25` or any aggregate-statistic rule;
- commit the pre-existing local measurement files (§2) — see D4.

---

## 11. Owner decisions required

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Ratify this amendment, including registry v2 (`COMMERCIAL-004`, `COMMERCIAL-005`) | Ratify |
| D2 | treg for answer collection (after PR #209 merges) | **Approve** a hybrid pilot: account creation by the owner, one dedicated token, ≤ $10 prepaid, R1 + R2 sweeps of the 10 queries |
| D3 | Prompt suffix ("Please cite the sources supporting your answer.") | **No suffix**; keep the 2026-09-06 run as a separate, non-comparable pilot |
| D4 | Commit the pre-existing local measurement files (2026-08-28 pilot, 2026-09-06 partial run) | Commit as historical pilot records in their own PR, marked non-baseline |
| D5 | Named reviewer and run window for R1/R2 | Owner as reviewer; R1 in the first week after ratification |
| D6 | Whether non-answer SEO data (keywords, backlinks) is wanted at all | Defer until after the baseline report |

---

## 12. Ratification record

```
STATUS:          DRAFT — PROPOSED (not ratified)
Drafted:         2026-10-24
Amends:          docs/24 (RATIFIED v0.1, 2026-08-28)
Baseline:        main @ fb0a412
Authorizes:      on ratification, ONE baseline pilot (R1 + R2) under §4–§8:
                 manual collection, plus a treg sweep only once D2 is approved.
Registry:        v2 = v1 + COMMERCIAL-004 + COMMERCIAL-005 (on ratification)
treg:            Evaluated by desk review; permitted once the docs/24 §1.1
                 prohibition is removed (PR #209); not installed, not connected.
Budget:          $10 ceiling; $0 authorized.

Ratified by:     —
Ratification date: —
```
