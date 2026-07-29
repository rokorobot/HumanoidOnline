# DATA-D1.LIVE — Live Market Acquisition Contract

> **STATUS: RATIFIED v0.1 — 2026-07-29, Robert Konecny (product owner).**
>
> **Implementation authorized: Slice A only** (schema + models + tests, §21).
> **Per-source crawling authorization: none.**
>
> Ratification is **not** permission to fetch any product page automatically.
> Two separate approvals are required before any live fetch, and only the first
> of them has been given:
> 1. ✅ ratification of this contract;
> 2. ⬜ an approved, attributed **per-source eligibility review** (§5) — held by
>    **no source**.
>
> **Factual standing (2026-07-29):**
> - The first read-only eligibility assessment **was completed** on 2026-07-29,
>   covering `robots.txt`, terms, legal / acceptable-use pages and the sitemaps
>   needed to locate them, across fourteen hosts.
> - **No manufacturer product page was fetched.**
> - **No live adapter was executed.**
> - **No discovery or canonical database row was written.**
>
> No live adapter exists, and the discovery layer shipped today (`docs/11`,
> merged at `3dca8cc`) remains **fixture-only**.

---

## 0. Why this exists

Phase 1 of HumanoidOnline is a *commercial intelligence* product. A catalogue of
seven hand-verified robots proves the model; it does not make the claim
"HumanoidOnline knows what is actually on the market" true. Making that claim
true requires continuous acquisition of real market facts: which humanoids exist,
which are actually obtainable, on what commercial terms, in which regions, with
what evidence, and what changed since last time.

The DATA-D1 architecture for that already exists and is ratified
(`RADAR → CANDIDATE → TRACE → VERIFY → PROMOTE`). What is missing is the first
link: something that reads the real world. Today the only adapter is
`FixtureAdapter`, which reads local JSON, because DATA-D1.9 gates every source
behind a human eligibility review that has never been performed.

This contract defines the **narrowest live acquisition capability that is worth
having**, and freezes the rules that keep it from contaminating the verified
catalogue.

**The failure this contract exists to prevent** is not "we crawl too slowly". It
is: *a crawler fills the catalogue with plausible, unverifiable, subtly wrong
market claims, and the product's one differentiator — that every commercial fact
carries evidence — quietly becomes false.* Every rule below is chosen against
that outcome.

### 0.1 Business model — FROZEN

*(Numbered as a subsection so that every `§n` cross-reference in this document
stays stable. Its standing is that of a frozen law, not an aside.)*

**HumanoidOnline is an independent market-intelligence and buyer-intent referral
platform. It is not the merchant of record for robot transactions in Phase 1 or
Phase 2.** Robot purchases, quotation contracts, pilot agreements, RaaS
agreements, payment, delivery, warranty and support remain between the **buyer**
and the **manufacturer or authorized seller**.

**Acquisition exists to create accurate, manufacturer-attributed listings and to
route qualified buyers to official manufacturer channels.**

**And that beneficial purpose grants nothing.** It does not override a source's
terms, and it does not confer permission for automated access. A restricted
source stays restricted until one of these exists:

1. **written authorization** from the source, recorded as eligibility evidence;
2. an **official feed or API** whose own terms permit the use; or
3. **manufacturer-supplied evidence** (press kit, data sheet, direct
   correspondence) provided for this purpose.

This is stated as a law because it is the argument most likely to be used to
justify an exception. "We are sending them customers" is a reason for a
manufacturer to *grant* permission — an excellent one, and the basis of the
partnership approach — but it is never a substitute for having been granted it.
A platform whose entire value proposition is *verifiable, attributed truth*
cannot acquire that truth by disregarding the terms of the people it attributes
it to. The first eligibility review (2026-07-29) found two of three approved
sources expressly prohibiting automated access; the answer is to **ask them**,
not to reinterpret their terms in our favour.

Two consequences bind the acquisition engine directly:

- **Attribution is not optional.** Every listing names the manufacturer and
  routes to their official channel. We are a directory that sends buyers *to*
  them, never an intermediary that stands between them and the buyer.
- **No transaction surface may be inferred from acquired data.** Discovering a
  price or a purchase URL never makes HumanoidOnline a seller. The routing
  fields in §16.1 exist so the platform can *point at* the official channel; the
  transaction itself completes off-platform, and the schema says so explicitly.

## 1. Relationship to existing contracts

DATA-D1.LIVE is **subordinate** to, not a replacement for:

| Contract | Standing |
|---|---|
| `11_DATA_D1_CONTRACT.md` (RATIFIED) | **Binding in full.** All ten laws DATA-D1.1–1.10 remain in force. This contract adds obligations; it removes none. Where they appear to conflict, DATA-D1 wins. |
| `09_MEDIA_CONTRACT.md` MEDIA-01 (FROZEN) | **Binding in full.** Imagery reaches the catalogue only through MEDIA-01. Live acquisition may propose image *references*; it may never display, self-host or promote an image. |
| `10_AGENT_CONTRACT.md` AGENT-01 (RATIFIED) | **Binding.** AGENT-01.7: machine surfaces expose published canonical rows only. Nothing acquired here is ever visible to an agent surface before promotion. |
| `12_WS8_RELEASE_CONTRACT.md` | **Binding.** WS8-L1 (no new product capability during release hardening) means this workstream does not merge into the MVP v0.1 release train; it runs beside it. |

**Inherited laws restated, because they are the ones a crawler is most tempted
to break:** UNKNOWN ≠ 0 / false / unavailable · QUOTE_ONLY ≠ UNKNOWN · maturity ≠
obtainability ≠ evidence · no commercial fact without evidence (G2) · competitors
are radar only · no direct crawler writes to canonical.

## 2. Scope

**In scope (v0.1):**

- an adapter framework for **official manufacturer sources first**, extensible
  to eligible aggregators, directories, marketplaces and editorial sources once
  each individually clears its own eligibility review (§4 amendment, below)
- a per-source eligibility review record, and the refusal that depends on it —
  identical discipline regardless of source class
- **two acquisition modes** (§2.1): `AUTOMATED_LIVE` (adapter-driven, eligibility
  gated) and `MANUAL_BOOTSTRAP` (a named human reading a source or reviewing
  manufacturer-supplied material — no automated traversal, no eligibility review
  required, same evidence and promotion discipline)
- a manually executed, local, resumable crawl with a full run report (for
  `AUTOMATED_LIVE`)
- extraction of specification claims, commercial signals and image *references*,
  each bound to evidence
- deterministic identity resolution and deduplication against the existing
  canonical catalogue and existing candidates
- operator review through the **existing** SQLAdmin views and CLI

**Explicitly out of scope (v0.1):** see §20. In particular: no scheduler, no
crawler VPS, no headless browser, no automated fetch of any source (official or
otherwise) without a passed eligibility review, no canonical writes, no image
binaries, no Operations Workbench.

### 2.1 Acquisition modes

Two modes reach the same destination — the discovery layer, then human
promotion — by different, non-overlapping means. Neither is a shortcut around
the other's discipline.

```
AUTOMATED_LIVE
  performed by            an adapter (§12), over HTTP, from a named human's
                           local machine (LIVE.4)
  requires                an affirmative, unexpired, attributed per-source
                           eligibility review (§5) — LIVE.2, no exceptions
  governed by              etiquette (§13): rate limits, robots re-check every
                           run, identifiable UA, bounded retries, kill switch
  produces                 crawl_run / fetched_page / extraction_result rows,
                           evidence excerpts with a locator (§7-§9)
  evidence granularity      systematic — a defined page set, run to run

MANUAL_BOOTSTRAP
  performed by             a named human reading a source directly, or
                           reviewing material supplied to us — no HTTP client,
                           no adapter, no automated traversal of any kind
  requires                 nothing beyond LIVE.6 (evidence) and LIVE.9
                           (imagery) — see "why no eligibility review" below
  governed by               the SAME evidence discipline as AUTOMATED_LIVE:
                           exact excerpts ≤ 1000 chars (LIVE.6), the official
                           URL or document identifier, retrieval timestamp,
                           image REFERENCES only (LIVE.9), discovery-layer
                           writes only (LIVE.5), human verification and
                           promotion still required (LIVE.8, DATA-D1 §18)
  produces                 the SAME discovery rows AUTOMATED_LIVE would,
                           attributed to the human who entered them
                           (extraction_method = MANUAL)
  evidence granularity      opportunistic — one robot, one fact, one session
```

