"""Discovery Stage B CLI (`python -m app.cli.discovery`) — offline.

`plan` never touches the network; `crawl` refuses before any request when policy
fails; argument rules (named operator, page cap) are enforced up front.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.discovery import DiscoverySource

pytestmark = pytest.mark.usefixtures("no_external_network")


@pytest.fixture
def shared_session(database_url, monkeypatch):
    """Route the CLI's SessionLocal to one rollback-isolated session."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    session.commit = session.flush  # CLI checkpoints must not escape the rollback

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


def _source(session, **overrides) -> DiscoverySource:
    fields = dict(
        key=f"cli-b:{uuid.uuid4().hex[:8]}", name="CLI maker", source_class="MANUFACTURER",
        homepage_url="https://maker.example/", allowed_path_prefixes=["/products/"],
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="owner",
    )
    fields.update(overrides)
    source = DiscoverySource(**fields)
    session.add(source)
    session.flush()
    return source


@pytest.mark.parametrize("argv", [
    ["crawl", "k", "--url", "https://maker.example/products/a"],            # no operator
    ["crawl", "k", "--operator", "  ", "--url", "https://maker.example/p"],  # blank operator
    ["crawl", "k", "--operator", "op", "--limit", "201"],
    ["plan", "k", "--limit", "0"],
    [],
])
def test_invalid_arguments_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_report_rejects_malformed_run_id(capsys):
    assert cli.main(["report", "not-a-uuid"]) == 2


def test_plan_makes_no_request_and_flags_policy(shared_session, capsys):
    source = _source(shared_session)
    code = cli.main(["plan", source.key, "--url", "https://maker.example/products/a",
                     "--url", "https://other.example/products/b"])
    out = capsys.readouterr().out
    assert code == cli.REFUSED
    assert "no request issued" in out
    assert "URL_OUTSIDE_APPROVED_HOST" in out and "OK" in out


def test_crawl_refuses_ineligible_source_before_any_request(shared_session, capsys, monkeypatch):
    source = _source(shared_session, is_enabled=False)

    def no_http(*args, **kwargs):
        pytest.fail("crawl built an HTTP request for an ineligible source")

    import httpx
    monkeypatch.setattr(httpx.Client, "send", no_http)
    code = cli.main(["crawl", source.key, "--operator", "Robert",
                     "--url", "https://maker.example/products/a"])
    assert code == cli.REFUSED
    assert "SOURCE_DISABLED" in capsys.readouterr().err


def test_unknown_source_is_refused(shared_session, capsys):
    assert cli.main(["plan", "no-such-source", "--url", "https://maker.example/products/a"]) \
        == cli.REFUSED


def test_kill_switch_files(tmp_path):
    engaged = cli.kill_switch_for("maker", tmp_path)
    assert engaged() is False
    (tmp_path / "KILL.maker").touch()
    assert engaged() is True
    (tmp_path / "KILL.maker").unlink()
    (tmp_path / "KILL").touch()
    assert engaged() is True
