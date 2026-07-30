#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Import the WS2B verified production catalogue into the canonical schema.

SELF-CONTAINED (no ORM): reads the JSON catalogue under db/catalogue/ and
idempotently loads it into the `humanoid` schema created by db/schema.sql
(via db/bootstrap.py). Safe to run repeatedly — re-running produces no
duplicate rows.

IDEMPOTENCY MODEL
  - regions, manufacturers, providers, capabilities, use_cases and robots are
    UPSERTed by their natural key (code / slug -> ON CONFLICT DO UPDATE).
  - A robot's child facts (variants, pricing_offer, availability_offer,
    deployment, robot_capability, use_case_fit) and their evidence_source rows
    have no natural key, so on each import they are DELETED for that robot and
    re-inserted from the JSON. This "replace children" pass keeps the import
    fully idempotent while honouring UPSERT-by-slug for the parents.

NULL / UNKNOWN (AGENTS.md rule 6): every field absent or null in the JSON is
written as SQL NULL — never coerced to 0, false or a made-up value.

EVIDENCE (AGENTS.md rule 7): every commercial fact (commercial_status, each
pricing_offer / availability_offer / deployment) carries its evidence_source
row(s), attached polymorphically via (subject_type, subject_id).

Connection: --database-url or $DATABASE_URL (a SQLAlchemy '+psycopg' driver
token is tolerated and stripped).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "db" / "catalogue"
ROBOTS_DIR = CATALOGUE_DIR / "robots"

