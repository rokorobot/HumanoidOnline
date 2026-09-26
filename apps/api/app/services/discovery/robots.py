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


def parse(text: str, product_token: str = PRODUCT_TOKEN) -> RobotsRules:
    token = product_token.lower()
    groups: list[tuple[list[str], list[_Rule]]] = []
    agents: list[str] = []
    rules: list[_Rule] = []
    last_was_agent = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.split("/", 1)[0].strip().lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if value and agents:  # an empty disallow restricts nothing
                rules.append(_Rule.build(key == "allow", value))
        else:
            last_was_agent = False
    if agents or rules:
        groups.append((agents, rules))

    specific = [r for names, group in groups if token in names for r in group]
    if any(token in names for names, _ in groups):
        return RobotsRules(tuple(specific))
    wildcard = [r for names, group in groups if "*" in names for r in group]
    return RobotsRules(tuple(wildcard))
