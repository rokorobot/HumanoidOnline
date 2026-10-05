"""Manual evidence capture — record bytes an operator ALREADY retrieved as a governed observation.

The smallest generic capability that lets manually / agent-retrieved public evidence enter the
same pipeline as automated observations:

    retained bytes -> immutable observation (`crawl_run` + `fetched_page`) -> proposals
    -> review -> accepted claims -> materialization

It performs NO network access and cannot: it takes the body as an argument. It does not enable,
review or schedule a source, so a source that is not approved for automated fetching (for
example Alza.cz) can still carry manually captured reference evidence. What it records is the
fact of the retrieval (who, when, under what provenance statement, which bytes by hash), exactly
like an automated observation, so every later claim keeps a verifiable chain to the bytes.

Rules:
- the URL must be on the source's own host (`homepage_url`); credentials / odd ports refused;
- a `provenance` statement is mandatory (the work order or occasion under which the bytes were
  retrieved); an unattributed capture is not evidence;
- `retrieved_at` is the time of the retrieval, never "now" by default and never in the future;
- idempotent: capturing the same bytes for the same URL again returns the existing observation.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError, cache
from app.services.discovery.eligibility import approved_host
from app.services.discovery.fingerprint import fingerprint, sha256_hex
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

ADAPTER_KEY = "manual-capture"
ADAPTER_VERSION = "1"


def record_manual_capture(
    session: Session, *, source_key: str, url: str, body: bytes, content_type: str,
    retrieved_at: datetime, captured_by: str, provenance: str,
    cache_dir: Path | None = None, http_status: int = 200,
) -> tuple[FetchedPage, bool]:
    """Record one retained page as an observation. Returns (page, created)."""
    if not captured_by or not captured_by.strip():
        raise DiscoveryError("a manual capture must name who captured it (--by)")
    if not provenance or not provenance.strip():
        raise DiscoveryError("a manual capture needs a provenance statement (work order / "
                             "occasion); unattributed bytes are not evidence")
    if not body:
        raise DiscoveryError("a manual capture needs the retrieved bytes")
    if retrieved_at.tzinfo is None:
        raise DiscoveryError("retrieved_at must be timezone-aware (UTC)")
    if retrieved_at > datetime.now(UTC):
        raise DiscoveryError("retrieved_at is in the future")
    source = session.scalar(select(DiscoverySource).where(DiscoverySource.key == source_key))
    if source is None:
        raise DiscoveryError(f"unknown discovery source {source_key!r}")
    try:
        norm = normalize_url(url)
    except UnsupportedUrl as exc:
        raise DiscoveryError(f"unusable capture URL: {exc}") from exc
    host = (urlsplit(norm).hostname or "").lower()
    if approved_host(source) is None or host != approved_host(source):
        raise DiscoveryError(f"{norm} is not on the source's own host "
                             f"({approved_host(source)!r}); refusing")
    digest = fingerprint(body, content_type)

    for page in session.scalars(select(FetchedPage).where(
            FetchedPage.source_id == source.id, FetchedPage.content_hash == digest)):
        try:
            if normalize_url(page.url) == norm:
                return page, False
        except UnsupportedUrl:
            continue

    run = CrawlRun(
        source_id=source.id, adapter_key=ADAPTER_KEY, adapter_version=ADAPTER_VERSION,
        trigger="MANUAL", operator=captured_by.strip(), status="COMPLETED",
        started_at=retrieved_at, finished_at=retrieved_at,
        run_manifest={"kind": "MANUAL_CAPTURE", "provenance": provenance.strip(),
                      "url": norm, "no_network_in_this_step": True},
        counters={"pages": 1})
    session.add(run)
    session.flush()
    page = FetchedPage(
        crawl_run_id=run.id, source_id=source.id, url=norm, final_url=norm,
        http_status=http_status, content_type=content_type, content_length=len(body),
        content_hash=digest, retrieved_at=retrieved_at, outcome="FETCHED",
        retrieval_method="HTTP_GET")
    session.add(page)
    session.flush()
    if cache_dir is not None:
        raw = cache.store_body(cache_dir, body)
        cache.record_observation(cache_dir, str(page.id), {
            "raw_sha256": raw, "sha256_check": sha256_hex(body), "fingerprint": digest,
            "url": norm, "final_url": norm, "retrieved_at": retrieved_at.isoformat(),
            "manual_capture": True, "provenance": provenance.strip(),
            "captured_by": captured_by.strip()})
    return page, True
