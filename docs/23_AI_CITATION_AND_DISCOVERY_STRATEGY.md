# AI_CITATION_AND_DISCOVERY_STRATEGY.md

> ## STATUS: DRAFT STRATEGY v0.1 — 2026-08-28
>
> **Repository baseline:** `main @ 313ff30`
>
> This document defines HumanoidOnline's strategy for becoming a highly retrievable, verifiable, and citable source for AI search systems, answer engines, LLMs, search engines, and future agents.
>
> This strategy is **subordinate to all ratified HumanoidOnline governance contracts**. It does not override PRODUCT, MEDIA-01, AGENT-01, DATA-D1, DATA-D1 LIVE, scheduled freshness, evidence, UNKNOWN, publication, or canonical-identity laws.
>
> This document does **not** create a second source of truth and does not itself authorize a new canonical database model, migration, write path, parallel knowledge store, autonomous publication mechanism, or agent API.

---

# 1. Purpose

HumanoidOnline shall be designed so that, when an AI system needs a factual answer about a humanoid robot, manufacturer, capability, commercial status, availability, price, deployment, or related market fact, HumanoidOnline is one of the easiest sources to:

1. discover;
2. retrieve;
3. interpret;
4. verify;
5. attribute;
6. cite.

The objective is not "AI SEO", keyword manipulation, content multiplication, or generation of pages solely to capture queries.

The objective is:

> **HumanoidOnline becomes a canonical, evidence-aware, freshness-aware reference layer for the humanoid robotics industry.**

The desired information path is:

```text
CANONICAL GOVERNED FACT
        ↓
PUBLISHED GOVERNED READ
        ↓
CITEABLE HUMAN HTML
        ↓
EVIDENCE + FRESHNESS
        ↓
MACHINE PROJECTION
        ↓
CRAWL / RETRIEVAL / INDEX
        ↓
AI ANSWER
        ↓
HUMANOIDONLINE CITATION
        ↓
MEASUREMENT + IMPROVEMENT
```

---

# 2. Relationship to AGENT-01

This strategy extends AGENT-01. It does not replace it.

AGENT-01 already establishes the essential architecture:

```text
canonical model
      ↓
governed read/projection
      ↓
HTML / JSON-LD / sitemap / robots.txt / llms.txt
```

AI citation optimization must remain inside that architecture.

There shall be no:

* AI-only factual database;
* SEO-only robot record;
* independently maintained JSON-LD fact;
* citation-specific truth store;
* generated answer corpus claiming canonical status;
* alternate availability or pricing calculation for crawlers.

A fact exposed for citation must ultimately come from the same governed application state used by the public HumanoidOnline experience.

---

# 3. Citation principles

## CITATION-01.1 — Canonical-only

Only canonical, public, `is_published = true` entities may be presented as HumanoidOnline facts to external search, LLM, or citation systems.

Discovery candidates and promoted-but-unpublished records remain outside the public citation surface.

## CITATION-01.2 — Semantic parity

A machine-readable or citation-oriented representation may never assert a fact that the governed public application cannot truthfully assert.

## CITATION-01.3 — UNKNOWN remains UNKNOWN

UNKNOWN must never become:

* `0`;
* `false`;
* empty string;
* unavailable;
* unsupported;
* no;
* zero price;
* zero payload;
* zero runtime;
* any inferred factual value.

Unknown data is explicitly identified where useful or omitted where the representation requires omission.

## CITATION-01.4 — Claim/evidence honesty

Evidence may only be attached to the claim it actually supports.

A robot record containing one verified pricing source does not make every specification on the record "verified".

A record-level evidence badge must never imply fact-level verification that does not exist.

## CITATION-01.5 — Freshness honesty

The following meanings remain separate:

```text
record updated_at
evidence verified_at
source publication date
freshness check time
material-change time
```

One must never be substituted for another.

## CITATION-01.6 — Human-visible first

Important facts intended to become citation material should exist in clean, server-delivered semantic HTML.

JSON-LD, `llms.txt`, feeds and future agent interfaces complement the page; they do not replace the human-readable factual surface.

## CITATION-01.7 — No shadow content

