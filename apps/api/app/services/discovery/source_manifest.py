"""Version-controlled source registry identity and its idempotent sync (docs/28 A4).

`db/discovery/source_registry.json` lists the IDENTITY of every registered
discovery source: key, name, class and the https origin. Syncing it against the
database is register-only and fail-closed:

    missing in the database   -> REGISTERED (apply) / WOULD_REGISTER (plan), through
                                 `register_source`: DISABLED, ToS and robots UNKNOWN
    present and identical     -> UNCHANGED
    present but different     -> DRIFT: reported, never overwritten (a human decides)
    in the database only      -> UNMANAGED: reported, never deleted

It never reviews, authorizes, enables or schedules a source and never fetches:
approval, access basis, enablement and cadence stay attributed database acts.
Adapter readiness is read from code (`sources.ADAPTERS`), never from the file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery.source_registry import SOURCE_CLASSES, register_source

MANIFEST = Path(__file__).resolve().parents[5] / "db" / "discovery" / "source_registry.json"
IDENTITY_FIELDS = ("name", "source_class", "homepage_url")

REGISTERED, WOULD_REGISTER, UNCHANGED, DRIFT, UNMANAGED = (
    "REGISTERED", "WOULD_REGISTER", "UNCHANGED", "DRIFT", "UNMANAGED")


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    """The validated manifest entries, sorted by key. Raises DiscoveryError."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise DiscoveryError(f"{path.name}: 'sources' must be a non-empty list")
    keys = [e.get("key") for e in entries]
    if len(keys) != len(set(keys)):
        raise DiscoveryError(f"{path.name}: duplicate source keys")
    for e in entries:
        missing = [f for f in ("key", *IDENTITY_FIELDS) if not (e.get(f) or "").strip()]
        if missing:
            raise DiscoveryError(f"{path.name}: {e.get('key')!r} is missing {missing}")
        if e["source_class"] not in SOURCE_CLASSES:
            raise DiscoveryError(f"{path.name}: {e['key']}: unknown class {e['source_class']!r}")
        parts = urlsplit(e["homepage_url"])
        if (parts.scheme != "https" or not parts.hostname or parts.path != "/"
                or parts.query or parts.fragment
                or e["homepage_url"] != f"https://{parts.hostname.lower()}/"):
            raise DiscoveryError(f"{path.name}: {e['key']}: homepage_url must be a "
                                 "lower-case https origin ending in '/'")
    return sorted(entries, key=lambda e: e["key"])


@dataclass
class SyncLine:
    key: str
    status: str
    detail: str = ""
    adapter: str = "-"


@dataclass
class SyncResult:
    applied: bool
    lines: list[SyncLine] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for line in self.lines if line.status == status)

    @property
    def needs_attention(self) -> bool:
        return bool(self.count(DRIFT) or self.count(UNMANAGED))

    def text(self) -> list[str]:
        mode = "APPLY" if self.applied else "PLAN (no write)"
        out = [f"SOURCE REGISTRY SYNC  {mode}"]
        out += [f"  {line.key:<28} {line.status:<15} adapter={line.adapter:<14} {line.detail}"
                .rstrip() for line in self.lines]
        out.append(f"summary: {self.count(REGISTERED)} registered, "
                   f"{self.count(WOULD_REGISTER)} would register, {self.count(UNCHANGED)} "
                   f"unchanged, {self.count(DRIFT)} drift, {self.count(UNMANAGED)} unmanaged; "
                   "no review, authorization, enablement, cadence or fetch")
        return out


def _adapter_text(key: str) -> str:
    from app.services.discovery.enrichment import DOCUMENT_SOURCES
    from app.services.discovery.sources import adapter_for

    config = adapter_for(key)
    if config is not None:
        return f"{config.key}@{config.version}"
    return "LANE_B_DOCUMENT" if key in DOCUMENT_SOURCES else "NONE"


def sync_sources(session: Session, *, apply: bool, by: str | None = None,
                 entries: list[dict] | None = None) -> SyncResult:
    """Reconcile the manifest with the database. Writes only on `apply`, and then
    only registrations of missing sources; the caller commits."""
    if apply and not (by or "").strip():
        raise DiscoveryError("--by is required with --apply "
                             "(an unattributed act is not a decision)")
    entries = load_manifest() if entries is None else entries
    existing = {s.key: s for s in session.scalars(select(DiscoverySource))}
    result = SyncResult(applied=apply)
    for entry in entries:
        key = entry["key"]
        source = existing.pop(key, None)
        if source is None:
            if apply:
                register_source(session, key=key, name=entry["name"],
                                source_class=entry["source_class"],
                                homepage_url=entry["homepage_url"],
                                registered_by=f"{by} (source sync, {MANIFEST.name})")
            result.lines.append(SyncLine(key, REGISTERED if apply else WOULD_REGISTER,
                                         "DISABLED, tos/robots UNKNOWN", _adapter_text(key)))
            continue
        diffs = [f"{f}: db={getattr(source, f)!r} manifest={entry[f]!r}"
                 for f in IDENTITY_FIELDS if getattr(source, f) != entry[f]]
        if diffs:
            result.lines.append(SyncLine(key, DRIFT, "; ".join(diffs) + " (not overwritten)",
                                         _adapter_text(key)))
        else:
            state = (f"enabled={source.is_enabled} basis={source.access_basis} "
                     f"tos={source.tos_status} robots={source.robots_status} "
                     f"cadence={source.observation_interval_hours or 'OFF'}")
            result.lines.append(SyncLine(key, UNCHANGED, state, _adapter_text(key)))
    for key in sorted(existing):
        result.lines.append(SyncLine(key, UNMANAGED, "registered in the database, not in the "
                                     "manifest (not deleted)", _adapter_text(key)))
    session.flush()
    return result