**Why `MANUAL_BOOTSTRAP` needs no per-source eligibility review.** LIVE.2 and
DATA-D1.9 gate *automated access* — a program issuing requests at a rate and
pattern a human does not. A person opening a public product page in a browser
and typing what they read into a form is the same act that built the existing
7-robot catalogue, and no terms-of-service reviewed during the first
eligibility assessment (§ eligibility reports) prohibits a *human* from reading
a public page. The line is not "official site vs. not" — it is **automated vs.
manual**. The moment any part of the fetch, navigation or extraction is
performed by code rather than a person, the activity is `AUTOMATED_LIVE` and
LIVE.2 applies without exception, in full.

**Authorized `MANUAL_BOOTSTRAP` evidence sources:**

- a public official page, opened and read by a human;
- **manufacturer-supplied evidence**, provided directly to HumanoidOnline by the
  manufacturer or an authorized representative: datasheets, press kits,
  catalogue exports, emails, official PDFs, price lists, partner feeds, API
  exports. Provenance is recorded as `MANUFACTURER_SUPPLIED`, distinct from a
  page the human retrieved themselves, because its evidence URL may be absent —
  the sender and the transmission are the provenance instead.

**Why this matters now.** `MANUAL_BOOTSTRAP` is how the general humanoid
inventory grows **immediately**, independent of per-source automated-access
permission. Permission negotiations (§23) and adapter development (Slice B/C,
§21) proceed in parallel, on their own timeline, without blocking inventory
growth on anyone else's response time.

## 3. Laws (frozen on ratification)

### LIVE.1 — Official-first, multi-source radar *(amended 2026-07-29)*
Manufacturer sources remain the **preferred evidence authority** — nothing below
demotes them. But manufacturer sites alone will miss robots not yet on our
radar, model and manufacturer aliases, regional listings, discontinued models,
price changes, and companies whose own web presence is thin. Restricting
acquisition to official sources only would make the platform blind to exactly
the market movement it exists to track.

**Eligible** aggregators, directories, marketplaces and editorial sources —
individually reviewed and enabled under §5, on identical terms to a manufacturer
site — may be acquired to:

- discover candidates for robots or manufacturers not yet in our catalogue;
- propose manufacturer/model **aliases** and identity links for a human to
  confirm (§11);
- add evidence-bound specification and commercial **claims**, carrying their own
  source classification (§4);
- surface **conflicts** between sources and **changes** since the last
  observation;
- provide **links to official sources**, which the platform then traces to
  directly — a lead is never treated as the trace itself (DATA-D1 §9, H2).

**Third-party evidence may never**: independently set a claim `VERIFIED`
(LIVE.8 unchanged) · write a canonical row (LIVE.5 unchanged) · override a
conflicting manufacturer claim (§6.1) · infer availability, maturity, image
rights or official status (LIVE.7, LIVE.9 unchanged) · bypass human promotion
(DATA-D1 §18 unchanged).

This is **radar**, not a second evidence tier with equal standing: DATA-D1.1
("competitors are discovery sources only") governs every non-manufacturer class
exactly as before. What changes is that those sources may now be **acquired
directly** (subject to their own eligibility review) rather than only entered by
a human as a lead. A lead may still point at an official URL, and the platform
traces to that official URL directly — acquiring it does not make the
aggregator's *page* the trace.

**Where third-party sources sit in the pipeline** — they enter at RADAR, and
every downstream stage is unchanged from the ratified DATA-D1 architecture:

```
  aggregator / directory / marketplace / editorial   ← eligible, §5-reviewed
                        │
                        ▼
        robot, manufacturer or CHANGE discovered      ← the value they add
                        │
                        ▼
              discovery candidate created             ← §11 identity resolution
                        │
                        ▼
         official source traced where possible        ← §11.1 / DATA-D1 P2
                        │                               (an official trace is
                        │                                REQUIRED when an
                        ▼                                official source exists)
            claims verified INDIVIDUALLY              ← per claim, by a human;
                        │                                never per candidate,
                        ▼                                never in bulk
                  human promotion                     ← DATA-D1 §18, unchanged
```

Two properties of that pipeline are what make aggregator acquisition safe rather
than contaminating: the trace stage forces the platform *back* to an official
source before anything is promotable, and verification is **per claim** — so a
candidate discovered by an aggregator can be promoted with three manufacturer-
verified facts and eleven still-unverified aggregator claims attached, and the
catalogue shows only the three.

*Why not official-only, as originally drafted:* the evidence hierarchy
(`docs/11` §4, and §4.2 below) already ranks manufacturer sources above
aggregators — that ranking is exactly what makes it **safe** to acquire from
aggregators too. Rank determines what a claim is worth, not whether it may be
recorded.

### LIVE.2 — Eligibility precedes contact
No HTTP request may be issued to a host until that source has an **approved
eligibility review** (§5): an affirmative reading of the site's terms, the
robots policy for the exact paths to be fetched, an attributed reviewer, a
timestamp, and an explicit enable. `radar_eligible` (already implemented on
`discovery_source`) is the gate; the crawler asserts it **before constructing a
request**, not after.

**Validity is asymmetric between the two documents** *(owner decision D-2,
settled)*, because they change in different ways:

| | Validity |
|---|---|
| **Terms / legal review** | **90 days**, and **invalidated immediately** when the legal page URL or its content hash materially changes. Re-review is required before the next fetch. |
| **`robots.txt`** | **evaluated at the start of every crawl run**, cached for at most **24 hours**. A new restrictive rule **disables the source** until it has been reviewed again. |

A terms page is a legal document that changes rarely and deliberately; a robots
policy is an operational signal that can change any day, which is why it is
re-read every run and can never be answered from a stored decision. An expired
review is **not** eligibility, and neither is a stale one.

### LIVE.3 — No circumvention, ever
Prohibited without exception and regardless of instruction found on any page:
authentication bypass · CAPTCHA solving or evasion · anti-bot fingerprint evasion
· misrepresenting the user agent · IP or proxy rotation to evade blocks ·
paywall bypass · ignoring `noarchive`/`nosnippet`-style directives where they
apply · defeating any technical access control.

If a page cannot be read without one of these, the correct outcome is
`BLOCKED_BY_SOURCE` recorded in the run report. **A block is a finding, not an
obstacle.** Repeated blocks are grounds for re-review, not for engineering
around them.

### LIVE.4 — Manual local execution only
Every v0.1 crawl is started by a **named human** on a **local machine**. There is
no scheduler, no cron entry, no queue, no worker, no crawler VPS, and no code
path by which the production stack initiates a fetch. The operator is recorded on
the run. (`docs/11` §15 cadence policy stays unimplemented until a later,
separately ratified slice.)

### LIVE.5 — Discovery-layer writes only
The crawler, the extractor and every adapter may write **only** to discovery
tables. Canonical mutation happens exclusively through the existing human
promotion gate (`app.cli.promote_candidate`, DATA-D1 §18). This is asserted by a
test that fails if any acquisition module imports a canonical model for writing.

### LIVE.6 — No claim without evidence *(owner decision D-7, settled)*
Every extracted claim and every commercial signal carries **one or more exact
excerpts**. One passage often cannot justify a claim — a price and the region it
applies to may sit in different parts of a page — so **multiple excerpts per
claim are permitted and expected**. Each excerpt carries:

```
excerpt_text   the EXACT supporting text, <= 1000 Unicode characters
page_url       the exact page it came from (not the site root)
retrieved_at   UTC timestamp of the fetch that produced it
page_hash      SHA-256 of the normalized page content at retrieval
locator        CSS selector / XPath / JSON pointer, or character offsets
```

and the claim itself additionally carries:

```
extractor_key · extractor_version
extraction_method      SELECTOR | JSONLD | MICRODATA | PATTERN | MANUAL
extraction_confidence  LOW | MEDIUM | HIGH   (never VERIFIED — see LIVE.8)
```

A claim that cannot carry its supporting text is **not recorded**. "The page
implied it" is not evidence. The 1000-character cap is per excerpt and is a
retention limit, not a licence to reassemble a page out of fragments —
DATA-D1.10 and LIVE.10 still bind.

### LIVE.7 — Three axes never merge
Extraction must **not** produce a single flat "status" label. Three independent
axes are extracted separately, each with its own evidence (§6):

- **maturity** — where the programme is (`commercial_status`)
- **obtainability** — whether a specific transaction mode is available, in a
  region, to a buyer type (`availability_status` × `transaction_type` ×
  `region` × `buyer_type`)
- **price semantics** — what a price figure *means* (`price_type`), separately
  from the number

`UNKNOWN` is the absence of a signal and never becomes `NOT_AVAILABLE`.
`QUOTE_ONLY` is a *price* fact and never becomes `UNKNOWN`. A robot being
`ANNOUNCED` says nothing about obtainability, and vice versa.

### LIVE.8 — Extraction confidence is not verification *(owner decision D-6, settled)*
`extraction_confidence` describes how sure the *parser* is that it read the page
correctly. It is **not** evidence quality.

It **may**: order the review queue by priority, and reject its own
low-confidence output before it is ever written.

