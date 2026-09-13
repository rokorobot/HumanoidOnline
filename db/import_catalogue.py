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
  - Manufacturer company evidence is replaced only where this importer owns it
    (`evidence_source.managed_by = 'CATALOGUE_IMPORT'`, migration 0013);
    manually maintained MANUFACTURER evidence is never deleted.

MANUFACTURER-ONLY MODE (`--manufacturers-only`)
  Imports manufacturer profiles and their company-level evidence and nothing
  else: robot files are not read, and robots, publication state,
  specifications, offers, capabilities, variants, deployments, images,
  providers, regions and robot-level evidence are not written. The data and its
  source attribution are validated before the transaction opens; the write is a
  single transaction. It is the production rollout path for manufacturer data.

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
from psycopg.types.json import Json

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

#: Marks the rows this importer OWNS in tables it shares with the seed and with
#: hand authoring (`specification`, `spec_definition`). It refreshes only these;
#: anything else occupying the same logical key is preserved and reported, never
#: overwritten. The catalogue is add-only and does not own what it did not write.
MANAGED_BY = "CATALOGUE_IMPORT"

#: Extra public columns on `pricing_offer` / `availability_offer`: separate facts
#: in separate columns (tax basis, box contents, seller warranty, order status,
#: edition match), so none of them has to be parsed back out of prose.
PRICING_DETAIL_COLUMNS = [
    "price_basis", "shipping_terms", "package_contents", "warranty_terms",
    "order_status_note", "edition_confirmed", "edition_note",
]
AVAILABILITY_DETAIL_COLUMNS = ["seller_wording", "delivery_estimate_label"]


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Evidence helper
# --------------------------------------------------------------------------- #
def insert_evidence(cur, subject_type: str, subject_id, ev: dict,
                    *, managed_by: str | None = None) -> None:
    cur.execute(
        """
        INSERT INTO evidence_source
            (subject_type, subject_id, source_url, source_type, source_title,
             excerpt, published_at, observed_at, verified_at, confidence, note,
             claim_fields, managed_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            subject_type, subject_id,
            ev.get("source_url"), ev["source_type"], ev.get("source_title"),
            ev.get("excerpt"), ev.get("published_at"), ev.get("observed_at"),
            ev.get("verified_at"), ev.get("confidence", "MEDIUM"), ev.get("note"),
            # MANUFACTURER rows name the profile fields they support (migration
            # 0013); every other row makes no field claim.
            ev.get("claim_fields"),
            managed_by,
        ),
    )


def _rowcount(result) -> int:
    """Rows affected by the statement just executed (0 when not reported)."""
    count = getattr(result, "rowcount", 0) or 0
    return count if count > 0 else 0


# --------------------------------------------------------------------------- #
# Manufacturer profiles: validation and company-level evidence ownership
# --------------------------------------------------------------------------- #
#: Company facts that must be attributed to an evidence row whenever they are
#: asserted (docs/03 §8). `website_url` may be claimed but predates attribution.
MANUFACTURER_ATTRIBUTED_FIELDS = (
    "legal_name", "country_region_code", "headquarters_city", "incorporation",
    "operating_locations", "founded_year", "description", "target_markets",
    "commercial_model", "deployment_status", "deployment_note",
    "is_public_company", "ticker", "parent_company", "parent_listing",
    "parent_relationship",
)
MANUFACTURER_CLAIMABLE_FIELDS = frozenset(MANUFACTURER_ATTRIBUTED_FIELDS) | {"website_url"}
COMMERCIAL_STATUSES = frozenset({
    "UNKNOWN", "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
})
SOURCE_TYPES = frozenset({
    "MANUFACTURER_STORE", "MANUFACTURER_SITE", "PRESS_RELEASE", "NEWS_ARTICLE",
    "ANALYST_REPORT", "FINANCIAL_FILING", "DIRECT_QUOTE", "CONFERENCE",
    "INTERVIEW", "OTHER",
})
CONFIDENCE_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "VERIFIED"})
#: docs/26 §3.1 fixed provenance statement prefix.
AGENT_RETRIEVAL_PREFIX = "RETRIEVAL: AGENT_ASSISTED_RESEARCH"


def _asserted(m: dict, field: str) -> bool:
    value = m.get(field)
    if value is None or value == [] or value == "":
        return False
    # UNKNOWN is the explicit absence of a status claim (docs/03 §7).
    return not (field == "deployment_status" and value == "UNKNOWN")


def validate_manufacturer_profiles(data: dict) -> list[str]:
    """Every reason `manufacturers.json` must not be written, or [] when clean.

    Pure (no database): the vocabularies, the three-state listing rule and the
    source-attribution rule `db/validate_catalogue.py` enforces after an import,
    checked BEFORE one, so an invalid profile never reaches a transaction.
    """
    rows = data.get("manufacturers")
    if not isinstance(rows, list) or not rows:
        return ["manufacturers.json has no non-empty 'manufacturers' list"]

    errors: list[str] = []
    seen: set[str] = set()
    for i, m in enumerate(rows):
        slug = m.get("slug")
        where = slug if isinstance(slug, str) and slug.strip() else f"manufacturers[{i}]"
        if where != slug:
            errors.append(f"{where}: missing slug")
        elif slug in seen:
            errors.append(f"{slug}: duplicate slug")
        else:
            seen.add(slug)
        if not isinstance(m.get("name"), str) or not m["name"].strip():
            errors.append(f"{where}: missing name")

        status = m.get("deployment_status")
        if status is not None and status not in COMMERCIAL_STATUSES:
            errors.append(f"{where}: deployment_status {status!r} is not a commercial_status")
        listed = m.get("is_public_company")
        if listed not in (True, False, None):
            errors.append(f"{where}: is_public_company must be true, false or null")
        if m.get("ticker") and listed is not True:
            errors.append(f"{where}: ticker given for an entity not recorded as listed")
        has_parent_detail = m.get("parent_listing") or m.get("parent_relationship")
        if has_parent_detail and not m.get("parent_company"):
            errors.append(f"{where}: parent listing/relationship without parent_company")
        year = m.get("founded_year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int)
                                 or not 1900 <= year <= 2100):
            errors.append(f"{where}: founded_year {year!r} outside 1900-2100")
        for field in ("operating_locations", "target_markets"):
            value = m.get(field)
            if value is not None and not (
                isinstance(value, list) and all(isinstance(v, str) for v in value)
            ):
                errors.append(f"{where}: {field} must be a list of strings")

        claimed: set[str] = set()
        for j, ev in enumerate(m.get("evidence") or []):
            at = f"{where} evidence[{j}]"
            if ev.get("source_type") not in SOURCE_TYPES:
                errors.append(f"{at}: source_type {ev.get('source_type')!r} is not a source_type")
            if ev.get("confidence", "MEDIUM") not in CONFIDENCE_LEVELS:
                errors.append(
                    f"{at}: confidence {ev.get('confidence')!r} is not a confidence_level"
                )
            if not ev.get("observed_at"):
                errors.append(f"{at}: missing observed_at")
            fields = ev.get("claim_fields")
            if fields is not None:
                if not isinstance(fields, list) or any(
                    f not in MANUFACTURER_CLAIMABLE_FIELDS for f in fields
                ):
                    errors.append(f"{at}: claim_fields names an unknown profile field")
                else:
                    claimed |= set(fields)
            if (ev.get("note") or "").startswith(AGENT_RETRIEVAL_PREFIX) and ev.get("verified_at"):
                errors.append(f"{at}: agent-assisted research row marked verified")

        unattributed = [f for f in MANUFACTURER_ATTRIBUTED_FIELDS
                        if _asserted(m, f) and f not in claimed]
        if unattributed:
            errors.append(f"{where}: asserted but no evidence row claims: "
                          + ", ".join(unattributed))
    return errors


def replace_manufacturer_evidence(cur, manufacturer_id, evidence: list[dict]) -> dict:
    """Refresh ONE manufacturer's company-level evidence without touching rows
    this importer does not own.

    * `managed_by = CATALOGUE_IMPORT` rows are the importer's: deleted, then the
      catalogue's rows are re-inserted with that marker, so repeated runs never
      duplicate them.
    * An UNMARKED row is adopted (replaced by its marked copy) only when stronger
      provenance shows it is an untouched row written by an import that predates
      the marker (migration 0013): EVERY column the importer writes (URL, type,
      title, excerpt, published/observed/verified dates, confidence, note) equals
      this catalogue source, and it carries no `claim_fields`, which only
      post-0013 writers set. URL, type and date alone never establish ownership.
    * An unmarked row that shares a catalogue source's URL, type and observed
      date but differs in any of that content was edited, or written by someone
      else. It is PRESERVED and returned as an ambiguous collision: never adopted,
      never overwritten.
    * Every other unmarked row is manually maintained and is left in place.
    """
    removed = _rowcount(cur.execute(
        "DELETE FROM evidence_source "
        "WHERE subject_type='MANUFACTURER' AND subject_id=%s AND managed_by = %s",
        (manufacturer_id, MANAGED_BY),
    ))
    adopted = 0
    collisions: list[str] = []
    for ev in evidence:
        adopted += _rowcount(cur.execute(
            """
            DELETE FROM evidence_source
            WHERE subject_type='MANUFACTURER' AND subject_id=%s
              AND managed_by IS NULL AND claim_fields IS NULL
              AND source_url IS NOT DISTINCT FROM %s AND source_type = %s
              AND source_title IS NOT DISTINCT FROM %s
              AND excerpt IS NOT DISTINCT FROM %s
              AND published_at IS NOT DISTINCT FROM %s::date
              AND observed_at::date IS NOT DISTINCT FROM %s::date
              AND verified_at::date IS NOT DISTINCT FROM %s::date
              AND confidence = %s
              AND note IS NOT DISTINCT FROM %s
            """,
            (
                manufacturer_id, ev.get("source_url"), ev["source_type"],
                ev.get("source_title"), ev.get("excerpt"), ev.get("published_at"),
                ev.get("observed_at"), ev.get("verified_at"),
                ev.get("confidence", "MEDIUM"), ev.get("note"),
            ),
        ))
        shared = cur.execute(
            """
            SELECT count(*) FROM evidence_source
            WHERE subject_type='MANUFACTURER' AND subject_id=%s AND managed_by IS NULL
              AND source_url IS NOT DISTINCT FROM %s AND source_type = %s
              AND observed_at::date IS NOT DISTINCT FROM %s::date
            """,
            (manufacturer_id, ev.get("source_url"), ev["source_type"], ev.get("observed_at")),
        ).fetchone()[0]
        if shared:
            collisions.append(
                f"{ev.get('source_url')} ({shared} unmarked row(s) share its URL, type "
                "and observed date but not its importer-written content)"
            )
        insert_evidence(cur, "MANUFACTURER", manufacturer_id, ev, managed_by=MANAGED_BY)
    return {"removed": removed, "adopted": adopted, "inserted": len(evidence),
            "collisions": collisions}


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


def import_manufacturers(cur, data: dict, region_id) -> dict:
    """Upsert manufacturer profiles by slug and refresh their company evidence.

    Shared by the full catalogue import and `--manufacturers-only`, so both write
    manufacturer data identically. Returns summed evidence counts and every
    ambiguous evidence collision (`slug: source_url (...)`).
    """
    totals: dict = {"manufacturers": 0, "removed": 0, "adopted": 0, "inserted": 0,
                    "collisions": []}
    for m in data["manufacturers"]:
        mid = cur.execute(
            """
            INSERT INTO manufacturer
                (slug, name, legal_name, country_region_id, headquarters_city,
                 incorporation, operating_locations, website_url,
                 founded_year, description, target_markets, commercial_model,
                 deployment_status, deployment_note, is_public_company, ticker,
                 parent_company, parent_listing, parent_relationship)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name, legal_name = EXCLUDED.legal_name,
                country_region_id = EXCLUDED.country_region_id,
                headquarters_city = EXCLUDED.headquarters_city,
                incorporation = EXCLUDED.incorporation,
                operating_locations = EXCLUDED.operating_locations,
                website_url = EXCLUDED.website_url, founded_year = EXCLUDED.founded_year,
                description = EXCLUDED.description, target_markets = EXCLUDED.target_markets,
                commercial_model = EXCLUDED.commercial_model,
                deployment_status = EXCLUDED.deployment_status,
                deployment_note = EXCLUDED.deployment_note,
                is_public_company = EXCLUDED.is_public_company, ticker = EXCLUDED.ticker,
                parent_company = EXCLUDED.parent_company,
                parent_listing = EXCLUDED.parent_listing,
                parent_relationship = EXCLUDED.parent_relationship
            RETURNING id
            """,
            (
                m["slug"], m["name"], m.get("legal_name"),
                region_id(m.get("country_region_code")), m.get("headquarters_city"),
                m.get("incorporation"), m.get("operating_locations"), m.get("website_url"),
                m.get("founded_year"), m.get("description"), m.get("target_markets"),
                m.get("commercial_model"), m.get("deployment_status"),
                m.get("deployment_note"),
                # No default: a missing key is NULL (listing status unknown), never
                # FALSE. FALSE is a claim and needs a source (validate_catalogue).
                m.get("is_public_company"), m.get("ticker"),
                m.get("parent_company"), m.get("parent_listing"),
                m.get("parent_relationship"),
            ),
        ).fetchone()[0]
        # Refresh only this importer's own company evidence: idempotent, and
        # manually maintained rows survive (see replace_manufacturer_evidence).
        counts = replace_manufacturer_evidence(cur, mid, m.get("evidence") or [])
        totals["manufacturers"] += 1
        for key in ("removed", "adopted", "inserted"):
            totals[key] += counts[key]
        totals["collisions"].extend(f"{m['slug']}: {line}" for line in counts["collisions"])
    return totals


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


def import_spec_definitions(cur, data: dict, collisions: list[str]) -> None:
    """Upsert the long-tail spec keys this catalogue uses — its OWN ones only.

    `spec_definition` is shared with `db/seed/seed.sql`, which authors keys like
    `swappable_battery` with its own labels, units and `is_filterable` flags. A
    blanket UPSERT would let the catalogue quietly redefine a key it does not
    own, changing the meaning of every existing value pointing at it. So the
    UPDATE is conditional on `managed_by = MANAGED_BY`: an unmanaged definition
    keeps its own shape and is reported. The catalogue may still *reference* it —
    only redefining it is refused.
    """
    for d in data["spec_definitions"]:
        row = cur.execute(
            """
            INSERT INTO spec_definition
                (key, label, category, value_type, unit, is_filterable, sort_order, managed_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (key) DO UPDATE SET
                label = EXCLUDED.label, category = EXCLUDED.category,
                value_type = EXCLUDED.value_type, unit = EXCLUDED.unit,
                is_filterable = EXCLUDED.is_filterable, sort_order = EXCLUDED.sort_order
            WHERE spec_definition.managed_by = %s
            RETURNING id
            """,
            (d["key"], d["label"], d.get("category", "OTHER"), d["value_type"],
             d.get("unit"), d.get("is_filterable", False), d.get("sort_order", 0),
             MANAGED_BY, MANAGED_BY),
        ).fetchone()
        if row is None:
            # The conflicting row exists but is not ours: DO UPDATE ... WHERE
            # matched nothing, so nothing was written. Keep theirs, say so.
            owner = cur.execute(
                "SELECT coalesce(managed_by, 'seed/hand-authored') FROM spec_definition WHERE key = %s",
                (d["key"],),
            ).fetchone()[0]
            collisions.append(
                f"spec_definition {d['key']!r} already exists and is owned by "
                f"{owner} — its definition was preserved, not overwritten"
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
    # `specification` is NOT wholly owned here: the seed and hand authoring write
    # rows to the same table. Only this importer's own rows are replaced.
    cur.execute(
        "DELETE FROM specification WHERE robot_id = %s AND managed_by = %s",
        (robot_id, MANAGED_BY),
    )


# Columns the importer owns outright: catalogue FACTS, refreshed from JSON on
# every run. `is_published` is deliberately NOT among them — see below.
EDITORIAL_COLUMNS = ("is_published",)


def import_robot(cur, robot: dict, region_id, manufacturer_id,
                 capability_id, use_case_id, spec_definition=None,
                 collisions=None, *,
                 apply_publication_state: bool = False) -> None:
    """Upsert one robot.

    The master catalogue (what we know about a robot) and the public catalogue
    (what is currently approved for display) are two different things. This
    importer owns the first and must not silently rewrite the second: a routine
    fact refresh must never change what the public sees. So `is_published` is
    written when the row is FIRST created and preserved on every later import,
    unless a deliberate publishing operation opts in via
    `apply_publication_state`.

    Without this, `is_published` behaves like disposable importer-controlled
    data: stub entries carry `"is_published": false`, so any editorial decision
    to display them is silently reverted by the next import. That is exactly how
    46 stored robots once collapsed to 7 on screen.
    """
    specs = robot.get("specs", {})
    caveats = robot.get("spec_caveats")
    cols = ["slug", "manufacturer_id", "name", "model_code", "summary",
            "announced_year", "official_url", "spec_caveats",
            "commercial_status", "is_published"] + SPEC_COLUMNS
    vals = [
        robot["slug"], manufacturer_id(robot["manufacturer_slug"]), robot["name"],
        robot.get("model_code"), robot.get("summary"), robot.get("announced_year"),
        # The maker's page for this model, and the per-field caveats explaining
        # UNKNOWNs/conflicts. Both were carried by the JSON and dropped for want
        # of a column until migration 0011.
        robot.get("official_url"), Json(caveats) if caveats else None,
        # Absent maturity means UNVERIFIED, not ANNOUNCED: an omitted key must
        # not become a factual claim the file never made.
        robot.get("commercial_status", "UNKNOWN"), robot.get("is_published", False),
    ] + [specs.get(c) for c in SPEC_COLUMNS]

    # On INSERT every column is written: a brand-new record has no editorial
    # state to preserve. On UPDATE the editorial columns are held back.
    preserved = () if apply_publication_state else EDITORIAL_COLUMNS
    placeholders = ",".join(["%s"] * len(cols))
    updates = ",".join(
        f"{c} = EXCLUDED.{c}" for c in cols if c != "slug" and c not in preserved
    )
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
                 price_type, currency, price, price_min, price_max, billing_period,
                 note, is_current, price_basis, shipping_terms, package_contents,
                 warranty_terms, order_status_note, edition_confirmed, edition_note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                robot_id, vid_of(po.get("variant_slug")),
                _provider(cur, po.get("provider_slug")), region_id(po.get("region_code")),
                po["transaction_type"], po["price_type"], po.get("currency", "USD"),
                po.get("price"), po.get("price_min"), po.get("price_max"),
                po.get("billing_period", "ONE_TIME"), po.get("note"),
                # A retired offer keeps its row and its evidence; it simply stops
                # being current. `edition_confirmed` stays tri-state: absent in the
                # JSON means NOT ASSESSED (NULL), never "confirmed".
                po.get("is_current", True),
            ) + tuple(po.get(c) for c in PRICING_DETAIL_COLUMNS),
        ).fetchone()[0]
        for ev in po.get("evidence", []):
            insert_evidence(cur, "PRICING_OFFER", pid, ev)

    # Availability offers.
    for ao in robot.get("availability_offers", []):
        aid = cur.execute(
            """
            INSERT INTO availability_offer
                (robot_id, variant_id, provider_id, region_id, transaction_type,
                 availability_status, available_from, lead_time_days, min_order_qty,
                 note, is_current, seller_wording, delivery_estimate_label)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                robot_id, vid_of(ao.get("variant_slug")),
                _provider(cur, ao.get("provider_slug")), region_id(ao.get("region_code")),
                ao["transaction_type"], ao.get("availability_status", "ON_REQUEST"),
                ao.get("available_from"), ao.get("lead_time_days"),
                ao.get("min_order_qty"), ao.get("note"), ao.get("is_current", True),
            ) + tuple(ao.get(c) for c in AVAILABILITY_DETAIL_COLUMNS),
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
                 attribution, is_representative, representative_note,
                 display_approved_by, display_approved_at, captured_at, last_verified_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                robot_id, im["image_url"], im.get("source_url"), im.get("source_name"),
                src, im.get("image_type", "FRONT"),
                im.get("identity_status", "UNVERIFIED"),
                im.get("rights_status", "UNKNOWN"),
                im.get("usage_basis", "NONE"),
                im.get("is_official", False), im.get("is_primary", False),
                im.get("attribution"),
                im.get("is_representative", False), im.get("representative_note"),
                im.get("display_approved_by"), im.get("display_approved_at"),
                im.get("captured_at"), im.get("last_verified_at"),
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

    # Long-tail specs. Each carries its own attribution and edition scope: these
    # values have no evidence_source row (they are descriptive, not commercial
    # facts), so provenance travels with the value or it does not exist at all.
    # `spec_definition`/`collisions` default to None so a caller inspecting the
    # robot upsert alone (the publication-state tests do exactly this) need not
    # build a definition registry. They become required the moment there is
    # actually a long-tail spec to write: writing one without a registry is
    # impossible, and silently DROPPING it would lose an attributed fact. So
    # their absence fails loudly here rather than quietly skipping the loop.
    extended = robot.get("extended_specs", [])
    if extended and (spec_definition is None or collisions is None):
        raise ValueError(
            f"robot {robot['slug']!r} carries {len(extended)} extended_specs, which "
            "require both `spec_definition` and `collisions`"
        )
    for x in extended:
        definition_id, value_type = spec_definition(x["key"])
        existing = cur.execute(
            """
            SELECT coalesce(managed_by, 'seed/hand-authored') FROM specification
            WHERE robot_id = %s AND variant_id IS NULL AND definition_id = %s
            """,
            (robot_id, definition_id),
        ).fetchone()
        if existing is not None:
            # Our own rows were deleted above, so anything still here belongs to
            # someone else and occupies this logical key. Preserve it and report:
            # deleting only our rows is not enough if the insert then overwrites.
            collisions.append(
                f"robot {robot['slug']!r}: specification {x['key']!r} already exists "
                f"and is owned by {existing[0]} — the catalogue value was skipped, "
                f"the existing row preserved"
            )
            continue
        value = x.get("value")
        cur.execute(
            """
            INSERT INTO specification
                (robot_id, variant_id, definition_id, value_number, value_bool,
                 value_text, unit, managed_by, source_label, source_url, source_kind,
                 edition_scope, observed_at)
            VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                robot_id, definition_id,
                value if value_type == "NUMBER" else None,
                value if value_type == "BOOLEAN" else None,
                value if value_type == "TEXT" else None,
                x.get("unit"), MANAGED_BY, x.get("source_label"), x.get("source_url"),
                x.get("source_kind"), x.get("edition_scope"), x.get("observed_at"),
            ),
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
          -- A listing whose edition does not match this record is a qualified
          -- listing: it may be shown, but it never sets this robot's price.
          -- NULL (not assessed) keeps its existing behaviour.
          AND edition_confirmed IS DISTINCT FROM FALSE
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


class UnknownSlugs(SystemExit):
    """`--only` named robot slugs the catalogue does not contain."""


def select_robot_files(only: set[str] | None) -> list[Path]:
    """The robot files this run will import.

    `None` (the default) is every file — unchanged behaviour. A non-empty
    allowlist is validated against the catalogue HERE, before any connection is
    opened, so an unknown slug can never be discovered halfway through a
    partially written import.
    """
    available = {p.stem: p for p in sorted(ROBOTS_DIR.glob("*.json"))}
    if only is None:
        return list(available.values())
    unknown = sorted(only - set(available))
    if unknown:
        raise UnknownSlugs(
            "unknown robot slug(s) in --only: " + ", ".join(unknown)
            + f" (catalogue has {len(available)} records)"
        )
    return [available[s] for s in sorted(only)]


def _ancestors(regions: dict, codes: set[str]) -> set[str]:
    """Referenced region codes plus every `parent_code` above them.

    A scoped import must not create a region whose parent is absent: `DE`
    without `EU` would break the applicability walk the catalogue depends on.
    """
    by_code = {r["code"]: r for r in regions["regions"]}
    out: set[str] = set()
    frontier = list(codes)
    while frontier:
        code = frontier.pop()
        if code in out or code not in by_code:
            continue
        out.add(code)
        parent = by_code[code].get("parent_code")
        if parent:
            frontier.append(parent)
    return out


def scoped_dependencies(robots: list[dict], regions: dict) -> dict[str, set[str]]:
    """Shared entities the SELECTED records actually reference.

    Restricting the shared upserts to these is what keeps a scoped import
    scoped: without it, importing one robot would still rewrite every
    manufacturer, provider, capability, use case and spec definition in the
    catalogue — rows belonging to robots the caller did not select.
    """
    deps: dict[str, set[str]] = {
        "manufacturers": set(), "providers": set(), "regions": set(),
        "capabilities": set(), "use_cases": set(), "spec_definitions": set(),
    }
    for r in robots:
        if r.get("manufacturer_slug"):
            deps["manufacturers"].add(r["manufacturer_slug"])
        for kind in ("pricing_offers", "availability_offers", "deployments"):
            for row in r.get(kind) or []:
                if row.get("provider_slug"):
                    deps["providers"].add(row["provider_slug"])
                if row.get("region_code"):
                    deps["regions"].add(row["region_code"])
        for c in r.get("capabilities") or []:
            slug = c.get("capability_slug") or c.get("slug")
            if slug:
                deps["capabilities"].add(slug)
        for f in r.get("use_case_fits") or []:
            if f.get("use_case_slug"):
                deps["use_cases"].add(f["use_case_slug"])
        for x in r.get("extended_specs") or []:
            deps["spec_definitions"].add(x["key"])
    # A provider may be owned by a manufacturer the selection does not name.
    deps["regions"] = _ancestors(regions, deps["regions"])
    return deps


def _narrow(data: dict, key: str, field: str, keep: set[str]) -> dict:
    """The same payload shape, carrying only the entries `keep` names."""
    return {key: [row for row in data[key] if row.get(field) in keep]}


# --------------------------------------------------------------------------- #
def run(url: str, *, apply_publication_state: bool = False,
        only: set[str] | None = None) -> None:
    regions = _load(CATALOGUE_DIR / "regions.json")
    providers = _load(CATALOGUE_DIR / "providers.json")
    capabilities = _load(CATALOGUE_DIR / "capabilities.json")
    use_cases = _load(CATALOGUE_DIR / "use_cases.json")
    spec_definitions = _load(CATALOGUE_DIR / "spec_definitions.json")
    manufacturers = _load(CATALOGUE_DIR / "manufacturers.json")

    # Validated BEFORE the connection opens: an unknown slug aborts with nothing
    # written, and the filter is applied before any robot or child-row mutation.
    robot_files = select_robot_files(only)
    loaded = [_load(p) for p in robot_files]

    if only is not None:
        deps = scoped_dependencies(loaded, regions)
        # A provider's own manufacturer must exist before the provider upsert
        # resolves `manufacturer_slug`.
        provider_rows = [p for p in providers["providers"] if p["slug"] in deps["providers"]]
        deps["manufacturers"] |= {
            p["manufacturer_slug"] for p in provider_rows if p.get("manufacturer_slug")
        }
        manufacturer_rows = [
            m for m in manufacturers["manufacturers"] if m["slug"] in deps["manufacturers"]
        ]
        deps["regions"] |= _ancestors(regions, {
            m["country_region_code"] for m in manufacturer_rows
            if m.get("country_region_code")
        } | {
            p["country_region_code"] for p in provider_rows if p.get("country_region_code")
        })
        regions = _narrow(regions, "regions", "code", deps["regions"])
        manufacturers = {"manufacturers": manufacturer_rows}
        providers = {"providers": provider_rows}
        capabilities = _narrow(capabilities, "capabilities", "slug", deps["capabilities"])
        use_cases = _narrow(use_cases, "use_cases", "slug", deps["use_cases"])
        spec_definitions = _narrow(
            spec_definitions, "spec_definitions", "key", deps["spec_definitions"]
        )

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

            def spec_definition(key):
                """(id, value_type) for a long-tail spec key. The value_type decides
                which of value_number/value_bool/value_text carries the value, so a
                definition and its values can never disagree about their own type."""
                r = cur.execute(
                    "SELECT id, value_type FROM spec_definition WHERE key=%s", (key,)
                ).fetchone()
                if not r:
                    raise SystemExit(f"unknown spec_definition key referenced: {key!r}")
                return r[0], r[1]

            collisions: list[str] = []

            import_regions(cur, regions)
            manufacturer_totals = import_manufacturers(cur, manufacturers, region_id)
            import_providers(cur, providers, region_id, manufacturer_id)
            import_capabilities(cur, capabilities)
            import_use_cases(cur, use_cases)
            import_spec_definitions(cur, spec_definitions, collisions)

            n_robots = 0
            for robot in loaded:
                import_robot(cur, robot, region_id, manufacturer_id,
                             capability_id, use_case_id, spec_definition, collisions,
                             apply_publication_state=apply_publication_state)
                n_robots += 1

            stored, displayed = cur.execute(
                "SELECT count(*), count(*) FILTER (WHERE is_published) FROM robot"
            ).fetchone()

        conn.commit()

    if only is not None:
        print(f"SCOPED IMPORT — {n_robots} selected record(s): "
              + ", ".join(sorted(only)))
    print(f"Catalogue import OK: {len(manufacturers['manufacturers'])} manufacturers, "
          f"{len(providers['providers'])} providers, {n_robots} robots.")
    # Stored vs displayed, always reported: the master catalogue is cumulative,
    # the public view is a subset of it, and a surprising gap should be visible
    # the moment it appears rather than discovered later in a browser.
    print(f"Catalogue state: {stored} stored, {displayed} displayed.")
    # Preserved, not silently skipped: a collision means someone else's row held a
    # key this catalogue also describes, and their row won. Saying so is the point.
    for line in collisions:
        print(f"PRESERVED (not overwritten): {line}")
    if collisions:
        print(f"{len(collisions)} unmanaged record(s) preserved on logical-key collision.")
    for line in manufacturer_totals["collisions"]:
        print(f"AMBIGUOUS EVIDENCE COLLISION (preserved, not adopted): {line}")
    if apply_publication_state:
        print("Publication state was REWRITTEN from JSON (--apply-publication-state).")


class ManufacturerImportAborted(SystemExit):
    """`--manufacturers-only` refused before writing anything."""


def run_manufacturers_only(url: str, *, manufacturers_path: Path | None = None) -> dict:
    """Import ONLY manufacturer profiles and their company-level evidence.

    Reads `manufacturers.json` and nothing else. No robot file is opened, and no
    robot, publication flag, specification, offer, capability, variant,
    deployment, image, provider, region or robot-level evidence row is written.

    Order: validate the file (vocabularies, listing rule, source attribution)
    -> open ONE transaction -> confirm every headquarters region already exists
    (this mode never writes regions) -> upsert the profiles and refresh only the
    importer's own company evidence -> commit. Any failure before the commit
    rolls the whole transaction back, so nothing is half-written.
    """
    path = manufacturers_path or CATALOGUE_DIR / "manufacturers.json"
    manufacturers = _load(path)
    errors = validate_manufacturer_profiles(manufacturers)
    if errors:
        raise ManufacturerImportAborted(
            "manufacturer-only import refused before writing — "
            f"{len(errors)} problem(s) in {path.name}:\n  " + "\n  ".join(errors)
        )

    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO humanoid, public")
            regions = dict(cur.execute("SELECT code, id FROM region").fetchall())
            missing = sorted({
                m["country_region_code"] for m in manufacturers["manufacturers"]
                if m.get("country_region_code") and m["country_region_code"] not in regions
            })
            if missing:
                raise ManufacturerImportAborted(
                    "manufacturer-only import refused before writing — region code(s) "
                    f"not in the database: {', '.join(missing)}. This mode does not "
                    "write regions; load them through the catalogue import first."
                )
            totals = import_manufacturers(
                cur, manufacturers, lambda code: regions[code] if code else None
            )
            preserved = cur.execute(
                "SELECT count(*) FROM evidence_source "
                "WHERE subject_type='MANUFACTURER' AND managed_by IS DISTINCT FROM %s",
                (MANAGED_BY,),
            ).fetchone()[0]
        conn.commit()

    totals["preserved"] = preserved
    print(f"MANUFACTURER-ONLY IMPORT OK: {totals['manufacturers']} "
          "manufacturer profile(s) upserted.")
    print(f"Company evidence: {totals['inserted']} catalogue row(s) written, "
          f"{totals['removed']} previous importer row(s) replaced, "
          f"{totals['adopted']} pre-marker importer row(s) adopted, "
          f"{preserved} unmarked row(s) preserved, "
          f"{len(totals['collisions'])} ambiguous collision(s).")
    # Preserved, never adopted: an unmarked row sharing a source's URL/type/date
    # but not its content may be an editor's correction. Saying so is the point.
    for line in totals["collisions"]:
        print(f"AMBIGUOUS EVIDENCE COLLISION (preserved, not adopted): {line}")
    print("Robot records, publication state and robot-level evidence were not read or written.")
    return totals


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Import the WS2B verified catalogue")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument(
        "--apply-publication-state",
        action="store_true",
        help="ALSO rewrite is_published from the JSON files. This is a publishing "
             "operation, not a fact refresh: it changes what the public sees. "
             "Omitted (the default), an import updates catalogue facts and leaves "
             "the existing publication state of every known robot untouched.",
    )
    ap.add_argument(
        "--only",
        action="append",
        metavar="SLUG",
        help="Import ONLY these robot slugs (repeatable, or comma-separated). "
             "Shared entities (regions, manufacturers, providers, capabilities, "
             "use cases, spec definitions) are narrowed to what the selected "
             "records reference. Unknown slugs abort before anything is written. "
             "Omitted, every catalogue record is imported, exactly as before.",
    )
    ap.add_argument(
        "--manufacturers-only",
        action="store_true",
        help="Import ONLY manufacturer profiles and their company-level evidence "
             "from manufacturers.json. No robot file is read, and no robot, "
             "publication flag, specification, offer, capability, variant, "
             "deployment, image, provider, region or robot-level evidence row is "
             "written. Data and source attribution are validated before writing, "
             "in one transaction. Cannot be combined with --only or "
             "--apply-publication-state.",
    )
    args = ap.parse_args(argv)
    if args.manufacturers_only:
        conflicts = [flag for flag, given in (
            ("--only", bool(args.only)),
            ("--apply-publication-state", args.apply_publication_state),
        ) if given]
        if conflicts:
            ap.error("--manufacturers-only cannot be combined with " + ", ".join(conflicts))
    if not args.database_url:
        ap.error("no database URL: pass --database-url or set DATABASE_URL")
    if args.manufacturers_only:
        run_manufacturers_only(normalize_url(args.database_url))
        return
    only = None
    if args.only:
        only = {s.strip() for item in args.only for s in item.split(",") if s.strip()}
        if not only:
            ap.error("--only was given with no slugs")
    run(normalize_url(args.database_url), only=only,
        apply_publication_state=args.apply_publication_state)


if __name__ == "__main__":
    main()