HumanoidOnline shall not serve substantially different factual content to crawlers than to human users.

## CITATION-01.8 — No scaled thin content

HumanoidOnline shall not automatically create thousands of near-identical pages solely from query permutations such as:

```text
best humanoid robots under X
best humanoid robots in Y
top robots for Z
robot A vs robot B
```

A new indexable URL must provide meaningful independent information value.

## CITATION-01.9 — Derived intelligence must be reproducible

HumanoidOnline may publish original market statistics and indices, but every published statistic must:

* derive from the governed canonical dataset;
* define its population;
* state its snapshot/effective date;
* distinguish published from tracked records;
* preserve UNKNOWN semantics;
* have a reproducible calculation.

## CITATION-01.10 — Measurability

Citation work must be evaluated by observable retrieval and citation outcomes rather than assumptions about "GEO scores".

---

# 4. Existing HumanoidOnline foundation

The following capabilities already provide the base layer and should be preserved rather than rebuilt:

### Canonical entity routes

Examples:

```text
/robots/[slug]
/manufacturers/[slug]
/use-cases/[slug]
```

### Server-rendered robot facts

Robot detail pages already render canonical robot data through the governed read path.

### Evidence surface

Robot records already expose evidence including relevant source information, confidence and verification dates where available.

### JSON-LD

Robot pages already expose a governed `Product` + `Organization` graph.

UNKNOWN values are omitted rather than invented.

### Sitemap

The sitemap already:

* enumerates published canonical entities;
* excludes candidates/unpublished records;
* uses canonical `updated_at` as `lastModified`;
* covers robots, manufacturers and use cases.

### robots.txt

HumanoidOnline currently deliberately permits public crawling.

### llms.txt

`/llms.txt` already identifies:

* canonical robot URLs;
* canonical manufacturer URLs;
* canonical use-case URLs;
* UNKNOWN semantics;
* maturity versus availability;
* evidence semantics.

It remains an auxiliary discovery surface, not a canonical source.

### Agent read layer

HumanoidOnline already has governed agent-oriented capabilities including robot search, robot retrieval and evidence retrieval.

### Scheduled freshness

The DATA-D1 scheduled freshness layer already provides the architectural basis for keeping important market information current.

AI Citation Layer v0.1 therefore builds on existing infrastructure instead of introducing a new subsystem.

---

# 5. Citation-ready robot records

Robot detail pages are the highest-priority citation surface.

Each `/robots/[slug]` page should have a clearly identifiable factual section with stable semantic headings and stable anchors.

Recommended structure:

```text
#robot-summary
#canonical-facts
#specifications
#commercial-status
#pricing
#availability
#deployments
#evidence
#sources
```

The visual design may follow the existing HumanoidOnline system, but the HTML hierarchy should remain understandable without CSS or JavaScript.

---

# 6. Canonical Facts block

Introduce a reusable robot-page component tentatively named:

```text
CitationFacts
```

Its purpose is not to create new facts.

It reorganizes selected existing governed facts into a concise, highly retrievable factual summary.

Example conceptual output:

```text
Canonical facts

Robot: Unitree G1
Manufacturer: Unitree Robotics
Commercial status: COMMERCIAL
Height: 132 cm
Weight: 35 kg
Degrees of freedom: 23
Runtime: 120 minutes
Mobility: BIPEDAL
```

Rules:

1. Use the existing `RobotDetail` governed read.
2. Never independently query the database.
3. Never parse facts back from rendered page text.
4. Never infer a missing value.
5. Preserve existing units.
6. Preserve commercial-status semantics.
7. Do not attach an evidence statement unless the corresponding evidence relationship actually exists.
8. Avoid promotional adjectives.
9. Avoid generated prose when structured facts are clearer.
10. Values displayed elsewhere on the same page must remain semantically identical.

The component should improve extraction and citation, not alter canonical truth.

---

# 7. Evidence-backed commercial facts

Pricing, availability and deployments have particularly high citation value because these facts change frequently and are often poorly documented elsewhere.

For each supported commercial claim, expose the existing governed dimensions clearly.

A price claim should preserve, as applicable:

