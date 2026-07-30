# DATA-D1.LIVE A1 — Limited Radar Implementation Contract

> **STATUS: PROPOSED — NOT RATIFIED.**
>
> Documentation only. This document authorizes **no source, no fetch and no
> code**. It exists so that the dangerous parts — mode widening, HTTP limits and
> database enforcement — are frozen *before* any network-capable code exists to
> shape the policy around.
>
> **Authority chain.** `docs/11` (DATA-D1, RATIFIED) → `docs/16` (DATA-D1.LIVE
> v0.1, RATIFIED) → `docs/17` (Amendment A1, RATIFIED + merged at
> `main @ 626d1ce`) → **this document**. Where any conflict appears, the earlier
> document wins. Nothing here amends A1's `AGGREGATOR`-only scope, its 90-day
> validity, its restriction-applicability rules, or any ratified law.
>
> Required by `docs/17` §13.1 step 1: *"a separate implementation contract
> covering enums, limited-radar mode, database constraints, expiry behaviour and
> the §10.3 numerical ceilings, ratified before any code is written."*

---

## 1. Repository truth as inspected

Recorded because the contract must bind to what the repository actually
contains, not to what a conversation asserted. Inspected at
`main @ 626d1ce873d650a3f3a46381b33a3f970e9e8648`.

### 1.1 What is on `main` today

| Object | State on `main` |
|---|---|
| Migrations | `0001`, `0002`, `0003` only. **`0004` is not on `main`.** |
| `discovery_source_class` | Ten values: `COMPETITOR_DIRECTORY`, `MARKETPLACE`, `EDITORIAL`, `SEARCH_RESULT`, `DISTRIBUTOR`, `MANUFACTURER`, `PRESS_RELEASE`, `OFFICIAL_DOCUMENT`, `OFFICIAL_VIDEO`, `OTHER`. **`AGGREGATOR` DOES NOT EXIST.** |
| `tos_status` | `UNKNOWN`, `ALLOWED`, `RESTRICTED`, `PROHIBITED` |
| `robots_status` | `UNKNOWN`, `ALLOWED`, `DISALLOWED`, `NOT_APPLICABLE` |
| `discovery_source` | `key`, `name`, `source_class`, `homepage_url`, `tos_status`, `robots_status`, `eligibility_reviewed_at`, `eligibility_reviewed_by`, `is_enabled`, `notes`, timestamps |
| `ck_discovery_source_eligible` | `NOT is_enabled OR (tos_status = 'ALLOWED' AND robots_status IN ('ALLOWED','NOT_APPLICABLE') AND eligibility_reviewed_at IS NOT NULL AND eligibility_reviewed_by IS NOT NULL)` — `db/schema.sql:1099` |
| `candidate_claim.discovery_source_id` | **nullable**, `ON DELETE SET NULL` |
| Discovery services | `adapters.py` (`FixtureAdapter` + `ingest`), `identity.py`, `pipeline.py`, `promotion.py` |
| CLI | `promote_candidate.py` only |
| Gate tests | `apps/api/tests/test_discovery.py` — gates A–K plus H1–H5 |
| Acquisition layer | **absent** — no `acquisition.py`, no `crawl_run`, no `fetched_page`, no `source_eligibility_review`, no `discovery_evidence_excerpt` |
| `MANUAL_BOOTSTRAP` | **absent** — no `bootstrap.py`, no `bootstrap_inventory` CLI |
| `/discovery-review` | **absent** |

### 1.2 What the unmerged stack adds