# Robot columns fed from a robot JSON's flat "specs" object (plus a few top-level
# fields handled separately). Kept explicit for readability (AGENTS.md rule 10).
SPEC_COLUMNS = [
    "height_cm", "weight_kg", "arm_span_cm", "reach_cm", "payload_kg",
    "walk_speed_ms", "runtime_minutes",
    "battery_wh", "mobility", "degrees_of_freedom", "hand_type", "hand_dof",
    "autonomy", "has_manipulation", "has_teleoperation", "has_vision",
    "has_language_ui", "has_sdk", "has_api", "ros_support", "developer_edition",
    "simulation_support",
]


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Evidence helper
# --------------------------------------------------------------------------- #
def insert_evidence(cur, subject_type: str, subject_id, ev: dict) -> None:
    cur.execute(
        """
        INSERT INTO evidence_source
            (subject_type, subject_id, source_url, source_type, source_title,
             excerpt, published_at, observed_at, verified_at, confidence, note)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            subject_type, subject_id,
            ev.get("source_url"), ev["source_type"], ev.get("source_title"),
            ev.get("excerpt"), ev.get("published_at"), ev.get("observed_at"),
            ev.get("verified_at"), ev.get("confidence", "MEDIUM"), ev.get("note"),
        ),
    )


# --------------------------------------------------------------------------- #
# Catalogue-level entities (upsert by natural key)
# --------------------------------------------------------------------------- #
def import_regions(cur, data: dict) -> None:
    rows = data["regions"]
    # Parents first so parent_code can resolve.
    for row in sorted(rows, key=lambda r: r.get("parent_code") is not None):
        parent_id = None
        if row.get("parent_code"):
            parent_id = cur.execute(
                "SELECT id FROM region WHERE code = %s", (row["parent_code"],)
            ).fetchone()[0]
        cur.execute(
            """
            INSERT INTO region (parent_id, type, code, name, iso_country)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (code) DO UPDATE SET
                parent_id = EXCLUDED.parent_id,
                type      = EXCLUDED.type,
                name      = EXCLUDED.name,
                iso_country = EXCLUDED.iso_country
            """,
            (parent_id, row["type"], row["code"], row["name"], row.get("iso_country")),
        )


def import_manufacturers(cur, data: dict, region_id) -> None:
    for m in data["manufacturers"]:
        mid = cur.execute(
            """
            INSERT INTO manufacturer
                (slug, name, legal_name, country_region_id, website_url,
                 founded_year, description, target_markets, commercial_model,
                 deployment_status, is_public_company, ticker)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name, legal_name = EXCLUDED.legal_name,
                country_region_id = EXCLUDED.country_region_id,
                website_url = EXCLUDED.website_url, founded_year = EXCLUDED.founded_year,
                description = EXCLUDED.description, target_markets = EXCLUDED.target_markets,
                commercial_model = EXCLUDED.commercial_model,
                deployment_status = EXCLUDED.deployment_status,
                is_public_company = EXCLUDED.is_public_company, ticker = EXCLUDED.ticker
            RETURNING id
            """,
            (
                m["slug"], m["name"], m.get("legal_name"),
                region_id(m.get("country_region_code")), m.get("website_url"),
                m.get("founded_year"), m.get("description"), m.get("target_markets"),
                m.get("commercial_model"), m.get("deployment_status"),
                m.get("is_public_company", False), m.get("ticker"),
            ),
        ).fetchone()[0]
        # Reset + re-insert manufacturer-level evidence to stay idempotent.
        cur.execute(
            "DELETE FROM evidence_source WHERE subject_type='MANUFACTURER' AND subject_id=%s",
            (mid,),
        )
        for ev in m.get("evidence", []):
            insert_evidence(cur, "MANUFACTURER", mid, ev)


def import_providers(cur, data: dict, region_id, manufacturer_id) -> None:
    for p in data["providers"]:
        cur.execute(
            """
            INSERT INTO provider
                (slug, type, name, manufacturer_id, country_region_id,
                 website_url, description)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                type = EXCLUDED.type, name = EXCLUDED.name,
                manufacturer_id = EXCLUDED.manufacturer_id,
                country_region_id = EXCLUDED.country_region_id,
                website_url = EXCLUDED.website_url, description = EXCLUDED.description
            """,
            (
                p["slug"], p["type"], p["name"],
                manufacturer_id(p.get("manufacturer_slug")),
                region_id(p.get("country_region_code")),
                p.get("website_url"), p.get("description"),
            ),
        )


def import_capabilities(cur, data: dict) -> None:
    for c in data["capabilities"]:
        cur.execute(
            """
            INSERT INTO capability (slug, name, category, description)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name, category = EXCLUDED.category,
                description = EXCLUDED.description
            """,
            (c["slug"], c["name"], c["category"], c.get("description")),
        )


def import_use_cases(cur, data: dict) -> None:
    for u in data["use_cases"]:
        cur.execute(
            """
            INSERT INTO use_case (slug, name, category, description, typical_tasks)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name, category = EXCLUDED.category,
                description = EXCLUDED.description, typical_tasks = EXCLUDED.typical_tasks
            """,
            (u["slug"], u["name"], u.get("category"), u.get("description"),
             u.get("typical_tasks")),
        )


# --------------------------------------------------------------------------- #
# Robots (+ children). Upsert robot by slug; replace children.
# --------------------------------------------------------------------------- #
def _reset_robot_children(cur, robot_id) -> None:
    """Delete a robot's fact rows and their evidence so re-import is idempotent."""
    for subject, table in (
        ("PRICING_OFFER", "pricing_offer"),
        ("AVAILABILITY_OFFER", "availability_offer"),
        ("DEPLOYMENT", "deployment"),
    ):
        cur.execute(
            f"""
            DELETE FROM evidence_source
            WHERE subject_type = %s
              AND subject_id IN (SELECT id FROM {table} WHERE robot_id = %s)
            """,
            (subject, robot_id),
        )
    cur.execute(
        "DELETE FROM evidence_source WHERE subject_type='COMMERCIAL_STATUS' AND subject_id=%s",
        (robot_id,),
    )
    for table in ("pricing_offer", "availability_offer", "deployment",
                  "robot_capability", "use_case_fit", "robot_variant", "robot_image"):
        cur.execute(f"DELETE FROM {table} WHERE robot_id = %s", (robot_id,))


def import_robot(cur, robot: dict, region_id, manufacturer_id,
                 capability_id, use_case_id) -> None:
    specs = robot.get("specs", {})
    cols = ["slug", "manufacturer_id", "name", "model_code", "summary",
            "announced_year", "commercial_status", "is_published"] + SPEC_COLUMNS
    vals = [
        robot["slug"], manufacturer_id(robot["manufacturer_slug"]), robot["name"],
        robot.get("model_code"), robot.get("summary"), robot.get("announced_year"),
        robot.get("commercial_status", "ANNOUNCED"), robot.get("is_published", False),
    ] + [specs.get(c) for c in SPEC_COLUMNS]

    placeholders = ",".join(["%s"] * len(cols))
    updates = ",".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "slug")
    robot_id = cur.execute(
        f"INSERT INTO robot ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (slug) DO UPDATE SET {updates} RETURNING id",
        vals,
    ).fetchone()[0]

    _reset_robot_children(cur, robot_id)

    # Variants -> map slug to id for offers that target a variant.
    variant_id: dict[str, object] = {}
    for v in robot.get("variants", []):
        vid = cur.execute(
            """
            INSERT INTO robot_variant (robot_id, slug, name, description, is_developer)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (robot_id, slug) DO UPDATE SET
                name = EXCLUDED.name, description = EXCLUDED.description,
                is_developer = EXCLUDED.is_developer
            RETURNING id
            """,
            (robot_id, v["slug"], v["name"], v.get("description"),
             v.get("is_developer", False)),
        ).fetchone()[0]
        variant_id[v["slug"]] = vid

    def vid_of(slug):
        return variant_id.get(slug) if slug else None

    # Commercial-status evidence (subject = the robot row).
    for ev in robot.get("commercial_status_evidence", []):
        insert_evidence(cur, "COMMERCIAL_STATUS", robot_id, ev)

    # Pricing offers.
    for po in robot.get("pricing_offers", []):
        pid = cur.execute(
            """
            INSERT INTO pricing_offer
                (robot_id, variant_id, provider_id, region_id, transaction_type,
                 price_type, currency, price, price_min, price_max, billing_period, note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                robot_id, vid_of(po.get("variant_slug")),
                _provider(cur, po.get("provider_slug")), region_id(po.get("region_code")),
                po["transaction_type"], po["price_type"], po.get("currency", "USD"),
                po.get("price"), po.get("price_min"), po.get("price_max"),
                po.get("billing_period", "ONE_TIME"), po.get("note"),
            ),
        ).fetchone()[0]
        for ev in po.get("evidence", []):
            insert_evidence(cur, "PRICING_OFFER", pid, ev)

    # Availability offers.
    for ao in robot.get("availability_offers", []):
        aid = cur.execute(
            """
            INSERT INTO availability_offer
                (robot_id, variant_id, provider_id, region_id, transaction_type,
                 availability_status, available_from, lead_time_days, min_order_qty, note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                robot_id, vid_of(ao.get("variant_slug")),
                _provider(cur, ao.get("provider_slug")), region_id(ao.get("region_code")),
                ao["transaction_type"], ao.get("availability_status", "ON_REQUEST"),
                ao.get("available_from"), ao.get("lead_time_days"),
                ao.get("min_order_qty"), ao.get("note"),
            ),
        ).fetchone()[0]
        for ev in ao.get("evidence", []):
            insert_evidence(cur, "AVAILABILITY_OFFER", aid, ev)

    # Deployments.
    for d in robot.get("deployments", []):
        did = cur.execute(
            """
            INSERT INTO deployment
                (robot_id, provider_id, customer_name, region_id, use_case_id,
                 transaction_type, unit_count, contract_value, contract_currency,
                 started_on, status, summary)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                robot_id, _provider(cur, d.get("provider_slug")), d.get("customer_name"),
                region_id(d.get("region_code")), use_case_id(d.get("use_case_slug")),
                d.get("transaction_type"), d.get("unit_count"), d.get("contract_value"),
                d.get("contract_currency"), d.get("started_on"), d.get("status"),
                d.get("summary"),
            ),
        ).fetchone()[0]
        for ev in d.get("evidence", []):
            insert_evidence(cur, "DEPLOYMENT", did, ev)

    # Verified product images (MEDIA-01). Provenance is mandatory and a synthesized
    # identity image is categorically rejected — `source_type` must be a real-source
    # enum value; GENERATED (or anything outside the enum) aborts the import rather
    # than silently degrading. Display eligibility is decided at read time by
    # identity_status + rights_status, never by the mere presence of image_url.
    _ALLOWED_IMAGE_SOURCES = {
        "MANUFACTURER", "PRESS_KIT", "DISTRIBUTOR", "EDITORIAL", "VIDEO_FRAME",
    }
    for im in robot.get("images", []):
        src = im.get("source_type")
        if src not in _ALLOWED_IMAGE_SOURCES:
            raise ValueError(
                f"robot {robot['slug']!r}: illegal image source_type {src!r} "
                f"(MEDIA-01 forbids generated/synthesized identity imagery; "
                f"allowed: {sorted(_ALLOWED_IMAGE_SOURCES)})"
            )
        cur.execute(
            """
            INSERT INTO robot_image
                (robot_id, image_url, source_url, source_name, source_type, image_type,
                 identity_status, rights_status, usage_basis, is_official, is_primary,
                 attribution, captured_at, last_verified_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                robot_id, im["image_url"], im.get("source_url"), im.get("source_name"),
                src, im.get("image_type", "FRONT"),
                im.get("identity_status", "UNVERIFIED"),
                im.get("rights_status", "UNKNOWN"),
                im.get("usage_basis", "NONE"),
                im.get("is_official", False), im.get("is_primary", False),
                im.get("attribution"), im.get("captured_at"), im.get("last_verified_at"),
            ),
        )

    # Capabilities.
    for c in robot.get("capabilities", []):
        cur.execute(
            """
            INSERT INTO robot_capability (robot_id, capability_id, supported, detail)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (robot_id, capability_id) DO UPDATE SET
                supported = EXCLUDED.supported, detail = EXCLUDED.detail
            """,
            (robot_id, capability_id(c["slug"]), c.get("supported", True), c.get("detail")),
        )

    # Use-case fits (subjective fits carry LOW/MEDIUM confidence in the JSON note).
    for f in robot.get("use_case_fits", []):
        cur.execute(
            """
            INSERT INTO use_case_fit
                (robot_id, use_case_id, fit_score, is_primary,
                 commercial_readiness, notes, limitations)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (robot_id, use_case_id) DO UPDATE SET
                fit_score = EXCLUDED.fit_score, is_primary = EXCLUDED.is_primary,
                commercial_readiness = EXCLUDED.commercial_readiness,
                notes = EXCLUDED.notes, limitations = EXCLUDED.limitations
            """,
            (robot_id, use_case_id(f["use_case_slug"]), f.get("fit_score"),
             f.get("is_primary", False), f.get("commercial_readiness"),
             f.get("notes"), f.get("limitations")),
        )

    # Denormalised lowest purchase price cache (source of truth stays pricing_offer).
    _refresh_lowest_price(cur, robot_id)