```text
amount
currency
price_type
transaction_type
provider
region
evidence
confidence
verified_at
```

An availability claim should preserve, as applicable:

```text
availability_status
transaction_type
provider
region
lead time
evidence
confidence
verified_at
```

Never collapse:

```text
commercial maturity
availability
transaction mode
price state
```

into a single "available" or "for sale" assertion.

HumanoidOnline's distinction between these concepts is a citation-quality advantage and must be retained.

---

# 8. Evidence presentation

The page should make provenance easy for both humans and retrieval systems to understand.

Where canonical evidence exists, the page should provide meaningful labels such as:

```text
Source
Source type
Claim subject
Confidence
Verified
```

A visible source link should remain associated with the claim it supports.

Do not:

* fabricate a source title;
* fabricate an author;
* fabricate a publication date;
* convert a crawl/check date into a publication date;
* mark all specifications VERIFIED because one evidence row is VERIFIED.

Stable HTML around evidence is preferable to evidence hidden behind client-only interactions.

---

# 9. Freshness presentation

Freshness is strategically important for humanoid robotics because commercial state, availability, pricing and specifications can change quickly.

Where semantically valid, entity pages should distinguish:

```text
Record last updated
Evidence verified
Commercial information checked
```

These labels may only be shown when their values exist in the governed model with the corresponding meaning.

The already-implemented scheduled freshness layer remains responsible for detecting and governing changes.

AI Citation Layer v0.1 must not introduce another monitoring database.

---

# 10. Metadata and canonical identity

Every indexable canonical entity page should expose one unambiguous canonical URL.

Robot metadata should favor descriptive factual titles while avoiding claims unsupported by the record.

Conceptually:

```text
{Robot name} by {Manufacturer} — Specs, Status & Evidence | HumanoidOnline
```

Price or availability language should only appear in metadata when that page actually contains the corresponding governed information.

Canonical metadata should be generated from the same entity identity used throughout the application.

Manufacturer pages should similarly expose explicit canonical identity.

---

# 11. Structured-data policy

Existing `Product` + `Organization` JSON-LD remains the baseline.

Structured data must follow these rules:

1. It maps governed facts rather than creating facts.
2. Human-visible and machine-visible facts remain consistent.
3. UNKNOWN is omitted rather than coerced.
4. Images continue to obey MEDIA-01.
5. Structured data is not keyword stuffing.
6. New schema types are added only when their semantics honestly map to HumanoidOnline data.

## Offer schema

Do **not** automatically add schema.org `Offer` merely because HumanoidOnline has a pricing offer.

HumanoidOnline's offer model contains richer semantics including:

* transaction type;
* region;
* price state;
* obtainability;
* provider;
* evidence.

`Offer` may be introduced in a later bounded change only after proving that the mapping does not destroy or misrepresent those semantics.

No fabricated availability or price value may be created merely to satisfy schema fields.

## Breadcrumbs

`BreadcrumbList` may be added where it faithfully mirrors visible page navigation.

## Manufacturer entities

Manufacturer `Organization` projections may be expanded where they map directly to the governed manufacturer read.

---

# 12. Crawler policy

Citation eligibility and model-training permission are separate policy questions.

HumanoidOnline should deliberately support:

### Search/discovery crawlers

Allow legitimate search engines required for normal indexing.

### AI search/retrieval crawlers

Allow crawler identities required for AI search/retrieval systems when citation visibility is desired.

This includes ensuring that `OAI-SearchBot` can retrieve public HumanoidOnline pages.

Anthropic and other providers should be handled according to their current published search/retrieval crawler identities.

### User-directed retrieval

User-directed AI retrieval should normally be able to access the public catalogue.

### Model-training crawlers

Training crawler access is a separate owner/business-policy decision.

AI Citation Layer v0.1 shall **not silently change HumanoidOnline's current training-crawler policy**.

Any future split such as:

```text
search/retrieval: ALLOW
training: DISALLOW
```

requires an explicit owner decision.

---

# 13. Infrastructure crawler audit

`robots.txt` alone is insufficient.

Citation eligibility requires auditing the whole public request path:

