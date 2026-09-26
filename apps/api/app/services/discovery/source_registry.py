"""Governed source registration (docs/16 §5 / §14; D6).

The separation this module preserves, one step per command:

    register  -> the source exists, DISABLED, ToS and robots UNKNOWN
    review    -> the owner's recorded decisions (his own ToS read, DR-A4; the
                 robots reading; approved path prefixes), appended to the
                 append-only `source_eligibility_review` history and mirrored as
                 the source's effective state. Reviewing never enables.
    enable    -> a separate, attributed act; refused unless the recorded review
                 makes the source radar-eligible (the DB CHECK agrees)
    disable   -> always allowed, attributed, with a reason
    cadence   -> Stage F (docs/16 §17.2): how often an enabled, approved source
                 is observed by the scheduler; attributed; off by default

Acquisition then still re-reads robots.txt on every run. Nothing here fetches
anything, and ToS age / page hashes are not gates (DR-A4).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.acquisition import SourceEligibilityReview
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError

SOURCE_CLASSES = (
    "MANUFACTURER", "AUTHORIZED_DISTRIBUTOR", "OFFICIAL_STORE", "AGGREGATOR",
    "MARKETPLACE", "EDITORIAL", "DISTRIBUTOR", "PRESS_RELEASE", "OFFICIAL_DOCUMENT",
    "OFFICIAL_VIDEO", "COMPETITOR_DIRECTORY", "SEARCH_RESULT", "COMMUNITY", "OTHER",
)
TOS_DECISIONS = ("ALLOWED", "RESTRICTED", "PROHIBITED", "UNKNOWN")
ROBOTS_DECISIONS = ("ALLOWED", "DISALLOWED", "NOT_APPLICABLE", "UNKNOWN")


def _now() -> datetime:
    return datetime.now(UTC)


def _required(value: str | None, what: str) -> str:
    if not value or not value.strip():
        raise DiscoveryError(f"{what} is required (an unattributed act is not a decision)")
    return value.strip()


def _note(source: DiscoverySource, line: str) -> None:
    source.notes = f"{source.notes}\n{line}" if source.notes else line


def get_source(session: Session, key: str) -> DiscoverySource:
    source = session.scalars(select(DiscoverySource).where(DiscoverySource.key == key)).first()
    if source is None:
        raise DiscoveryError(f"no discovery source {key!r}")
    return source


def register_source(
    session: Session, *, key: str, name: str, source_class: str, homepage_url: str,
    registered_by: str, now: datetime | None = None,
) -> DiscoverySource:
    by = _required(registered_by, "--by")
    key, name = _required(key, "key"), _required(name, "--name")
    if source_class not in SOURCE_CLASSES:
        raise DiscoveryError(f"unknown source class {source_class!r}")
    parts = urlsplit(homepage_url or "")
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        raise DiscoveryError("--homepage must be an https origin such as https://example.com/")
    if session.scalars(select(DiscoverySource.id).where(DiscoverySource.key == key)).first():
        raise DiscoveryError(f"source {key!r} is already registered")
    source = DiscoverySource(
        key=key, name=name, source_class=source_class,
        homepage_url=f"https://{parts.hostname.lower()}/",
        is_enabled=False, tos_status="UNKNOWN", robots_status="UNKNOWN",
    )
    _note(source, f"{(now or _now()).isoformat()} registered by {by} (disabled; no review)")
    session.add(source)
    session.flush()
    return source


def review_source(
    session: Session, key: str, *, reviewed_by: str, tos_decision: str,
    robots_decision: str, path_prefixes: list[str], tos_url: str | None = None,
    robots_url: str | None = None, notes: str | None = None, now: datetime | None = None,
) -> SourceEligibilityReview:
    by = _required(reviewed_by, "--reviewed-by")
    if tos_decision not in TOS_DECISIONS:
        raise DiscoveryError(f"--tos-decision must be one of {TOS_DECISIONS}")
    if robots_decision not in ROBOTS_DECISIONS:
        raise DiscoveryError(f"--robots-decision must be one of {ROBOTS_DECISIONS}")
    bad = [p for p in path_prefixes if not p.startswith("/")]
    if bad:
        raise DiscoveryError(f"path prefixes must be absolute paths: {bad}")
    when = now or _now()
    source = get_source(session, key)
    review = SourceEligibilityReview(
        source_id=source.id, robots_url=robots_url, robots_decision=robots_decision,
        tos_url=tos_url, tos_decision=tos_decision, path_prefixes=list(path_prefixes),
        reviewed_by=by, reviewed_at=when, recommendation=tos_decision, notes=notes,
    )
    session.add(review)
    source.tos_status = tos_decision
    source.robots_status = robots_decision
    source.allowed_path_prefixes = list(path_prefixes)
    source.eligibility_reviewed_at = when
    source.eligibility_reviewed_by = by
    source.tos_reviewed_at = when
    if source.is_enabled and not source.radar_eligible:
        source.is_enabled = False
        _note(source, f"{when.isoformat()} disabled: review by {by} no longer permits "
                      "acquisition")
    _note(source, f"{when.isoformat()} reviewed by {by}: tos={tos_decision} "
                  f"robots={robots_decision} paths={list(path_prefixes)} (not enabled)")
    session.flush()
    return review


def enable_source(session: Session, key: str, *, by: str,
                  now: datetime | None = None) -> DiscoverySource:
    who = _required(by, "--by")
    source = get_source(session, key)
    reasons = []
    if source.tos_status != "ALLOWED":
        reasons.append(f"tos_status={source.tos_status} (needs the owner's ALLOWED)")
    if source.robots_status not in ("ALLOWED", "NOT_APPLICABLE"):
        reasons.append(f"robots_status={source.robots_status}")
    if source.eligibility_reviewed_at is None or not source.eligibility_reviewed_by:
        reasons.append("no attributed review")
    if not source.allowed_path_prefixes:
        reasons.append("no approved path prefixes")
    if reasons:
        raise DiscoveryError("cannot enable: " + "; ".join(reasons))
    source.is_enabled = True
    _note(source, f"{(now or _now()).isoformat()} enabled by {who}")
    session.flush()
    return source


def disable_source(session: Session, key: str, *, by: str, reason: str,
                   now: datetime | None = None) -> DiscoverySource:
    who = _required(by, "--by")
    why = _required(reason, "--reason")
    source = get_source(session, key)
    source.is_enabled = False
    _note(source, f"{(now or _now()).isoformat()} disabled by {who}: {why}")
    session.flush()
    return source


#: Stage F cadence bounds (the DB CHECK agrees): hours to days, never minutes.
MIN_INTERVAL_HOURS = 6
MAX_INTERVAL_HOURS = 90 * 24


def parse_interval(value: str) -> int:
    """'12h', '1d', '7d' (or bare hours) -> whole hours, within the bounds."""
    match = re.fullmatch(r"\s*(\d+)\s*([hd]?)\s*", value or "")
    if not match:
        raise DiscoveryError(f"cadence {value!r}: use whole hours or days, e.g. 12h, 1d, 7d")
    hours = int(match.group(1)) * (24 if match.group(2) == "d" else 1)
    if not MIN_INTERVAL_HOURS <= hours <= MAX_INTERVAL_HOURS:
        raise DiscoveryError(f"cadence must be between {MIN_INTERVAL_HOURS}h and "
                             f"{MAX_INTERVAL_HOURS // 24}d (got {hours}h)")
    return hours


def set_cadence(session: Session, key: str, *, every: str | None, by: str,
                now: datetime | None = None) -> DiscoverySource:
    """Set (or, with every=None, turn off) a source's Stage F observation cadence.

    Attributed. Setting a cadence never enables a source and never fetches: a
    disabled or unapproved source is still never observed by the scheduler."""
    who = _required(by, "--by")
    source = get_source(session, key)
    when = now or _now()
    hours = parse_interval(every) if every is not None else None
    source.observation_interval_hours = hours
    source.observation_cadence_set_by = who
    source.observation_cadence_set_at = when
    _note(source, f"{when.isoformat()} observation cadence "
                  f"{'every ' + str(hours) + 'h' if hours else 'OFF'} set by {who}")
    session.flush()
    return source


def next_observation_at(source: DiscoverySource) -> datetime | None:
    """When the scheduler next considers the source due (None = not scheduled).
    Never observed = due now; otherwise the last run's end plus the interval."""
    if source.observation_interval_hours is None:
        return None
    if source.last_crawled_at is None:
        return datetime.min.replace(tzinfo=UTC)
    return source.last_crawled_at + timedelta(hours=source.observation_interval_hours)


