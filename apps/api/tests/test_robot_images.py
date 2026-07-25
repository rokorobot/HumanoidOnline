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


def _insert_image(robot_id, *, identity, rights, source_type="MANUFACTURER") -> uuid.UUID:
    with engine.begin() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        return c.execute(
            text(
                "INSERT INTO robot_image "
                "(robot_id, image_url, source_url, source_name, source_type, "
                " identity_status, rights_status, is_primary, attribution) "
                "VALUES (:r, :u, :su, :sn, :st, :idn, :rgt, true, :at) RETURNING id"
            ),
            {
                "r": robot_id, "u": "https://example.com/robot.jpg",
                "su": "https://example.com/source", "sn": "Example Source",
                "st": source_type, "idn": identity, "rgt": rights,
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
    # (identity, rights) -> should the image be display-eligible?
    matrix = [
        ("VERIFIED", "PERMITTED", True),
        ("VERIFIED", "ATTRIBUTION_REQUIRED", True),
        ("VERIFIED", "UNKNOWN", False),          # UNKNOWN rights != PERMITTED
        ("VERIFIED", "RESTRICTED", False),
        ("UNVERIFIED", "PERMITTED", False),      # identity not established
        ("UNVERIFIED", "UNKNOWN", False),
    ]
    for identity, rights, should_display in matrix:
        img_id = _insert_image(rid, identity=identity, rights=rights)
        try:
            imgs = _detail_images(client)
            shown = len(imgs) == 1
            assert shown == should_display, (identity, rights, imgs)
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
