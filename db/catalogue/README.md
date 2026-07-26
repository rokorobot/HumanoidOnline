# HumanoidOnline — Verified Production Catalogue (WS2B)

A curated, evidence-backed dataset of real humanoid robots and their **commercial**
facts, kept **separate** from `db/seed/seed.sql`.

- `db/seed/seed.sql` is a **schema stress test** with *indicative* values (most
  deliberately unverified) — it exists to exercise the schema/API/UI.
- **This catalogue** is the *first honest pass* at editorial truth: every published
  commercial fact is traced to a primary source. It is the seed of HumanoidOnline's
  moat — **verified commercial intelligence**.

`db/schema.sql` is the canonical data model (AGENTS.md rule 2). Nothing here edits
the schema, the seed, or the docs — the catalogue is **add-only** and is loaded by
its own importer.

---

## 1. Files

```
db/catalogue/
  README.md              <- this file
  regions.json           <- region codes (GLOBAL, US, CN, EU, DE, NO, UK ...)
  providers.json         <- commercial counterparties (OEM store, RaaS provider ...)
  capabilities.json      <- capability catalogue (descriptive, not commercial)
  use_cases.json         <- use-case catalogue
  manufacturers.json     <- OEM company profiles (+ MANUFACTURER evidence)
  robots/<slug>.json     <- one file per robot, with every commercial fact + its evidence
db/import_catalogue.py   <- self-contained UPSERT importer (PEP 723 uv script)
db/validate_catalogue.py <- catalogue-level G2 gate (PEP 723 uv script)
```

Regions/providers/capabilities/use_cases are shared catalogues referenced by the
robot files via natural keys (`code` / `slug`).

## 2. Robot file shape

Each `robots/<slug>.json` has robot identity + a flat `specs` object (first-class
physical/intelligence/developer columns from `robot`), then the commercial facts,
each carrying **its own evidence array**:

```jsonc
{
  "slug": "unitree-g1",
  "name": "G1",
  "manufacturer_slug": "unitree",
  "commercial_status": "COMMERCIAL",     // commercial_status enum, verbatim
  "is_published": true,                   // only true when every published fact has evidence
  "specs": { "height_cm": 132, "payload_kg": null, ... },   // unknown -> null (never 0/false)
  "commercial_status_evidence": [ { <evidence> } ],
  "variants":            [ { "slug": "...", "name": "...", "is_developer": true } ],
  "pricing_offers":      [ { "transaction_type": "...", "price_type": "...", ..., "evidence": [ ... ] } ],
  "availability_offers": [ { "transaction_type": "...", "availability_status": "...", ..., "evidence": [ ... ] } ],
  "deployments":         [ { "customer_name": "...", ..., "evidence": [ ... ] } ],
  "capabilities":        [ { "slug": "...", "supported": true, "detail": "..." } ],
  "use_case_fits":       [ { "use_case_slug": "...", "fit_score": 0.75, "confidence": "MEDIUM", ... } ],
  "images":              [ { <robot_image> } ]   // MEDIA-01 verified imagery (see below)
}
```

### `images[]` — MEDIA-01 verified product imagery (`docs/09_MEDIA_CONTRACT.md`)

Each image of a **specific named robot** must depict that exact robot. There is no
`GENERATED` source — a synthesized/look-alike identity image is rejected by the
importer. An image is only *displayed* when `identity_status = VERIFIED` **and**
`rights_status ∈ {PERMITTED, ATTRIBUTION_REQUIRED}`; a non-null `image_url` is never
sufficient. A robot with no honestly-clearable image simply has an empty `images`
array → the UI shows `IMAGE_UNAVAILABLE` (never a placeholder fill).

```jsonc
{
  "image_url":       "https://…/g1.jpg",       // the asset rendered
  "source_url":      "https://…/press-kit",     // authoritative provenance page
  "source_name":     "Unitree Robotics",
  "source_type":     "MANUFACTURER",            // MANUFACTURER|PRESS_KIT|DISTRIBUTOR|EDITORIAL|VIDEO_FRAME (never GENERATED)
  "image_type":      "FRONT",                   // FRONT|SIDE|REAR|ACTION|WORKPLACE|DETAIL|DIMENSIONS
  "identity_status": "VERIFIED",                // VERIFIED|UNVERIFIED — depicts THIS exact model?
  "rights_status":   "ATTRIBUTION_REQUIRED",    // PERMITTED|ATTRIBUTION_REQUIRED|UNKNOWN|RESTRICTED — UNKNOWN != PERMITTED
  "is_official":     true,
  "is_primary":      true,                       // at most one primary per robot
  "attribution":     "© Unitree Robotics",      // required when ATTRIBUTION_REQUIRED
  "captured_at":     "2025-01-01",
  "last_verified_at":"2026-07-25T00:00:00Z"
}
```

Every **evidence** object:

```jsonc
{
  "source_url":   "https://shop.unitree.com/products/unitree-g1",
  "source_type":  "MANUFACTURER_STORE",   // source_type enum, verbatim
  "source_title": "Unitree G1 — official store listing",
  "excerpt":      "$13,500.00 USD",        // the exact fact text supported
  "published_at": null,                    // source publication date, if known
  "observed_at":  "2026-07-24",            // when WE observed it
  "verified_at":  "2026-07-24",            // set ONLY when confirmed on the primary source
  "confidence":   "VERIFIED",              // confidence_level enum, verbatim
  "note":         "Store list price observed directly on the OEM store (2026-07-24)."
}
```