def _cadence_text(source: DiscoverySource) -> str:
    hours = source.observation_interval_hours
    return f"every {hours}h" if hours else "OFF"


def _next_due_text(source: DiscoverySource) -> str:
    if source.observation_interval_hours is None:
        return "-"
    if source.last_crawled_at is None:
        return "now (never observed)"
    return next_observation_at(source).isoformat()


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else "-"


def describe(source: DiscoverySource) -> list[str]:
    return [
        f"SOURCE {source.key}   class={source.source_class}   host={source.homepage_url}",
        f"  enabled={source.is_enabled}   radar_eligible={source.radar_eligible}",
        f"  tos_status={source.tos_status}   robots_status={source.robots_status}",
        f"  reviewed_by={source.eligibility_reviewed_by or '-'}   "
        f"reviewed_at={_iso(source.eligibility_reviewed_at)}",
        f"  allowed_path_prefixes={list(source.allowed_path_prefixes or [])}",
        f"  last_robots_checked_at={source.last_robots_checked_at or '-'}   "
        f"last_crawled_at={source.last_crawled_at or '-'}",
        f"  observation_cadence={_cadence_text(source)}"
        f"   set_by={source.observation_cadence_set_by or '-'}   "
        f"next_due={_next_due_text(source)}",
        *(f"  | {line}" for line in (source.notes or "").splitlines()),
    ]