| PR | Adds |
|---|---|
| **#35** `fm/data-d1-live-slice-a-schema` | Migration `0004_add_live_acquisition_layer.sql`. Widens `discovery_source_class` with `AGGREGATOR`, `AUTHORIZED_DISTRIBUTOR`, `OFFICIAL_STORE`, `COMMUNITY` (line 83–86, `ADD VALUE IF NOT EXISTS`). Adds `discovery_source.allowed_path_prefixes TEXT[]`, `tos_reviewed_at`, `tos_expires_at`, `tos_page_hash`, `last_robots_hash`, `last_robots_checked_at`, `last_crawled_at`. Creates `source_eligibility_review`, `crawl_run`, `fetched_page`, `extraction_result`, `candidate_commercial_signal`, `discovery_evidence_excerpt`. Creates enums `crawl_run_status`, `crawl_trigger` (`MANUAL` only), `fetch_outcome`, `extraction_method`, `extraction_confidence`, `signal_axis`, `eligibility_decision`, `extraction_status`, `evidence_subject_type`. Promotes `candidate_claim.discovery_source_id` to `NOT NULL` + `ON DELETE RESTRICT`. Adds trigger functions `refuse_eligibility_review_mutation()`, `assert_acquisition_lineage()`, `assert_evidence_excerpt_subject()`. Tests in `test_acquisition_schema.py`, `test_acquisition_migration.py`, including `test_slice_a_adds_no_http_client_or_crawler`. |
| **#36** `fm/data-d1-live-slice-b-manual-bootstrap` | `services/discovery/bootstrap.py`, `cli/bootstrap_inventory.py`, `db/discovery/bootstrap/humanoid_radar_v1.json` (43 candidates / 29 manufacturers). Registers a `MANUAL_BOOTSTRAP` source with `source_class = OTHER`, `tos_status = ALLOWED`, `robots_status = NOT_APPLICABLE`, `is_enabled = true`. |
| **#37** `fm/data-d1-discovery-review-ui` | `routers/discovery_review.py`, `schemas/discovery_review.py`, `app/discovery-review/page.tsx`. Router mounted **only** under `if settings.is_relaxed:` (`main.py:105`); the page `notFound()`s outside relaxed. |

### 1.3 The consequence that orders everything

**A1 names `AGGREGATOR`, and `AGGREGATOR` arrives with migration `0004`.** This
contract's migration is therefore **`0005`**, and it cannot be written, applied
or tested until `0004` is on `main`. That is not a preference; it is a hard
dependency, and it is why §21 sequences the existing stack ahead of A1-I1.

## 2. Frozen scope

**In scope:** enum widening required by A1 · an explicit limited-radar operating
mode · source eligibility and owner enablement · structured eligibility-review
evidence · database enforcement · bounded HTTP retrieval · discovery-layer
extraction · expiry and revocation behaviour · operator run reporting · internal
review-surface integration · implementation slices and acceptance gates.

**Out of scope, and not authorized by ratification of this document:** any
source, any live fetch, any implementation. See §22.

## 3. Source-class boundary — FROZEN

**`NO_EXPRESS_PROHIBITION` is available only when
`discovery_source_class = AGGREGATOR`.**

It is **not** available to `COMPETITOR_DIRECTORY`, `EDITORIAL`, `MANUFACTURER`,
`OFFICIAL_STORE`, `AUTHORIZED_DISTRIBUTOR`, `MARKETPLACE`, `SEARCH_RESULT`,
`DISTRIBUTOR`, `PRESS_RELEASE`, `OFFICIAL_DOCUMENT`, `OFFICIAL_VIDEO`,
`COMMUNITY` or `OTHER` — that is, to any other class, present or future.

This document does not redesign or broaden A1. **A source is never reclassified
to make it eligible** (`docs/17` §2.1, adversarial example 16). A later widening
requires a separate amendment to A1, not an implementation decision.

## 4. Operating modes

Boolean-only eligibility is replaced by an explicit mode. The existing
`DiscoverySource.radar_eligible` Python property — which returns a single
boolean and is consumed by `ingest()` — is **removed**, not widened, so that no
call site can silently inherit a capability it was never granted.

### 4.1 The enum

```
CREATE TYPE radar_mode AS ENUM (
    'DISABLED',       -- no automated access of any kind
    'MANUAL_ONLY',    -- MANUAL_BOOTSTRAP: human entry, no automated access
    'LIMITED_RADAR',  -- A1 bounded radar; AGGREGATOR only
    'FULL_RADAR'      -- ALLOWED sources, within their reviewed scope
);
```

Stored as `discovery_source.radar_mode radar_mode NOT NULL DEFAULT 'DISABLED'`.

> **`MANUAL_ONLY` requires the product owner's explicit confirmation.** It is a
> fourth value beyond the three named in the instruction, and it is proposed
> because omitting it **breaks PR #36**. A `MANUAL_BOOTSTRAP` source is
> registered today with `tos_status = ALLOWED`, `robots_status =
> NOT_APPLICABLE`, `is_enabled = true`, and reaches `ingest()` through
> `radar_eligible`. Under a three-mode model it would have to be recorded as
> `FULL_RADAR` — asserting an automated-access capability for a source that
> performs no automated access, which is exactly the kind of untruthful record
> this contract exists to prevent. `MANUAL_ONLY` states the truth: enabled for
> human-entered ingest, permitted zero requests. **A `MANUAL_ONLY` source may
> never construct an HTTP request**, and an acceptance gate asserts it. See
> §23 for the decision.