```text
crawler
  ↓
DNS / Cloudflare
  ↓
Netlify
  ↓
edge functions / rate limiting
  ↓
Next.js
  ↓
public entity page
```

The audit must verify that legitimate search/retrieval crawlers are not unintentionally rejected by:

* CDN configuration;
* WAF/firewall rules;
* native edge rate limits;
* bot protection;
* redirects;
* malformed canonical origins;
* 403/429 responses;
* excessive timeout behavior.

Crawler allowance must be tested at runtime, not inferred from `robots.ts`.

---

# 14. Sitemap policy

The existing sitemap architecture should be retained.

Requirements:

* canonical entities only;
* published entities only;
* meaningful `lastModified`;
* no candidate URLs;
* no search-result permutations;
* no uncontrolled comparison permutations;
* no fabricated freshness timestamp.

At larger catalogue scale the sitemap may be split by entity type without changing the canonical-data rule.

---

# 15. llms.txt policy

`/llms.txt` remains useful as a concise machine orientation surface, but HumanoidOnline must not architect its discovery strategy around it.

It should continue to:

* identify HumanoidOnline;
* explain key semantics;
* link canonical entity collections;
* expose canonical public entities only;
* exclude candidates/internal state;
* avoid claiming authority beyond the underlying governed catalogue.

Where useful it may later point toward public methodology, research or agent documentation.

It is never a replacement for high-quality HTML, canonical URLs, sitemap coverage or search indexing.

---

# 16. Original HumanoidOnline intelligence

The largest long-term citation opportunity is not reproducing manufacturer text.

It is publishing factual analysis that only HumanoidOnline can conveniently produce from its governed cross-manufacturer dataset.

Potential future surfaces include:

```text
/research
/research/humanoid-market
/research/humanoid-prices
/research/commercial-humanoids
/research/humanoid-availability
/research/manufacturer-landscape
```

Potential original metrics include:

```text
published humanoid platforms
commercial-status distribution
commercially obtainable platforms
availability by region
advertised price distribution
SDK availability
runtime distribution
payload distribution
manufacturer geography
market-state changes over time
```

Every metric must disclose:

```text
snapshot date
population definition
published-record rule
UNKNOWN treatment
calculation methodology
```

These research/index pages are **not part of Citation Layer v0.1** unless separately authorized.

They are a subsequent product/research slice.

---

# 17. Citation-quality content policy

HumanoidOnline should prefer:

```text
specific fact
+
scope
+
source
+
date
+
uncertainty
```

over generic prose.

Good:

```text
Advertised price: €19,798.54
Transaction: purchase
Region: EU
Provider: …
Evidence verified: …
```

Weak:

```text
This innovative humanoid offers excellent value and is widely available.
```

Citation-oriented writing should be:

* concise;
* specific;
* neutral;
* directly attributable;
* semantically structured;
* useful independently of search ranking.

Do not generate filler paragraphs merely to increase page length.

---

# 18. Comparison and programmatic-page containment

Current comparison functionality must not become an uncontrolled index-generation mechanism.

A URL containing arbitrary robot query combinations is not automatically a canonical search document.

Permanent pairwise comparison URLs may be considered later only where:

* the combination has meaningful user demand;
* the page adds independent analysis;
* canonicalization is deterministic;
* permutations do not create duplicates;
* indexing policy is explicitly designed.

AI Citation Layer v0.1 does not introduce programmatic comparison SEO pages.

---

# 19. Authority development

Technical citation readiness is necessary but not sufficient.

HumanoidOnline should seek legitimate references from:

* robot manufacturers;
* universities;
* robotics laboratories;
* distributors;
* conferences;
* robotics publications;
* industry analysts;
* open technical projects;
* research papers and datasets.

Authority must emerge from useful data and original research.

No automated backlink schemes, synthetic citation networks, purchased-link programs or fake mentions are authorized.

---

# 20. Measurement

Citation work must have an observable feedback loop.

## Primary outcome metrics

Track where available:

```text
AI citations
cited HumanoidOnline URLs
citation-bearing queries
AI-search impressions
AI-search clicks
AI referral sessions
```

## Platform signals

Use available platform reporting including:

