"""Governed source registration (docs/16 §5 / §14; D6) — offline, PostgreSQL.

register -> review (owner's own ToS decision, DR-A4; never enables) -> enable
(separate attributed act) -> acquisition; disable at any time. No network.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.acquisition import EligibilityReviewImmutableError, SourceEligibilityReview
from app.models.discovery import DiscoverySourceOwnerAuthorizationEvent
from app.services.discovery import DiscoveryError
from app.services.discovery import source_registry as registry

pytestmark = pytest.mark.usefixtures("no_external_network")


@pytest.fixture
def shared_session(database_url, monkeypatch):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    session.commit = session.flush  # CLI commits must not escape the rollback

    @contextmanager
    def local():
        yield session

    monkeypatch.setattr(db_session, "SessionLocal", local)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


def _key() -> str:
    return f"registry-{uuid.uuid4().hex[:8]}"


def _register(session, key):
    return registry.register_source(
        session, key=key, name="Fixture maker", source_class="MANUFACTURER",
        homepage_url="https://Maker.example", registered_by="robert")


def _review(session, key, tos="ALLOWED", robots="ALLOWED", paths=("/products",)):
    return registry.review_source(
        session, key, reviewed_by="robert", tos_decision=tos, robots_decision=robots,
        path_prefixes=list(paths), tos_url="https://maker.example/terms")


def test_register_creates_a_disabled_unreviewed_source(shared_session):
    key = _key()
    source = _register(shared_session, key)
    assert (source.is_enabled, source.tos_status, source.robots_status) == (
        False, "UNKNOWN", "UNKNOWN")
    assert source.homepage_url == "https://maker.example/"
    assert not source.radar_eligible
    with pytest.raises(DiscoveryError, match="already registered"):
        _register(shared_session, key)


@pytest.mark.parametrize("homepage", ["http://maker.example/", "https://maker.example/shop",
                                      "maker.example", ""])
def test_register_requires_an_https_origin(shared_session, homepage):
    with pytest.raises(DiscoveryError):
        registry.register_source(shared_session, key=_key(), name="x",
                                 source_class="MANUFACTURER", homepage_url=homepage,
                                 registered_by="robert")


def test_review_records_history_and_never_enables(shared_session):
    key = _key()
    source = _register(shared_session, key)
    review = _review(shared_session, key)
    assert (source.tos_status, source.robots_status, source.allowed_path_prefixes) == (
        "ALLOWED", "ALLOWED", ["/products"])
    assert source.eligibility_reviewed_by == "robert" and source.tos_expires_at is None
    assert source.is_enabled is False                       # reviewing is not enabling
    assert review.reviewed_by == "robert" and review.tos_decision == "ALLOWED"
    review.notes = "edited"
    with pytest.raises(EligibilityReviewImmutableError):
        shared_session.flush()                               # append-only history


def test_enable_requires_the_owners_allowed_decision(shared_session):
    key = _key()
    _register(shared_session, key)
    with pytest.raises(DiscoveryError, match="tos_status=UNKNOWN"):
        registry.enable_source(shared_session, key, by="robert")
    _review(shared_session, key, tos="RESTRICTED")
    with pytest.raises(DiscoveryError, match="tos_status=RESTRICTED"):
        registry.enable_source(shared_session, key, by="robert")
    _review(shared_session, key, tos="ALLOWED")
    source = registry.enable_source(shared_session, key, by="robert")
    assert source.is_enabled and source.radar_eligible
    assert shared_session.scalar(select(func.count()).select_from(SourceEligibilityReview)
                                 .where(SourceEligibilityReview.source_id == source.id)) == 2


def test_a_later_negative_review_disables_an_enabled_source(shared_session):
    key = _key()
    _register(shared_session, key)
    _review(shared_session, key)
    registry.enable_source(shared_session, key, by="robert")
    source = _review(shared_session, key, robots="DISALLOWED") and registry.get_source(
        shared_session, key)
    assert source.is_enabled is False
    assert "no longer permits acquisition" in source.notes


def test_disable_is_attributed_and_needs_a_reason(shared_session):
    key = _key()
    _register(shared_session, key)
    _review(shared_session, key)
    registry.enable_source(shared_session, key, by="robert")
    with pytest.raises(DiscoveryError):
        registry.disable_source(shared_session, key, by="robert", reason=" ")
    source = registry.disable_source(shared_session, key, by="robert", reason="site asked")
    assert source.is_enabled is False and "disabled by robert: site asked" in source.notes


def test_cli_full_path(shared_session, capsys):
    key = _key()
    assert cli.main(["source", "register", key, "--name", "Fixture maker", "--class",
                     "MANUFACTURER", "--homepage", "https://maker.example/", "--by", "robert"]) == 0
    assert cli.main(["source", "enable", key, "--by", "robert"]) == 1       # refused: no review
    assert cli.main(["source", "review", key, "--reviewed-by", "robert", "--tos-decision",
                     "ALLOWED", "--robots-decision", "ALLOWED", "--path-prefix", "/products"]) == 0
    assert "enabled=False" in capsys.readouterr().out
    assert cli.main(["source", "enable", key, "--by", "robert"]) == 0
    assert cli.main(["source", "show", key]) == 0
    assert "radar_eligible=True" in capsys.readouterr().out
    assert cli.main(["source", "disable", key, "--by", "robert", "--reason", "pause"]) == 0
    assert registry.get_source(shared_session, key).is_enabled is False


def test_cli_adapter_plan_refuses_neura_until_registered(shared_session, capsys):
    assert cli.main(["adapter", "plan", "neura-robotics-official"]) == cli.REFUSED
    out = capsys.readouterr().out
    assert "SOURCE_NOT_REGISTERED" in out and "NOT RUNNABLE" in out
    assert "ADAPTER_BLOCKED" not in out
    assert cli.main(["adapter", "plan", "no-such-source"]) == cli.REFUSED


def test_cli_adapter_run_requires_an_operator():
    with pytest.raises(SystemExit):
        cli.main(["adapter", "run", "neura-robotics-official", "--operator", "  "])


# ------------------------------------------------- docs/28 (A4) OWNER_AUTHORIZED --


def _events(session, source):
    return list(session.scalars(
        select(DiscoverySourceOwnerAuthorizationEvent)
        .where(DiscoverySourceOwnerAuthorizationEvent.source_id == source.id)
        .order_by(DiscoverySourceOwnerAuthorizationEvent.decided_at)))


def _owner(session, key, paths=("/products",), reason="A4 owner instruction 2026-10-18"):
    return registry.authorize_owner(session, key, by="robert", reason=reason,
                                    path_prefixes=list(paths))


def test_owner_authorization_is_not_publisher_permission(shared_session):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN", robots="ALLOWED", paths=("/products",))
    with pytest.raises(DiscoveryError, match="tos_status=UNKNOWN.*authorize-owner"):
        registry.enable_source(shared_session, key, by="robert")
    _owner(shared_session, key)
    assert source.tos_status == "UNKNOWN"                    # never rewritten to ALLOWED
    assert source.access_basis == "OWNER_AUTHORIZED"
    assert source.is_enabled is False                         # authorizing never enables
    assert source.observation_interval_hours is None          # ... nor schedules
    registry.enable_source(shared_session, key, by="robert")
    assert source.radar_eligible is True
    [event] = _events(shared_session, source)
    assert (event.action, event.decided_by, event.approved_path_prefixes) == (
        "AUTHORIZE", "robert", ["/products"])
    text_out = "\n".join(registry.describe(source))
    assert "access_basis=OWNER_AUTHORIZED" in text_out and "NOT publisher consent" in text_out
    assert "tos_status=UNKNOWN" in text_out


def test_revocation_disables_and_is_appended_to_the_history(shared_session):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN")
    _owner(shared_session, key)
    registry.enable_source(shared_session, key, by="robert")
    registry.revoke_owner(shared_session, key, by="robert", reason="cancelled")
    assert source.is_enabled is False and source.radar_eligible is False
    assert source.access_basis == "SOURCE_PERMISSION" and source.owner_authorized_by is None
    assert [e.action for e in _events(shared_session, source)] == ["AUTHORIZE", "REVOKE"]
    assert _events(shared_session, source)[1].approved_path_prefixes == ["/products"]
    with pytest.raises(DiscoveryError, match="cannot enable"):
        registry.enable_source(shared_session, key, by="robert")
    with pytest.raises(DiscoveryError, match="nothing to revoke"):
        registry.revoke_owner(shared_session, key, by="robert", reason="again")


@pytest.mark.parametrize("tos", ["PROHIBITED", "RESTRICTED"])
def test_owner_authorization_cannot_override_a_recorded_restriction(shared_session, tos):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos=tos, robots="ALLOWED", paths=("/products",))
    with pytest.raises(DiscoveryError, match="cannot be overridden"):
        _owner(shared_session, key)
    assert source.access_basis == "SOURCE_PERMISSION" and _events(shared_session, source) == []


def test_a_later_restriction_or_robots_disallow_stops_an_owner_authorized_source(shared_session):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN")
    _owner(shared_session, key)
    registry.enable_source(shared_session, key, by="robert")
    _review(shared_session, key, tos="PROHIBITED")
    assert source.is_enabled is False and source.tos_status == "PROHIBITED"
    with pytest.raises(DiscoveryError, match="owner authorization does not apply"):
        registry.enable_source(shared_session, key, by="robert")
    _review(shared_session, key, tos="UNKNOWN", robots="DISALLOWED")
    with pytest.raises(DiscoveryError, match="robots_status=DISALLOWED"):
        registry.enable_source(shared_session, key, by="robert")


def test_owner_authorization_needs_an_attributed_review_and_fitting_paths(shared_session):
    key = _key()
    _register(shared_session, key)
    with pytest.raises(DiscoveryError, match="no attributed review"):
        _owner(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN", robots="ALLOWED", paths=("/products",))
    with pytest.raises(DiscoveryError, match="scope"):
        _owner(shared_session, key, paths=("/",))                 # wider than the review
    with pytest.raises(DiscoveryError, match="scope"):
        _owner(shared_session, key, paths=("/productsX",))        # not inside /products
    with pytest.raises(DiscoveryError, match="absolute"):
        _owner(shared_session, key, paths=("products",))
    with pytest.raises(DiscoveryError, match="--reason"):
        _owner(shared_session, key, reason="  ")


def test_owner_scope_caps_url_eligibility_and_a_narrower_review_narrows_it(shared_session):
    from app.services.discovery.eligibility import URL_OUTSIDE_APPROVED_PATHS, url_ineligibility
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN", robots="ALLOWED", paths=("/products", "/news"))
    _owner(shared_session, key, paths=("/products",))
    registry.enable_source(shared_session, key, by="robert")
    assert url_ineligibility(source, "https://maker.example/products/a") is None
    assert url_ineligibility(source, "https://maker.example/news/b") == URL_OUTSIDE_APPROVED_PATHS
    assert url_ineligibility(source, "https://shop.maker.example/products/a") is not None
    _review(shared_session, key, tos="UNKNOWN", robots="ALLOWED", paths=("/news",))
    assert url_ineligibility(source, "https://maker.example/products/a") is not None


def test_database_refuses_an_incomplete_owner_authorization(shared_session):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN")
    shared_session.flush()
    complete = {"by": "robert", "why": "r", "paths": ["/products"]}
    # A NULL or empty scope, or a blank reason, never satisfies the CHECK (no NULL bypass).
    for broken in ({"paths": None}, {"paths": []}, {"why": " "}, {"by": None}):
        with pytest.raises(IntegrityError), shared_session.begin_nested():
            shared_session.execute(text(
                "UPDATE discovery_source SET access_basis = 'OWNER_AUTHORIZED', "
                "owner_authorized_by = :by, owner_authorized_at = now(), "
                "owner_authorization_reason = :why, owner_authorized_path_prefixes = :paths "
                "WHERE id = :id"), {**complete, **broken, "id": source.id})
    # Owner fields without the OWNER_AUTHORIZED basis are refused too.
    with pytest.raises(IntegrityError), shared_session.begin_nested():
        shared_session.execute(text("UPDATE discovery_source SET owner_authorized_by = 'robert' "
                                    "WHERE id = :id"), {"id": source.id})
    with pytest.raises(IntegrityError), shared_session.begin_nested():   # UNKNOWN, no owner
        shared_session.execute(text("UPDATE discovery_source SET is_enabled = true "
                                    "WHERE id = :id"), {"id": source.id})


def test_owner_authorization_history_is_append_only(shared_session):
    key = _key()
    source = _register(shared_session, key)
    _review(shared_session, key, tos="UNKNOWN")
    _owner(shared_session, key)
    shared_session.flush()
    for statement in ("UPDATE discovery_source_owner_authorization_event SET reason = 'x' "
                      "WHERE source_id = :id",
                      "DELETE FROM discovery_source_owner_authorization_event "
                      "WHERE source_id = :id",
                      "TRUNCATE discovery_source_owner_authorization_event"):
        with pytest.raises(DBAPIError, match="append-only"), shared_session.begin_nested():
            shared_session.execute(text(statement), {"id": source.id})
    assert len(_events(shared_session, source)) == 1


def test_cli_owner_authorization_path(shared_session, capsys):
    key = _key()
    assert cli.main(["source", "register", key, "--name", "Fixture maker", "--class",
                     "MANUFACTURER", "--homepage", "https://maker.example/", "--by", "robert"]) == 0
    assert cli.main(["source", "review", key, "--reviewed-by", "robert", "--tos-decision",
                     "UNKNOWN", "--robots-decision", "ALLOWED", "--path-prefix", "/products"]) == 0
    assert cli.main(["source", "enable", key, "--by", "robert"]) == 1
    assert cli.main(["source", "authorize-owner", key, "--by", "robert", "--reason",
                     "A4 owner instruction", "--path-prefix", "/products"]) == 0
    out = capsys.readouterr().out
    assert "access_basis=OWNER_AUTHORIZED" in out and "enabled=False" in out
    assert "tos_status=UNKNOWN" in out
    assert cli.main(["source", "enable", key, "--by", "robert"]) == 0
    assert cli.main(["source", "revoke-owner", key, "--by", "robert", "--reason", "stop"]) == 0
    assert "enabled=False" in capsys.readouterr().out