It **may never**: set `claim_status = VERIFIED`, modify canonical
`confidence_level`, or bypass human promotion in any way. Only a human, through
the existing promotion path, converts a claim into canonical truth (DATA-D1.2,
DATA-D1.4). Cross-source agreement raises **priority**, never confidence
(DATA-D1 §16).

### LIVE.9 — Reference-only imagery
Image acquisition produces a **URL plus provenance**, never a binary
(DATA-D1 R3). The recorded provenance is the *retrieval* provenance: an image
found on the manufacturer's own product page is `MANUFACTURER`; an image
credited to a manufacturer but retrieved elsewhere is `EDITORIAL` (the Figure 02
precedent). `is_official`, `rights_status` and `usage_basis` are **never**
inferred by the extractor — they are MEDIA-01 decisions made by a human.

### LIVE.10 — Minimal retention, no site mirror *(owner decision D-3, settled)*
The database stores **bounded evidence excerpts and content hashes**, never page
bodies (DATA-D1.10). Full response bodies live in a local, **content-addressed**
cache outside the database:

```
var/discovery/cache/          git-ignored, outside the Docker build context
  <sha256>[.meta.json]        addressed by SHA-256 of the raw body
```

Retention is asymmetric on purpose:

| Artefact | Retained |
|---|---|
| successful raw page bodies | **90 days** |
| failed / blocked responses | **30 days** |
| crawl manifests, page hashes, evidence excerpts, provenance records | **indefinitely**, unless a later retention policy supersedes this |

The distinction is the whole point: the *evidence* of what a page said, and the
audit trail of what we did, are durable; the *page* is not. The cache is never
committed, never deployed, and is not a corpus — content addressing means an
unchanged page is stored once, not once per run.

### LIVE.11 — Determinism and audit
Every run has a **manifest** (what was attempted and with which adapter
versions) and a **report** (§18). Runs are **resumable** without re-fetching what
succeeded. Replaying a run against recorded fixtures produces **identical**
extraction output — that is what makes extraction changes reviewable.

## 4. Source classes *(amended 2026-07-29 — official-first, multi-source radar)*

| Class | v0.1 fetch? | Role |
|---|---|---|
| `MANUFACTURER` (site, store, press room, documentation) | **yes**, after eligibility | preferred evidence authority |
| `AUTHORIZED_DISTRIBUTOR` | **yes**, after eligibility | price / obtainability, second-tier authority |
| `OFFICIAL_STORE` (manufacturer-operated storefront, if distinct from the site) | **yes**, after eligibility | price / obtainability evidence |
| `AGGREGATOR` (specialist humanoid-robot directory) | **yes**, after **its own** eligibility | discovery, aliases, cross-source conflict signal |
| `MARKETPLACE` | **yes**, after **its own** eligibility | commercial / regional availability signal |
| `EDITORIAL` / `NEWS` / `PRESS_RELEASE` | **yes**, after **its own** eligibility | maturity, announcement and change signal |
| `COMMUNITY` (forums, social posts) | **no** — lead only | too unreliable to acquire; a human may still enter a lead |
| `UNKNOWN` | **no** | unclassified; must be classified before any review can pass |

**Eligibility is per-host, not per-class.** A class being *fetchable in
principle* is not a source being *eligible in fact* — every individual host,
manufacturer or aggregator alike, still needs its own passed review under §5
before a single request is issued (LIVE.2 unchanged). Nothing in this table
grants access to any specific site; §23 records what has actually been
reviewed, and as of ratification that is **zero** sources.

Adding an entirely new *class* (one not listed above) to the fetchable set is a
contract amendment. Reviewing and enabling a *specific site* within an existing
class is an ordinary §5 procedure, not a contract change.

### 4.1 What each class may do

The eligibility gate controls *whether a source may be fetched at all*. This
table controls *what its evidence may become* once fetched or entered —
identical for `AUTOMATED_LIVE` and `MANUAL_BOOTSTRAP` — and is the more
important one, because it is what actually protects the catalogue.

| Source class | Create candidate | Add claims | Verify a claim | Canonical write |
|---|---|---|---|---|
| `MANUFACTURER` | Yes | Yes | Human only (promotion) | Promotion only |
| `AUTHORIZED_DISTRIBUTOR` | Yes | Yes | Human only (promotion) | Promotion only |
| `OFFICIAL_STORE` | Yes | Yes | Human only (promotion) | Promotion only |
| `AGGREGATOR` | Yes | Yes | **Never automatic** | **Never** |
| `MARKETPLACE` | Yes | Yes | **Never automatic** | **Never** |
| `EDITORIAL` / `NEWS` / `PRESS_RELEASE` | Yes | Yes | **Never automatic** | **Never** |
| `COMMUNITY` | Lead only | Limited (a human-entered lead, not a structured claim) | No | Never |

No class ever writes canonical rows directly — that column exists to make the
asymmetry visible, not to imply an official source gets one. **Every** class's
path to canonical truth is the same human promotion gate (DATA-D1 §18); what
differs is which classes may set `claim_status = VERIFIED` en route to it, and
the answer for every non-manufacturer class is **none, ever, automatically**.

### 4.2 Evidence hierarchy

Extends `docs/11` §4 with the classes this amendment introduces. Rank affects
**conflict resolution** (§6.1) and **review priority**, never automatic
verification — verification stays human at every rank.

```
1. Manufacturer product page or official datasheet
2. Manufacturer store, press room or documentation
3. Authorized distributor or partner feed
4. Reputable specialist aggregator
5. Marketplace listing
6. News / editorial source
7. Community or social post          (lead only — never a structured claim)
```

An `AGGREGATOR`-only claim may enter the discovery database and stay useful and
visible to an operator while it waits — it is never silently discarded — but it
remains, always: `claim_status = NOT_VERIFIED`, `source_class = AGGREGATOR` (or
whichever class it came from, preserved on the claim, never collapsed into an
unattributed record), and it contributes **zero** canonical rows on its own.

## 5. Source eligibility review

The existing `discovery_source` row already carries the *effective* decision
(`tos_status`, `robots_status`, `eligibility_reviewed_by/at`, `is_enabled`).
This contract adds an **append-only review record** so the decision can be
audited and re-reviewed rather than silently overwritten.

**Procedure (human, recorded):**

1. Fetch and read `https://<host>/robots.txt` **manually** and record it.
2. Read the site's terms of use / legal page and record the exact passage that
   governs automated access.
3. Decide per axis: `robots_decision ∈ {ALLOWED, DISALLOWED, NOT_APPLICABLE}`
   for the specific path prefixes to be fetched; `tos_decision ∈ {ALLOWED,
   RESTRICTED, PROHIBITED, UNKNOWN}`.
4. Record the reviewer, the timestamp, the exact URLs, bounded excerpts and
   content hashes of both documents, the path prefixes covered, and an expiry.
5. Enable the source **explicitly and separately**. Reviewing is not enabling.

**Refusal semantics:** anything other than an affirmative `ALLOWED` terms
decision, with robots `ALLOWED`/`NOT_APPLICABLE`, an attributed and unexpired
review, and an explicit enable, means **the source is not fetched**. Silence is
not permission (DATA-D1.9).

**Applies identically to every source class.** An aggregator, a marketplace or
an editorial outlet is reviewed by the exact same procedure as a manufacturer —
there is no lighter-touch path for "just a directory". The first eligibility
assessment (§ eligibility reports, 2026-07-29) found the opposite of what
intuition might suggest: official manufacturer sites had the *more* restrictive
terms of the sources checked. Source class predicts nothing about eligibility;
only reading the actual terms does.

**Preferred acquisition mechanisms.** Before assuming a source must be crawled
at all, check for a mechanism that makes the question moot — this applies with
particular force to aggregators, who are often easier to work with than
manufacturers precisely because indexing is closer to their business model:

```
a public API                          preferred over crawling entirely
an RSS / Atom feed
a downloadable CSV / JSON export
a licensed dataset
a partner feed
explicit, written indexing permission
```

Any of these, once its own terms are reviewed under this same procedure,
**outranks** building or running an adapter against rendered pages — less
fragile, lower load on the source, and usually a clearer permission story.

## 6. Commercial state: the mapping that keeps the axes apart

The owner's proposed working vocabulary is a good description of *what an
operator wants to see*. It cannot be stored as a single enum, because several of
its values live on different canonical axes that the platform deliberately keeps
separate (`R15`: "maturity ≠ obtainability ≠ evidence" is an automated release
invariant asserting no `available` boolean exists anywhere).

Proposed decomposition — this is the contract's answer to "what does *on market*
mean":

