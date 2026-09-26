"""robots.txt evaluation (RFC 9309) — pure, no network.

A small, explicit implementation rather than the standard library's robots
parser, whose first-match rule evaluation differs from RFC 9309's longest-match
rule: with `Allow: /` before `Disallow: /private`, the stdlib parser allows
`/private`, which is exactly the kind of silent over-permission robots
enforcement must not have. (It is also still banned by the Slice A guard in
tests/test_acquisition_schema.py, which this module need not be exempted from.)

Rules (RFC 9309 §2.2):
- the group(s) naming our product token apply; otherwise the `*` group(s);
  otherwise nothing is restricted;
- the longest matching `allow`/`disallow` pattern wins; on a tie, allow wins;
- `*` matches any sequence and a trailing `$` anchors the end;
- `/robots.txt` itself is always allowed.

`Crawl-delay` is not part of RFC 9309 but is honoured when the applicable group
states one: it can only make the fetcher slower (see `HttpFetcher.honour_crawl_delay`),
never faster than the 2 s floor. A malformed or negative value is ignored.

Fetch-status semantics (RFC 9309 §2.3.1), applied by the runner:
- 2xx: parse the body;
- 401/403: treated as a complete disallow (conservative);
- any other 4xx: no restrictions;
- 5xx / unreachable: robots is unavailable -> no target page is fetched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

PRODUCT_TOKEN = "humanoidonlinemarketbot"


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern

    @classmethod
    def build(cls, allow: bool, pattern: str) -> _Rule:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        return cls(allow, pattern, re.compile(regex + ("$" if anchored else "")))


@dataclass
class RobotsRules:
    """Parsed rules for our product token. `disallow_all` models 401/403."""

    rules: tuple[_Rule, ...] = field(default_factory=tuple)
    disallow_all: bool = False
    #: Seconds, from the applicable group's `Crawl-delay`; None when not stated.
    crawl_delay: float | None = None

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if path == "/robots.txt":
            return True
        if self.disallow_all:
            return False
        target = path + (f"?{parts.query}" if parts.query else "")
        best: _Rule | None = None
        for rule in self.rules:
            if not rule.regex.match(target):
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow)
            ):
                best = rule
        return best is None or best.allow


def _delay(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 and seconds == seconds and seconds != float("inf") else None


def parse(text: str, product_token: str = PRODUCT_TOKEN) -> RobotsRules:
    token = product_token.lower()
    groups: list[tuple[list[str], list[_Rule], list[float]]] = []
    agents: list[str] = []
    rules: list[_Rule] = []
    delays: list[float] = []
    last_was_agent = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules or delays):
                groups.append((agents, rules, delays))
                agents, rules, delays = [], [], []
            agents.append(value.split("/", 1)[0].strip().lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if value and agents:  # an empty disallow restricts nothing
                rules.append(_Rule.build(key == "allow", value))
        elif key == "crawl-delay":
            last_was_agent = False
            seconds = _delay(value)
            if seconds is not None and agents:
                delays.append(seconds)
        else:
            last_was_agent = False
    if agents or rules or delays:
        groups.append((agents, rules, delays))

    for name in (token, "*"):
        matching = [g for g in groups if name in g[0]]
        if matching:
            found = [d for _, _, ds in matching for d in ds]
            return RobotsRules(
                tuple(r for _, rs, _ in matching for r in rs),
                crawl_delay=max(found) if found else None,
            )
    return RobotsRules()
