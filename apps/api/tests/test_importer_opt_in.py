"""The shared importer's two promotion-only behaviours are OPT-IN (PR #177, owner decision C).

`run(..., probe_unchanged=False, before_write=None)`: by default the importer issues exactly the
statements it did before the promotion work - no advisory lock, no probe SELECT. With
`probe_unchanged=True` an unchanged row is detected by a SELECT in a savepoint instead of an
`INSERT .. ON CONFLICT DO UPDATE` that needs the UPDATE privilege.

The wider behaviour (stable ids, no-op imports, in-place updates, fail-closed authorization,
transaction integrity) is exercised in BOTH modes by test_importer_stable_ids.py.
"""
from __future__ import annotations

import contextlib

import psycopg
import pytest
from test_identity_decision_migration import scratch_db  # noqa: F401
from test_importer_stable_ids import ROBOTS, _edit, _state, ic, world  # noqa: F401

LOCK = "SELECT pg_advisory_xact_lock(hashtext('catalogue-write'))"


def _lock(cur):
    cur.execute(LOCK)


@contextlib.contextmanager
def _recording(monkeypatch, rewrite=None):
    log: list[str] = []

    class Cursor(psycopg.Cursor):
        def execute(self, query, params=None, **kw):
            if isinstance(query, str):
                log.append(query)
                if rewrite is not None:
                    query = rewrite(query)
            return super().execute(query, params, **kw)

    real = psycopg.connect

    def connect(*a, **kw):
        return real(*a, cursor_factory=Cursor, **kw)

    with monkeypatch.context() as m:
        m.setattr(ic.psycopg, "connect", connect)
        yield log


def _is_probe(q: str) -> bool:
    return q.startswith("SELECT NOT (")


def _is_upsert(q: str) -> bool:
    return q.startswith("INSERT INTO") and " ON CONFLICT (" in q and " DO UPDATE SET " in q


def _subsequence_extras(default: list[str], opted: list[str]) -> list[str]:
    """The statements of `opted` that are not in `default`, checking that `default` is
    a subsequence of `opted` once the opt-in extras are dropped, in order."""
    extras, i = [], 0
    for q in opted:
        if i < len(default) and q == default[i]:
            i += 1
        else:
            extras.append(q)
    assert i == len(default), "opt-in changed or reordered a statement of the default run"
    return extras


@pytest.mark.parametrize("edit", [False, True])
def test_default_run_issues_no_lock_and_no_probe_and_opt_in_only_adds_them(
        world, monkeypatch, edit):  # noqa: F811
    url, cat = world
    if edit:
        _edit(cat, "unitree-h2-edu", lambda d: d.update(summary="A reworded summary."))
    with _recording(monkeypatch) as default:
        ic.run(url, only=ROBOTS)
    assert not any(q == LOCK or _is_probe(q) for q in default)
    if edit:
        _edit(cat, "unitree-h2-edu", lambda d: d.update(summary="Another reworded summary."))
    with _recording(monkeypatch) as opted:
        ic.run(url, only=ROBOTS, before_write=_lock, probe_unchanged=True)
    # every statement the default run issues, the opted-in run issues in the same order; the
    # extras are the lock, the probes, and (instead of them) the skipped no-change upserts
    extras = _subsequence_extras([q for q in default if not _is_upsert(q)],
                                 [q for q in opted if not _is_upsert(q)])
    assert extras and all(q == LOCK or _is_probe(q) for q in extras)
    assert {q for q in opted if _is_upsert(q)} <= {q for q in default if _is_upsert(q)}


def test_opt_in_leaves_no_trace_when_off(world, monkeypatch):  # noqa: F811
    """Explicit False/None is the default: same statements as omitting the arguments."""
    url, _cat = world
    with _recording(monkeypatch) as omitted:
        ic.run(url, only=ROBOTS)
    with _recording(monkeypatch) as explicit:
        ic.run(url, only=ROBOTS, before_write=None, probe_unchanged=False)
    assert omitted == explicit and not any(_is_probe(q) or q == LOCK for q in explicit)


def test_a_failed_probe_aborts_only_its_savepoint_and_the_import_completes(
        world, monkeypatch):  # noqa: F811
    url, cat = world
    _edit(cat, "unitree-h2-edu", lambda d: d.update(summary="A reworded summary."))
    with _recording(monkeypatch, rewrite=lambda q: "SELECT 1/0" if _is_probe(q) else q) as log:
        recon = ic.run(url, only=ROBOTS, probe_unchanged=True)   # every probe errors in the DB
    assert any(_is_probe(q) for q in log)
    assert recon.counts["robot"]["updated"] == 1                  # the outer transaction lived
    assert _scalar_summary(url) == "A reworded summary."


def _scalar_summary(url):
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT summary FROM humanoid.robot WHERE slug = 'unitree-h2-edu'"
                            ).fetchone()[0]


def test_a_refusing_before_write_hook_leaves_nothing_written(world):  # noqa: F811
    url, cat = world
    before, summary = _state(url), _scalar_summary(url)
    _edit(cat, "unitree-h2-edu", lambda d: d.update(summary="A reworded summary."))

    def refuse(cur):
        raise ic.ReconcileRefused("production changed since review")

    with pytest.raises(ic.ReconcileRefused, match="production changed"):
        ic.run(url, only=ROBOTS, before_write=refuse, probe_unchanged=True)
    assert _state(url) == before and _scalar_summary(url) == summary
