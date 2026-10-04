# ADR-027 — Regional Research Content Contract

> Internal terminology: these are **Regional Research Resources**, not "SEO articles". SEO, GEO/AEO and agent citation are distribution and retrieval objectives of the resource, not its editorial format.

**Status:** Accepted
**Date:** 2026-10-04
**Decision Owners:** HumanoidOnline / Humanoid.Company
**Scope:** Structure, data derivation, evidence rules, SEO/GEO/AI-agent surfaces and publication gates for regional humanoid-market research resources (Europe, North America, Asia). Does not authorize implementation, publication, or any schema change.
**Related:**
- `01_PRODUCT_CONTRACT`
- `10_AGENT_CONTRACT`
- `23_AI_CITATION_AND_DISCOVERY_STRATEGY` (§16 Original HumanoidOnline intelligence, §17 Citation-quality content policy)
- `24_AI_VISIBILITY_AND_CITATION_MEASUREMENT`
- `25_CONTINUOUS_CATALOGUE_INTELLIGENCE_AND_AUTOMATED_UPDATE_PIPELINE` (§16–17 Regional resources and model, §29)
- `26_PUBLIC_AGENT_DATA_INTERFACE_AND_MCP_BOUNDARY`
- `db/schema.sql` (canonical data model)

---

## 1. Context

Doc 23 §16 names a future `/research` layer, including "availability by region", and requires every metric to disclose snapshot date, population definition, published-record rule, UNKNOWN treatment and methodology. Doc 25 §16 requires regional resources to be **generated from canonical catalogue data** and never maintained as separate editorial datasets.

No regional resource exists yet. This contract defines what one is, so that Europe, North America and Asia are three instances of one template rather than three unrelated articles.

## 2. Decision

1. A regional resource (Regional Research Resource) is a **generated, snapshot-dated research page with editorial framing**, not a blog article.
2. All robot facts, prices, availability statuses, counts and provenance are **derived at render time from the canonical catalogue**. No such fact is typed into page copy by hand.
3. Canonical commercial facts come only from governed catalogue data. **Derived statistics and answer blocks** (e.g. "5 of 8 qualifying platforms have published purchase pricing") are permitted provided they are deterministically computed from the declared snapshot and reproducible. Editorial prose may provide scope, interpretation and methodology but MUST NOT introduce independent commercial facts absent from the catalogue.
4. All three regions share one template, one section order, one query set and one citation format. Only region parameters and region-specific editorial context differ.
5. Europe is built first and is the reference implementation. North America and Asia are derived from it.

## 3. Location and routing

Per doc 23 §16, regional resources live under **Research**, not News.

```text
/research/humanoid-availability/europe
/research/humanoid-availability/north-america
/research/humanoid-availability/asia
```

These are regional instances of the `/research/humanoid-availability` surface listed in doc 23. A parent page `/research/humanoid-availability` lists regions and the global population.

**Decided (owner, 2026-10-04):** the URL family is `/research/humanoid-availability/{region}`. Doc 25 §16's `/market/{region}` paths are illustrative ("For example") and are superseded by this form for implementation. The path is frozen once published; any later change requires 301 redirects.

No separate `content/` directory of hand-written regional `.md` articles is created. Editorial copy, if stored as files, lives alongside the template as region context fragments (see §10), never as complete articles containing facts.

## 4. Region definitions

Regions map to the `region` table (`db/schema.sql`: `region_type` GLOBAL / CONTINENT / ECONOMIC_ZONE / COUNTRY / SUBREGION; `code` unique).

Each regional resource MUST state its **region membership rule** explicitly and render it on the page:

```text
Europe          = region codes in the Europe membership list (to be fixed in implementation:
                  EU member states + UK + EFTA + other listed European countries, plus the
                  EU and EUROPE rows themselves)
North America   = US, CA, MX (+ NORTH_AMERICA row)
Asia            = listed Asian countries/zones (+ ASIA / APAC rows)
```

The exact membership lists are a data decision recorded in the catalogue's region hierarchy (`parent_id`), not in page copy. If a needed region row does not exist, adding it is a separate reviewed change (AGENTS.md rule 2).

**GLOBAL is not regional.** Per doc 25 §17, an offer whose `region_id` is GLOBAL, or a manufacturer's generic claim of worldwide availability, MUST NOT be counted as availability in a specific region unless evidence names that region or a covering one. Such robots appear in a separate "Global availability, region unconfirmed" group, never in the confirmed list.

## 5. Population and record rules