| Operator-facing state | maturity (`commercial_status`) | obtainability (`availability_status` + `transaction_type`) | price (`price_type`) |
|---|---|---|---|
| `AVAILABLE_NOW` | `COMMERCIAL` | `AVAILABLE` + `PURCHASE` | any |
| `QUOTE_ONLY` | unchanged | `ON_REQUEST` | `QUOTE_ONLY` |
| `PREORDER` | `COMMERCIAL` / `LIMITED_COMMERCIAL` | `PREORDER` | any |
| `PILOT_OR_LIMITED_DEPLOYMENT` | `PILOT` / `LIMITED_COMMERCIAL` | `LIMITED` + `PILOT` | any |
| `RAAS_OR_LEASE` | `RAAS_DEPLOYMENT` | `AVAILABLE`/`ON_REQUEST` + `RAAS`/`LEASE` | any |
| `DEVELOPER_ACCESS` | `EARLY_ACCESS` | `LIMITED` + `DEVELOPER` | any |
| `ANNOUNCED` | `ANNOUNCED` | *no availability signal* (**not** `NOT_AVAILABLE`) | none |
| `RESEARCH_ONLY` | `DEVELOPMENT` **only with explicit evidence**, else no signal | `UNKNOWN` — never a signal | none |
| `DISCONTINUED` | `DISCONTINUED` | `DISCONTINUED` | none |
| `UNKNOWN` | no signal recorded | no signal recorded | no signal recorded |

Two consequences worth stating plainly:

- **`ANNOUNCED` must not imply `NOT_AVAILABLE`.** Absence of an obtainability
  signal is UNKNOWN. Writing `NOT_AVAILABLE` because a robot was merely
  announced would be the crawler inventing a commercial fact.
- **`RESEARCH_ONLY` stays a discovery classification** *(owner decision D-1,
  settled)*. It is **not** added to any canonical enum. Its mapping is
  deliberately conservative:

  ```
  maturity_status   DEVELOPMENT   only when the page EXPLICITLY supports it
                                  (otherwise: no maturity signal at all)
  availability      UNKNOWN       never a signal, and NEVER NOT_AVAILABLE
  transaction_type  UNKNOWN
  buyer_type / access restriction   written ONLY when explicitly stated
  ```

  "Research only" on a manufacturer page is usually marketing register, not a
  commercial statement. Treating it as evidence of unobtainability would be the
  crawler inventing a fact — the exact failure this contract exists to prevent.

Each extracted signal is one row with its own evidence, region and buyer type. A
robot may legitimately be `AVAILABLE` for `PURCHASE` in one region and
`ON_REQUEST` elsewhere; a single label cannot express that, which is precisely
why the axes are separate.

### 6.1 Conflicting evidence *(added 2026-07-29 — multi-source amendment)*

Multi-source acquisition means the same field can now arrive with different
values from different sources on the same run. **The system must not average,
and must not simply take the majority value.** Concretely:

```
Manufacturer reports    payload = 30 kg
Aggregator A reports    payload = 35 kg
Aggregator B reports    payload = 30 kg

Result:
  30 kg   → the preferred candidate value (rank 1 in §4.2, and corroborated)
  35 kg   → PRESERVED as a conflicting claim, not deleted, not overwritten
  —       → flagged for human review
```

Both rows survive (DATA-D1.8, unchanged). **Cross-source agreement raises
review priority — it never raises confidence, and it never verifies anything**
(DATA-D1 §16, LIVE.8). Two aggregators agreeing with each other is worth a
human's attention sooner; it is not evidence of the fact being true. The
preferred value is read off the evidence hierarchy (§4.2) by the *human*
reviewer — the system surfaces the ranking, it does not resolve the conflict for
them.

### 6.2 Pricing and availability need special handling

A price or availability signal from an aggregator is often genuinely useful for
*discovery* and routinely wrong for *fact*. It may be outdated, regional,
distributor-specific, exclusive or inclusive of shipping and tax inconsistently
with our convention, a deposit rather than the full price, an analyst estimate
presented as fact, a rental or monthly RaaS figure mislabeled as a purchase
price, or simply the launch price of a since-discontinued configuration. None of
that makes the signal worthless — it makes it a **lead requiring the full
`candidate_commercial_signal` shape** (§9) before it means anything:
`price_type`, `price_amount`, `currency`, `region_code`, `buyer_type`,
`transaction_type`, its evidence excerpt, retrieval date and `claim_status`.

**An aggregator stating "available" must never automatically become canonical
`AVAILABLE`.** It becomes a `candidate_commercial_signal` row with
`claim_status = NOT_VERIFIED` and `source_class = AGGREGATOR`, exactly like any
other unverified claim — §6.1's conflict handling and §4.1's "never automatic"
rule apply to it without exception.

## 7. Crawl run model

```
crawl_run
  id · source_id · adapter_key · adapter_version
  trigger            MANUAL (v0.1: the only legal value)
  operator           the named human who started it
  started_at · finished_at
  status             RUNNING | COMPLETED | FAILED | HALTED_BY_POLICY | CANCELLED
  resume_of_run_id   the run this one continues (nullable)
  run_manifest       JSONB: the planned URL set, limits, rate policy, UA string,
                     robots snapshot hash, fixture mode
  counters           JSONB: the §18 report figures
```

`HALTED_BY_POLICY` is a first-class outcome: robots changed, terms review
expired mid-run, or a source started returning access denials. It is not an
error to be retried.

**Resumability:** a run records per-URL outcome (§8). Resuming skips URLs already
fetched successfully in the parent run, honours the same manifest, and produces a
new run row linked by `resume_of_run_id`. Resume never re-fetches to "be safe" —
re-fetching is a decision, not a default.

## 8. Fetched-page evidence model

```
fetched_page
  id · crawl_run_id · source_id
  url · canonical_url
  http_status · content_length · content_type
  content_hash        normalized-body hash (dedupe + change detection)
  etag · last_modified conditional-request validators
  retrieved_at
  outcome             FETCHED | NOT_MODIFIED | FROM_CACHE | BLOCKED_BY_ROBOTS
                      | BLOCKED_BY_SOURCE | ERROR | SKIPPED_UNCHANGED
  robots_decision_at_fetch   what robots said at the moment of the request
  error_class         (nullable) transport/status/parse
```

**No body column.** Bodies live in the ephemeral local cache (LIVE.10). A page
whose `content_hash` is unchanged is not re-extracted unless extraction logic
changed — which is why `adapter_version` is on the run.

## 9. Extraction result and claim provenance

```
extraction_result
  id · crawl_run_id · fetched_page_id · candidate_id (nullable)
  extractor_key · extractor_version
  entity_type · status  (EXTRACTED | NOTHING_FOUND | AMBIGUOUS | ERROR)
  notes
```

Because a claim may need **several** passages (D-7), excerpts are their own rows
rather than a column — one claim or signal, many excerpts:

```
discovery_evidence_excerpt
  id · subject_type (CLAIM | COMMERCIAL_SIGNAL | IMAGE_REF) · subject_id
  crawl_run_id · fetched_page_id
  excerpt_text     <= 1000 Unicode characters, enforced by a CHECK
  page_url · retrieved_at · page_hash
  locator          selector / XPath / JSON pointer / "offset:START-END"
  ordinal          stable ordering of the passages behind one claim
```

Existing `candidate_claim` gains (additive, nullable): `extraction_method`,
`extraction_confidence`, `extractor_key`, `extractor_version`, `crawl_run_id`,
`fetched_page_id`. Its evidence lives in the table above.

### 9.1 Claim-level provenance is per claim, and never blended

Multi-source acquisition makes this load-bearing. **Every claim carries its own
source identity**, and no operation anywhere in the system merges claims from
different sources into one unattributed record.

The anchor already exists: `candidate_claim.discovery_source_id` (shipped in
migration `0003`) is a FK to `discovery_source`, which carries
`source_class` — so every claim resolves to exactly one classified source, and
`candidate_commercial_signal` (§9) and `discovery_evidence_excerpt` (§9) carry
the same FK for the same reason. The class is therefore never *stored on* the
claim redundantly; it is *always derivable from* the claim, which is what makes
the following invariants assertable rather than aspirational:

- **One claim, one source.** A claim row is never written from two sources'
  evidence combined. Two sources asserting the same value produce **two rows**
  (§6.1), which is what allows corroboration to be *counted* without being
  *merged*.
- **No unattributed claim.** A claim without a resolvable
  `discovery_source_id` — and therefore without a `source_class` — is rejected
  at write time. There is no "unknown source" fallback that would let
  provenance be dropped for convenience.
- **No re-classification by promotion.** Promoting a candidate does not
  retroactively upgrade the class of the claims behind it. An aggregator claim
  that a human independently verified against a manufacturer page results in a
  *new* manufacturer-class claim plus the original aggregator claim, both
  retained — never one row whose class was quietly rewritten.
