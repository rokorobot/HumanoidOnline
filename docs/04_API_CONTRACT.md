# HumanoidOnline — API Contract (MVP v0.1)

**Status:** Frozen shape, extensible fields. FastAPI implements these endpoints with Pydantic models mirroring the shapes below. Adding fields is fine; renaming/removing or changing semantics requires product-owner approval.

Conventions: JSON over HTTPS · `snake_case` keys · UUID ids · enum values exactly as in `03_DATA_DICTIONARY.md` · list endpoints paginate with `?limit=` (default 24, max 100) and `?offset=`, returning `{items, total, limit, offset}` · errors return `{ "detail": string }` with proper status codes · unknown values are `null`, never `0`/`false`/`""`.

---

## 1. Robots

### `GET /api/robots`
Catalogue with filters. Query params (all optional):

```
q                    full-text search
manufacturer         manufacturer slug
commercial_status    repeatable enum
transaction_type     repeatable enum   → robots with a current availability_offer of this type
availability_status  repeatable enum
region               region code (e.g. EU, US, DE)
use_case             use_case slug
payload_min          number (kg)
height_min|height_max  number (cm)
price_max            number  → against lowest_purchase_price cache
mobility             enum
autonomy_min         enum (ordered)
has_sdk|ros_support|developer_edition|has_manipulation ... boolean flags
sort                 name | price | payload | newest   (+ "-" prefix for desc)
limit, offset
```

Response `200`:
```json
{
  "items": [
    {
      "id": "uuid", "slug": "unitree-g1", "name": "G1",
      "manufacturer": { "slug": "unitree", "name": "Unitree Robotics" },
      "summary": "…", "hero_image_url": null,
      "commercial_status": "COMMERCIAL",
      "payload_kg": 3.0, "height_cm": 130.0, "mobility": "BIPEDAL",
      "price_display": { "type": "PUBLIC", "amount": 16000, "currency": "USD", "billing_period": "ONE_TIME" },
      "available_modes": ["PURCHASE", "DEVELOPER"],
      "deployment_count": 0
    }
  ],
  "total": 20, "limit": 24, "offset": 0
}
```
`price_display` is `null` when no pricing rows exist (UI renders **"No confirmed pricing"** — unknown price). A known quote-gated model comes through as `{"type": "QUOTE_ONLY", "amount": null, ...}` (UI renders **"Price on request"**). These are different facts and must not collapse. `available_modes` is `[]` when unknown (UI renders "No confirmed commercial availability") and is computed with the canonical `commercially_accessible()` predicate.

### `GET /api/robots/{slug}`
Full detail. Response `200` (abbreviated):
```json
{
  "id": "uuid", "slug": "digit", "name": "Digit",
  "manufacturer": { "slug": "agility-robotics", "name": "Agility Robotics", "country": "US" },
  "commercial_status": "RAAS_DEPLOYMENT",
  "status_history": [ { "status": "PILOT", "effective_at": "2024-06-01" } ],
  "specs": { "height_cm": 175.0, "payload_kg": 16.0, "runtime_minutes": null, "...": "..." },
  "extended_specs": [ { "key": "reach_cm", "label": "Reach", "value": 90, "unit": "cm", "category": "MANIPULATION" } ],
  "capabilities": [ { "slug": "bimanual-manipulation", "name": "Bimanual manipulation", "supported": true, "detail": null } ],
  "variants": [ { "slug": "digit-v5", "name": "Digit v5", "is_developer": false } ],
  "use_case_fits": [ { "use_case": "warehouse-logistics", "fit_score": 0.9, "commercial_readiness": "RAAS_DEPLOYMENT", "limitations": null } ],
  "pricing_offers": [
    { "transaction_type": "RAAS", "price_type": "QUOTE_ONLY", "price": null, "currency": "USD",
      "billing_period": "ANNUAL", "region": "US", "provider": "agility-robotics",
      "evidence": { "source_type": "MANUFACTURER_SITE", "verified_at": "2026-07-01", "confidence": "HIGH" } }
  ],
  "availability_offers": [
    { "transaction_type": "RAAS", "availability_status": "AVAILABLE", "region": "US",
      "provider": "agility-robotics", "available_from": null, "lead_time_days": null }
  ],
  "deployments": [
    { "customer_name": "GXO", "region": "US", "use_case": "warehouse-logistics",
      "transaction_type": "RAAS", "unit_count": null, "contract_value": null, "summary": "…",
      "evidence": { "source_type": "PRESS_RELEASE", "confidence": "HIGH", "verified_at": "2026-06-15" } }
  ]
}
```
`404` for unknown slug.

### `GET /api/robots/compare?ids=slug1,slug2[,slug3,slug4]`
2–4 robots; returns the detail shape above for each plus a `rows` array of normalized comparison rows grouped by `commercial | physical | manipulation | intelligence | developer | deployment`. `422` if <2 or >4 valid slugs.

## 2. Manufacturers

### `GET /api/manufacturers` — index: `{items: [{slug, name, country, robot_count, deployment_status}], total, ...}`
### `GET /api/manufacturers/{slug}` — profile + `robots: []` portfolio + `providers: []` + `deployments: []`. `404` unknown.

