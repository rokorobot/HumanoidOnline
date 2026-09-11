"""Catalogue offer integrity — provenance, seller identity, canonical identity.

`db/validate_catalogue.py` proves G2 against an imported database, but only for
*published* robots and only where Postgres exists. These checks run on the
repository files themselves, for every record whether published or not, so a
fact cannot enter the master catalogue in a shape that becomes a violation the
moment someone publishes it.

The failures pinned here are the ones a hand-authored distributor offer
invites:

* an offer attributed to one seller but evidenced by another seller's page —
  the data-level form of "provider A's availability must never surface
  provider B's price" (docs/03 §4);
* an offer or evidence row missing what makes it provenance (source URL,
  observation date);
* a VERIFIED claim with no verification date (docs/03 §5);
* an enum label that `db/schema.sql` does not define (docs/03: never invent
  enum values — "On Demand" is retailer wording, not a status);
* a price shaped differently from what the database will accept;
* the same robot entering the catalogue twice under two slugs.

No database: this operates purely on repository files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
SCHEMA = REPO_ROOT / "db" / "schema.sql"

ROBOTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((CATALOGUE / "robots").glob("*.json"))
}
PROVIDERS = {
    p["slug"]: p
    for p in json.loads((CATALOGUE / "providers.json").read_text(encoding="utf-8"))["providers"]
}
REGIONS = {
    r["code"]
    for r in json.loads((CATALOGUE / "regions.json").read_text(encoding="utf-8"))["regions"]
}
OFFER_KINDS = ("pricing_offers", "availability_offers")


def _schema_enums() -> dict[str, set[str]]:
    """Enum labels exactly as the canonical DDL defines them (AGENTS.md rule 2)."""
    sql = re.sub(r"--[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))
    return {
        name: set(re.findall(r"'([^']+)'", body))
        for name, body in re.findall(r"CREATE TYPE (\w+) AS ENUM \((.*?)\);", sql, flags=re.S)
    }


ENUMS = _schema_enums()


def _offers():
    for slug, robot in ROBOTS.items():
        for kind in OFFER_KINDS:
            for offer in robot.get(kind, []):
                yield slug, kind, offer


def _evidence_rows():
    for slug, robot in ROBOTS.items():
        for ev in robot.get("commercial_status_evidence", []):
            yield slug, "commercial_status", ev
        for kind in (*OFFER_KINDS, "deployments"):
            for item in robot.get(kind, []):
                for ev in item.get("evidence", []):
                    yield slug, kind, ev


def _host(url: str | None) -> str:
    return (urlparse(url or "").hostname or "").removeprefix("www.")


def _identity(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def test_the_schema_enums_were_actually_read():
    """Guards the parser: an empty result would let every enum check pass vacuously."""
    for name in ("commercial_status", "availability_status", "transaction_type",
                 "price_type", "billing_period", "source_type", "confidence_level",
                 "mobility_type", "autonomy_level"):
        assert ENUMS.get(name), f"no labels parsed for enum {name!r}"
    assert "UNKNOWN" in ENUMS["commercial_status"]
    assert "ON_DEMAND" not in ENUMS["availability_status"]


def test_every_enum_label_exists_in_the_schema():
    for slug, robot in ROBOTS.items():
        assert robot["commercial_status"] in ENUMS["commercial_status"], slug
        for field, enum in (("mobility", "mobility_type"), ("autonomy", "autonomy_level")):
            value = robot["specs"].get(field)
            assert value is None or value in ENUMS[enum], f"{slug}.specs.{field} = {value!r}"
    for slug, kind, offer in _offers():
        assert offer["transaction_type"] in ENUMS["transaction_type"], slug
        if kind == "pricing_offers":
            assert offer["price_type"] in ENUMS["price_type"], slug
            assert offer.get("billing_period", "ONE_TIME") in ENUMS["billing_period"], slug
        else:
            # The importer's own default when the key is absent.
            status = offer.get("availability_status", "ON_REQUEST")
            assert status in ENUMS["availability_status"], f"{slug}: {status!r}"
    for slug, where, ev in _evidence_rows():
        assert ev["source_type"] in ENUMS["source_type"], f"{slug} {where}"
        assert ev.get("confidence", "MEDIUM") in ENUMS["confidence_level"], f"{slug} {where}"


def test_offers_reference_providers_and_regions_that_exist():
    for slug, kind, offer in _offers():
        provider, region = offer.get("provider_slug"), offer.get("region_code")
        assert provider is None or provider in PROVIDERS, f"{slug} {kind}: provider {provider!r}"
        assert region is None or region in REGIONS, f"{slug} {kind}: region {region!r}"


def test_every_commercial_fact_row_carries_provenance():
    for slug, robot in ROBOTS.items():
        for kind in (*OFFER_KINDS, "deployments"):
            for item in robot.get(kind, []):
                assert item.get("evidence"), f"{slug}: a {kind} row with no evidence"
    for slug, where, ev in _evidence_rows():
        assert ev.get("source_url"), f"{slug} {where}: evidence with no source_url"
        assert ev.get("observed_at"), f"{slug} {where}: evidence with no observed_at"


def test_verified_confidence_requires_a_verification_date():
    """Only VERIFIED may render a Verified badge, and it needs `verified_at`."""
    for slug, where, ev in _evidence_rows():
        if ev.get("confidence") == "VERIFIED":
            assert ev.get("verified_at"), f"{slug} {where}: VERIFIED with no verified_at"


def test_prices_have_the_shape_the_database_enforces():
    """Mirrors `chk_price_type_shape`, plus: a point price is never 0 (UNKNOWN ≠ 0)."""
    for slug, kind, offer in _offers():
        if kind != "pricing_offers":
            continue
        price_type = offer["price_type"]
        price, low, high = offer.get("price"), offer.get("price_min"), offer.get("price_max")
        if price_type == "QUOTE_ONLY":
            assert price is None and low is None and high is None, slug
        elif price_type == "RANGE":
            assert price is None and low is not None and high is not None, slug
            assert high >= low, slug
        else:
            assert price is not None and price > 0, slug
            assert low is None and high is None, slug


def test_a_distributor_offer_is_evidenced_by_that_distributor():
    """A seller's price or availability can only be sourced from that seller.

    Exact host match on purpose: RobotShop's US and EU storefronts are separate
    providers that share a registrable domain, so a suffix match would let a US
    offer cite the EU storefront — the cross-attribution this test exists for.
    """
    for slug, kind, offer in _offers():
        provider = PROVIDERS.get(offer.get("provider_slug"))
        if provider is None or provider["type"] != "DISTRIBUTOR":
            continue
        home = _host(provider["website_url"])
        for ev in offer.get("evidence", []):
            assert _host(ev["source_url"]) == home, (
                f"{slug} {kind}: {provider['slug']} offer evidenced by "
                f"{ev['source_url']!r}, not by {home!r}"
            )


def test_no_robot_is_catalogued_twice():
    """One robot, one slug: same maker + same name or model code is a duplicate."""
    by_name: dict[tuple[str, str], str] = {}
    by_code: dict[tuple[str, str], str] = {}
    for slug, robot in ROBOTS.items():
        name_key = (robot["manufacturer_slug"], _identity(robot["name"]))
        assert name_key not in by_name, f"{slug} duplicates {by_name[name_key]} by name"
        by_name[name_key] = slug
        if robot.get("model_code"):
            code_key = (robot["manufacturer_slug"], _identity(robot["model_code"]))
            assert code_key not in by_code, f"{slug} duplicates {by_code[code_key]} by model code"
            by_code[code_key] = slug
