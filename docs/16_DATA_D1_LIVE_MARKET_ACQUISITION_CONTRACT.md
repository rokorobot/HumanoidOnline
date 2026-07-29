# DATA-D1.LIVE — Live Market Acquisition Contract

> **STATUS: DRAFT — NOT RATIFIED. NOTHING IMPLEMENTED. NO NETWORK ACCESS HAS
> OCCURRED.**
>
> This document is a proposal for owner review. No live adapter exists, no
> robots.txt or terms page has been fetched for any candidate source, and no
> code in this repository performs an outbound HTTP request to a manufacturer.
> The discovery layer that exists today (`docs/11`, merged at `3dca8cc`) is
> **fixture-only**.
>
> **Two separate approvals are required before any live fetch:**
> 1. ratification of this contract, and
> 2. an approved, attributed **per-source eligibility review** (§5) for each
>    individual source.
>
> Ratifying this contract does **not** authorize a crawl of any particular site.

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

- an adapter framework for **official manufacturer sources**
- a per-source eligibility review record, and the refusal that depends on it
- a manually executed, local, resumable crawl with a full run report
- extraction of specification claims, commercial signals and image *references*,
  each bound to evidence
- deterministic identity resolution and deduplication against the existing
  canonical catalogue and existing candidates
- operator review through the **existing** SQLAdmin views and CLI

**Explicitly out of scope (v0.1):** see §20. In particular: no scheduler, no
crawler VPS, no headless browser, no third-party directory fetching, no
canonical writes, no image binaries, no Operations Workbench.

## 3. Laws (frozen on ratification)

### LIVE.1 — Official-first
The live crawler fetches **official manufacturer sources only**: the
manufacturer's own product pages, catalogue/store pages, specification
documents, press room and official documentation. Third-party directories,
marketplaces, aggregators and competitor databases remain **radar leads** under
DATA-D1.1 and are **not fetched** by the live crawler in v0.1. A lead may point
at an official URL; the crawler visits the official URL, not the lead.

*Why:* the evidence hierarchy (`docs/11` §4) already says manufacturer sources
outrank aggregators. Fetching aggregators first would optimise for volume of
claims we cannot promote.

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

## 4. Source classes

| Class | v0.1 fetch? | Role |
|---|---|---|
| `OFFICIAL_MANUFACTURER` | **yes**, after eligibility | primary and only live source |
| `OFFICIAL_STORE` (manufacturer-operated storefront) | **yes**, after eligibility | price / obtainability evidence |
| `OFFICIAL_PRESS` (manufacturer press room) | **yes**, after eligibility | maturity / announcement evidence |
| `DIRECTORY` / `AGGREGATOR` / `COMPETITOR` | **no** | radar leads only (DATA-D1.1) |
| `NEWS` / `EDITORIAL` | **no** | may be recorded as a human-entered lead |

Adding a class to the fetchable set is a contract amendment, not a
configuration change.

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
`fetched_page_id`. It keeps `media_status = 'CANDIDATE'`.

The extractor sets **no** MEDIA-01 field. Promotion of an image to `robot_image`
remains a human MEDIA-01 evaluation: exact-model identity, rights status, usage
basis, attribution. For robots already in the catalogue with a verified image,
acquisition may propose *additional* references; it may never replace or
generate one (MEDIA-01 frozen law).

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

## 12. Adapter interface

Extends the existing `SourceAdapter` protocol rather than replacing it, so
`FixtureAdapter` keeps working and stays the test path.

```python
class LiveSourceAdapter(Protocol):
    key: str                    # stable identifier, e.g. "unitree-official"
    version: str                # bump ⇒ re-extraction is meaningful
    source_class: str           # OFFICIAL_MANUFACTURER | OFFICIAL_STORE | OFFICIAL_PRESS
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
  page is a prerequisite of slice 2 (§21), not a follow-up.
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

# review
python -m app.cli.discovery report <run-id>                # the §18 report
python -m app.cli.discovery candidates --status READY_FOR_PROMOTION
python -m app.cli.promote_candidate <candidate-id> --show | --approve …
```

`--dry-run` performs the robots evaluation and prints exactly what *would* be
requested, without issuing a request.

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
                         crawl_run_id, fetched_page_id
  discovery_source     + allowed_path_prefixes, tos_reviewed_at,
                         tos_expires_at (90d), tos_page_hash,
                         last_robots_hash, last_robots_checked_at (24h max),
                         last_crawled_at
