"""Source-stable URL -> `external_ref` normalizer (docs/16 §11).

A live adapter keys every candidate by `(source_id, external_ref)`, which the
database already holds unique. If the same product page could arrive under two
spellings (a tracking parameter, an upper-case host, a trailing slash), a
re-crawl would create a second candidate for it, and the resolver would then
report the two as POSSIBLE_DUPLICATE of each other. This module removes those
non-semantic differences, and nothing else.

Rules (pure, deterministic; no network, no clock):
- scheme and host are lower-cased; a default port (80 for http, 443 for https)
  is dropped; any other port is kept;
- the fragment is dropped (it never reaches the server);
- query parameters named in `TRACKING_PARAMS`, or starting with a prefix in
  `TRACKING_PREFIXES`, are removed; every other parameter is kept with its
  exact value, and the kept parameters are sorted so their order is not
  identity;
- one trailing slash is removed from a non-root path ("/robots/4ne1/" ->
  "/robots/4ne1"); the root path stays "/";
- the path's letter case and percent-encoding are preserved: servers may treat
  them as meaningful, so folding them could merge two different pages.

A URL that is not absolute http(s) is refused rather than guessed at.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Parameters that identify a campaign or click, never a page.
TRACKING_PARAMS = frozenset({
    "gclid", "dclid", "gbraid", "wbraid", "fbclid", "msclkid", "yclid", "twclid",
    "igshid", "mc_cid", "mc_eid", "_ga", "_gl", "_hsenc", "_hsmi", "mkt_tok",
})
TRACKING_PREFIXES = ("utm_",)

_DEFAULT_PORTS = {"http": 80, "https": 443}


class UnsupportedUrl(ValueError):
    """The value is not an absolute http(s) URL, so it has no stable reference."""


def _is_tracking(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    """The source-stable form of `url`, used as a live candidate's external_ref."""
    parts = urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parts.hostname:
        raise UnsupportedUrl(f"not an absolute http(s) URL: {url!r}")
    if parts.username is not None or parts.password is not None:
        raise UnsupportedUrl(f"URL carries credentials: {url!r}")

    host = parts.hostname.lower()
    port = parts.port
    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(name)
    ]
    query = urlencode(sorted(kept), doseq=False)
    return urlunsplit((scheme, netloc, path, query, ""))