- **Display and API surfaces carry the class or carry nothing.** Any operator
  surface that shows a claim shows which class it came from (§17). Stripping
  provenance for presentation is how "an aggregator said so" silently becomes
  "HumanoidOnline says so".

New `candidate_commercial_signal` — because a commercial signal is not a
scalar field/value pair and must not be forced into one:

```
candidate_commercial_signal
  id · candidate_id · crawl_run_id · fetched_page_id
  axis               MATURITY | OBTAINABILITY | PRICE
  maturity_value     commercial_status  (nullable)
  availability_value availability_status (nullable)
  transaction_type · region_code · buyer_type
  price_type · price_amount · price_currency · billing_period  (all nullable)
  extractor_key · extractor_version · extraction_method · extraction_confidence
  claim_status       NOT_VERIFIED (default; only a human changes it)
                     evidence: one or more discovery_evidence_excerpt rows
```

Conflicting signals from different pages are **preserved as separate rows**
(DATA-D1.8). Nothing averages, and nothing overwrites.

## 10. Image references

`candidate_image_ref` gains: `page_url` (where it was seen), `retrieved_at`,
`declared_credit` (the credit line as printed), `alt_text`, `crawl_run_id`,
`fetched_page_id`, and — for the multi-source amendment —
**`retrieval_source_class`** (the `discovery_source_class`, §4, of the page the
image was actually seen on) and **`attribution_claimed`** (the credit text
exactly as printed, kept separate from any verified attribution). It keeps
`media_status = 'CANDIDATE'`.

**Retrieval provenance, not original provenance.** An image found on an
aggregator is `retrieval_source_class = AGGREGATOR`, in accordance with the
existing Figure 02 precedent (an image credited to an OEM but retrieved from an
editorial page is recorded as `EDITORIAL` retrieval, never `MANUFACTURER`) —
even when the aggregator's own credit line names the manufacturer. Credit is a
*claim*, recorded in `attribution_claimed`; it is not itself proof. Until a
human MEDIA-01 review establishes otherwise, an aggregator-retrieved image
carries:

```
retrieval_source_class = AGGREGATOR (or MARKETPLACE / EDITORIAL, as retrieved)
attribution_claimed     = the credit line as printed, unverified
is_official              UNKNOWN  ← MEDIA-01 field, never set by the extractor
rights_status            UNKNOWN  ← MEDIA-01 field, never set by the extractor
usage_basis               NONE    ← pending MEDIA-01 review, never inferred
```

The extractor sets **no** MEDIA-01 field, from any source class. Promotion of an
image to `robot_image` remains a human MEDIA-01 evaluation: exact-model
identity, rights status, usage basis, attribution. For robots already in the
catalogue with a verified image, acquisition may propose *additional*
references from any eligible source; it may never replace or generate one
(MEDIA-01 frozen law) — and an image originally from a manufacturer does not
retroactively become manufacturer-provenance because it was *retrieved* via an
aggregator. Retrieval path is the provenance that is recorded, full stop.

## 11. Identity resolution and deduplication

Reuses the existing deterministic resolver (`services/discovery/identity.py`)
and DATA-D1.6/1.7: identity resolves before facts attach, and deduplication is
evidence-aware. Additions for live acquisition:

- **Source-stable external ref.** For an official source the natural key is the
  canonical product URL path, normalized (scheme/host lowercased, tracking
  params stripped, trailing slash removed). Re-crawling a page must reach the
  *same* candidate, not create a second one — `(source_id, external_ref)` is
  already unique.
- **Deterministic, reviewable matching.** Normalized manufacturer + model
  comparison only. No fuzzy scoring, no embeddings, no LLM. An ambiguous match
  is `AMBIGUOUS` for a human, never a guess.
- **Variant discipline.** "G1 EDU" vs "G1" is a variant question a human
  decides; the extractor records both strings verbatim and does not merge them.
- **Aliases are proposals, not merges.** An aggregator naming a robot
  differently from our canonical name (a regional name, an older model name, a
  colloquial name) is recorded as a *proposed alias* on the candidate, never
  used to silently fold two candidates into one. A human confirms an alias
  exactly as they confirm any other identity decision (DATA-D1.6).

### 11.1 Promotion still requires an official trace when one exists

Multi-source acquisition makes this explicit rather than incidental: DATA-D1's
promotion gate P2 already requires a **confirmed authoritative trace**
(`record_trace`, never inferred from a lead — H2) before promotion. This
contract adds nothing to that mechanism; it states the consequence plainly so
an aggregator-rich candidate is never mistaken for an official-source one.

**When an official-class source exists for an entity** — `MANUFACTURER`,
`AUTHORIZED_DISTRIBUTOR` or `OFFICIAL_STORE` — **the recorded trace must be to
one of those classes.** A candidate that has accumulated ten corroborating
aggregator claims and zero official ones is not closer to promotable than a
candidate with none; it is exactly as far, because P2 is not a vote count. Where
no official source exists at all (a very new company, a market with only
aggregator coverage), a human may still trace to the best available source —
that judgment call belongs to the human reviewer at promotion time, not to the
acquisition layer.

## 12. Adapter interface

Extends the existing `SourceAdapter` protocol rather than replacing it, so
`FixtureAdapter` keeps working and stays the test path.

```python
class LiveSourceAdapter(Protocol):
    key: str                    # stable identifier, e.g. "unitree-official"
    version: str                # bump ⇒ re-extraction is meaningful
    source_class: str           # any §4 class — MANUFACTURER, AUTHORIZED_DISTRIBUTOR,
                                 # OFFICIAL_STORE, AGGREGATOR, MARKETPLACE, EDITORIAL —
                                 # the class does not change the adapter's obligations;
                                 # §4.1's "never automatic" rule is enforced downstream
                                 # of extract(), by claim_status defaults, not by the
                                 # adapter self-reporting trust
    allowed_path_prefixes: tuple[str, ...]   # exactly what the review covered

    def plan(self, session, source) -> list[PlannedFetch]:
        """URLs this run intends to fetch. Bounded, deterministic, no requests."""

    def extract(self, page: FetchedPage, body: bytes) -> ExtractionOutput:
        """Pure function of (page, body). No network, no database, no clock."""
```

Two properties make this reviewable: `plan()` issues **no requests** (so a dry
run can be inspected before anything is fetched), and `extract()` is **pure** (so
fixture replay is exact and an extraction change shows up as a diff).

The fetcher — rate limiting, robots evaluation, conditional requests, retries,
caching, recording — is **shared infrastructure**, not per-adapter code. Adapters
cannot opt out of etiquette because they never touch the network.

## 13. Etiquette (implements DATA-D1 §14)

- **Identifiable user agent** *(owner decision D-4, settled)* — this exact
  string, recorded in every run manifest, never a browser impersonation string:

  ```
  HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)
  ```

  **`/crawler-policy` must resolve, and must explain purpose, contact, rate
  limits and opt-out, before the first product-page fetch.** A contact URL that
  404s is worse than none: it advertises accountability that does not exist. The
  page is a prerequisite of Slice B (§21), not a follow-up.
- **Conservative, per-host rate limiting**: proposed ≥ 2 s between requests to a
  host, concurrency 1 per host, and a per-run page cap (proposed 200).
- **Conditional requests** (`If-None-Match` / `If-Modified-Since`) and local
  caching; unchanged pages are not re-downloaded.
- **Bounded retries**: at most 2 retries, exponential backoff, only for
  transient transport errors and 5xx. Never retry a 4xx. Never retry a block.
- **Back off and stop** on 429/403 patterns; record and halt the source.
- **Per-source and global kill switch** that takes effect between requests.

## 14. CLI (operator surface for v0.1)

```
# eligibility (human, records evidence; does NOT enable)
python -m app.cli.discovery source review <key> \
    --robots-url … --tos-url … --robots-decision … --tos-decision … \
    --path-prefix … --reviewed-by "…" --expires-in-days 180 --evidence-file …

python -m app.cli.discovery source enable  <key> --by "…"    # separate act
python -m app.cli.discovery source disable <key> --by "…" --reason "…"

# planning and crawling (manual, local)
python -m app.cli.discovery plan  <key>                    # prints the URL set, fetches nothing
python -m app.cli.discovery crawl <key> --operator "…" [--limit N] [--dry-run]
python -m app.cli.discovery crawl <key> --resume <run-id> --operator "…"
python -m app.cli.discovery crawl <key> --fixtures <dir>   # replay, no network

# manual bootstrap (§2.1) — NO network call is made by this command; the human
# has already read the source, and is entering what they found
python -m app.cli.discovery record-manual <candidate-key-or-"new"> \
    --source-url … | --source-kind MANUFACTURER_SUPPLIED --evidence-file … \
    --entered-by "…" --retrieved-at … \
    --claim field=<key> value=<v> --excerpt "<= 1000 chars, exact>" \
    --image-ref <url> --credited-to "…"

# review
python -m app.cli.discovery report <run-id>                # the §18 report
python -m app.cli.discovery candidates --status READY_FOR_PROMOTION
python -m app.cli.promote_candidate <candidate-id> --show | --approve …
```