All enum labels (`commercial_status`, `transaction_type`, `price_type`,
`availability_status`, `billing_period`, `source_type`, `confidence_level`,
`mobility_type`, `autonomy_level`, region/provider/capability categories) are used
**verbatim** from `docs/03_DATA_DICTIONARY.md` / `db/schema.sql`.

### `chk_price_type_shape` (enforced by the DB)

| `price_type` | price | price_min / price_max |
|---|---|---|
| `PUBLIC` / `FROM` / `ESTIMATED` | **set** | null |
| `RANGE` | null | **both set**, `price_max >= price_min` |
| `QUOTE_ONLY` | null | null |

A price is recorded **only** where a real price or quote basis is public. Unknown
price = **no `pricing_offers` row** (≠ `QUOTE_ONLY`, ≠ 0).

## 3. Sourcing standards (binding)

Use public **primary** sources first: manufacturer product pages & official stores,
official datasheets/technical docs, manufacturer press releases, regulatory/financial
filings, official deployment announcements, and customer/operator announcements that
directly confirm a deployment.

For **every** commercial fact record: `source_url`, `source_type` (mapped to the
`source_type` enum), `observed_at`, `confidence`, and the **exact fact supported**
(placed in the evidence `excerpt` / `note`).

- **Public ≠ verified.** `VERIFIED` / `HIGH` requires a **direct authoritative source
  for that specific fact**.
- Inferred or indirectly supported facts → `LOW` / `MEDIUM` confidence, or
  `price_type = ESTIMATED`.
- **Conflicting facts** across sources are **preserved as conflicts** (a note and/or
  multiple evidence rows), never silently resolved. (See `unitree-h1.json`: the store
  shows a `$90,000` figure but disavows it as "the real price" — recorded as
  `QUOTE_ONLY`, the conflict retained in the offer note.)
- **Unsupported facts stay `NULL` / `UNKNOWN`** — never invented, never defaulted
  (no 0, no false, no made-up price) — AGENTS.md rule 6.
- Prefer primary sources over media/aggregators; secondary sources are for discovery
  / corroboration only, never the sole basis for a `VERIFIED` fact.
- `is_published = true` **only** when every published commercial fact carries evidence.

### Status normalization (deterministic mappings)

Where a manufacturer states a status in their own words, HumanoidOnline maps it
**deterministically** to a `commercial_status` enum value. A directly manufacturer-
declared mapping is `VERIFIED`; an inferred/framing-only one is at most `HIGH`.

| Manufacturer statement (primary source) | Normalized `commercial_status` | Confidence |
|---|---|---|
| Explicit product/fleet **retirement** ("retiring", "retirement of X", "discontinued") | `DISCONTINUED` | `VERIFIED` |
| Retirement only **implied** by a successor launch (no explicit retire statement) | prior supported status; `DISCONTINUED` only at `HIGH` with rationale | `HIGH` |

Example — **Figure 02**: Figure's own page (2025-11-19) states *"officially starting
the retirement of Figure 02"* and *"fleet-wide retirement"* → `DISCONTINUED`,
`VERIFIED`. The historical BMW deployment is retained as **separate** evidence:
retiring the product does not erase its verified deployment history.

## 4. Confidence rubric (`confidence_level`)

| Level | When to use | `verified_at` |
|---|---|---|
| `VERIFIED` | Fact confirmed **directly** on the primary/authoritative source for *that* fact (e.g. a price read off the OEM store; a deployment metric on the manufacturer's own page). Only `VERIFIED` may render a "Verified" badge. | **required** |
| `HIGH` | Primary source supports the fact but with mild interpretation/mapping (e.g. "backordered" → `LIMITED`), or an official press release on a distribution wire. | set when checked |
| `MEDIUM` | Corroborated but indirect, or a reasonable editorial judgement (most subjective `use_case_fit` rows). | usually null |
| `LOW` | Weakly supported / single secondary source / indicative only. Publishable only as `ESTIMATED` price or clearly-hedged fact. | null |

## 5. Import & validate

Prereqs: schema present (`db/bootstrap.py`, **no seed**), `$DATABASE_URL` set
(a `+psycopg` driver token is tolerated), `uv` available.

```bash
# fresh DB, schema only (NO seed) — keep the catalogue distinct from the seeded DB
export DATABASE_URL="postgresql://humanoid:humanoid@localhost:5432/catalogue_test"
uv run db/bootstrap.py            # schema baseline + forward migrations
uv run db/import_catalogue.py     # UPSERTs the catalogue (idempotent)
uv run db/validate_catalogue.py   # G2 gate: fails non-zero if any published fact lacks evidence
```

- **Idempotent:** parents (regions/manufacturers/providers/capabilities/use_cases/
  robots) UPSERT by natural key; each robot's fact rows + evidence are replaced on
  re-import. Running the importer N times yields identical row counts.
- **`validate_catalogue.py`** asserts the catalogue-level G2: every published robot's
  `commercial_status`, and every `pricing_offer` / `availability_offer` / `deployment`
  attached to a published robot, has a backing `evidence_source` row. It prints a
  summary (robots, offers, deployments, evidence counts) and exits non-zero on any gap.

CI runs exactly this chain in the `catalogue-validate` job
(`.github/workflows/ci.yml`), against a Postgres 16 service, **schema only, no seed**.
