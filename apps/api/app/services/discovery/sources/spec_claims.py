"""Verbatim specification claims for the A4 manufacturer adapters (pure helpers, no I/O).

One rule, shared so every adapter behaves the same: a page's own label/value pair becomes one
TEXT claim `<prefix>.spec[<edition>]/<label>` with the value exactly as written and `unit=None`.
The same key stated twice with the SAME value is kept once (pages repeat blocks for responsive
layouts). The same key stated with DIFFERENT values is dropped entirely and reported, never
resolved. The `<prefix>.*` keys are outside promotion's approved fields, so a claim never becomes
a catalogue fact without the separately governed trace / review / claim chain.
"""
from __future__ import annotations

from app.services.discovery.live_adapter import ExtractedClaim, _evidence
from app.services.discovery.sources import xpeng_iron_proposals as html


class SpecClaims:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self._values: dict[str, str] = {}
        self._claims: dict[str, ExtractedClaim] = {}
        self._conflicted: set[str] = set()
        self.rejected: list[str] = []

    def add(self, edition: str, label: str, value: str, locator: str) -> None:
        label, value = " ".join(label.split()), " ".join(value.split())
        if not (edition and label and value):
            return
        key = f"{self.prefix}.spec[{edition}]/{label}"
        if key in self._conflicted:
            return
        if key in self._values:
            if self._values[key] != value:
                self._conflicted.add(key)
                self._claims.pop(key, None)
                self.rejected.append(f"{key}: stated with different values (dropped)")
            return
        evidence = _evidence(f"{edition} | {label} | {value}", locator)
        if evidence is None:
            self.rejected.append(f"{locator}: excerpt missing or too long")
            return
        self._values[key] = value
        self._claims[key] = ExtractedClaim(key, value, None, "SELECTOR", "HIGH", evidence)

    @property
    def claims(self) -> tuple[ExtractedClaim, ...]:
        return tuple(self._claims.values())


def classes(node) -> set[str]:
    return set((node.attrs.get("class") or "").split())


def children(node) -> list:
    return [c for c in node.children if isinstance(c, html._Node)]


def find(root, tag: str | None = None, cls: str | None = None) -> list:
    """Every element below `root` (document order) with this tag and/or class token."""
    return [n for n in html._walk(root)
            if (tag is None or n.tag == tag) and (cls is None or cls in classes(n))]


def text(node) -> str:
    return html._text(node)