### 4.2 Required mapping — FROZEN

| Eligibility state | Permitted mode | Additional condition |
|---|---|---|
| `ALLOWED` | `FULL_RADAR` | within the reviewed path scope; `MANUAL_ONLY` and `DISABLED` also permissible |
| `NO_EXPRESS_PROHIBITION` | **`LIMITED_RADAR` only** | **`source_class = AGGREGATOR` required** |
| `UNKNOWN` | `DISABLED` only | — |
| `PROHIBITED` | `DISABLED` only | — |
| `REVIEW_EXPIRED` (derived) | `DISABLED` only | — |
| no review at all | `DISABLED` only | — |

Additional frozen rules:

1. **Review completion does not enable a source.** Reviewing and enabling are
   two acts, recorded separately (`docs/16` §5 step 5).
2. **Owner enablement is explicit and separately attributed** — its own actor
   and timestamp, distinct from the reviewer's. A source may not be enabled by
   the same act that reviewed it.
3. **No boolean compatibility mapping.** No property, projection, serializer,
   API field, admin column, report line or test helper may reduce
   `LIMITED_RADAR` to a truthy "eligible" value that `FULL_RADAR` also
   satisfies. Where a boolean is genuinely needed, it must be named for the
   specific question asked (`may_fetch_under_limited_radar`), never a general
   `is_eligible`.
4. **`LIMITED_RADAR` never escalates.** No code path may raise a source from
   `LIMITED_RADAR` to `FULL_RADAR`; that requires a new review recording an
   affirmative `ALLOWED` finding, plus a fresh enablement.

## 5. Schema changes — migration `0005`

Depends on `0004`. Additive only; no existing value or column is removed except
the Python-level `radar_eligible` property, which is application code.

### 5.1 Enum widening

```
ALTER TYPE tos_status           ADD VALUE IF NOT EXISTS 'NO_EXPRESS_PROHIBITION';
ALTER TYPE eligibility_decision ADD VALUE IF NOT EXISTS 'NO_EXPRESS_PROHIBITION';

ALTER TYPE fetch_outcome ADD VALUE IF NOT EXISTS 'NOT_FOUND';        -- 404, bounded run may continue
ALTER TYPE fetch_outcome ADD VALUE IF NOT EXISTS 'TOO_LARGE';        -- ceiling exceeded, aborted
ALTER TYPE fetch_outcome ADD VALUE IF NOT EXISTS 'BLOCKED_BY_SCOPE'; -- redirect left reviewed scope
ALTER TYPE fetch_outcome ADD VALUE IF NOT EXISTS 'BUDGET_EXHAUSTED'; -- run ceiling reached

CREATE TYPE radar_mode AS ENUM ('DISABLED','MANUAL_ONLY','LIMITED_RADAR','FULL_RADAR');
CREATE TYPE eligibility_axis AS ENUM (
    'ROBOTS_TXT','AGENT_DIRECTIVES','CONTENT_SIGNALS',
    'TERMS','LICENSING','TECHNICAL_ACCESS');
CREATE TYPE eligibility_check_result AS ENUM (
    'NO_RESTRICTION_FOUND','RESTRICTION_FOUND_NOT_APPLICABLE',
    'RESTRICTION_FOUND_APPLICABLE','INDETERMINATE','NOT_RETRIEVABLE');
```

**PostgreSQL constraint, stated because it dictates migration shape:**
`ALTER TYPE … ADD VALUE` cannot be used and then referenced in the same
transaction. Migration `0005` therefore performs all enum widening first, in its
own committed step, before any DDL or data write references a new value.

`RESTRICTION_FOUND_NOT_APPLICABLE` is the `docs/17` §4.1 rule-2 outcome — a
training-only restriction, found, recorded, binding against training, and not
disqualifying. `INDETERMINATE` is the rule-5 outcome and forces `UNKNOWN`.

### 5.2 `discovery_source` additions

```
ALTER TABLE discovery_source
    ADD COLUMN IF NOT EXISTS radar_mode          radar_mode NOT NULL DEFAULT 'DISABLED',
    ADD COLUMN IF NOT EXISTS enabled_by          TEXT,
    ADD COLUMN IF NOT EXISTS enabled_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS eligibility_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_reason      TEXT,
    ADD COLUMN IF NOT EXISTS declared_user_agent TEXT,
    -- per-source ceilings, permitted to be STRICTER than the frozen maxima only
    ADD COLUMN IF NOT EXISTS max_pages_per_run       INTEGER,
    ADD COLUMN IF NOT EXISTS min_request_interval_ms INTEGER;
```

