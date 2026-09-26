"""Content-addressed raw-body cache (docs/16 LIVE.10) — outside the database.

Layout under `var/discovery/cache/` (git-ignored via `var/`):

    <sha256>                        raw response body, addressed by SHA-256 of
                                    its bytes; written once, never rewritten
    observations/<fetched_page_id>.json
                                    links one immutable fetched_page row to the
                                    body it retrieved (raw sha256, fingerprint,
                                    fingerprint version, urls, retrieved_at)

The database keeps hashes and provenance; the page itself lives only here. An
unchanged page is stored once however many observations reference it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.services.discovery.fingerprint import sha256_hex

#: repo root = apps/api/app/services/discovery/cache.py -> parents[5]
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[5] / "var" / "discovery" / "cache"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def store_body(root: Path, body: bytes) -> str:
    """Store `body` under its SHA-256 (idempotent) and return the digest."""
    digest = sha256_hex(body)
    target = root / digest
    if not target.exists():
        _atomic_write(target, body)
    return digest


def read_body(root: Path, digest: str) -> bytes:
    return (root / digest).read_bytes()


def record_observation(root: Path, fetched_page_id: str, meta: dict) -> Path:
    """Write the observation sidecar. Refuses to overwrite: observations are immutable."""
    target = root / "observations" / f"{fetched_page_id}.json"
    if target.exists():
        raise FileExistsError(f"observation {fetched_page_id} already recorded")
    _atomic_write(target, json.dumps(meta, sort_keys=True, indent=2).encode())
    return target
