# db/migrations

Forward, SQL-first migrations applied **after** the canonical baseline.

## Rules

- **`db/schema.sql` is canonical** (AGENTS.md rule 2). It is the baseline —
  the bootstrap applies it as migration `0000_schema`. Migrations here only
  carry the schema *forward* from that baseline; they never restate it.
- Migrations are **hand-written SQL**, never generated from ORM models.
- Any change to the canonical data model is its own product-owner-reviewed
  change to `db/schema.sql` first (schema wins); a matching forward migration
  is then added here so existing databases converge. Migrations must never
  drift from `schema.sql`.
- **Do not remove dormant Phase 3–5 structures** to simplify a migration
  (AGENTS.md rule 3).

## Naming

```
NNNN_short_description.sql      e.g. 0001_add_robot_warranty_months.sql
```

Zero-padded, monotonically increasing. The runner applies them in
lexicographic order and records each in `public.schema_migrations`
(version + sha256), so re-running is a no-op.

## Applying

```bash
uv run db/bootstrap.py            # baseline (schema.sql) + every pending migration
uv run db/bootstrap.py --seed     # ...then load the seed dataset
```

Forward migrations:

- `0001_add_commercial_lead_message.sql` — adds `commercial_lead.message`
  (WS7), reconciling the frozen `POST /api/commercial-leads` body with the
  canonical model. Idempotent (`ADD COLUMN IF NOT EXISTS`) so it is a no-op on
  fresh databases already built from `schema.sql`.
- `0002_add_robot_image.sql` — adds the MEDIA-01 verified-imagery entity
  `robot_image` and its four enums (`docs/09_MEDIA_CONTRACT.md`). Idempotent
  (pg_type guards + `CREATE TABLE/INDEX IF NOT EXISTS`) so it is a no-op on fresh
  databases already built from `schema.sql`. `robot.hero_image_url` stays dormant.