### 5.3 Structured eligibility evidence — `source_eligibility_check`

An append-only normalized child of `source_eligibility_review` (which PR #35
already creates as append-only). A `notes` field cannot carry a six-axis review
auditably: it cannot be queried, cannot enforce that all six axes were
attempted, and cannot distinguish "searched and found nothing" from "never
looked" — the precise distinction A1 rests on.

```
CREATE TABLE source_eligibility_check (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id         UUID NOT NULL REFERENCES source_eligibility_review(id) ON DELETE RESTRICT,
    axis              eligibility_axis NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    url_attempted     TEXT,                    -- NULL only where the axis has no URL
    http_status       INTEGER,
    outcome_note      TEXT,
    retrieved_at      TIMESTAMPTZ NOT NULL,
    content_hash      TEXT,                    -- present iff content was obtained
    excerpt           TEXT,
    negative_finding  TEXT,                    -- REQUIRED when nothing was found
    reviewer          TEXT NOT NULL,
    declared_user_agent TEXT NOT NULL,
    result            eligibility_check_result NOT NULL,
    applied_rule      TEXT,                    -- docs/17 §4.1 rule applied, where relevant
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_eligibility_check_axis_ordinal UNIQUE (review_id, axis, ordinal),
    CONSTRAINT ck_eligibility_check_excerpt_len
        CHECK (excerpt IS NULL OR char_length(excerpt) <= 1000),
    CONSTRAINT ck_eligibility_check_hash_iff_content
        CHECK ((content_hash IS NULL) OR (http_status IS NOT NULL)),
    CONSTRAINT ck_eligibility_check_negative_finding
        CHECK (result <> 'NO_RESTRICTION_FOUND' OR btrim(coalesce(negative_finding,'')) <> ''),
    CONSTRAINT ck_eligibility_check_reviewer
        CHECK (btrim(reviewer) <> '' AND btrim(declared_user_agent) <> '')
);
```

**`ck_eligibility_check_negative_finding` is the load-bearing constraint.** A
claim of "no restriction found" that does not say what was searched is refused
by the database, not by convention. Excerpt limit is 1000 Unicode characters,
matching `EVIDENCE_EXCERPT_MAX_CHARS` and `ck_evidence_excerpt_len`.

Append-only, enforced by a trigger in the pattern of
`refuse_eligibility_review_mutation()`:

```
CREATE TRIGGER trg_refuse_eligibility_check_mutation
    BEFORE UPDATE OR DELETE ON source_eligibility_check
    FOR EACH ROW EXECUTE FUNCTION refuse_eligibility_review_mutation();
```

### 5.4 Database enforcement

**Extend `ck_discovery_source_eligible`** so the class precondition and the mode
mapping are enforced by the database, not the application:

```
ALTER TABLE discovery_source DROP CONSTRAINT ck_discovery_source_eligible;
ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_source_eligible CHECK (
    -- unchanged: FULL_RADAR still requires affirmative permission
    (radar_mode <> 'FULL_RADAR' OR (
        tos_status = 'ALLOWED'
        AND robots_status IN ('ALLOWED','NOT_APPLICABLE')
        AND eligibility_reviewed_at IS NOT NULL
        AND eligibility_reviewed_by IS NOT NULL))
    -- A1: LIMITED_RADAR requires AGGREGATOR + the new state + attribution
    AND (radar_mode <> 'LIMITED_RADAR' OR (
        source_class = 'AGGREGATOR'
        AND tos_status = 'NO_EXPRESS_PROHIBITION'
        AND robots_status IN ('ALLOWED','NOT_APPLICABLE')
        AND eligibility_reviewed_at IS NOT NULL
        AND eligibility_reviewed_by IS NOT NULL
        AND eligibility_expires_at IS NOT NULL
        AND declared_user_agent IS NOT NULL
        AND btrim(declared_user_agent) <> ''))
    -- enablement is a separate attributed act for every non-DISABLED mode
    AND (radar_mode = 'DISABLED' OR (
        enabled_by IS NOT NULL AND btrim(enabled_by) <> '' AND enabled_at IS NOT NULL))
    -- a revoked source is DISABLED, full stop
    AND (revoked_at IS NULL OR radar_mode = 'DISABLED')
    -- MANUAL_ONLY asserts no automated-access capability and needs none
    AND (radar_mode <> 'MANUAL_ONLY' OR robots_status = 'NOT_APPLICABLE')
    -- legacy is_enabled may never contradict the mode
    AND (is_enabled = (radar_mode <> 'DISABLED'))
);
```

