"""HO CONTROL V1 — authenticated, READ-ONLY operations dashboard.

Lives inside the existing SQLAdmin boundary at ``/admin/ops`` and therefore
inherits ``AdminAuth`` (no second login, no public API, no new table).

Rules this module keeps:
  * SELECT only. No write path, no POST route, no network call of any kind.
  * Unknown stays UNKNOWN: external systems (CI, Netlify, probes) are rendered
    as not connected rather than guessed.
  * proposal != accepted claim != catalogue mutation != publication — each is
    counted separately and never merged into one "done" figure.
  * Database-derived text is HTML-escaped; evidence excerpts, error detail,
    contact data and exceptions are never selected or rendered.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any

from sqladmin import BaseView, expose
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.db.session import engine

logger = logging.getLogger(__name__)

RECENT_WINDOW_DAYS = 7
SCHEDULE_ROW_LIMIT = 25
ACTIVITY_ROW_LIMIT = 20
REFRESH_SECONDS = 60

HEALTHY, ATTENTION, CRITICAL = "HEALTHY", "ATTENTION", "CRITICAL"
UNKNOWN = "UNKNOWN"
DUE, NOT_DUE, NEVER_RUN = "DUE", "NOT_DUE", "NEVER_RUN"

# Candidates whose identity still needs a human, excluding terminal states.
_UNRESOLVED_IDENTITIES = ("UNRESOLVED", "AMBIGUOUS", "POSSIBLE_DUPLICATE")
_TERMINAL_CANDIDATE_STATUSES = ("PROMOTED", "REJECTED")

EXTERNAL_SIGNALS = (
    ("GitHub CI", "NOT CONNECTED — V1"),
    ("Netlify frontend deploy", "NOT CONNECTED — V1"),
    ("Netlify Forms delivery", "UNKNOWN — EXTERNAL SIGNAL NOT WIRED"),
    ("External production probe", "UNKNOWN — EXTERNAL SIGNAL NOT WIRED"),
)


@dataclass
class Snapshot:
    generated_at: datetime
    database_ok: bool = True
    catalogue: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    governance: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    schedule: list[dict[str, Any]] = field(default_factory=list)
    activity: list[dict[str, Any]] = field(default_factory=list)

    @property
    def attention(self) -> list[tuple[str, int]]:
        """Actionable conditions with a non-zero count."""
        if not self.database_ok:
            return []
        items = [
            ("Proposals awaiting a first human decision", self.governance["undecided"]),
            ("Proposals whose latest decision is DEFER", self.governance["deferred"]),
            ("Unresolved / ambiguous discovery identities", self.governance["unresolved"]),
            ("Manual freshness targets due", self.freshness["manual_due"]),
            (f"Failed crawl runs (last {RECENT_WINDOW_DAYS}d)", self.discovery["failed_recent"]),
            (f"Freshness fetch errors (last {RECENT_WINDOW_DAYS}d)",
             self.freshness["fetch_errors_recent"]),
        ]
        return [(label, n) for label, n in items if n]

    @property
    def overall(self) -> str:
        if not self.database_ok:
            return CRITICAL
        return ATTENTION if self.attention else HEALTHY


def _scalar(s: Session, sql: str, **params: Any) -> Any:
    return s.execute(text(sql), params).scalar()


def _rows(s: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in s.execute(text(sql), params).mappings()]


def _schedule_state(interval_hours: int, last: datetime | None, now: datetime):
    if last is None:
        return NEVER_RUN, None
    next_due = last + timedelta(hours=interval_hours)
    return (DUE if next_due <= now else NOT_DUE), next_due


def collect_snapshot(now: datetime | None = None) -> Snapshot:
    """Read-only snapshot. Fails closed: any DB error -> database_ok=False."""
    now = now or datetime.now(UTC)
    snap = Snapshot(generated_at=now)
    since = now - timedelta(days=RECENT_WINDOW_DAYS)
    try:
        with Session(engine) as s:
            s.execute(text("SET TRANSACTION READ ONLY"))
            snap.catalogue = {
                "robots": _scalar(s, "SELECT count(*) FROM robot"),
                "published": _scalar(s, "SELECT count(*) FROM robot WHERE is_published"),
                "manufacturers": _scalar(s, "SELECT count(*) FROM manufacturer"),
                "pricing": _scalar(s, "SELECT count(*) FROM pricing_offer"),
                "availability": _scalar(s, "SELECT count(*) FROM availability_offer"),
                "evidence": _scalar(s, "SELECT count(*) FROM evidence_source"),
                "evidence_latest": _scalar(s, "SELECT max(observed_at) FROM evidence_source"),
            }

            sources = _rows(
                s,
                "SELECT key, name, is_enabled, observation_interval_hours AS hours, "
                "last_crawled_at AS last FROM discovery_source",
            )
            scheduled = []
            for src in sources:
                if src["hours"] is None:
                    continue
                state, next_due = _schedule_state(src["hours"], src["last"], now)
                scheduled.append({**src, "state": state, "next_due": next_due})
            order = {DUE: 0, NEVER_RUN: 1, NOT_DUE: 2}
            scheduled.sort(key=lambda r: (order[r["state"]], r["key"]))
            latest_run = _rows(
                s, "SELECT status, started_at FROM crawl_run ORDER BY started_at DESC LIMIT 1"
            )
            snap.schedule = scheduled[:SCHEDULE_ROW_LIMIT]
            snap.discovery = {
                "enabled": sum(1 for r in sources if r["is_enabled"]),
                "scheduled": len(scheduled),
                "due": sum(1 for r in scheduled if r["state"] in (DUE, NEVER_RUN)),
                "running": _scalar(s, "SELECT count(*) FROM crawl_run WHERE status = 'RUNNING'"),
                "failed_recent": _scalar(
                    s,
                    "SELECT count(*) FROM crawl_run WHERE status = 'FAILED' "
                    "AND started_at >= :since",
                    since=since,
                ),
                "latest_status": latest_run[0]["status"] if latest_run else None,
                "latest_at": latest_run[0]["started_at"] if latest_run else None,
            }

            snap.governance = {
                "unresolved": _scalar(
                    s,
                    "SELECT count(*) FROM discovery_candidate "
                    "WHERE identity_status::text = ANY(:ids) "
                    "AND status::text <> ALL(:terminal)",
                    ids=list(_UNRESOLVED_IDENTITIES),
                    terminal=list(_TERMINAL_CANDIDATE_STATUSES),
                ),
                "proposals": _scalar(s, "SELECT count(*) FROM discovery_claim_proposal"),
                "undecided": _scalar(
                    s,
                    "SELECT count(*) FROM discovery_claim_proposal p WHERE NOT EXISTS "
                    "(SELECT 1 FROM discovery_proposal_decision d WHERE d.proposal_id = p.id)",
                ),
                "deferred": _scalar(
                    s,
                    "SELECT count(*) FROM discovery_claim_proposal p WHERE "
                    "(SELECT d.decision::text FROM discovery_proposal_decision d "
                    "WHERE d.proposal_id = p.id ORDER BY d.decision_seq DESC LIMIT 1) = 'DEFER'",
                ),
                "active_claims": _scalar(
                    s,
                    "SELECT count(*) FROM accepted_claim c WHERE NOT EXISTS "
                    "(SELECT 1 FROM claim_retraction r WHERE r.claim_id = c.id)",
                ),
                "write_audits": _scalar(s, "SELECT count(*) FROM catalogue_write_audit"),
            }

            due_sql = (
                "FROM freshness_target WHERE active AND (last_checked_at IS NULL "
                "OR last_checked_at <= :now - make_interval(days => interval_days))"
            )
            latest_change = _scalar(s, "SELECT max(last_change_detected_at) FROM freshness_target")
            snap.freshness = {
                "active": _scalar(s, "SELECT count(*) FROM freshness_target WHERE active"),
                "due": _scalar(s, "SELECT count(*) " + due_sql, now=now),
                "manual_due": _scalar(
                    s, "SELECT count(*) " + due_sql + " AND manual_override", now=now
                ),
                "fetch_errors_recent": _scalar(
                    s,
                    "SELECT count(*) FROM freshness_observation "
                    "WHERE result::text = 'FETCH_ERROR' AND checked_at >= :since",
                    since=since,
                ),
                "latest_check": _scalar(s, "SELECT max(checked_at) FROM freshness_observation"),
                "latest_change": latest_change,
            }

            # Process / reference / outcome only — never excerpts, rationale,
            # error detail or operator identities.
            activity = _rows(
                s,
                "SELECT started_at AS at, 'CRAWL' AS process, adapter_key AS ref, "
                "status::text AS outcome FROM crawl_run ORDER BY started_at DESC LIMIT :n",
                n=ACTIVITY_ROW_LIMIT,
            )
            activity += _rows(
                s,
                "SELECT d.created_at AS at, 'PROPOSAL DECISION' AS process, "
                "p.robot_slug AS ref, d.decision::text AS outcome "
                "FROM discovery_proposal_decision d "
                "JOIN discovery_claim_proposal p ON p.id = d.proposal_id "
                "ORDER BY d.created_at DESC LIMIT :n",
                n=ACTIVITY_ROW_LIMIT,
            )
            activity += _rows(
                s,
                "SELECT o.checked_at AS at, 'FRESHNESS' AS process, "
                "t.purpose::text AS ref, o.result::text AS outcome "
                "FROM freshness_observation o "
                "JOIN freshness_target t ON t.id = o.freshness_target_id "
                "ORDER BY o.checked_at DESC LIMIT :n",
                n=ACTIVITY_ROW_LIMIT,
            )
            activity += _rows(
                s,
                "SELECT applied_at AS at, 'CATALOGUE WRITE' AS process, "
                "robot_slug AS ref, method AS outcome "
                "FROM catalogue_write_audit ORDER BY applied_at DESC LIMIT :n",
                n=ACTIVITY_ROW_LIMIT,
            )
            activity.sort(key=lambda r: r["at"], reverse=True)
            snap.activity = activity[:ACTIVITY_ROW_LIMIT]
    except Exception:  # noqa: BLE001 — fail closed; never surface the exception text
        logger.exception("HO CONTROL snapshot failed")
        return Snapshot(generated_at=now, database_ok=False)
    return snap


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _ts(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if value else UNKNOWN


def _num(value: Any) -> str:
    return UNKNOWN if value is None else str(value)


def _stat(label: str, value: Any, tone: str = "") -> str:
    return (f'<div class="stat {tone}"><div class="n">{_e(_num(value))}</div>'
            f'<div class="l">{_e(label)}</div></div>')


def _text_stat(label: str, value: str | None) -> str:
    return (f'<div class="stat"><div class="t">{_e(value or UNKNOWN)}</div>'
            f'<div class="l">{_e(label)}</div></div>')


def _panel(title: str, body: str, cls: str = "") -> str:
    return f'<section class="panel {cls}"><h2>{_e(title)}</h2>{body}</section>'


_CSS = """
:root{--bg:#131210;--raised:#1D1B18;--text:#E7E3D8;--signal:#FF4A00;--ok:#2E6B4F;
--warn:#9A6B12;--unk:#7C776B}
*{box-sizing:border-box;border-radius:0}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:var(--text)}
header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;
padding:20px 24px;border-bottom:1px solid var(--unk)}
.brand{letter-spacing:.2em;font-size:12px;color:var(--unk)}
h1{margin:4px 0 0;font-size:28px;letter-spacing:.12em}
.sub{color:var(--unk);font-size:12px;letter-spacing:.15em}
.state{padding:8px 16px;border:2px solid var(--unk);font-size:20px;letter-spacing:.15em}
.state.HEALTHY{border-color:var(--ok);color:var(--ok)}
.state.ATTENTION{border-color:var(--warn);color:var(--warn)}
.state.CRITICAL{border-color:var(--signal);color:var(--signal)}
nav a{margin-right:16px;font-size:12px;letter-spacing:.1em}
main{padding:24px;display:grid;gap:16px;grid-template-columns:repeat(3,1fr)}
.panel{background:var(--raised);border:1px solid var(--unk);padding:16px}
.panel.wide{grid-column:1/-1}
.panel.attn{border:2px solid var(--warn)}
.panel.attn.clear{border-color:var(--ok)}
h2{margin:0 0 12px;font-size:12px;letter-spacing:.2em;color:var(--unk)}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.attn .stats{grid-template-columns:repeat(3,1fr)}
.n{font-size:32px;line-height:1}.t{font-size:15px;line-height:1.6}
.l{font-size:11px;color:var(--unk);margin-top:4px}
.stat.warn .n{color:var(--warn)}
.big{font-size:22px;letter-spacing:.1em;color:var(--ok)}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #2c2a26}
th{color:var(--unk);font-weight:normal;letter-spacing:.1em}
.DUE,.NEVER_RUN{color:var(--warn)}.NOT_DUE{color:var(--unk)}
.unk{color:var(--unk)}
.note{font-size:11px;color:var(--unk);margin-top:12px}
@media(max-width:1000px){main{grid-template-columns:1fr}}
"""


def _render_attention(snap: Snapshot) -> str:
    if not snap.attention:
        return _panel("NEEDS ATTENTION",
                      '<div class="big">NO HUMAN ACTION REQUIRED</div>', "wide attn clear")
    stats = "".join(_stat(label, n, "warn") for label, n in snap.attention)
    return _panel("NEEDS ATTENTION", f'<div class="stats">{stats}</div>', "wide attn")


def _render_table(headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f'<div class="unk">{_e(empty)}</div>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def render_dashboard(snap: Snapshot) -> str:
    if not snap.database_ok:
        panels = _panel("DATABASE", '<div class="big" style="color:var(--signal)">'
                        "CRITICAL / DATABASE DOWN</div>"
                        '<div class="note">The dashboard could not query PostgreSQL. '
                        "No figures are shown rather than guessed.</div>", "wide")
    else:
        c, d, g, f = snap.catalogue, snap.discovery, snap.governance, snap.freshness
        panels = _render_attention(snap)
        panels += _panel("CATALOGUE", '<div class="stats">' + "".join([
            _stat("robots", c["robots"]), _stat("published", c["published"]),
            _stat("manufacturers", c["manufacturers"]), _stat("pricing offers", c["pricing"]),
            _stat("availability offers", c["availability"]),
            _stat("evidence sources", c["evidence"]),
        ]) + "</div>" + f'<div class="note">Latest evidence observed: '
            f'{_e(_ts(c["evidence_latest"]))}</div>')
        panels += _panel("DISCOVERY", '<div class="stats">' + "".join([
            _stat("enabled sources", d["enabled"]), _stat("scheduled sources", d["scheduled"]),
            _stat("sources due", d["due"]), _stat("running crawls", d["running"]),
            _stat(f"failed crawls ({RECENT_WINDOW_DAYS}d)", d["failed_recent"]),
            _text_stat("latest crawl status", d["latest_status"]),
        ]) + "</div>" + f'<div class="note">Latest crawl: {_e(_ts(d["latest_at"]))}</div>')
        panels += _panel("GOVERNANCE", '<div class="stats">' + "".join([
            _stat("unresolved identities", g["unresolved"]),
            _stat("structured proposals", g["proposals"]),
            _stat("no human decision", g["undecided"]),
            _stat("latest decision DEFER", g["deferred"]),
            _stat("active accepted claims", g["active_claims"]),
            _stat("catalogue write audits", g["write_audits"]),
        ]) + "</div>" + '<div class="note">proposal ≠ accepted claim ≠ catalogue mutation '
            "≠ publication</div>")
        panels += _panel("FRESHNESS", '<div class="stats">' + "".join([
            _stat("active targets", f["active"]), _stat("targets due", f["due"]),
            _stat("manual-override due", f["manual_due"]),
            _stat(f"FETCH_ERROR ({RECENT_WINDOW_DAYS}d)", f["fetch_errors_recent"]),
        ]) + "</div>" + f'<div class="note">Latest check: {_e(_ts(f["latest_check"]))}'
            f' · latest change: {_e(_ts(f["latest_change"]))}</div>')
        panels += _panel("EXTERNAL SIGNALS", _render_table(
            ["Signal", "State"],
            [[f"<td>{_e(n)}</td>", f'<td class="unk">{_e(s)}</td>'] for n, s in EXTERNAL_SIGNALS],
            "",
        ) + '<div class="note">No external network call is made by this page.</div>')

        sched = [[
            f"<td>{_e(r['key'])}<br><span class='unk'>{_e(r['name'])}</span></td>",
            f"<td>{_e(r['hours'])}h</td>", f"<td>{_e(_ts(r['last']))}</td>",
            f"<td>{_e(_ts(r['next_due']) if r['next_due'] else 'NOW')}</td>",
            f"<td class='{_e(r['state'])}'>{_e(r['state'])}</td>",
        ] for r in snap.schedule]
        panels += _panel("SCHEDULED SOURCE STATUS", _render_table(
            ["Source", "Interval", "Last crawl", "Next due", "State"], sched,
            "No scheduled discovery sources."), "wide")
        act = [[f"<td>{_e(_ts(r['at']))}</td>", f"<td>{_e(r['process'])}</td>",
                f"<td>{_e(r['ref'])}</td>", f"<td>{_e(r['outcome'])}</td>"]
               for r in snap.activity]
        panels += _panel("RECENT ACTIVITY", _render_table(
            ["When", "Process", "Reference", "Outcome"], act, "No recorded activity."), "wide")

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<meta http-equiv=\"refresh\" content=\"{REFRESH_SECONDS}\">"
        "<title>HO CONTROL — HumanoidOnline</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header><div><div class=\"brand\">HUMANOID. ONLINE</div><h1>HO CONTROL</h1>"
        "<div class=\"sub\">OPERATIONS / READ ONLY</div>"
        f"<div class=\"sub\">GENERATED {_e(_ts(snap.generated_at))}</div></div>"
        "<div><div class=\"state " + _e(snap.overall) + "\">" + _e(snap.overall) + "</div>"
        "<nav style=\"margin-top:12px\"><a href=\"/admin/ops\">REFRESH</a>"
        "<a href=\"/admin/\">← ADMIN</a></nav></div></header>"
        f"<main>{panels}</main></body></html>"
    )


class OpsDashboardView(BaseView):
    """Read-only HO CONTROL page. GET only; auth comes from the Admin backend."""

    name = "HO CONTROL"
    icon = "fa-solid fa-gauge"

    @expose("/ops", methods=["GET"])
    async def ops(self, request: Request) -> HTMLResponse:
        return HTMLResponse(render_dashboard(collect_snapshot()),
                            headers={"Cache-Control": "no-store"})