* ChatGPT referral attribution;
* Bing Webmaster AI citation reporting;
* Google Search generative-AI reporting;
* search-console index/crawl status;
* infrastructure crawler logs.

## Diagnostic metrics

Measure:

```text
published canonical pages crawlable
published pages present in sitemap
canonical URL conflicts
crawler 4xx / 5xx / 429 rate
pages containing CitationFacts
pages containing evidence
pages with meaningful freshness
JSON-LD validation failures
UNKNOWN coercion regressions
```

## Benchmark query set

Maintain a stable, human-reviewed set of representative questions such as:

```text
What humanoid robots are commercially available?
How much does the Unitree G1 cost?
Which humanoid robots can be purchased in Europe?
What is the payload of Atlas?
Which humanoids offer SDK access?
Compare Unitree G1 and Figure 02.
Who manufactures Apollo?
```

Periodically test major AI search systems and record:

```text
date
query
answer engine
HumanoidOnline cited? yes/no
cited URL
citation position/context
answer correctness
```

This benchmark is diagnostic, not a guaranteed-ranking test.

---

# 21. AI Citation Layer v0.1 — bounded implementation scope

The first implementation slice shall focus on making existing canonical robot records easier to retrieve and cite.

## IN

### CID-01 — Baseline audit

Audit:

```text
robots.txt
sitemap.xml
llms.txt
canonical metadata
robot HTML
JSON-LD
crawler accessibility
edge-rate-limit interaction
existing SEO/agent tests
```

No edits before the audit is reported.

### CID-02 — CitationFacts

Introduce a reusable server-rendered citation-oriented factual section on robot pages using only the existing governed `RobotDetail`.

### CID-03 — Stable semantic anchors

Provide deterministic section identifiers for high-value factual sections.

### CID-04 — Canonical metadata hardening

Ensure canonical entity pages emit correct canonical metadata from the authoritative site-origin resolver.

### CID-05 — Evidence clarity

Ensure existing evidence-backed pricing, availability and deployment claims remain visibly connected to source/confidence/verified date.

No new evidence is invented.

### CID-06 — Freshness clarity

Expose existing canonical freshness values only where their meanings are unambiguous.

### CID-07 — Crawler eligibility

Verify AI-search/search retrieval crawlers can access public pages.

Explicitly test `OAI-SearchBot`.

Do not modify training-crawler policy without owner approval.

### CID-08 — JSON-LD parity hardening

Preserve Product + Organization projection and strengthen tests proving HTML/JSON-LD semantic parity.

Do not introduce `Offer` in v0.1.

### CID-09 — llms.txt audit

Verify canonical-only enumeration and semantics remain correct.

Do not expand `llms.txt` into a second knowledge API.

### CID-10 — Acceptance tests

Add automated regression coverage for citation invariants.

---

# 22. Explicit OUT list — Citation Layer v0.1

The following are NOT authorized by this slice:

* no database migration;
* no new canonical model;
* no duplicate truth store;
* no new discovery pipeline;
* no changes to promotion/publication governance;
* no candidate exposure;
* no autonomous publication;
* no MCP changes;
* no new agent actions;
* no transactional-agent work;
* no scraped AI-answer corpus;
* no autogenerated mass landing pages;
* no research section yet;
* no market index yet;
* no synthetic FAQ generation;
* no backlink automation;
* no fabricated author or reviewer identities;
* no fake ratings/reviews;
* no speculative facts;
* no schema.org Offer yet;
* no training-crawler policy change;
* no Search Console/Bing/OpenAI credentials committed to the repository.

---

# 23. Expected implementation files

Likely web-layer changes include:

```text
apps/web/components/CitationFacts.tsx              NEW
apps/web/app/robots/[slug]/page.tsx               MODIFY
apps/web/lib/seo.ts                               MODIFY if needed
apps/web/lib/jsonld.ts                            TEST/HARDEN; minimal change only if required
apps/web/app/robots.ts                            AUDIT / TEST
apps/web/app/sitemap.ts                           AUDIT / TEST
apps/web/app/llms.txt/route.ts                    AUDIT / minimal change only if justified
```