- **Published-only.** Only robots and offers that are public under the master-vs-public rule (DR-C1) appear. Unpublished robots, candidates and internal state never appear in the page, its JSON, its sitemap entry or its structured data. The catalogue invariant that robots are never removed is unaffected.
- **Current-only for status counts.** Only `availability_offer.is_current = TRUE` rows feed status tables. Historical rows may feed a change log, clearly labelled.
- **Humanoid-only** per current scope policy; quadrupeds and non-humanoid platforms are excluded from the population and the exclusion is stated in methodology.
- **Snapshot.** Every render carries one snapshot timestamp (UTC) taken from the data read, shown in the page header and in JSON-LD `dateModified`. Counts and tables on one page share that snapshot.

## 6. Facts the page may show, and their sources

| Page content | Canonical source | Rule |
|---|---|---|
| Robot name, manufacturer, mobility | `robot`, `manufacturer` | Published only |
| Commercial maturity | `robot.commercial_status` | Shown independently of availability |
| Regional availability | `availability_offer` joined to `region` | Per region/provider/transaction type; never inferred from GLOBAL |
| Availability status | `availability_status` | Rendered verbatim: AVAILABLE, LIMITED, WAITLIST, PREORDER, ON_REQUEST, NOT_AVAILABLE, DISCONTINUED |
| Seller | `provider` (`provider_type`) | OEM vs DISTRIBUTOR distinguished |
| Advertised price | price records with `price_type`, currency, billing period | Currency as published; no silent conversion |
| Lead time, MOQ | `availability_offer` | Shown only when non-NULL |
| Deployments in region | `deployment` | Evidence dimension, separate from purchasability |
| Verification date, source | `evidence_source` (`verified_at`, `source_url`, `source_type`, `confidence`) | Required for every price/availability row |

Maturity, transaction availability and deployment evidence are **three distinct dimensions** (schema design) and MUST NOT be collapsed into one "available" label.

## 7. UNKNOWN handling

Per AGENTS.md rules 6–7 and doc 25 §12:

- A NULL price renders as **"Not published"** or **"Unknown"**, never `0`, "free", "N/A" or an estimate. Where only `QUOTE_ONLY` is recorded, render "Price on request".
- A robot with no availability row for the region is listed under **"No confirmed offer in this region"** only if the page states that this means *no evidence on file*, not *not sold*. It is never rendered as `NOT_AVAILABLE`; that value requires its own evidence.
- `ON_REQUEST` is used only for quote/contact-gated offers with evidence.
- Counts disclose their denominator: "N of M published humanoid platforms have a confirmed offer in Europe", with UNKNOWN counted explicitly, not dropped.
- No evidence row, no commercial fact: a price or availability row lacking `evidence_source` linkage is not rendered.

## 8. Standard page structure

Section order is fixed across regions. Headings are stable so AI systems and agents can rely on them.

1. **Title and one-sentence scope.** Question-form H1, e.g. "Which humanoid robots are available in Europe?" plus snapshot date.
2. **Direct answer block.** 40–80 words, fully generated from data: count of confirmed offers, statuses, seller types, price range where published, snapshot date, link to methodology. Placed first so retrieval systems can quote it standalone.
3. **Key figures.** Small generated table: published humanoid platforms (population); with confirmed regional offer; by availability status; with published price; UNKNOWN counts.
4. **Confirmed offers table.** One row per robot × provider × transaction type: robot, manufacturer, status, seller type, price (or "Not published"), lead time, verified date, source link.
5. **Waitlist, preorder and quote-only.** Same columns, separated from AVAILABLE so readers do not conflate them.
6. **Global availability, region unconfirmed.** Robots with only GLOBAL or manufacturer-level claims (§4).
7. **No confirmed offer in this region.** With the §7 disclaimer.
8. **Deployments in the region.** From `deployment`, labelled as evidence of use, not of purchasability.
9. **Regional context (editorial).** Short, sourced prose: import/regulatory notes, distribution landscape, language/support. Every factual claim in this section carries a citation or is limited to non-commercial context. Marked visibly as editorial.
10. **What changed.** Generated change log since the previous snapshot (promotions from the doc 25 pipeline), rendered only when the delta is reproducible (§15); otherwise omitted.
11. **Methodology.** Population definition, published-record rule, region membership rule, UNKNOWN treatment, calculation, refresh cadence, evidence confidence meaning (doc 23 §16 disclosures).
12. **FAQ.** Generated/templated Q&A (see §9).
13. **Citation block.** How to cite, canonical URL, snapshot date, machine-readable links.