**Expiry cannot be enforced by `CHECK`.** PostgreSQL requires `CHECK`
expressions to be immutable, and `now()` is `STABLE`; a constraint comparing
`eligibility_expires_at` to the current time is not creatable, and one that
appeared to work would be evaluated only on write. **Expiry is therefore
enforced in the request-construction path (§12) and by a `BEFORE INSERT` trigger
on `crawl_run` and `fetched_page`** that refuses a row whose source is expired
or revoked. Stating this is not a caveat — it is the reason the expiry gate must
be tested behaviourally rather than assumed structural.

## 6. Operational ceilings — FROZEN

**Product limits, not adapter defaults.** A configuration that exceeds any
ceiling is refused at startup. A ceiling that is unset, zero, negative or
unlimited is invalid and fails closed. Per-source values may be **stricter
only**; a per-source value looser than the frozen maximum is refused by
`CHECK`.

### 6.1 Concurrency and pacing

| Limit | Value |
|---|---|
| Maximum concurrent requests per host | **1** |
| Maximum global concurrent requests | **2** |
| Minimum delay between requests to the same host | **5 seconds** |
| Maximum request rate per host | **12 requests / minute** |
| Publisher-declared `Crawl-delay` > 5 s | **becomes the minimum delay** |
| Unlimited, zero-delay or missing-limit configuration | **invalid** |

### 6.2 Run scope

| Limit | Value |
|---|---|
| Maximum candidate-content pages per host per manual run | **60** |
| Maximum total requests per host per run, including policy requests | **70** |
| Maximum candidate-content pages across one run | **200** |
| Maximum total run duration | **60 minutes** |
| URL selection | only explicitly enumerated candidate URLs, or URLs matching a reviewed path-prefix allowlist |
| Traversal | **no recursive traversal, no general link-following** |

### 6.3 Response limits — decompressed bytes

| Limit | Value |
|---|---|
| Maximum response body per content page | **2 MiB** |
| Maximum response bytes per host per run | **64 MiB** |
| Maximum response bytes across a complete run | **256 MiB** |
| A response exceeding a limit | **aborted mid-stream and recorded `TOO_LARGE`** |
| Partial oversized content | **cannot be extracted or stored** |

Byte accounting is on **decompressed** bytes, measured as the stream is
consumed, so a compression bomb is stopped by the same ceiling rather than after
decompression.

### 6.4 Request behaviour

| Rule | Value |
|---|---|
| Methods allowed | **`GET` and `HEAD` only** |
| Maximum redirects | **3** |
| Redirect scope | only within the reviewed hostname, or an explicitly reviewed same-site hostname |
| Unreviewed cross-host redirect | **halts retrieval of that URL**, recorded `BLOCKED_BY_SCOPE`, becomes a review lead |
| TLS certificate validation | **mandatory** |
| Cookies, login sessions, authenticated state | **prohibited** |
| Browser automation, JavaScript execution | **prohibited** |
| Proxy rotation, user-agent spoofing | **prohibited** |
| CAPTCHA or Cloudflare circumvention | **prohibited** |
| Undocumented or hidden APIs | **prohibited** |
| External scripts, stylesheets, fonts, media, images | **never fetched** |

### 6.5 Timeouts and retries

| Limit | Value |
|---|---|
| Connection timeout | **10 seconds** |
| Read timeout | **30 seconds** |
| Total request timeout | **45 seconds** |
| Maximum retries | **1** |
| Retry permitted only for | transient network failure, or `5xx` |
| Minimum wait before that retry | **30 seconds** |
| Retry for `4xx` | **never** |
| `404` | records a missing page (`NOT_FOUND`); the bounded run may continue |
| `401`, `403`, `429`, CAPTCHA, challenge page, login wall, robots denial | **halts the source immediately** with `HALTED_BY_POLICY`; the source becomes disabled pending a fresh review |

### 6.6 Identification

The user agent must be honest, stable, and identify HumanoidOnline with a
configured contact URI. The precise contact value is deployment configuration;
the constraints are not:

- it must be non-empty;
- it must be present in **every** request;
- **startup fails closed when it is missing**;
- it may not impersonate a browser or another crawler;
- a material change requires re-review (it changes what the publisher was
  offered the chance to block).

