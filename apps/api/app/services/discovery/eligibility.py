"""Acquisition eligibility — the one place automated acquisition asks "may we?".

Owner decision DR-A4 (docs/decisions/DR-A4_TOS_NOT_TIME_GATED.md): the owner
reads each source's terms personally and records the result in `tos_status`.
That recorded decision is enforced through `radar_eligible` and the
`ck_discovery_source_eligible` CHECK, unchanged. What is NOT an acquisition
gate: `tos_expires_at`, `tos_reviewed_at` currency, `tos_page_hash` changes, or
re-fetching a terms page. None of those are read here. robots.txt remains
mandatory: `radar_eligible` holds the stored decision, and the runner re-evaluates
robots per run and per URL (docs/16 LIVE.2), which this module does not replace.

Source-level policy (all must hold, fails closed):
  - `radar_eligible`: enabled, owner-recorded ToS ALLOWED, robots not a
    disallow, attributed approval;
  - an approved host: `homepage_url` is an absolute http(s) URL with a host;
  - approved paths: at least one `allowed_path_prefixes` entry, each an
    absolute path ("/products/").

URL-level policy: http(s), the exact approved host (no subdomain, credentials
or non-default port), and a path inside one approved prefix.

Passing this check is NOT permission to fetch by itself: a live run still needs
a robots.txt evaluation for the exact URL at fetch time.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from app.models.discovery import DiscoverySource

SOURCE_DISABLED = "SOURCE_DISABLED"
NOT_RADAR_ELIGIBLE = "NOT_RADAR_ELIGIBLE"
NO_APPROVED_HOST = "NO_APPROVED_HOST"
NO_APPROVED_PATHS = "NO_APPROVED_PATHS"
URL_OUTSIDE_APPROVED_HOST = "URL_OUTSIDE_APPROVED_HOST"
URL_OUTSIDE_APPROVED_PATHS = "URL_OUTSIDE_APPROVED_PATHS"

_SCHEMES = ("http", "https")


def approved_host(source: DiscoverySource) -> str | None:
    """The single host a source's approval covers, or None when unusable."""
    if not source.homepage_url:
        return None
    parts = urlsplit(source.homepage_url.strip())
    if parts.scheme.lower() not in _SCHEMES or not parts.hostname:
        return None
    return parts.hostname.lower()


def approved_prefixes(source: DiscoverySource) -> tuple[str, ...]:
    """Well-formed approved path prefixes. A malformed entry approves nothing."""
    return tuple(p for p in (source.allowed_path_prefixes or ()) if p and p.startswith("/"))


def source_ineligibility(source: DiscoverySource | None) -> str | None:
    """None when the source may be acquired from; otherwise the first reason."""
    if source is None or not source.is_enabled:
        return SOURCE_DISABLED
    if not source.radar_eligible:
        return NOT_RADAR_ELIGIBLE
    if approved_host(source) is None:
        return NO_APPROVED_HOST
    if not approved_prefixes(source):
        return NO_APPROVED_PATHS
    return None


def source_acquisition_eligible(source: DiscoverySource | None) -> bool:
    return source_ineligibility(source) is None


def _path_within(path: str, prefix: str) -> bool:
    # "/products" approves "/products" and "/products/x", never "/productsX".
    if prefix.endswith("/"):
        return path.startswith(prefix) or path == prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def url_ineligibility(source: DiscoverySource | None, url: str) -> str | None:
    """None when `url` is inside the source's approved host/path boundary."""
    reason = source_ineligibility(source)
    if reason:
        return reason
    parts = urlsplit(url.strip())
    if (
        parts.scheme.lower() not in _SCHEMES
        or (parts.hostname or "").lower() != approved_host(source)
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 80, 443)
    ):
        return URL_OUTSIDE_APPROVED_HOST
    path = parts.path or "/"
    # Dot segments (plain or percent-encoded) could climb out of a prefix.
    segments = path.lower().replace("%2e", ".").split("/")
    if any(segment in (".", "..") for segment in segments):
        return URL_OUTSIDE_APPROVED_PATHS
    if not any(_path_within(path, prefix) for prefix in approved_prefixes(source)):
        return URL_OUTSIDE_APPROVED_PATHS
    return None