Expected tests may include:

```text
apps/web/__tests__/citation-facts.test.tsx        NEW
apps/web/__tests__/jsonld.test.ts                 MODIFY
apps/web/__tests__/seo.test.ts                    MODIFY
apps/web/e2e/agent-accessibility.spec.ts          MODIFY
apps/web/e2e/seo.spec.ts                          MODIFY
```

The implementation should avoid API/backend modifications unless the audit proves that a required canonical value is not available through the existing governed read.

If a backend or schema change appears necessary, STOP and report it as a proposed separately governed dependency.

---

# 24. Acceptance gates

## CIT-A — Canonical-only

No unpublished entity or discovery candidate appears through the citation layer.

## CIT-B — UNKNOWN safety

No absent/UNKNOWN value is converted into a factual value.

## CIT-C — Evidence honesty

Every displayed evidence relationship reflects an existing canonical evidence relationship.

## CIT-D — Server-visible facts

CitationFacts is present in delivered HTML without requiring client interaction.

## CIT-E — Canonical identity

Each robot record resolves to one canonical robot URL.

## CIT-F — Stable anchors

High-value factual sections have deterministic stable IDs.

## CIT-G — Search/retrieval crawlability

Public robot records, sitemap and machine discovery surfaces are reachable by intended search/retrieval crawlers.

`OAI-SearchBot` is explicitly permitted.

## CIT-H — Training policy unchanged

Citation Layer v0.1 does not silently alter training crawler policy.

## CIT-I — Projection parity

JSON-LD contains no factual assertion inconsistent with the governed robot record and visible page semantics.

## CIT-J — Freshness honesty

`updated_at`, `verified_at`, source dates and freshness-check dates are never conflated.

## CIT-K — Existing semantics preserved

Commercial status, availability, transaction type and price state remain separate dimensions.

## CIT-L — No new source of truth

No citation-specific canonical data store exists.

## CIT-M — Existing regression suite remains green

Existing unit, typecheck, lint, build, E2E, semantic, agent-accessibility, SEO and performance gates remain satisfied.

---

# 25. Implementation order

The implementation sequence is intentionally conservative:

```text
0. Ratify/approve strategy
        ↓
1. Baseline citation audit
        ↓
2. Lock acceptance tests
        ↓
3. CitationFacts + semantic anchors
        ↓
4. Canonical metadata hardening
        ↓
5. Evidence/freshness presentation
        ↓
6. crawler eligibility verification
        ↓
7. JSON-LD parity hardening
        ↓
8. llms.txt verification
        ↓
9. full regression suite
        ↓
10. production crawl verification
        ↓
11. measurement baseline
```

Do not skip directly to content generation or schema expansion.

---

# 26. Later authorized candidates

After v0.1 proves stable, separately review:

### Citation Layer v0.2

* manufacturer citation blocks;
* use-case citation blocks;
* richer Organization semantics;
* BreadcrumbList;
* change-history presentation;
* IndexNow integration;
* AI crawler observability.

### Research Layer v0.1

* `/research`;
* monthly HumanoidOnline market snapshot;
* commercial humanoid index;
* price index;
* availability index;
* manufacturer landscape;
* downloadable governed snapshot where appropriate.

### Agent Discovery Layer

* public typed read interface;
* MCP or equivalent;
* explicit machine citation identifiers;
* structured evidence access.

Each remains subordinate to the same canonical governed model.

---

# 27. Success definition

AI Citation Layer v0.1 succeeds when:

1. every public robot record remains truthful under existing governance;
2. important robot facts are easier for both humans and machines to extract;
3. evidence and freshness are clearer rather than weaker;
4. major search/retrieval crawlers can reliably access those facts;
5. canonical identity is unambiguous;
6. no UNKNOWN or provenance regression occurs;
7. citation activity can begin to be measured.

Long-term success is achieved when external AI systems routinely use HumanoidOnline as supporting evidence for factual humanoid-robot answers.

The target is not:

> "HumanoidOnline has many AI-optimized pages."

The target is:

> **"HumanoidOnline is one of the most reliable sources an AI can cite when answering factual questions about humanoid robots."**