### 6.7 Content types

**Candidate-content retrieval:** `text/html` and `application/xhtml+xml` only.
Embedded JSON-LD **within a retrieved HTML page** may be parsed as part of that
page. **Separate JSON endpoints are not fetched under limited mode.**

**Policy-review artefacts** may additionally use `text/plain`, and a normally
linked legal document only where the eligibility-review procedure explicitly
records it (§5.3).

**Binary product documents, images and media remain outside the limited-radar
acquisition path** unless separately authorized by another contract.

## 7. Run lifecycle — fail-closed

1. A **named operator** manually starts the run (`crawl_trigger = MANUAL`,
   LIVE.4). No scheduler, cron, queue or worker may start one.
2. Validate **source class** and **explicit owner enablement**.
3. Validate a **current, unexpired eligibility review**.
4. Validate **all operational ceilings** are present and within the frozen
   maxima.
5. **Re-read `robots.txt`** (LIVE.2; never answered from a cache older than 24 h).
6. Confirm the **reviewed path scope**.
7. Create the **run record**.
8. Retrieve **only enumerated pages**.
9. Extract **only discovery-layer claims and evidence**.
10. Produce the **run report**.
11. Finish **without any canonical mutation**.

**Before every single request**, re-check: the source remains enabled · the
review remains unexpired · no revocation flag exists · the remaining request,
page, byte and duration budgets · and that the target URL remains within the
reviewed scope. A failure at any point aborts that request; a policy failure
halts the source.

## 8. Expiry semantics

The ratified 90-day law of `docs/17` §7 and §7.1 is preserved exactly.
Eligibility expiry:

- sets or derives **`REVIEW_EXPIRED`** — **derived** from
  `eligibility_expires_at` rather than stored, so it cannot go stale;
- **disables new acquisition**;
- **blocks request construction** (asserted before a request object exists);
- **halts an in-flight run** as `HALTED_BY_POLICY`;
- **triggers zero HTTP requests**;
- **triggers no automatic review**;
- **triggers no content refresh**;
- **retains all existing discovery evidence and audit records**;
- requires a **fresh complete review and explicit re-enablement**.

**Acceptance tests must prove that expiry causes zero transport calls** — with a
recording fake transport asserting an empty call list, not by inspecting a
status field.

## 9. Revocation

Immediate revocation is required when: robots directives change materially ·
terms or licensing change materially · an applicable rights reservation appears ·
an agent-specific block appears · technical access denial occurs · the publisher
objects · the review expires.

**Disable first; investigate later.** `PROHIBITED` never automatically
transitions to `NO_EXPRESS_PROHIBITION`. Every state transition requires a new
attributed review or an explicit owner action; no transition is a side effect of
a run.

## 10. Extraction outputs

Limited radar writes **only** to the discovery layer (LIVE.5, Gate C). Every
extracted claim is:

- tied to a **discovery candidate**;
- tied to the actual **`AGGREGATOR` source** (`discovery_source_id`, `NOT NULL`
  + `RESTRICT` as of `0004`);
- tied to the **fetched page** (`fetched_page_id`);
- supported by **one or more bounded evidence excerpts**
  (`discovery_evidence_excerpt`, ≤1000 characters);
- marked **`NOT_VERIFIED`**;
- **version- and generation-aware** — a claim is bound to the specific model
  generation it describes, never merged across generations;
- **preserved separately when conflicting** with another source (Gate T,
  Gate X).

Missing values remain **`UNKNOWN`**. The extractor may not infer: zero from
absence · false from absence · unavailable from absence · maturity from
availability · availability from pricing · obtainability from an announcement ·
deployment from a partnership announcement · verification from source agreement.

**No raw response body may be persisted after processing.** Hashes, metadata,
excerpts and extraction results remain (LIVE.10, `fetched_page` has no body
column by construction).

## 11. Commercial axes

The ratified independent axes are preserved: **maturity · availability ·
obtainability · pricing · deployment**. One sentence may support multiple claims
only when each claim carries its **own** explicit evidence excerpt and its own
semantic review. An aggregator label such as "available now" does not
automatically establish maturity, obtainability and deployment. All remain
`NOT_VERIFIED`.

## 12. Images

Limited radar must never: request image URLs · download images · store image
bytes · populate media records · infer MEDIA-01 permission · reuse an aggregator
image credited to a manufacturer. Image acquisition remains a separate governed
process (MEDIA-01, `docs/09`).