`--dry-run` performs the robots evaluation and prints exactly what *would* be
requested, without issuing a request. `record-manual` never touches the
network at all — it is the `MANUAL_BOOTSTRAP` write path, and it is not part of
Slice A (schema and models only); it lands with the CLI in a later slice.

## 15. Fixtures and determinism

Every live run may record its fetched bodies into a fixture directory. Replaying
that directory must produce **byte-identical extraction output**. Consequences:

- extraction changes are reviewed as diffs against recorded real pages;
- the test suite runs offline and deterministically (CI never touches the
  network — an acceptance gate asserts this);
- a parsing regression is reproducible without re-crawling anyone.

## 16. Proposed schema additions (migration `0004`)

Additive only; no canonical table is modified. Consistent with AGENTS.md rule 2
(DDL is canonical, models mirror it) and DATA-D1 §5 structural isolation — the
new tables reference discovery and canonical rows, and **no canonical table
references back**.

```
New enums
  crawl_run_status      RUNNING | COMPLETED | FAILED | HALTED_BY_POLICY | CANCELLED
  crawl_trigger         MANUAL                      (v0.1 has exactly one)
  fetch_outcome         FETCHED | NOT_MODIFIED | FROM_CACHE | BLOCKED_BY_ROBOTS
                        | BLOCKED_BY_SOURCE | ERROR | SKIPPED_UNCHANGED
  extraction_method     SELECTOR | JSONLD | MICRODATA | PATTERN | MANUAL
  extraction_confidence LOW | MEDIUM | HIGH
  signal_axis           MATURITY | OBTAINABILITY | PRICE
  eligibility_decision  ALLOWED | RESTRICTED | PROHIBITED | UNKNOWN

New tables
  source_eligibility_review     append-only; the §5 record (terms + robots)
  crawl_run                     §7
  fetched_page                  §8   (no body column)
  extraction_result             §9
  candidate_commercial_signal   §9
  discovery_evidence_excerpt    §9   (<= 1000 chars, CHECK-enforced)

Altered (additive, nullable) — existing behaviour unchanged
  candidate_claim      + extractor_key, extractor_version, extraction_method,
                         extraction_confidence, crawl_run_id, fetched_page_id
  candidate_image_ref  + page_url, retrieved_at, declared_credit, alt_text,
                         crawl_run_id, fetched_page_id, retrieval_source_class,
                         attribution_claimed
  discovery_source     + allowed_path_prefixes, tos_reviewed_at,
                         tos_expires_at (90d), tos_page_hash,
                         last_robots_hash, last_robots_checked_at (24h max),
                         last_crawled_at
  discovery_source_class (existing enum, migration 0003) gains ADDITIVE values
                         AGGREGATOR, AUTHORIZED_DISTRIBUTOR, OFFICIAL_STORE,
                         COMMUNITY — existing values (COMPETITOR_DIRECTORY,
                         MARKETPLACE, EDITORIAL, SEARCH_RESULT, DISTRIBUTOR,
                         MANUFACTURER, PRESS_RELEASE, OFFICIAL_DOCUMENT,
                         OFFICIAL_VIDEO, OTHER) are RETAINED UNCHANGED — no
                         rename, no removal, no re-mapping of existing rows.
                         This is the §4 multi-source vocabulary layered onto
                         the enum DATA-D1 already ships; it is additive to a
                         NONCANONICAL discovery-layer type, not a canonical
                         schema change.
```

### 16.1 Future-ready commercial routing fields — DECLARED, NOT IN `0004`

These express §0.1 in the schema: the platform routes buyers to official
channels and is not the merchant of record. They are **canonical** fields, so
they are **not** part of migration `0004` and **not** authorized by this
contract — each needs its own ratification alongside the commercial workstream
(Rent → Buy → Lease/RaaS). They are declared here so that acquisition is built
knowing where its output eventually lands, and so nobody invents a parallel
vocabulary later.

| Field | Lives on | Meaning | Default / discipline |
|---|---|---|---|
| `official_purchase_url` | robot / variant / availability offer | the manufacturer's own buy page | UNKNOWN when absent — never guessed, never a search link |
| `official_quote_url` | robot / variant / availability offer | the manufacturer's own quote or contact-sales page | UNKNOWN when absent |
| `lead_route_type` | commercial lead | how a qualified buyer is routed: `MANUFACTURER_DIRECT` · `AUTHORIZED_SELLER` · `PLATFORM_INTRODUCTION` · `UNROUTED` | `UNROUTED` until a route is evidenced |
| `lead_recipient` | commercial lead | the manufacturer or authorized seller the lead was routed to | never HumanoidOnline |
| `manufacturer_partner_status` | manufacturer | `NONE` · `CONTACTED` · `PERMISSION_GRANTED` · `PARTNER` · `DECLINED` | `NONE`. **Also the eligibility artefact** for §5 when it reaches `PERMISSION_GRANTED` |
| `referral_tracking_code` | manufacturer / lead | the code a partner asked us to attach, if any | NULL — never fabricated, never appended without agreement |
| `commission_model` | manufacturer partnership | `NONE` · `FLAT_FEE` · `PER_LEAD` · `REVENUE_SHARE` · `UNDISCLOSED` | `NONE`. **Disclosed on the surface** where it could bias ranking |
| `merchant_of_record` | availability / pricing offer | who the buyer actually contracts with | `MANUFACTURER` or `AUTHORIZED_SELLER`. **`PLATFORM` is not a legal value in Phase 1–2** — a CHECK constraint, not a convention |
| `transaction_completed_off_platform` | availability offer / lead | states plainly where the transaction happens | `true` in Phase 1–2 |

**What acquisition may do with them:** propose `official_purchase_url` and
`official_quote_url` as ordinary evidence-bound candidate claims — they are
facts on a manufacturer page like any other, and they carry the same excerpt,
timestamp and confidence. **Everything else on that list is a commercial
relationship, not an observable fact**, and a crawler may never write it.
`manufacturer_partner_status` in particular is set by a human recording an
agreement; if a parser could set it, the eligibility gate would be forgeable.

Two invariants worth testing the moment those fields exist: `merchant_of_record`
never takes the value `PLATFORM`, and no ranking, match score or ordering reads
`commission_model` or `manufacturer_partner_status`. The catalogue's neutrality
is the product; a partnership must never be able to buy a better position in it.

## 17. Operator review path

v0.1 deliberately ships **no new UI**. Review happens through:

- the existing SQLAdmin views (`discovery-candidate`, `candidate-claim`,
  `candidate-image-ref`, `discovery-source`, `promotion-audit`), reachable only
  through the loopback admin listener (WS8.7 DEP P4), plus the new tables as
  read-only views;
- the CLI above, including `promote_candidate --show`, which prints the
  structured proposal and every failing gate.

The Operations Workbench is deferred **on purpose**: the right design for a
review queue is not knowable before real acquired data shows which decisions
reviewers actually make, and how often they disagree with the extractor.

## 18. The run report

Emitted at the end of every run and reproducible from the database afterwards
(`discovery report <run-id>`):

```
RUN <id>   source=<key>   adapter=<key>@<version>   operator=<name>
started=<utc>  finished=<utc>  status=<…>  resumed_from=<run-id|->
user-agent=<exact string>   rate=<per-host policy>   robots=<hash, checked at start>

Sources attempted                    n
Pages fetched                        n
Pages unchanged from cache           n   (NOT_MODIFIED + FROM_CACHE + SKIPPED_UNCHANGED)
Robots discovered                    n
Existing robots matched              n   (MATCHED_EXISTING)
Possible duplicates                  n   (AMBIGUOUS — needs a human)
New robot candidates                 n   (NEW_ENTITY)
Changed specifications               n   (claim differs from the last observation)
Commercial-status changes            n   (by axis: maturity / obtainability / price)
Price or quote signals               n
Real image references found          n
Claims requiring human verification  n   (every claim; NOT_VERIFIED is the only state a crawl can produce)
Rejected or unsupported claims        n   (extracted but dropped: no evidence text, failed validation)
Fetch and parsing errors             n   (by class, with the first N URLs)
Blocked by robots / by source        n   ← policy outcomes, listed explicitly
Canonical rows written               0   ← must always be 0 (asserted, not hoped)
```

The last line is not decoration. It is the invariant this whole contract
protects, printed on every run.

## 19. Acceptance gates (v0.1)

