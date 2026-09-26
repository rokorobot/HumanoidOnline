"""Deterministic, versioned content fingerprint for change detection (Stage B).

`fetched_page.content_hash` is the SHA-256 of the *normalized* body (docs/16 §8),
so that markup churn which says nothing new (rotating nonces, reordered class
names, inline script bundles) does not read as a changed page. The raw body's
own SHA-256 is separate: it addresses the cache (`cache.py`).

Normalization `html-text+jsonld/1` (pure: bytes in, hex digest out, no clock,
no network):

- HTML: the visible text (entities decoded, whitespace collapsed; `<script>`,
  `<style>`, `<noscript>` and `<template>` contents dropped) plus every
  `application/ld+json` block, re-serialized with sorted keys and sorted as a
  set, because structured data is where launch, price and availability changes
  most often surface.
- JSON: re-serialized with sorted keys.
- Anything else: the raw bytes.

Changing any rule above requires a new FINGERPRINT_VERSION: observations are
only compared with earlier observations of the same version.
"""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser

FINGERPRINT_VERSION = "html-text+jsonld/1"

_SKIPPED = {"script", "style", "noscript", "template"}
_WHITESPACE = re.compile(r"\s+")
_CHARSET = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _decode(body: bytes, content_type: str | None) -> str:
    match = _CHARSET.search(content_type or "")
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:  # unknown charset label: fall back deterministically
        return body.decode("utf-8", errors="replace")


def _canonical_json(text: str) -> str | None:
    try:
        return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    except ValueError:
        return None


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.jsonld: list[str] = []
        self._skip_depth = 0
        self._in_jsonld = False
        self._jsonld_buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIPPED:
            kind = (dict(attrs).get("type") or "").strip().lower()
            if tag == "script" and kind == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buffer = []
            else:
                self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            raw = "".join(self._jsonld_buffer)
            self.jsonld.append(_canonical_json(raw) or _collapse(raw))
            self._in_jsonld = False
        elif tag in _SKIPPED and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buffer.append(data)
        elif not self._skip_depth:
            self.text.append(data)


def is_html(content_type: str | None, body: bytes) -> bool:
    if content_type:
        return "html" in content_type.lower()
    return body.lstrip()[:1] == b"<"


def normalize(body: bytes, content_type: str | None) -> bytes:
    """The exact bytes that are hashed into `content_hash`."""
    ctype = (content_type or "").lower()
    if is_html(content_type, body):
        extractor = _Extractor()
        extractor.feed(_decode(body, content_type))
        extractor.close()
        text = _collapse(" ".join(extractor.text))
        blocks = "\n".join(sorted(extractor.jsonld))
        return f"text:\n{text}\njsonld:\n{blocks}".encode()
    if "json" in ctype:
        canonical = _canonical_json(_decode(body, content_type))
        if canonical is not None:
            return canonical.encode()
    return body


def fingerprint(body: bytes, content_type: str | None) -> str:
    return sha256_hex(normalize(body, content_type))