## 13. Canonical and public isolation

Structural and behavioural enforcement must prove:

- limited-radar code **cannot import or map canonical writers** (import-level
  assertion, in the pattern of `test_no_acquisition_model_maps_a_canonical_table`);
- no canonical `robot`, `manufacturer`, `specification`, commercial or media row
  can be written;
- **Gate W, S, T and X remain unchanged**;
- **canonical row counts before and after every run are identical**;
- discovery data remains absent from the public API, MCP, sitemap, `llms.txt`
  and every other machine surface (Gate I, Gate O, AGENT-01.7);
- **`/discovery-review` remains internal and fail-closed** exactly as PR #37
  establishes it (`main.py:105`, mounted only under `settings.is_relaxed`);
- **`/api/robots` remains unchanged**.

## 14. Run report

Written to `crawl_run.counters` (JSONB, exists as of `0004`) and printed by the
CLI. Every run report includes: run ID · named operator · source · source class ·
eligibility state · **operating mode** · eligibility review ID and expiry ·
declared user agent · the frozen ceilings in force · actual request count · pages
attempted, fetched, missing, blocked and oversized · bytes received · retries ·
candidates discovered or matched · claims created · conflicts found · ambiguous
identities · policy halt reason · and **canonical rows written, which must equal
`0`** and is printed on every run rather than assumed.

## 15. Acceptance gates

Numbered A1-G1 … A1-G30. Each is a test, not a statement.

| # | Assertion |
|---|---|
| **G1** | Only `AGGREGATOR` can receive `LIMITED_RADAR` — refused at the database, exercised per class |
| **G2** | `COMPETITOR_DIRECTORY` specifically cannot receive it |
| **G3** | Reclassification is not an eligibility shortcut: changing `source_class` does not carry an existing mode or review with it; the mode resets to `DISABLED` and a new review is required |
| **G4** | `ALLOWED` and `NO_EXPRESS_PROHIBITION` remain distinct in the database, the ORM, the run report, the admin and `/discovery-review` |
| **G5** | `LIMITED_RADAR` can never become `FULL_RADAR` by projection, property or boolean conversion; no general `is_eligible` boolean exists |
| **G6** | An expired review produces **zero transport calls** (recording fake transport, empty call list) |
| **G7** | A missing review produces **zero transport calls** |
| **G8** | Owner enablement is required, separately attributed from the reviewer |
| **G9** | Manual operator attribution is required; no non-manual trigger exists |
| **G10** | Run-start `robots.txt` check occurs **before** any candidate retrieval (call ordering asserted) |
| **G11** | A named-agent `Disallow` halts **before** retrieval |
| **G12** | `403`, `429`, CAPTCHA or challenge halts the source and disables it |
| **G13** | No forbidden retry occurs — never on `4xx`, never more than once, never sooner than 30 s |
| **G14** | Concurrency, rate, page, byte and duration ceilings are each enforced under a fast fake source |
| **G15** | A missing or unlimited limit fails closed at startup |
| **G16** | Redirects cannot escape the reviewed scope; an out-of-scope redirect records `BLOCKED_BY_SCOPE` |
| **G17** | No recursive link-following occurs |
| **G18** | No hidden API or separate JSON endpoint is fetched |
| **G19** | **No image request occurs** — asserted on the transport, not on storage |
| **G20** | No raw page body persists after processing |
| **G21** | Every claim has a source, a fetched page and at least one evidence excerpt |
| **G22** | Every claim remains `NOT_VERIFIED` |
| **G23** | Conflicting values remain separate rows |
| **G24** | `UNKNOWN` semantics remain intact; `QUOTE_ONLY` never degrades to `UNKNOWN` |
| **G25** | Commercial axes remain independent; one sentence cannot set three axes without three excerpts |
| **G26** | Repeated processing is idempotent |
| **G27** | Canonical row count is identical before and after every run |
| **G28** | Public API and machine surfaces are unchanged; `/api/robots` byte-identical for a fixed catalogue |
| **G29** | Run reports expose mode and eligibility state honestly, including `canonical_rows_written = 0` |
| **G30** | A recorded publisher objection immediately disables the source |
| **G31** | *(added)* A `MANUAL_ONLY` source constructs **zero** HTTP requests |

## 16. Implementation slices

### A1-I1 — state and database enforcement
Enum widening · `radar_mode` · `source_eligibility_check` · database constraints
and triggers · expiry and transition rules · removal of `radar_eligible` with
every call site updated explicitly. **No network client.** Mirrors the Slice A
discipline, including a test in the pattern of
`test_slice_a_adds_no_http_client_or_crawler`.