```

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
| **R** | `/crawler-policy` resolves and is non-empty before the first product-page fetch; slice 2 cannot run without it. |

## 20. Non-goals (v0.1)

No scheduler, cron, queue or worker · no crawler VPS or any production-hosted
fetching · no headless browser or JavaScript execution · no third-party
directory, marketplace or competitor fetching · no login-gated content · no
canonical writes · no auto-promotion · no image binaries · no Operations
Workbench · no LLM extraction, scoring or matching · no cross-source averaging ·
no PDF/document parsing (deferred: specification sheets are attractive and worth
a separate slice) · no more than three adapters.

## 21. Build sequence (on ratification)

**Execution model (owner-directed).** This workstream runs **in parallel with
WS8.8 / WS8.9**, on isolated branches or worktrees. It does **not** enter or
alter the WS8 release train — WS8-L1 forbids new product capability inside a
release-hardening slice, and nothing here may appear in the MVP v0.1 release
candidate.

0. **Eligibility assessment (authorized now, read-only).** For the three
   approved sources, fetch **only** `robots.txt`, terms of use, legal /
   acceptable-use pages, and crawler-policy documents linked from those pages.
   Record exact URLs, retrieval timestamps, HTTP status, hashes, relevant
   excerpts and a provisional `ALLOWED / DISALLOWED / UNCLEAR` recommendation.
   **This authorization does not extend to product pages, adapters, network
   ingestion, database writes, or declaring any source eligible** — eligibility
   remains an owner decision on the evidence.
1. **Eligibility approval.** The owner accepts or rejects each assessment.
   Nothing below may start for a source without an affirmative decision.
2. **Slice 1 — infrastructure, no adapters.** Schema `0004`, fetcher with
   robots/rate/cache/retry/kill switch, crawl-run + report, CLI, gates A–H,
   N, P. Provable end to end against a **local fake server**, not the internet.
3. **Slice 2 — first adapter** for the approved source. Gates I–M, O. First
   real run is `--dry-run`, reviewed, then a capped live run.
4. **Slice 3 — adapters two and three**, chosen to *differ* commercially
   (see §22), generalizing only what real variation demands.
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
| **D-5** | First sources | **1. Unitree Robotics → 2. Agility Robotics → 3. Engineered Arts**, each subject to affirmative eligibility. | §23 |
| **D-6** | Extraction confidence | **Never auto-verifies.** May prioritise review or reject its own low-confidence output; may never set `VERIFIED`, alter canonical confidence, or bypass human promotion. | LIVE.8 |
| **D-7** | Evidence excerpts | **≤ 1000 Unicode characters each**, multiple excerpts per claim permitted; each carries page URL, retrieval time, page hash and locator/offsets. | LIVE.6, §9 |

## 23. First sources — APPROVED ORDER (D-5)

**Approval of this order authorizes the eligibility ASSESSMENT only.** No source
is eligible until its review returns an affirmative terms decision and a
non-disallowing robots policy, recorded and attributed (§5). The order is chosen
so the first three adapters exercise three genuinely different commercial shapes
rather than three variations of one.

| # | Source | Why in this order | What it exercises |
|---|---|---|---|
| **1** | **Unitree Robotics** — official site + official store | Already canonical in our catalogue (G1 at `$13,500 PUBLIC`, H1 `QUOTE_ONLY`), so identity matching has something real to match, and extraction can be checked against a fact we already verified by hand | `PUBLIC` price · `PURCHASE` availability · spec extraction · **regression against known truth** |
| **2** | **Agility Robotics** — official site + press room | Digit is canonical with `RAAS_DEPLOYMENT` maturity and *no* price data — the case where a naive crawler invents a number or writes `NOT_AVAILABLE` | `RAAS` / deployment language · maturity vs obtainability separation · **UNKNOWN preservation** |
| **3** | **Engineered Arts** — official site | Ameca is canonical as `QUOTE_ONLY` / `ON_REQUEST` with UNKNOWN specs | `QUOTE_ONLY ≠ UNKNOWN` · quote-model extraction · sparse-spec pages |

Deliberately **not** first: Figure AI (our own Figure 02 image provenance
correction shows how easily its media is misattributed — better once the image
path is proven), Boston Dynamics and Tesla (heavy JS/marketing surfaces, low
commercial-fact density), and every directory or marketplace (LIVE.1).

The strongest argument for this trio: all three already exist in the verified
catalogue, so the **first live run can be scored against hand-verified truth**.
If the crawler disagrees with the catalogue on a fact a human already checked,
that is a parser bug caught before any promotion — the cheapest possible place to
find it.

## 24. Ratification record

```
STATUS:                     DRAFT — NOT RATIFIED
Ratified by:                ____________________  (product owner)
Date:                       ____________________

Decisions D-1 … D-7:        SETTLED by the product owner, 2026-07-29 (§22)
First-source ORDER:         APPROVED — Unitree -> Agility -> Engineered Arts
Eligibility ASSESSMENT:     AUTHORIZED (read-only: robots.txt, terms, legal /
                            acceptable-use, linked crawler-policy documents)
Source ELIGIBILITY:         NOT granted for any source — owner decision on the
                            assessment evidence, per source, still required
Product-page crawling:      NOT authorized
```

Ratification freezes **principles**, not implementation, and authorizes the
build sequence in §21. It does **not** authorize contact with any source: that
requires the per-source eligibility review of §5, recorded and attributed.

> **Proposed ratification statement:**
>
> DATA-D1.LIVE v0.1 is ratified. HumanoidOnline may acquire market facts from
> official manufacturer sources only, after a recorded, attributed, per-source
> terms and robots review, executed manually and locally, writing to the
> discovery layer only. Every claim carries its source URL, exact supporting
> text, retrieval timestamp and extraction confidence. Maturity, obtainability
> and price semantics are extracted as separate evidence-bound signals and are
> never merged; UNKNOWN remains UNKNOWN. Extraction confidence is never
> verification, and no crawler writes canonical truth — promotion stays human.
> Imagery remains reference-only under MEDIA-01. No scheduler, no hosted
> crawler, and no circumvention of any access control, ever.