## 3. Use cases

### `GET /api/use-cases` — index with `robot_count` per use case.
### `GET /api/use-cases/{slug}` — detail + `suitable_robots: [{slug, name, fit_score, commercial_readiness, limitations}]` ordered by `fit_score` desc.

## 3b. Regions (supporting read)

### `GET /api/regions`
Canonical geography for pickers — added in WS5 to drive the buyer-intent **Country** step from live data (never a hardcoded country array), mirroring how the TASK step is seeded from `GET /api/use-cases`. Optional `?type=` filters by `region_type` (e.g. `COUNTRY`). Returns a bare array ordered by name:
```json
[ { "code": "DE", "name": "Germany", "type": "COUNTRY", "iso_country": "DE" } ]
```
`code` is exactly what `POST /api/buyer-requirements` resolves for `country` (COUNTRY rows only). Read-only; product-owner-authorized additive endpoint.

## 4. Buyer intent & matching

`POST /api/buyer-requirements` is **anonymous intent capture** (WS5): it collects **no contact identity** (name/email/organization belong to WS7 `commercial-leads`), runs **no matching** and creates **no** `match_result`/`commercial_lead`. `raw_input` is **required and versioned** (`wizard_version` + per-answer `state` ∈ `ANSWERED|UNKNOWN|SKIPPED`), and `country` resolves **only** to a canonical `COUNTRY` region (an economic zone like `EU` or `GLOBAL` is rejected `422`).

### `POST /api/buyer-requirements`
Body (all fields optional except a required versioned `raw_input` and at least one requirement signal):
```json
{
  "buyer_type": "COMMERCIAL_BUYER",
  "use_case": "warehouse-logistics",
  "industry": "logistics",
  "task_description": "tote handling between conveyor and pallets",
  "country": "DE",
  "environment": "indoor warehouse",
  "payload_min_kg": 10,
  "operating_hours_day": 16,
  "manipulation_required": true,
  "autonomy_required": "SUPERVISED_AUTONOMY",
  "budget": { "currency": "EUR", "min": null, "max": 250000 },
  "required_by": "2027-01-01",
  "preferred_transaction": "RAAS",
  "raw_input": {
    "wizard_version": 1,
    "answers": { "country": { "state": "ANSWERED", "value": "DE" }, "payload": { "state": "UNKNOWN" } }
  }
}
```
Response `201`: `{ "id": "uuid" }`. In WS5 matching does **not** run on create — it runs on the first `GET …/matches` fetch below (WS6). Invalid `use_case`/`country`, a missing/unversioned `raw_input`, a contact field, or no requirement signal all return `422`, and a rejected request persists nothing.

### `GET /api/buyer-requirements/{id}` (WS6 supporting read)
Anonymous requirement read (no contact identity) — powers **Adjust Requirements**: the wizard prefills from the stored `raw_input` (versioned answers) and submitting creates a **new** `buyer_requirement` (the historical one is never mutated — no `PUT`/`PATCH`). `404` for an unknown id. Product-owner-authorized additive read.

### `GET /api/buyer-requirements/{id}/matches`
Deterministic matching runs on the **first** request and is persisted; later requests return the stored result unchanged (idempotent; the requirement row is locked so a concurrent first request reads the persisted result rather than rescoring). A zero-survivor outcome persists nothing (no sentinel row, no schema change) and is recomputed deterministically. `404` for an unknown id.
Response `200`:
```json
{
  "requirement_id": "uuid",
  "matches": [
    {
      "robot": { "slug": "digit", "name": "Digit", "manufacturer": "Agility Robotics" },
      "score": 82, "rank": 1, "category": "BEST_COMMERCIAL",
      "score_breakdown": { "use_case_fit": 22.5, "technical_fit": 16.0, "commercial_availability": 20.0,
                            "geographic_fit": 7.5, "budget_fit": 5.0, "deployment_readiness": 10.0 },
      "reasons": ["commercial deployment available", "suitable payload", "supports required application"],
      "warnings": ["pricing is quote-only"]
    }
  ],
  "excluded_count": 14,
  "no_match_explanation": null
}
```
When `matches` is empty, `no_match_explanation` states the dominant eliminating constraint.

## 5. Commercial leads

### `POST /api/commercial-leads`
```json
{
  "requirement_id": "uuid",
  "contact_name": "…", "contact_email": "…", "organization": "…",
  "robot_slugs": ["digit", "apollo"],
  "preferred_transaction": "RAAS",
  "message": "…"
}
```
Response `201`: `{ "id": "uuid", "lead_status": "NEW" }`. `contact_email` required here (this is the capture point). **No checkout, no payment fields — ever, in v0.1.**

## 6. Analytics

### `POST /api/events` — `{event_type, robot_slug?, requirement_id?, payload?}` → `202`. Fire-and-forget.

## 7. Admin (internal, auth-gated, shapes flexible)

CRUD for robots, manufacturers, offers, evidence, providers; list/detail for `buyer_requirements`, `match_results`, `commercial_leads` (with `lead_status` transitions). Not part of the public contract.