| Gate | Assertion |
|---|---|
| **A** | No request is issued for a source without an approved, unexpired, enabled eligibility review — proven with a fake transport that records every attempt. |
| **B** | Robots is re-evaluated at run start and per URL, never answered from a cache older than 24 h; a disallow halts the source, records `HALTED_BY_POLICY` and disables it pending re-review. A terms review older than 90 days, or whose page hash changed, blocks the run. |
| **C** | No acquisition module can write a canonical table (import-level assertion + a run that ends with `Canonical rows written = 0`). |
| **D** | The user agent is exactly `HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)`; no browser impersonation string appears anywhere in the codebase. |
| **E** | Per-host rate limit and per-run page cap are honoured under a simulated fast source. |
| **F** | Conditional requests are issued when validators exist; unchanged pages are not re-extracted. |
| **G** | Retries are bounded, never applied to 4xx or to blocks, and backoff increases. |
| **H** | A killed run resumes without re-fetching successfully fetched URLs, and links to its parent. |
| **I** | Fixture replay of a recorded run produces byte-identical extraction output. |
| **J** | Every persisted claim and signal has **at least one** evidence excerpt carrying page URL, `retrieved_at`, page hash and locator, plus a confidence; one without is rejected at write time. No excerpt exceeds 1000 Unicode characters (CHECK-enforced, tested with a multi-byte string so the limit is characters, not bytes). |
| **K** | No merged status label exists: a maturity signal never sets availability, and `ANNOUNCED` never produces `NOT_AVAILABLE`. |
| **L** | `UNKNOWN` is preserved end to end; `QUOTE_ONLY` never degrades to `UNKNOWN`. |
| **M** | No image binary is stored anywhere; image rows carry retrieval provenance and no MEDIA-01 verdict. |
| **N** | No page body column exists in any table; the on-disk cache is outside the database and outside the build context. |
| **O** | The public API and all machine surfaces expose nothing from the new tables (extends DATA-D1 Gate I / AGENT-01.7). |
| **P** | The test suite makes no network request (asserted by a transport guard active in CI). |
| **Q** | The cache is content-addressed under `var/discovery/cache/`, git-ignored, excluded from the Docker build context, and enforces 90-day / 30-day retention — while manifests, hashes, excerpts and provenance survive cache expiry (proven by expiring a cache entry and re-reading the claim's evidence). |
| **R** | `/crawler-policy` resolves and is non-empty before the first product-page fetch; slice B cannot run without it. |
| **S** | *(multi-source, §4.1)* No source class other than `MANUFACTURER` / `AUTHORIZED_DISTRIBUTOR` / `OFFICIAL_STORE` can ever produce a row with `claim_status = VERIFIED` or a canonical write — exercised specifically against `AGGREGATOR`, `MARKETPLACE` and `EDITORIAL` fixtures, not just asserted in the abstract. |
| **T** | *(multi-source, §6.1)* Conflicting claims from different sources are preserved as separate rows, never averaged and never silently overwritten by a later or higher-ranked one; the higher-ranked value is surfaced for a human, not substituted automatically. |
| **U** | *(multi-source, §10)* An aggregator- or marketplace-retrieved image is recorded with `retrieval_source_class` matching where it was actually seen, never `MANUFACTURER`, even when its claimed credit line names one. |
| **V** | *(`MANUAL_BOOTSTRAP`, §2.1)* A manually recorded claim carries the same evidence shape as an automated one — excerpt, URL or document identifier, retrieved-at, `extraction_method = MANUAL` — and is rejected at write time if any is missing; it is discovery-layer-only, identically to Gate C. |
| **W** | *(promotion trace, §11.1)* When an official-class (`MANUFACTURER` / `AUTHORIZED_DISTRIBUTOR` / `OFFICIAL_STORE`) source exists for an entity, promotion is refused unless the recorded trace (DATA-D1 P2) is to one of those classes — an aggregator-only trace does not satisfy P2 for that entity. |
| **X** | *(claim provenance, §9.1)* Every claim, commercial signal and evidence excerpt resolves to exactly one classified source; a write without a resolvable `discovery_source_id` is rejected. Two sources asserting the same value produce two rows, never one merged row, and promotion never rewrites the class of an existing claim. |

## 20. Non-goals (v0.1)

No scheduler, cron, queue or worker · no crawler VPS or any production-hosted
fetching · no headless browser or JavaScript execution · **no automated fetch of
any source — official, aggregator, marketplace or editorial — without its own
passed eligibility review** (multi-source acquisition is *permitted in
principle*, §4; it is not *pre-approved* for any specific host, §5) · no
login-gated content · no canonical writes from any source class · no
auto-verification or auto-promotion from any source class · no image binaries ·
no Operations Workbench · no LLM extraction, scoring or matching · no
cross-source averaging, ever (§6.1) · no PDF/document parsing via automated
fetch (deferred: specification sheets are attractive and worth a separate
slice — `MANUAL_BOOTSTRAP` may still record facts read from a
manufacturer-supplied PDF, §2.1) · no more than three `AUTOMATED_LIVE` adapters
in v0.1, of any source class.

## 21. Build sequence (on ratification)

**Execution model (owner-directed).** This workstream runs **in parallel with
WS8.8 / WS8.9**, on isolated branches or worktrees. It does **not** enter or
alter the WS8 release train — WS8-L1 forbids new product capability inside a
release-hardening slice, and nothing here may appear in the MVP v0.1 release
candidate.

**Status (2026-07-29):** step 0 is **complete** — the first read-only
eligibility assessment ran across the three permission/truth-set targets (§23)
plus a wider market scan; see the eligibility reports. Step 1's outcome so far:
**zero** sources hold an affirmative eligibility decision. Step 2 (Slice A) is
authorized to proceed regardless, per the owner-directed note below.

0. **Eligibility assessment (read-only) — DONE for the initial pass, ongoing.**
   For each candidate source, fetch **only** `robots.txt`, terms of use, legal /
   acceptable-use pages, and crawler-policy documents linked from those pages —
   **regardless of source class**: the same read-only scope applies to an
   aggregator under review as to a manufacturer. Record exact URLs, retrieval
   timestamps, HTTP status, hashes, relevant excerpts and a provisional
   `ALLOWED / DISALLOWED / UNCLEAR` recommendation. **This authorization does
   not extend to product pages, adapters, network ingestion, database writes,
   or declaring any source eligible** — eligibility remains an owner decision on
   the evidence, source by source.
1. **Eligibility approval.** The owner accepts or rejects each assessment.
   Nothing below may start `AUTOMATED_LIVE` acquisition for a source without an
   affirmative decision. `MANUAL_BOOTSTRAP` (§2.1) is not gated by this step.
2. **Slice A — infrastructure, no adapters** *(owner-directed: proceed
   immediately; it is source-agnostic, so no eligibility outcome blocks it).*
   Schema `0004`, fetcher with
   robots/rate/cache/retry/kill switch, crawl-run + report, CLI, gates A–H,
   N, P. Provable end to end against a **local fake server**, not the internet.
3. **Slice B — first adapter(s).** May target **any** eligible source that has
   cleared §5 by the time this slice starts — an official source, a high-value
   aggregator, or both. §11.1's trace requirement is the safeguard, not source
   restriction: whenever an official-class source exists for an entity,
   promotion still requires a trace to it, so an aggregator-first adapter cannot
   promote around a manufacturer that simply hasn't approved us yet. Gates
   I–M, O, S–V. First real run is `--dry-run`, reviewed, then a capped live run.
4. **Slice C — the remaining adapters**, chosen to *differ* commercially and,
   where possible, by source class (see §22–23), generalizing only what real
   variation demands. Gate W exercised end to end once an aggregator and an
   official source coexist for the same entity.
5. **Review.** Real acquired data drives the decision on the Operations
   Workbench, cadence, and whether P3/P5/P7 promotion gates need to change.

Each slice is a separate PR under the existing ritual (branch from main →
in-scope build → exact-head CI green → Draft PR → owner review).

## 22. Owner decisions — SETTLED (2026-07-29)

All seven were decided by the product owner before this contract was opened for
review, and are folded into the sections named below. They are settled inputs to
ratification, not open questions.

| # | Decision | Settled as | In |
|---|---|---|---|
| **D-1** | `RESEARCH_ONLY` | Discovery classification only, never a canonical enum value. `maturity = DEVELOPMENT` **only with explicit evidence**; availability and transaction stay `UNKNOWN`; buyer/access restriction written only when explicitly stated. **Never infer `NOT_AVAILABLE`.** | §6 |
| **D-2** | Eligibility validity | Terms: **90 days**, invalidated immediately on material URL/content-hash change. `robots.txt`: **evaluated every run**, ≤ 24 h cache; a new restrictive rule disables the source until re-reviewed. | §5, LIVE.2 |
| **D-3** | Cache | `var/discovery/cache/`, git-ignored, **SHA-256 content-addressed**. Successful bodies **90 d**, failed/blocked **30 d**; manifests, page hashes, evidence excerpts and provenance **indefinite**. | LIVE.10 |
| **D-4** | User agent | `HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)` — the policy page must resolve and explain purpose, contact, rate limits and opt-out **before the first product-page fetch**. | §13 |
| **D-5** | Permission and truth-set targets | **Unitree Robotics · Agility Robotics · Engineered Arts** — a priority list for the eligibility/permission conversation, *not* an enabled adapter sequence. **The first automated adapters are the first three official sources to receive an affirmative, attributed, unexpired eligibility approval** — which three, and in what order, is decided by who says yes first, not by this list alone. | §23 |
| **D-6** | Extraction confidence | **Never auto-verifies.** May prioritise review or reject its own low-confidence output; may never set `VERIFIED`, alter canonical confidence, or bypass human promotion. | LIVE.8 |
| **D-7** | Evidence excerpts | **≤ 1000 Unicode characters each**, multiple excerpts per claim permitted; each carries page URL, retrieval time, page hash and locator/offsets. | LIVE.6, §9 |

## 23. Permission and truth-set targets (D-5)

**This section names who we ask first, not what we may crawl first.** No source
below is eligible until its own review returns an affirmative terms decision and
a non-disallowing robots policy, recorded and attributed (§5) — and, as of the
first assessment (2026-07-29), **none of the three has cleared that bar** (two
expressly prohibit automated access in their terms; the third could not be
fully read). **The first automated adapters are whichever official sources
actually say yes first** — a priority list is not a guarantee of order, only of
who gets asked, and in what sequence, while permission conversations run in
parallel with Slice A/B engineering.

| # | Target | Why prioritized for outreach | What it would exercise, once eligible |
|---|---|---|---|
| **1** | **Unitree Robotics** — official site + official store | Already canonical in our catalogue (G1 at `$13,500 PUBLIC`, H1 `QUOTE_ONLY`), so identity matching has something real to match, and extraction can be checked against a fact we already verified by hand | `PUBLIC` price · `PURCHASE` availability · spec extraction · **regression against known truth** |
| **2** | **Agility Robotics** — official site + press room | Digit is canonical with `RAAS_DEPLOYMENT` maturity and *no* price data — the case where a naive crawler invents a number or writes `NOT_AVAILABLE` | `RAAS` / deployment language · maturity vs obtainability separation · **UNKNOWN preservation** |
| **3** | **Engineered Arts** — official site | Ameca is canonical as `QUOTE_ONLY` / `ON_REQUEST` with UNKNOWN specs | `QUOTE_ONLY ≠ UNKNOWN` · quote-model extraction · sparse-spec pages |

Deliberately **not** prioritized: Figure AI (our own Figure 02 image provenance
correction shows how easily its media is misattributed — better once the image
path is proven), Boston Dynamics and Tesla (heavy JS/marketing surfaces, low
commercial-fact density), and every aggregator or marketplace not individually
reviewed under §5 (LIVE.1 amendment: *eligible* for acquisition in principle,
but none is reviewed yet).

The strongest argument for this trio as the **outreach** priority: all three
already exist in the verified catalogue, so once eligible, the **first live run
can be scored against hand-verified truth** — a disagreement with a
hand-checked fact is a parser bug caught before any promotion, the cheapest
possible place to find it. Permission requests to all three are drafted and
ready to send (see the eligibility reports); sending them is the owner's step,
not an automated one.

### 23.1 Provisional candidate — NEURA Robotics *(not approved, not in D-5)*

The wider market scan run alongside the initial assessment surfaced
**neura-robotics.com** as the most promising lead outside the three D-5 targets:
its `robots.txt` carries an explicit `Allow: /` for all agents, a
`Crawl-delay: 3`, individually blocked AI-training crawlers (GPTBot, ClaudeBot,
CCBot, Google-Extended, Bytespider — a deliberate, informed policy, not an
oversight), and a Cloudflare content-signal header
(`search=yes, ai-train=no, use=reference`) that reads as close to
machine-readable affirmative permission for search-style indexing specifically.

**This is a lead, not a decision.** It is recorded here as the **leading
provisional review candidate** for a *future* eligibility review — the terms
page has not yet had the same full legal read the three D-5 targets received,
and NEURA holds **no eligibility status of any kind** until that review is
performed and the owner signs off on it. Nothing about this entry changes §5's
procedure or its refusal semantics: a promising robots signal is still not a
terms decision, and it is still not this contract's decision to make.

## 24. Ratification record

```
STATUS:                      RATIFIED v0.1
Ratified by:                 Robert Konecny
Ratification date:           2026-07-29
Implementation authorized:   Slice A only (schema `0004` + models + tests, §21)
Per-source crawling
  authorization:             none

Decisions D-1 … D-7:         SETTLED by the product owner, 2026-07-29 (§22)
Permission/truth-set
  targets (D-5):              Unitree Robotics · Agility Robotics ·
                              Engineered Arts — NOT an enabled adapter order
First automated adapters:     the first official sources to receive an
                              affirmative, attributed, unexpired eligibility
                              approval (undetermined as of ratification)
NEURA Robotics:               provisional review candidate only (§23.1) —
                              NOT approved, NOT reviewed, NOT in D-5
Eligibility ASSESSMENT:       COMPLETED (first pass, 2026-07-29): robots.txt,
                              terms, legal / acceptable-use pages, linked
                              crawler-policy documents, across fourteen hosts
Source ELIGIBILITY:           NOT granted for any source — owner decision on
                              the assessment evidence, per source, still
                              required
Product-page crawling:        NOT authorized
MANUAL_BOOTSTRAP (§2.1):      permitted under existing law (LIVE.5, LIVE.6,
                              LIVE.9, DATA-D1 §18) — not gated by per-source
                              eligibility, because it performs no automated
                              access
Multi-source radar (LIVE.1
  amendment):                 RATIFIED — eligible aggregators, directories,
                              marketplaces and editorial sources may be
                              acquired once individually reviewed (§4-§6.1);
                              none reviewed as of ratification
§16.1 commercial routing
  fields:                     DECLARED, NOT AUTHORIZED — excluded from
                              Slice A and every slice until separately
                              ratified with the commercial workstream
```

**Ratification is not permission to fetch any product page automatically.**
It freezes **principles** and this document's amendments, and authorizes
exactly one piece of implementation: **Slice A**, described in full in §21 —
schema, models, and the tests proving discovery-only isolation. It does **not**
authorize contact with any source, official or otherwise: that requires the
per-source eligibility review of §5, recorded and attributed, source by source,
regardless of class.

> **Ratification statement (in force, 2026-07-29):**
>
> DATA-D1.LIVE v0.1 is ratified. HumanoidOnline is an independent
> market-intelligence and buyer-intent referral platform, not the merchant of
> record for any robot transaction (§0.1) — acquisition exists to build
> accurate, attributed listings and route qualified buyers to official
> channels, and that purpose confers no automated-access permission of its own.
>
> Acquisition follows **official-first, multi-source radar** (LIVE.1): official
> manufacturer sources remain the preferred evidence authority; eligible
> aggregators, directories, marketplaces and editorial sources may also be
> acquired, individually reviewed on identical terms, to discover candidates,
> aliases, links, conflicts and commercial signals — never to set a claim
> `VERIFIED`, never to write canonical rows, never to override a conflicting
> manufacturer claim, never to infer availability, maturity or image rights, and
> never to bypass human promotion.
>
> Two acquisition modes are authorized in principle: `AUTOMATED_LIVE`, gated
> per source by an affirmative, attributed, unexpired eligibility review before
> a single request is issued; and `MANUAL_BOOTSTRAP`, a named human reading a
> public source or reviewing manufacturer-supplied evidence directly, under the
> same evidence and promotion discipline but no automated traversal and no
> eligibility review, because no automated access occurs.
>
> Every claim carries its source URL, exact supporting text, retrieval
> timestamp and extraction confidence. Maturity, obtainability and price
> semantics are extracted as separate evidence-bound signals and are never
> merged; UNKNOWN remains UNKNOWN; conflicting sources are preserved, never
> averaged. Extraction confidence is never verification, and no source class
> writes canonical truth — promotion stays human, and where an official source
> exists for an entity, promotion requires a trace to it. Imagery remains
> reference-only under MEDIA-01, with retrieval provenance recorded honestly
> regardless of claimed attribution. No scheduler, no hosted crawler, and no
> circumvention of any access control, ever.
>
> **This ratification authorizes Slice A only. It grants no per-source
> crawling permission for any source, official or aggregator, and it is not to
> be read as authorizing a single automated fetch of any product page.**