def _provider(cur, slug):
    if not slug:
        return None
    row = cur.execute("SELECT id FROM provider WHERE slug = %s", (slug,)).fetchone()
    if not row:
        raise SystemExit(f"unknown provider slug referenced: {slug!r}")
    return row[0]


def _refresh_lowest_price(cur, robot_id) -> None:
    """Set robot.lowest_purchase_price to the cheapest current PUBLIC/FROM PURCHASE
    point price, else NULL. Denormalised cache only (schema comment)."""
    row = cur.execute(
        """
        SELECT price, currency FROM pricing_offer
        WHERE robot_id = %s AND is_current
          AND transaction_type = 'PURCHASE'
          AND price_type IN ('PUBLIC','FROM') AND price IS NOT NULL
        ORDER BY price ASC LIMIT 1
        """,
        (robot_id,),
    ).fetchone()
    if row:
        cur.execute(
            "UPDATE robot SET lowest_purchase_price=%s, lowest_price_currency=%s WHERE id=%s",
            (row[0], row[1], robot_id),
        )
    else:
        cur.execute(
            "UPDATE robot SET lowest_purchase_price=NULL, lowest_price_currency=NULL WHERE id=%s",
            (robot_id,),
        )


# --------------------------------------------------------------------------- #
def run(url: str) -> None:
    regions = _load(CATALOGUE_DIR / "regions.json")
    providers = _load(CATALOGUE_DIR / "providers.json")
    capabilities = _load(CATALOGUE_DIR / "capabilities.json")
    use_cases = _load(CATALOGUE_DIR / "use_cases.json")
    manufacturers = _load(CATALOGUE_DIR / "manufacturers.json")
    robot_files = sorted(ROBOTS_DIR.glob("*.json"))

    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO humanoid, public")

            # Resolver closures backed by simple per-key lookups.
            def region_id(code):
                if not code:
                    return None
                r = cur.execute("SELECT id FROM region WHERE code=%s", (code,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown region code referenced: {code!r}")
                return r[0]

            def manufacturer_id(slug):
                if not slug:
                    return None
                r = cur.execute("SELECT id FROM manufacturer WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown manufacturer slug referenced: {slug!r}")
                return r[0]

            def capability_id(slug):
                r = cur.execute("SELECT id FROM capability WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown capability slug referenced: {slug!r}")
                return r[0]

            def use_case_id(slug):
                if not slug:
                    return None
                r = cur.execute("SELECT id FROM use_case WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown use_case slug referenced: {slug!r}")
                return r[0]

            import_regions(cur, regions)
            import_manufacturers(cur, manufacturers, region_id)
            import_providers(cur, providers, region_id, manufacturer_id)
            import_capabilities(cur, capabilities)
            import_use_cases(cur, use_cases)

            n_robots = 0
            for path in robot_files:
                robot = _load(path)
                import_robot(cur, robot, region_id, manufacturer_id,
                             capability_id, use_case_id)
                n_robots += 1

        conn.commit()

    print(f"Catalogue import OK: {len(manufacturers['manufacturers'])} manufacturers, "
          f"{len(providers['providers'])} providers, {n_robots} robots.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Import the WS2B verified catalogue")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args(argv)
    if not args.database_url:
        ap.error("no database URL: pass --database-url or set DATABASE_URL")
    run(normalize_url(args.database_url))


if __name__ == "__main__":
    main()
