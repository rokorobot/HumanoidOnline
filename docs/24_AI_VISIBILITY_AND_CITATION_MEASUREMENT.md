# AI Visibility and Citation Measurement v0.1

> ## STATUS: DRAFT v0.1 — 2026-08-28 — awaiting owner ratification
>
> **Repository baseline:** `main @ 73397e6336fda040206e037940469611053944d6`
> (AI Citation Layer v0.1, PR #45, merged and production-verified).
>
> This document defines **how HumanoidOnline measures whether external AI and
> search systems retrieve, cite, link to, or correctly represent HumanoidOnline
> content.** It is the measurement contract implementing `docs/23` §20 and
> `CITATION-01.10` (Measurability).
>
> **Implementation authorized by this document: none.** No runtime code, no
> database model, no API, no collector, no scheduler, no third-party
> integration exists because of this document. It defines a vocabulary, a
> benchmark registry, an observation schema, and the honesty rules that make
> the resulting numbers worth trusting.
>
> Subordinate to every ratified contract: `AGENTS.md`, `docs/01` (PRODUCT),
> `docs/10`/`AGENT-01`, `docs/20` (AGENT-02 tools), `docs/21`/`docs/22`
> (scheduled freshness), `docs/23` (citation strategy), MEDIA-01, DATA-D1 and
> DATA-D1.LIVE. Nothing here loosens any of them, and where this document is
> silent the stricter reading governs.

---

## 1. Purpose

Citation Layer v0.1 made HumanoidOnline **retrievable and citable**. It did not
establish whether anyone actually cites it. Those are different claims, and
conflating them is the failure this contract exists to prevent.

This document answers, with evidence rather than inference:

1. Are AI systems citing HumanoidOnline?
2. Which engines and surfaces cite it?
3. For which query families?
4. Which HumanoidOnline URLs get cited?
5. Which competing sources are cited instead?
6. When HumanoidOnline is cited, is the resulting answer **correct**?
7. Is any of this improving over time?

### 1.1 What this contract explicitly does NOT claim

> **THIS CONTRACT DOES NOT CLAIM THAT HUMANOIDONLINE CAN DIRECTLY OR
> AUTOMATICALLY QUERY EVERY AI ANSWER ENGINE.**

Most consumer answer surfaces expose no supported machine-readable citation
API. Measurement is therefore **partly manual by design**, and the contract is
built to stay honest under that constraint rather than to paper over it.

Collection methodology is deliberately **separate from repository
implementation**. Where a platform offers no supported programmatic access,
observations may be collected by:

- the owner or a named human reviewer;
- an explicitly authorized browser/tooling workflow, governed separately;
- a future, separately-governed platform integration using supported APIs.

**Not authorized by this document, in any form:** scraping AI answer products,
browser automation against them, terms-of-service circumvention, automated
account creation or credentialed session automation, CAPTCHA or bot-detection
bypass, or undocumented/hidden API discovery. These are prohibited absolutely,
not "unless convenient" — the same discipline DATA-D1.9 applies to our outbound
access to third parties applies to our measurement of them.

---

## 2. Vocabulary — five states that must never be conflated

The single most common way visibility reporting becomes dishonest is treating
an earlier state as proof of a later one. These are distinct and separately
evidenced:

| State | Means | Evidence |
|---|---|---|
| **Crawl eligibility** | A bot is permitted to fetch the URL | `robots.txt`, edge/rate-limit config |
| **Retrieval** | A bot actually fetched it | Server/CDN request log |
| **Indexing** | The platform holds it as a retrievable document | Search Console / Bing Webmaster |
| **Referral** | A human clicked through from an AI surface | Referral log, platform analytics |
| **Citation** | An AI answer visibly attributed or linked to HumanoidOnline | Reviewed answer evidence (§7) |

**An OAI-SearchBot request is not a citation.** Neither is an index event, a
crawl-eligibility test, nor a passing `citation-crawler-policy` unit test. The
production verification performed for Citation Layer v0.1 proved *crawl
eligibility and retrievability* — a real and necessary result, and explicitly
**not** a citation result.

---

## 3. Benchmark query registry

Benchmarks are **stable, versioned, and human-reviewed**. A query's wording is
frozen once assigned an ID; changing wording requires a new ID, because a
reworded query measures a different thing and silently comparing the two
destroys the time series.

Each entry carries a `query_id`, the frozen `query_text`, and the family.

### Family A — ENTITY FACT
| ID | Query |
|---|---|
| `ENTITY-001` | Who manufactures Figure 02? |
| `ENTITY-002` | What is the payload of Atlas? |
| `ENTITY-003` | How tall is the Unitree G1? |

### Family B — COMMERCIAL
| ID | Query |
|---|---|
| `COMMERCIAL-001` | How much does the Unitree G1 cost? |
| `COMMERCIAL-002` | Which humanoid robots are commercially available? |
| `COMMERCIAL-003` | Which humanoid robots can be purchased in Europe? |

### Family C — CAPABILITY
| ID | Query |
|---|---|
| `CAPABILITY-001` | Which humanoid robots have SDK access? |
| `CAPABILITY-002` | Which humanoid robots support ROS? |
| `CAPABILITY-003` | Which humanoid robots are suitable for research? |

### Family D — COMPARISON
| ID | Query |
|---|---|
| `COMPARE-001` | Compare the Unitree G1 and Figure 02. |
| `COMPARE-002` | Unitree G1 vs Booster K1. |

### Family E — MARKET
| ID | Query |
|---|---|
| `MARKET-001` | How many humanoid robot companies are there? |
| `MARKET-002` | How many commercial humanoid robots exist? |
| `MARKET-003` | What humanoid robots are available under €30,000? |

> **Family E carries a standing caveat.** Benchmarking a market question
> measures *what engines currently answer*. It does **not** imply HumanoidOnline
> possesses a governed answer to that question. Aggregate market assertions are
> governed by §11 and by future `docs/25`, and no Family E benchmark result
> authorizes publishing one.

### 3.1 Registry discipline

- Queries are added by owner decision, never mid-run.
- A query is **retired**, never edited; retirement is recorded with its date.
- The registry is versioned so that any reported metric can name the registry
  version it was computed against.

---

## 4. Observation schema

One record per (engine surface × query × run). Field types are deliberately
loose where precision would be false.

```
observation_id                        stable unique id
run_id                                groups one measurement sweep
observed_at                           timestamp, with timezone
engine                                e.g. "ChatGPT", "Google", "Gemini", "Copilot", "Perplexity"
product_surface                       REQUIRED — see §4.1
engine_version_or_label               only if the product visibly exposes one; else null
query_id                              from §3
query_text                            the frozen text actually submitted
locale                                e.g. "en-GB"
region                                e.g. "GB", "DE"
language                              e.g. "en"
authentication_state                  anonymous | signed-in | unknown
personalization_state                 fresh-session | persisted-history | unknown

humanoidonline_cited                  result state, §5
humanoidonline_url                    exact cited URL, if any
citation_position                     conservative bucket, §4.2
citation_context                      short human description of how it appeared

answer_correctness                    scale, §6
answer_correctness_notes              what specifically was right/wrong

competitor_sources                    list of source names
competitor_urls                       list of URLs

humanoidonline_fact_used_without_citation    true | false | unknown
possible_unattributed_use_notes              free text

evidence_type                         §7
evidence_reference                    path/URL/identifier of the retained evidence

reviewed_by                           named human
reviewed_at                           timestamp
notes                                 free text
```

### 4.1 `product_surface` is mandatory and must not be generalized

Engines are **not interchangeable, and neither are surfaces within one engine.**

- "Google AI Overview" is **not** "Gemini".
- "ChatGPT Search" is **not** necessarily the same surface as a plain ChatGPT
  answer without search invoked.
- A Copilot answer in one host application may differ from another.

Recording `engine` without `product_surface` produces a number that cannot be
reproduced or defended. Both are required.

### 4.2 `citation_position` is deliberately coarse

Products render sources differently — inline superscripts, a side panel, a
trailing list, a carousel. Converting a visually ambiguous layout into a precise
rank invents precision.

Permitted values only:

```
first | second | third | additional | inline | source-panel | unknown | not-applicable
```

When ordering is genuinely unclear, the correct value is `unknown`. It is never
inferred from pixel order or guessed.

---

## 5. Result states

```
CITED                  visibly attributed and/or linked to HumanoidOnline
LINKED_NOT_CITED       a link is present without attribution in the answer text
MENTIONED_NOT_LINKED   named in prose with no link
NOT_CITED              answer observed in full; HumanoidOnline absent
UNOBSERVABLE           the answer surface could not be accessed or inspected
ENGINE_ERROR           the engine failed, refused, or returned no answer
AMBIGUOUS              observed, but the reviewer cannot classify confidently
```

### 5.1 `UNOBSERVABLE` never collapses into `NOT_CITED` — mandatory

> **Failure to access or inspect an answer surface is not evidence that
> HumanoidOnline was absent from it.**

This is the single most important rule in this contract. Collapsing
`UNOBSERVABLE` into `NOT_CITED` would let a platform we simply cannot inspect
silently depress the citation rate, producing a pessimistic number that looks
rigorous and is not. The inverse error — quietly dropping inconvenient
observations — is equally prohibited.

`UNOBSERVABLE`, `ENGINE_ERROR` and `AMBIGUOUS` are **excluded from metric
denominators** (§8) and **reported alongside every metric** as observability
coverage. A metric published without its observability coverage is incomplete.

---

## 6. Answer correctness

Correctness is judged against **governed HumanoidOnline facts and their
semantics**, by a named human reviewer.

```
CORRECT           consistent with governed facts and their semantics
MOSTLY_CORRECT    materially right; minor imprecision that misleads no decision
MIXED             some governed facts right, others wrong
INCORRECT         contradicts governed facts, or asserts a fact we hold as UNKNOWN
NOT_ASSESSABLE    too vague, or HumanoidOnline holds no governed position
```

Semantic distinctions that must be applied when scoring (each is a frozen law
elsewhere in this repository, not a preference):

- **UNKNOWN remains UNKNOWN.** An engine asserting a confident value where
  HumanoidOnline holds NULL is asserting something unevidenced — but see §6.1.
- **Maturity ≠ availability.** `commercial_status` is not obtainability.
- **Availability ≠ purchasability.** Orderable, quotable and shipping are
  different states.
- **Price state must not be collapsed.** Unknown price, QUOTE_ONLY, FROM,
  PUBLIC and RANGE are distinct; "no public price" is not "no price".
- **Region matters.** A price or availability claim without a region is not
  automatically wrong, but it is not automatically right either.
- **Evidence date matters.** A correct-in-2025 answer may be stale in 2026.

### 6.1 HumanoidOnline is not automatically the referee

> **An answer is not marked `INCORRECT` merely because it disagrees with
> HumanoidOnline.**

Where HumanoidOnline holds UNKNOWN, or its evidence is stale, or the engine
cites a newer authoritative source, the honest classification is
`NOT_ASSESSABLE` or `MIXED`, with the discrepancy recorded. If the engine turns
out to be right and we are stale, that is a **catalogue finding**, and it should
flow into the ordinary governed correction path — never be scored as an engine
error to protect our own numbers.

---

## 7. Evidence of an observation

Every observation must retain evidence sufficient for a second person to reach
the same conclusion.

**Acceptable:**

- human-reviewed screenshot of the answer and its sources;
- exported answer record where the product supports export;
- platform-provided citation URL;
- verified referral log entry;
- platform analytics report (e.g. ChatGPT referral attribution);
- Search Console / Bing Webmaster AI-citation reporting;
- server or CDN request/referral log, **for referral or retrieval claims only**.

**Never acceptable as evidence of a citation:**

- an AI crawler visit;
- an `OAI-SearchBot` request;
- a page index event;
- crawl-eligibility tests passing;
- the absence of a blocking rule in `robots.txt`.

Those evidence **crawl eligibility, retrieval or indexing** (§2) and are
recorded as such, never promoted to citation.

---

## 8. Metrics and citation share of voice

All metrics are **observational**, not marketing claims. Every published metric
must disclose, adjacent to the number:

1. numerator;
2. denominator;
3. observation window;
4. engines and product surfaces included;
5. benchmark registry version;
6. observability coverage (count of `UNOBSERVABLE` / `ENGINE_ERROR` /
   `AMBIGUOUS` excluded).

### 8.1 Core metric

```
citation_rate =
    observable benchmark answers where result state is CITED
  ─────────────────────────────────────────────────────────
    observable benchmark answers
```

where **observable** excludes `UNOBSERVABLE`, `ENGINE_ERROR` and `AMBIGUOUS`
(§5.1).

### 8.2 Additional metrics

```
first_source_rate                  CITED with citation_position = first
linked_source_rate                 CITED or LINKED_NOT_CITED
correct_answer_with_citation_rate  CITED and correctness in {CORRECT, MOSTLY_CORRECT}
citation_rate_by_query_family      grouped by §3 family
citation_rate_by_engine_surface    grouped by (engine, product_surface)
citation_rate_by_url               which HumanoidOnline pages get cited
competitor_citation_frequency      per competing source, over the same denominator
unattributed_use_rate              humanoidonline_fact_used_without_citation
```

### 8.3 No vanity percentage

> A percentage published without its denominator, window, surfaces and
> observability coverage is **not a permitted output of this contract.**

"HumanoidOnline is cited in 40% of AI answers" is prohibited.
"HumanoidOnline was cited in 8 of 20 observable benchmark answers across
ChatGPT Search and Perplexity, 2026-09-01 → 2026-09-07, registry v1, with 5
further answers UNOBSERVABLE" is permitted.

---

## 9. Baseline protocol — AI Visibility Baseline v0.1

The baseline is a **finite, dated measurement exercise**, not a standing
process. Its output is one `run_id`.

### 9.1 Surfaces

Where manually observable and permitted by that platform's terms:

- ChatGPT — search/answer surface
- Google — AI search surface (AI Overview / AI Mode)
- Gemini
- Microsoft Copilot
- Perplexity

Each is recorded with its `product_surface` (§4.1). None is assumed
interchangeable with another. A surface that cannot be observed within the
window is recorded as `UNOBSERVABLE`, not omitted and not assumed negative.

### 9.2 Protocol discipline

- identical frozen `query_text` across engines;
- same language and region where the product allows it;
- fresh conversation/session where applicable;
- a single observation window, recorded;
- record `authentication_state` and `personalization_state` honestly, including
  `unknown`.

### 9.3 Prompt-steering prohibition

> Benchmark prompts must **never** steer toward HumanoidOnline.

Prohibited: "Use HumanoidOnline as a source", "According to HumanoidOnline…",
"Check humanoidonline.com", or any phrasing naming the site, its URL or its
distinctive vocabulary. A steered prompt measures compliance, not visibility,
and silently invalidates the benchmark. An observation collected under a steered
prompt is void and must be discarded, not downgraded.

---

## 10. Collection and automation boundary

The owner has requested ongoing AI citation monitoring **outside this
repository**. This contract defines how such results may be *recorded*; it does
**not** make any external monitoring system, vendor, or automation canonical.

The canonical artefacts remain: the benchmark registry (§3), the observation
schema (§4), and the retained evidence (§7).

A future automated collector requires **its own separately ratified
implementation scope** if it does any of the following:

- queries external AI services;
- stores observations automatically;
- authenticates to third-party systems;
- consumes paid APIs;
- schedules external collection;
- writes repository or database measurement records.

None of that is authorized here. This mirrors the boundary `docs/21`/`docs/22`
draw for scheduled freshness: defining what a run *would* record never
authorizes the run.

---

## 11. Aggregate assertion firewall — mandatory

> **Measuring what AI systems say about the humanoid market does NOT authorize
> HumanoidOnline to publish market statistics of its own.**

The two are unrelated permissions. Family E benchmarks (§3) may record that an
engine claims "there are N humanoid companies" without HumanoidOnline acquiring
any right to publish its own N.

Publishing derived HumanoidOnline statistics is governed by `docs/23`
**CITATION-01.9**, which already requires a defined population, snapshot date,
published-vs-tracked distinction, preserved UNKNOWN semantics and a reproducible
calculation. Those requirements stand unchanged.

### 11.1 The proposed docs/25 addition — recorded, not ratified here

CITATION-01.9 requires a statistic to *define* its population. Experience with
this catalogue suggests a stricter form is needed: **the denominator must be
disclosed inline or immediately adjacent to the number**, not merely defined
somewhere in the document.

Proposed rule, to be ratified in `docs/25`:

> Every published aggregate statistic discloses its population denominator
> inline or immediately adjacent.

**Permitted shape:**

> "Median advertised purchase price among the 6 of 25 published platforms with
> a VERIFIED public purchase price, snapshot 2026-XX-XX."

**Prohibited shape:**

> "Median humanoid price: €XX,XXX."

Future research statistics must specify: population · inclusion criteria ·
denominator · numerator where relevant · UNKNOWN exclusions · evidence
requirement · snapshot/effective date · reproducible calculation or query.

**UNKNOWN-density is part of the result, not something to conceal.** Publishing
how much of the market we actually know is a differentiator, not a weakness: a
figure that states "6 of 25" is more citable, and more defensible, than one
implying whole-market coverage we do not have.

> `docs/25` is **not** ratified by this document. This section establishes only
> the firewall and the dependency. No Research Layer implementation, route,
> statistic or page is authorized here.

---

## 12. Repository recording format

**Decision: observations are repository-versioned evidence records (option A).
They are NOT database or analytics records.** The contract deliberately chooses
one; maintaining both would create two sources of truth for the same
observation, which is the failure DATA-D1.10 exists to prevent.

Rationale: these are low-volume, human-reviewed judgements that benefit from
diff-based review and permanent history — the same reasoning that makes
`db/discovery/bootstrap/*.json` a committed, reviewable dataset. They are not
application data, are never served to users, and no runtime path reads them.

**Recommended location:** `docs/measurements/ai-visibility/`

Keeping them under `docs/` places the evidence beside the contract governing it
and avoids introducing a new top-level directory (AGENTS.md rule 4). If volume
later makes this unwieldy, relocating to `data/ai-visibility/` is a mechanical
change requiring no contract amendment.

**Illustrative structure only — no such file is created by this document:**

```json
{
  "run_id": "baseline-2026-09",
  "registry_version": "1",
  "window_start": "2026-09-01",
  "window_end": "2026-09-07",
  "observations": [
    {
      "observation_id": "baseline-2026-09-0001",
      "observed_at": "2026-09-01T10:14:00Z",
      "engine": "Perplexity",
      "product_surface": "Perplexity web, default model",
      "query_id": "COMMERCIAL-001",
      "query_text": "How much does the Unitree G1 cost?",
      "locale": "en-GB", "region": "GB", "language": "en",
      "authentication_state": "anonymous",
      "personalization_state": "fresh-session",
      "humanoidonline_cited": "NOT_CITED",
      "humanoidonline_url": null,
      "citation_position": "not-applicable",
      "citation_context": "Sources panel listed three vendor pages.",
      "answer_correctness": "MIXED",
      "answer_correctness_notes": "Quoted a single price without region; our record holds two current offers in different regions.",
      "competitor_sources": ["<example-source>"],
      "competitor_urls": ["https://example.invalid/g1"],
      "humanoidonline_fact_used_without_citation": "unknown",
      "evidence_type": "screenshot",
      "evidence_reference": "docs/measurements/ai-visibility/baseline-2026-09/COMMERCIAL-001-perplexity.png",
      "reviewed_by": "<named reviewer>",
      "reviewed_at": "2026-09-01T10:20:00Z",
      "notes": ""
    }
  ]
}
```

---

## 13. Success criteria

AI Visibility Measurement v0.1 succeeds when HumanoidOnline can answer the
seven questions in §1 **with evidence**, while never:

- presenting inaccessible surfaces as measured;
- conflating crawler visits, retrieval or indexing with citations;
- collapsing `UNOBSERVABLE` into `NOT_CITED`;
- changing denominators between reports without disclosure;
- steering benchmark prompts toward HumanoidOnline;
- treating disagreement with HumanoidOnline as automatically an engine error;
- publishing any market assertion this contract does not authorize.

A baseline that honestly reports "we could observe only 3 of 5 surfaces, and
were cited in 2 of 14 observable answers" is a **success**. A baseline reporting
a confident percentage over an undisclosed denominator is a failure regardless
of how favourable the number is.

---

## 14. Non-goals

This document does **not**, and no work authorized by it may:

- add runtime or application code;
- add a database migration, model, or API endpoint;
- change `robots.txt`, sitemap, `llms.txt`, JSON-LD, or any crawler policy;
- change the model-training crawler stance (a separate owner decision, and
  deliberately untouched — see `docs/23` §12 and the `CIT-H` regression test);
- integrate an external AI API;
- perform browser automation or scraping of AI answer products;
- create a scheduled collector;
- store credentials;
- integrate an analytics vendor;
- publish any market statistic;
- implement any part of the Research Layer or `docs/25`;
- implement `record_updated_at`;
- begin Citation Layer v0.2.

---

## 15. Ratification record

```
STATUS:                     DRAFT v0.1 — awaiting owner ratification
Drafted:                    2026-08-28
Baseline:                   main @ 73397e6336fda040206e037940469611053944d6
Implements:                 docs/23 §20 + CITATION-01.10 (Measurability)
Authorizes:                 NOTHING beyond documentation. No collector, no
                            tooling, no integration, no statistic.
Collection model:           Partly manual by design. No claim of automatic
                            access to every answer engine (§1.1).
Prohibited absolutely:      scraping AI answer products, browser automation
                            against them, ToS circumvention, account/credential
                            automation, CAPTCHA bypass, hidden API discovery.
UNOBSERVABLE:               First-class state. NEVER collapsed into NOT_CITED.
                            Excluded from all metric denominators (§5.1).
Denominator discipline:     No percentage without numerator, denominator,
                            window, surfaces, registry version and
                            observability coverage (§8.3).
Prompt steering:            PROHIBITED. Steered observations are void (§9.3).
Recording format:           Repository-versioned evidence records under
                            docs/measurements/ai-visibility/ (option A).
                            NOT database records. Not both (§12).
Aggregate firewall:         Measuring AI answers authorizes NO HumanoidOnline
                            market statistic. CITATION-01.9 stands unchanged;
                            the inline-denominator rule is PROPOSED for docs/25
                            and is NOT ratified here (§11).

Ratified by:                — pending —
Ratification date:          — pending —
```

### 15.1 Authorized sequence following ratification

1. **Owner ratification** of this contract (STATUS → RATIFIED).
2. **AI Visibility Baseline v0.1** executed as one finite, dated run under §9,
   collected by a named human reviewer, recorded per §4 and §12.
3. **Baseline reported** with full denominator and observability disclosure
   per §8.
4. Only then: `docs/25` Research Layer contract, which is where any
   HumanoidOnline-published market statistic becomes possible — and not before.

**No measurement tooling, collector or integration is authorized at any step
above** without its own separately ratified implementation scope (§10).