### A1-I2 — bounded transport and run control
Manual trigger only · every ceiling · every policy check · a **local fake/test
server** for all tests. **No real external source adapter. No extraction into
canonical structures.** The transport is written against the fake and never
points at a real host in this slice.

### A1-I3 — discovery extraction
Discovery-layer claims · evidence excerpts · conflicts · identity ambiguity.
**No images. No canonical path.**

### A1-I4 — fresh source reviews
Only after I1–I3 are merged and validated. Review The Mimic, Lineroid,
WhichHumanoid and RoboZaps. **Classify each honestly before eligibility
assessment.** Any source classified other than `AGGREGATOR` remains unavailable
under A1.

### A1-I5 — single-source proof
Enable **at most one** qualifying `AGGREGATOR`. Run a manually triggered,
bounded proof against a small named candidate subset. Review the result before
enabling another source. **A four-source bulk run is not authorized as the first
live proof.**

## 17. Existing PR stack — sequencing dependency

`AGGREGATOR` does not exist on `main`; it arrives with `0004` (PR #35). A1-I1's
migration is `0005` and cannot be written until `0004` lands.

1. Ratify and merge **this** implementation contract.
2. **Rebase PR #35** onto the resulting `main` (it is based on pre-A1 `main` and
   currently reports non-mergeable).
3. Rerun its **exact-head gates** and review.
4. **Rebase PR #36** onto refreshed #35.
5. **Rebase PR #37** onto refreshed #36.
6. Clear and merge **#35 → #36 → #37** in order.
7. Begin **A1-I1** from the resulting clean `main`.

**Those PRs are not altered by this contract-drafting branch.** PR #32 (WS8.7)
is independent and untouched.

## 18. Non-goals

This contract proposal does not: approve any source · perform an eligibility
review · fetch any external page · implement any enum or migration · build an
HTTP client · create an adapter · run extraction · change canonical data ·
expose discovery publicly · acquire images · amend A1's `AGGREGATOR`-only scope ·
mark another PR Ready · merge anything.

## 19. Ratification record

```
STATUS:                      PROPOSED — NOT RATIFIED
Proposed:                    2026-07-30
Implements:                  docs/17 §13.1 step 1 (Amendment A1, RATIFIED,
                             main @ 626d1ce)
Base:                        main @ 626d1ce873d650a3f3a46381b33a3f970e9e8648
Implementation authorized:   NONE — documentation only
Sources approved:            NONE
Eligible source class:       AGGREGATOR ONLY — unchanged from A1 §2.1
Migration:                   0005, DEPENDS ON 0004 (PR #35, unmerged)
Default expiry:              90 days — unchanged from A1 §7
Gate W / S / T / X, P2 / P8: UNCHANGED

OPEN DECISION (one):         radar_mode value MANUAL_ONLY — see §4.1 and §20.
                             Required so MANUAL_BOOTSTRAP (PR #36) is not
                             forced to declare FULL_RADAR. Needs explicit
                             product-owner confirmation.

Ratified by:                 ____________________
Ratification date:           ____________________
```

## 20. The one open decision

**`radar_mode` needs a fourth value, `MANUAL_ONLY`, or PR #36 breaks.**

`MANUAL_BOOTSTRAP` registers a source with `tos_status = ALLOWED`,
`robots_status = NOT_APPLICABLE`, `is_enabled = true`, and that source reaches
`ingest()` via `radar_eligible`. This contract removes `radar_eligible`. With
only `DISABLED` / `LIMITED_RADAR` / `FULL_RADAR` available, a bootstrap source
must be recorded as `FULL_RADAR` — a record asserting automated-access
capability for a source that performs none.

Three options:

1. **Add `MANUAL_ONLY`** *(recommended)*. Truthful, and the `CHECK` in §5.4
   plus gate G31 make "zero requests" enforced rather than assumed.
2. Record bootstrap sources as `FULL_RADAR`. Rejected: it writes a false
   capability into the record that authorizes a fetch nobody reviewed.
3. Exempt `MANUAL_BOOTSTRAP` from the mode column entirely (nullable
   `radar_mode`). Rejected: a nullable mode reintroduces the ambiguity the mode
   column exists to remove, and `NULL` would need interpreting at every call
   site.

Recommendation: option 1. It is the only one that leaves the record true.
