"""Issue #179: materialization and a promotion apply share ONE `catalogue-write` lock.

`materialize.verify_applied` (the only database write path of materialization: it reads the
imported rows and appends `catalogue_write_audit`) takes the same transaction-scoped advisory
lock as the promotion executor's `before_write` hook, so the two serialize in both directions.
Local throwaway Postgres only (promotion_support.World); nothing here touches production.
"""
from __future__ import annotations

import threading
import time

import psycopg
from promotion_support import ROBOT, template_db, world  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.discovery import materialize
from app.services.discovery import promotion_execute as px
from app.services.discovery.catalogue_lock import CATALOGUE_WRITE_LOCK_SQL

WHO = "Robert Konecny"


def _engine(url: str):
    return create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))


def _wait_for_a_blocked_advisory_lock(url: str, timeout: float = 60) -> int:
    with psycopg.connect(url, autocommit=True) as conn:
        deadline = time.time() + timeout
        while time.time() < deadline:
            waiting = conn.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                                   "AND NOT granted").fetchone()[0]
            if waiting:
                return waiting
            time.sleep(0.1)
    return 0


def _in_thread(fn) -> tuple[threading.Thread, dict]:
    out: dict = {}

    def body():
        try:
            out["result"] = fn()
        except BaseException as exc:               # surfaced in the test thread
            out["error"] = exc
        out["done_at"] = time.monotonic()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, out


def test_the_lock_has_one_spelling_shared_by_the_executor_and_materialize():
    assert CATALOGUE_WRITE_LOCK_SQL == "SELECT pg_advisory_xact_lock(hashtext('catalogue-write'))"
    assert px.CATALOGUE_WRITE_LOCK_SQL is CATALOGUE_WRITE_LOCK_SQL
    assert materialize.CATALOGUE_WRITE_LOCK_SQL is CATALOGUE_WRITE_LOCK_SQL


def test_verify_applied_holds_the_catalogue_write_lock_until_its_transaction_ends(world):  # noqa: F811
    engine = _engine(world.owner_url)
    try:
        with Session(engine) as session:
            assert materialize.verify_applied(session, ROBOT, change_ref="chg-1",
                                              applied_by=WHO) == []
            held = session.connection().exec_driver_sql(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND pid = pg_backend_pid() AND granted").scalar()
            assert held == 1
            session.rollback()
            assert session.connection().exec_driver_sql(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND pid = pg_backend_pid()").scalar() == 0
    finally:
        engine.dispose()


def test_materialize_verification_waits_for_a_running_promotion_apply(world):  # noqa: F811
    """A promotion apply holds the lock (inside the importer transaction, before its writes):
    verify_applied blocks and appends nothing until the import has committed."""
    world.prepare()
    locked, release = threading.Event(), threading.Event()
    committed: dict = {}

    def hook(cur):                                 # the executor's lock, then a pause
        cur.execute(CATALOGUE_WRITE_LOCK_SQL)
        locked.set()
        assert release.wait(60)

    def promote():
        summary = px._import(world.owner_url, [ROBOT], world.head, before_write=hook)
        committed["at"] = time.monotonic()
        return summary

    importer, imported = _in_thread(promote)
    assert locked.wait(60)
    engine = _engine(world.owner_url)
    try:
        with Session(engine) as session:
            verifier, verified = _in_thread(lambda: materialize.verify_applied(
                session, ROBOT, change_ref="chg-1", applied_by=WHO))
            waiting = _wait_for_a_blocked_advisory_lock(world.owner_url)
            alive = verifier.is_alive()
            release.set()
            importer.join(120)
            verifier.join(120)
            session.commit()
    finally:
        release.set()
        engine.dispose()
    assert "error" not in imported and "error" not in verified, (imported, verified)
    assert (waiting, alive) == (1, True)
    assert verified["result"] == []
    assert verified["done_at"] >= committed["at"]  # it ran only after the promotion committed
    assert world.spec_rows()                       # and the promotion's write landed


def test_promotion_apply_waits_for_an_uncommitted_materialize_verification(world, monkeypatch):  # noqa: F811
    """verify_applied holds the lock until its caller commits: the real executor's apply step
    waits behind it with nothing written, then completes once the verification commits. (The
    verification starts at the apply step: an open session would block the rehearsal copy.)"""
    world.prepare()
    real = px._import
    seen: dict = {}

    def apply_behind_a_verification(url, robots, catalogue_dir, **kw):
        if url != world.url:                       # the rehearsal copy is not under test
            return real(url, robots, catalogue_dir, **kw)
        engine = _engine(world.owner_url)
        try:
            with Session(engine) as session:
                seen["verified"] = materialize.verify_applied(
                    session, ROBOT, change_ref="chg-1", applied_by=WHO)
                apply, applied = _in_thread(lambda: real(url, robots, catalogue_dir, **kw))
                seen["waiting"] = _wait_for_a_blocked_advisory_lock(world.owner_url)
                seen["alive"] = apply.is_alive()
                seen["written_while_blocked"] = world.spec_rows()
                session.commit()                   # releases the lock
            apply.join(120)
        finally:
            engine.dispose()
        if "error" in applied:
            raise applied["error"]
        return applied["result"]

    monkeypatch.setattr(px, "_import", apply_behind_a_verification)
    receipt = world.execute()
    assert seen == {"verified": [], "waiting": 1, "alive": True,
                    "written_while_blocked": []}, seen
    assert receipt["outcome"] == "SUCCESS", receipt
    assert world.spec_rows()
