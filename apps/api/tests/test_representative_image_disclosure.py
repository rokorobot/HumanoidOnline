"""MEDIA-01 §4 — a representative image must disclose itself on every public path.

`RobotImageRead.is_representative` / `representative_note` are DEFAULTED fields.
`serialize_detail` built the object without passing them, so the omission could
not fail: the API served `false`/`null` for rows the database correctly marked
representative, the gallery took its `is_official ? ... : "Verified ✓"` branch,
and an owner-approved stand-in was published as a verified image of that exact
edition — the precise claim the designation exists to prevent.

That class of defect is invisible to a component test (props were fine) and to a
schema test (the field existed). It is only catchable by asserting through the
real read and serialization paths, which is what this module does — for the
human surface, the agent surface, and the parity between them.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import get_robot
from app.services.evidence_refs import EvidenceRefKeyring

ROBOT = "digit"  # published in the seed dataset

KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([1]) * 64})

NOTE = "Representative R1 image; EDU appearance and equipment may vary."


def _robot_id() -> uuid.UUID:
    with engine.connect() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        return c.execute(
            text("SELECT id FROM robot WHERE slug=:s"), {"s": ROBOT}
        ).scalar_one()


def _insert_image(
    robot_id,
    *,
    identity="VERIFIED",
    rights="PERMITTED",
    usage="NONE",
    representative=False,
    note=None,
    official=False,
) -> uuid.UUID:
    with engine.begin() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        return c.execute(
            text(
                "INSERT INTO robot_image "
                "(robot_id, image_url, source_url, source_name, source_type, "
                " identity_status, rights_status, usage_basis, is_primary, "
                " is_official, attribution, is_representative, representative_note) "
                "VALUES (:r, :u, :su, :sn, :st, :idn, :rgt, :ub, true, :off, :at, "
                "        :rep, :note) RETURNING id"
            ),
            {
                "r": robot_id,
                "u": "https://example.com/robot.jpg",
                "su": "https://example.com/source",
                "sn": "Example Source",
                "st": "DISTRIBUTOR",
                "idn": identity,
                "rgt": rights,
                "ub": usage,
                "off": official,
                "at": "© Example",
                "rep": representative,
                "note": note,
            },
        ).scalar_one()


def _delete_image(img_id) -> None:
    with engine.begin() as c:
        c.execute(text("SET search_path TO humanoid, public"))
        c.execute(text("DELETE FROM robot_image WHERE id=:i"), {"i": img_id})


def _http_images(client) -> list[dict]:
    r = client.get(f"/api/robots/{ROBOT}")
    assert r.status_code == 200, r.text
    return r.json()["images"]


def _agent_images() -> list:
    with SessionLocal() as s:
        return get_robot(s, ROBOT, keyring=KEYRING).data.images


def _representative_row(rid):
    """An owner-approved stand-in exactly as the catalogue records one."""
    return _insert_image(
        rid,
        identity="UNVERIFIED",
        rights="UNKNOWN",
        usage="OWNER_APPROVED_DISPLAY",
        representative=True,
        note=NOTE,
    )


# ---- the human read path --------------------------------------------------


def test_the_representative_designation_survives_the_public_read(client, database_url):
    rid = _robot_id()
    img_id = _representative_row(rid)
    try:
        imgs = _http_images(client)
        assert len(imgs) == 1, imgs
        assert imgs[0]["is_representative"] is True
        assert imgs[0]["representative_note"] == NOTE
    finally:
        _delete_image(img_id)


def test_a_verified_image_is_not_labelled_representative(client, database_url):
    """The fix must not relabel genuine imagery: the flag reports the row."""
    rid = _robot_id()
    img_id = _insert_image(rid, identity="VERIFIED", rights="PERMITTED", official=True)
    try:
        imgs = _http_images(client)
        assert len(imgs) == 1, imgs
        assert imgs[0]["is_representative"] is False
        assert imgs[0]["representative_note"] is None
    finally:
        _delete_image(img_id)


def test_the_note_is_never_served_without_the_designation(client, database_url):
    """A note alone would render nothing: the UI keys the disclosure off the flag."""
    rid = _robot_id()
    img_id = _representative_row(rid)
    try:
        img = _http_images(client)[0]
        assert img["is_representative"] is True
        assert img["representative_note"], "a stand-in must arrive with its note"
    finally:
        _delete_image(img_id)


# ---- the agent read path, and parity with the human one -------------------


def test_the_agent_surface_carries_the_same_disclosure(client, database_url):
    rid = _robot_id()
    img_id = _representative_row(rid)
    try:
        agent = _agent_images()
        assert len(agent) == 1
        assert agent[0].is_representative is True
        assert agent[0].representative_note == NOTE
    finally:
        _delete_image(img_id)


def test_human_and_agent_images_are_identical(client, database_url):
    """`projections.py` passes `images=detail.images`, so parity holds by
    construction — this pins that, so a future divergence is a failing test and
    not a silently under-disclosed machine surface."""
    rid = _robot_id()
    img_id = _representative_row(rid)
    try:
        http = _http_images(client)
        agent = [i.model_dump(mode="json") for i in _agent_images()]
        assert agent == http
    finally:
        _delete_image(img_id)


def test_parity_holds_for_non_representative_images_too(client, database_url):
    rid = _robot_id()
    img_id = _insert_image(rid, identity="VERIFIED", rights="PERMITTED", official=True)
    try:
        http = _http_images(client)
        agent = [i.model_dump(mode="json") for i in _agent_images()]
        assert agent == http
        assert http[0]["is_representative"] is False
    finally:
        _delete_image(img_id)


# ---- eligibility itself is unchanged by this fix --------------------------


def test_the_stand_in_is_display_eligible_only_as_a_labelled_representative(
    client, database_url
):
    """The row is UNVERIFIED: it crosses the boundary solely because it is an
    owner-approved representative. If that basis is what admits it, the label
    must travel with it — otherwise the gate admits an image whose only
    justification is a designation the reader never sees."""
    rid = _robot_id()
    img_id = _representative_row(rid)
    try:
        imgs = _http_images(client)
        assert len(imgs) == 1
        assert imgs[0]["is_representative"] is True
    finally:
        _delete_image(img_id)

    # Same row, same UNVERIFIED identity, but no representative designation ->
    # not display-eligible at all. The disclosure is the price of admission.
    plain = _insert_image(rid, identity="UNVERIFIED", rights="UNKNOWN")
    try:
        assert _http_images(client) == []
    finally:
        _delete_image(plain)
