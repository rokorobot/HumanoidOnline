"""MEDIA-01 verified-imagery tests (against the seeded database).

Proves the display-eligibility gate: an image crosses the API boundary ONLY when
identity_status=VERIFIED AND rights_status IN (PERMITTED, ATTRIBUTION_REQUIRED) —
never because `image_url` is non-null. Also proves the schema forbids a
GENERATED identity-image source outright.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import engine

ROBOT = "digit"  # published in the seed dataset


def _robot_id() -> uuid.UUID:
    with engine.connect() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        return c.execute(
            text("SELECT id FROM robot WHERE slug=:s"), {"s": ROBOT}
        ).scalar_one()


def _insert_image(
    robot_id, *, identity, rights, usage="NONE", source_type="MANUFACTURER"
) -> uuid.UUID:
    with engine.begin() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        return c.execute(
            text(
                "INSERT INTO robot_image "
                "(robot_id, image_url, source_url, source_name, source_type, "
                " identity_status, rights_status, usage_basis, is_primary, attribution) "
                "VALUES (:r, :u, :su, :sn, :st, :idn, :rgt, :ub, true, :at) RETURNING id"
            ),
            {
                "r": robot_id, "u": "https://example.com/robot.jpg",
                "su": "https://example.com/source", "sn": "Example Source",
                "st": source_type, "idn": identity, "rgt": rights, "ub": usage,
                "at": "© Example",
            },
        ).scalar_one()


def _delete_image(img_id) -> None:
    with engine.begin() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        c.execute(text("DELETE FROM robot_image WHERE id=:i"), {"i": img_id})


def _detail_images(client) -> list[dict]:
    r = client.get(f"/api/robots/{ROBOT}")
    assert r.status_code == 200, r.text
    return r.json()["images"]


# ---- baseline: no images -> IMAGE_UNAVAILABLE (empty list) ----------------

def test_no_images_returns_empty(client, database_url) -> None:
    # The seed/catalogue ship no robot_image rows, so the detail carries none and
    # the UI renders IMAGE_UNAVAILABLE.
    assert _detail_images(client) == []


# ---- the display-eligibility negative matrix ------------------------------

def test_display_eligibility_matrix(client, database_url) -> None:
    rid = _robot_id()
    # (identity, rights, usage_basis) -> should the image be display-eligible?
    matrix = [
        ("VERIFIED", "PERMITTED", "NONE", True),
        ("VERIFIED", "ATTRIBUTION_REQUIRED", "NONE", True),
        ("VERIFIED", "UNKNOWN", "NONE", False),          # UNKNOWN + no policy basis
        ("VERIFIED", "RESTRICTED", "NONE", False),
        ("UNVERIFIED", "PERMITTED", "NONE", False),      # identity not established
        ("UNVERIFIED", "UNKNOWN", "NONE", False),
        # §H2: official-manufacturer-media policy authorises display when rights are
        # merely UNKNOWN (no false license), but RESTRICTED still blocks.
        ("VERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", True),
        ("VERIFIED", "RESTRICTED", "OFFICIAL_MANUFACTURER_MEDIA", False),
        ("UNVERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", False),  # identity gate
    ]
    for identity, rights, usage, should_display in matrix:
        img_id = _insert_image(rid, identity=identity, rights=rights, usage=usage)
        try:
            imgs = _detail_images(client)
            shown = len(imgs) == 1
            assert shown == should_display, (identity, rights, usage, imgs)
            if shown:
                assert imgs[0]["image_url"] == "https://example.com/robot.jpg"
                assert imgs[0]["source_name"] == "Example Source"
        finally:
            _delete_image(img_id)


# ---- image_url alone is NEVER sufficient ----------------------------------

def test_image_url_present_but_uncleared_is_hidden(client, database_url) -> None:
    rid = _robot_id()
    # A perfectly good URL, but identity unverified + rights unknown -> hidden.
    img_id = _insert_image(rid, identity="UNVERIFIED", rights="UNKNOWN")
    try:
        assert _detail_images(client) == []
    finally:
        _delete_image(img_id)


# ---- schema forbids a GENERATED identity-image source ---------------------

def test_generated_source_type_is_rejected_by_schema(client, database_url) -> None:
    rid = _robot_id()
    with pytest.raises((DBAPIError, psycopg.errors.InvalidTextRepresentation)):
        with engine.begin() as c:
            c.execute(text("SET search_path TO humanoid, public"))
            c.execute(
                text(
                    "INSERT INTO robot_image (robot_id, image_url, source_type) "
                    "VALUES (:r, :u, 'GENERATED')"
                ),
                {"r": rid, "u": "https://example.com/fake.jpg"},
            )