## 9. AI-answer blocks and FAQ

Direct-answer and FAQ text is **template-generated from data**, so it cannot drift from the catalogue.

Direct-answer template (illustrative):

```text
As of {snapshot_date}, HumanoidOnline lists {n_confirmed} published humanoid robots with a
confirmed offer in {region}: {n_available} available, {n_waitlist} waitlist or preorder,
{n_request} on request. {n_priced} of {n_confirmed} have a published price
({price_min}–{price_max} {currency_note}). {n_unknown} published platforms have no confirmed
{region} offer on file. Evidence sources and verification dates are listed below.
```

Rules:

- If a figure is not computable (e.g. mixed currencies), the sentence omits it rather than approximating.
- FAQ entries are limited to questions the data can answer: which robots can be bought, which are waitlist-only, which have published prices, which have EU/regional distributors, what a status means, how fresh the data is.
- No FAQ answer may assert a legal, regulatory, import, certification (e.g. CE) or warranty fact unless it exists as a catalogue field with evidence.
- Question-form headings use natural phrasing matching target queries (e.g. "Can I buy a humanoid robot in Europe?") without keyword stuffing.

## 10. Editorial fragments

Editorial context (§8 item 9, region framing text) may be stored as versioned fragments in the repository, e.g. `apps/web/content/research/regions/{region}.md`, with front matter:

```yaml
region: europe
reviewed_at: 2026-10-04
reviewed_by: <owner>
sources: [<urls>]
```

Fragments:

- contain no prices, statuses, counts or robot-specific commercial claims;
- cite a source for any externally verifiable claim;
- carry a `reviewed_at` date shown on the page and trigger a "context may be outdated" label past the review window (default 180 days);
- are authored only after the data for that region passes the §12 gate.

The exact directory is an implementation choice and is fixed in the implementation task.

## 11. Machine-readable surfaces

Each regional page exposes, from the same query:

- **HTML** with semantic tables (`<table>`, `<caption>`, `<th scope>`), stable heading ids, server-rendered (no client-only content).
- **JSON-LD**: `Dataset` (name, description, `temporalCoverage`/snapshot, `dateModified`, `spatialCoverage` = region, `variableMeasured`, `license`/usage statement, `isBasedOn` canonical catalogue URL), plus `ItemList` of listed robot URLs and `FAQPage` for the FAQ block. Structured data MUST match visible content exactly and include only published entities (doc 10 published-only law).
- **JSON endpoint** for the same data, read-only, consistent with doc 26's boundary, e.g. `/research/humanoid-availability/europe.json`, containing rows, snapshot, population definition, UNKNOWN counts and evidence links. Added only within doc 26's authorized scope.
- **CSV download** of the offers table (optional, same rows).
- **Sitemap** entry with `lastmod` equal to the snapshot's last meaningful data change, not the render time.
- **`/llms.txt`** link to the regional pages and methodology, per doc 23 (supporting role only).
- Canonical URL, `hreflang` only if localized variants are later added (none in v0.1).

Links point to canonical robot, manufacturer and evidence pages; the page is a hub into the catalogue, not a parallel copy.

## 12. Publication gate (per region)

A regional page MAY be published only when all hold:

1. The relevant region rows and membership list exist in the catalogue.
2. At least **5 published robots from at least 3 manufacturers** have a current, evidence-linked, region-specific availability offer (owner decision 2026-10-04; a region below this minimum is held back or published as "limited evidence" with that stated plainly). Counting follows §4 and §7: GLOBAL offers and price-only rows do not count.
3. Every rendered price/availability row has `evidence_source` whose latest evidence date is within the **90-day freshness window** for regional commercial-offer evidence (owner decision 2026-10-04; doc 25 §14 leaves TTLs per field, this sets it for v0.1). The evidence date is `verified_at` when set, otherwise `observed_at`, measured against the page snapshot date. A row older than 90 days is stale: it is not counted toward the §12 minimum and is not rendered as current.
4. Counts reconcile: sections 3–7 sum to the stated population.
5. Rendered facts match JSON-LD and JSON endpoint (contract test).
6. Robots excluded because unpublished are not leaked anywhere in output.
7. Owner approval of the region's editorial fragment and of publication itself. Publication is the owner's decision; it is not implied by this contract or by the data being ready.

**Human verification is not required for regional-resource publication.** A current, evidence-linked regional commercial offer may qualify when `verified_at` is null, provided its confidence and provenance are shown honestly. `verified_at` represents a stronger verification state; it is not a publication prerequisite. Freshness is measured from `verified_at` when present, otherwise from `observed_at`.

**Confidence must not be upgraded by publication.** A MEDIUM agent-observed row remains MEDIUM on the Regional Research Resource and must not be presented as verified.

Pages failing freshness after publication degrade visibly ("Last observed …, some entries stale") rather than disappearing silently.

## 13. Tests (AGENTS.md rule 5)

Implementation lands with tests:

- query tests against fixtures: GLOBAL offers never counted as regional; unpublished robots excluded; `is_current` honored; NULL price → "Not published"; missing offer ≠ `NOT_AVAILABLE`;
- determinism: same data and snapshot → identical output;
- direct-answer and FAQ generator unit tests, including omit-when-uncomputable cases;
- JSON-LD / JSON / HTML consistency test;
- journey test for the page (doc 05 acceptance criteria style) and sitemap/`lastmod` test.

The aggregation functions are pure over a read snapshot; no LLM and no randomness in producing figures or answer blocks (AGENTS.md rule 8).

## 14. Measurement

Regional pages are added to the doc 24 measurement set: target queries per region (e.g. "buy humanoid robot Europe", "humanoid robot price Europe", "which humanoid robots ship to Germany") are tracked for citation and retrieval. Baseline is taken before publication so effect is attributable. This contract does not choose queries; the measurement protocol does.

## 15. Refresh model

- Data freshness comes from the doc 25 pipeline; pages are regenerated when canonical regional data changes, not on a manual editorial calendar.
- The "What changed" section is generated from promotion records since the previous snapshot, and **only when the previous snapshot and canonical change history make the delta reproducible**. Otherwise the section is omitted. A change or change date is never reconstructed from present state or inferred.
- Editorial fragments are reviewed on their own `reviewed_at` clock.

## 16. Non-goals

- No purchase, checkout, booking or payment on these pages (AGENTS.md rule 9). Lead capture remains the only commercial action and may be linked, not embedded as a transaction.
- No manually maintained regional robot lists or price tables.
- No regulatory/compliance advice, no investment or market-size forecasts, no unsourced market-share claims.
- No new infrastructure, service, or search engine (AGENTS.md rule 4).
- No schema change as a side effect; any region/field additions are separate reviewed changes.
- No country-level pages in v0.1 (the model supports them later).
- No competitor-derived facts as canonical data (doc 11 radar-only rule).

## 17. Implementation sequence (proposal only)

Each step needs its own owner authorization.

1. **Europe data readiness audit (read-only):** report qualifying robots (published, current regional offer, evidence-linked) and near-ready excluded robots, grouped by reason: unpublished; missing regional offer; stale or non-current offer; offer without evidence; unresolved region mapping. Also report region hierarchy completeness. The output is an actionable publication/enrichment queue and informs the §12 threshold.
2. **Europe query module + tests** (pure aggregation over fixtures).
3. **Europe page, JSON endpoint, JSON-LD, sitemap** behind a non-public flag.
4. **Europe editorial fragment** drafted for owner review.
5. **Owner publication decision** for Europe; add to doc 24 measurement.
6. **North America, then Asia** by parameterizing the same module; each repeats the §12 gate.

## 18. Consequences

**Positive:** no duplicated facts; regional pages stay fresh automatically; one reviewed template scales to three regions; citation-grade structure (snapshot, scope, source, date, uncertainty) per doc 23 §17.

**Cost:** pages are held until evidence-backed regional data exists; thin regions may stay unpublished; template work precedes any visible content.

## 19. Rejected alternatives

- **Hand-written regional articles with embedded facts.** Violates doc 25 §16 and AGENTS.md rules 6–7; drifts from the catalogue.
- **Three independently structured articles.** Inconsistent evidence method and citation format; triple maintenance.
- **Treating GLOBAL offers as regional availability.** Overstates evidence; contradicts doc 25 §17.
- **Placing regional resources under News.** Time-bound framing undermines a living, snapshot-dated resource (doc 23 §16).

## 20. Final decision statement

Regional humanoid-market resources are generated, snapshot-dated, evidence-linked research pages under `/research/humanoid-availability/{region}`, built Europe-first from one shared template. Canonical commercial facts come only from governed catalogue data; derived statistics and answer blocks must be deterministic and reproducible from the declared snapshot; editorial prose may provide interpretation and methodology but may not introduce independent commercial facts. UNKNOWN is preserved everywhere, and publication is gated on data readiness and owner approval.
