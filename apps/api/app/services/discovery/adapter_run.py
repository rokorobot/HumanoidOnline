"""Slice B — one adapter run, end to end (docs/16 §12 / §12.1 / §21 step 3).

    reviewed seeds -> bounded one-level enumeration -> Stage B acquisition
    -> deterministic extraction -> evidence excerpts -> candidate / claims /
    signals / image refs -> existing resolve_identity (via pipeline.advance)
    -> human review

Two phases, each behind its own write guard:

1. Acquisition (`acquisition.run_acquisition`, unchanged guard): may write only
   crawl_run, fetched_page and discovery_source bookkeeping.
2. Extraction (this module): may write only discovery-layer rows — candidates,
   claims, commercial signals, evidence excerpts, image refs, extraction results
   and the run's counters. Any other write, canonical above all, is refused, so
   `canonical_rows_written = 0` is enforced rather than hoped.

Identity is the EXISTING deterministic resolver, untouched: exact normalized
manufacturer + model, confirmed aliases only, no fuzzy scoring, no embeddings,
no LLM, no variant folding, no candidate merging. A candidate is keyed by
`(source_id, normalize_url(product URL))`, so re-crawling a page reaches the
same candidate. Nothing is promoted: `advance()` stops at SOURCE_TRACE until a
human records a trace, and promotion stays a separate human act.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.acquisition import (
    EVIDENCE_EXCERPT_MAX_CHARS,
    CandidateCommercialSignal,
    CrawlRun,
    DiscoveryEvidenceExcerpt,
    ExtractionResult,
    FetchedPage,
)
from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
)
from app.services.discovery import cache as body_cache
from app.services.discovery.acquisition import (
    CHANGED,
    COMPLETED_OUTCOMES,
    FIRST_OBSERVATION,
    SOURCE_REMOVED,
    UNCHANGED,
    AcquisitionRefused,
    CanonicalWriteRefused,
    _planned_urls,
    _utcnow,
    classify,
    resume_plan,
    run_acquisition,
    run_chain,
)
from app.services.discovery.eligibility import (
    approved_host,
    approved_prefixes,
    source_ineligibility,
    url_ineligibility,
)
from app.services.discovery.fetcher import HttpFetcher
from app.services.discovery.live_adapter import (
    ANNOUNCEMENT,
    OFFICIAL_CLASSES,
    AnnouncementExtraction,
    Evidence,
    ProductExtraction,
    SourceAdapterConfig,
    _within,
    enumerate_targets,
    extract_announcement,
    extract_product,
)
from app.services.discovery.pipeline import _TERMINAL, advance, flag_recheck
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

NEW_ANNOUNCEMENT_URL = "NEW_ANNOUNCEMENT_URL"
ANNOUNCEMENT_CHANGED = "ANNOUNCEMENT_CHANGED"

_EXTRACTION_WRITES = (
    DiscoveryCandidate, CandidateClaim, CandidateImageRef, CandidateCommercialSignal,
    DiscoveryEvidenceExcerpt, ExtractionResult, CrawlRun,
)
_ORDERABLE = {"AVAILABLE", "PREORDER"}
_MAX_LISTED = 50


class AdapterRefused(AcquisitionRefused):
    """The adapter/source pairing failed review; nothing was requested."""


# ------------------------------------------------------------------ checks --


def adapter_problems(config: SourceAdapterConfig, source: DiscoverySource | None) -> list[str]:
    """Every reason this adapter may not run against this source. Pure."""
    problems: list[str] = []
    if config.structural_review is None:
        problems.append("ADAPTER_NOT_STRUCTURALLY_REVIEWED")
    if config.blocked_reason:
        problems.append(f"ADAPTER_BLOCKED ({config.blocked_reason})")
    if not config.seed_urls:
        problems.append("ADAPTER_HAS_NO_SEEDS")
    if not config.allowed_path_prefixes:
        problems.append("ADAPTER_HAS_NO_PATH_PREFIXES")
    if source is None:
        return [*problems, "SOURCE_NOT_REGISTERED"]
    if source.key != config.source_key:
        problems.append("SOURCE_KEY_MISMATCH")
    if source.source_class != config.source_class:
        problems.append(f"SOURCE_CLASS_MISMATCH ({source.source_class} != {config.source_class})")
    if approved_host(source) != config.host:
        problems.append("HOST_NOT_APPROVED")
    for prefix in config.allowed_path_prefixes:
        if not any(_within(prefix, approved) for approved in approved_prefixes(source)):
            problems.append(f"PATH_PREFIX_NOT_APPROVED ({prefix})")
    reason = source_ineligibility(source)
    if reason:
        problems.append(reason)
    for seed in config.seed_urls:
        try:
            if normalize_url(seed) != seed:
                problems.append(f"SEED_NOT_NORMALIZED ({seed})")
        except UnsupportedUrl:
            problems.append(f"SEED_UNSUPPORTED ({seed})")
            continue
        if not reason and url_ineligibility(source, seed):
            problems.append(f"SEED_OUTSIDE_APPROVAL ({seed})")
    return problems


def plan_adapter(config: SourceAdapterConfig, source: DiscoverySource | None) -> list[str]:
    """No network, no writes: the refusal reasons (empty = runnable)."""
    return adapter_problems(config, source)


# --------------------------------------------------------------------- run --


def _last_seen(session: Session, source: DiscoverySource) -> dict[str, datetime]:
    rows = session.execute(
        select(FetchedPage.url, func.max(FetchedPage.retrieved_at))
        .where(FetchedPage.source_id == source.id)
        .group_by(FetchedPage.url)
    ).all()
    return {url: seen for url, seen in rows}


def run_adapter(
    session: Session,
    *,
    source: DiscoverySource | None,
    config: SourceAdapterConfig,
    operator: str,
    fetcher: HttpFetcher,
    cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow,
    checkpoint: Callable[[], None] = lambda: None,
) -> CrawlRun:
    """One MANUAL adapter run. Refuses before any request unless the adapter is
    structurally reviewed and the source is registered, ToS-approved, enabled and
    approved for exactly this adapter's host and path prefixes."""
    problems = adapter_problems(config, source)
    if problems:
        raise AdapterRefused([("-", p) for p in problems])

    last_seen = _last_seen(session, source)
    holder: dict = {}

    def expand(seed_pages, robots_rules):
        enumeration = enumerate_targets(
            config, [(page.final_url or page.url, body) for page, body in seed_pages],
            robots_rules, last_seen,
        )
        holder["enumeration"] = enumeration
        return enumeration.selected

    run = run_acquisition(
        session, source=source, urls=list(config.seed_urls), operator=operator,
        fetcher=fetcher, cache_dir=cache_dir, now=now, checkpoint=checkpoint,
        expand=expand, adapter=(config.key, config.version),
        manifest_extra={
            "adapter_structural_review": config.structural_review,
            "adapter_manufacturer": config.manufacturer,
            "seed_urls": list(config.seed_urls),
            "target_cap": config.target_cap,
        },
    )
    enumeration = holder.get("enumeration")
    if enumeration is not None:
        run.run_manifest = {**run.run_manifest, "enumeration": {
            "selected": enumeration.selected,
            "deferred": enumeration.deferred,
            "excluded": [{"url": u, "reason": r} for u, r in enumeration.excluded],
        }}
    return _extract_durably(session, run, source, config, cache_dir, now, checkpoint)


def resume_adapter(
    session: Session,
    *,
    parent_run_id,
    source: DiscoverySource | None,
    config: SourceAdapterConfig,
    operator: str,
    fetcher: HttpFetcher,
    cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow,
    checkpoint: Callable[[], None] = lambda: None,
) -> CrawlRun:
    """Resume a FAILED or CANCELLED adapter run (docs/16 §7).

    Honours the parent's manifest: no re-enumeration, only the parent's planned
    seeds and targets that no run in the chain fetched successfully. Committed
    observations are neither re-requested nor duplicated. Extraction then covers
    this run's pages AND any page the chain fetched but never extracted (a run
    interrupted before or during extraction)."""
    problems = adapter_problems(config, source)
    if problems:
        raise AdapterRefused([("-", p) for p in problems])
    parent = session.get(CrawlRun, parent_run_id)
    remaining, skipped = resume_plan(session, parent, source, (config.key, config.version),
                                     fetcher.limits.as_manifest())
    parent_manifest = parent.run_manifest or {}
    parent_targets = parent_manifest.get("expanded_urls", [])
    run = run_acquisition(
        session, source=source, urls=remaining, operator=operator, fetcher=fetcher,
        cache_dir=cache_dir, now=now, checkpoint=checkpoint,
        adapter=(config.key, config.version), resume_of=parent,
        manifest_extra={
            "adapter_structural_review": config.structural_review,
            "adapter_manufacturer": config.manufacturer,
            "seed_urls": parent_manifest.get("seed_urls", list(config.seed_urls)),
            "target_cap": parent_manifest.get("target_cap", config.target_cap),
            "planned_urls": _planned_urls(parent),
            "expanded_urls": [u for u in remaining if u in parent_targets],
            "resume_skipped_completed": skipped,
            **({"enumeration": parent_manifest["enumeration"]}
               if "enumeration" in parent_manifest else {}),
        },
    )
    return _extract_durably(session, run, source, config, cache_dir, now, checkpoint)


def _extract_durably(session, run, source, config, cache_dir, now, checkpoint) -> CrawlRun:
    """Extraction is part of an adapter run: if it raises, its partial rows are
    rolled back and the (already committed) run is durably marked FAILED, so a
    resume re-extracts it. Acquisition observations are untouched."""
    run_id = run.id
    try:
        extract_run(session, run, source, config, cache_dir)
        checkpoint()
        return run
    except Exception as exc:
        session.rollback()
        failed = session.get(CrawlRun, run_id)
        if failed is not None and failed.status in ("COMPLETED", "RUNNING"):
            failed.status = "FAILED"
            failed.finished_at = failed.finished_at or now()
            failed.counters = {**(failed.counters or {}),
                               "halt_reason": f"extraction_failed: {type(exc).__name__}"}
            session.flush()
            checkpoint()
        raise


# -------------------------------------------------------------- extraction --


def _guard(session: Session):
    def before_flush(sess, _ctx, _instances):
        for obj in (*sess.new, *sess.dirty, *sess.deleted):
            if not isinstance(obj, _EXTRACTION_WRITES):
                raise CanonicalWriteRefused(
                    f"adapter extraction may not write {type(obj).__name__} (LIVE.5)"
                )
    event.listen(session, "before_flush", before_flush)
    return lambda: event.remove(session, "before_flush", before_flush)


def _new_counters() -> dict:
    return {
        "target_pages": 0, "deferred_urls": 0, "new_product_urls": 0,
        "products_extracted": 0, "new_entity": 0, "matched_existing": 0,
        "known_robot_new_url": 0, "possible_duplicate": 0, "ambiguous": 0,
        "terminal_candidate_observed": 0, "claims_written": 0, "claims_unchanged": 0,
        "changed_specifications": 0, "signals_written": 0, "signals_unchanged": 0,
        "price_or_quote_signals": 0, "price_changes": 0, "newly_orderable": 0,
        "commercial_status_changes": {"MATURITY": 0, "OBTAINABILITY": 0, "PRICE": 0},
        "image_refs": 0, "rejected_or_unsupported": 0, "changed_pages": 0,
        "unchanged_not_reextracted": 0, "removed_pages": 0, "identity_changed": 0,
        "new_announcement_urls": 0, "announcements_changed": 0,
        "announcement_candidates": 0, "extraction_errors": 0,
        "canonical_rows_written": 0,
    }


def extract_run(
    session: Session, run: CrawlRun, source: DiscoverySource,
    config: SourceAdapterConfig, cache_dir: Path,
) -> dict:
    """Extract every target page of `run` and write discovery-layer rows only."""
    release = _guard(session)
    try:
        counters = _new_counters()
        pages_out: list[dict] = []
        enumeration = (run.run_manifest or {}).get("enumeration") or {}
        counters["deferred_urls"] = len(enumeration.get("deferred", []))
        manifest = run.run_manifest or {}
        targets = _extraction_targets(manifest, config)
        pages = list(session.scalars(
            select(FetchedPage)
            .where(FetchedPage.crawl_run_id == run.id, FetchedPage.url.in_(targets))
            .order_by(FetchedPage.retrieved_at, FetchedPage.url)
        ).all()) if targets else []
        if run.resume_of_run_id is not None:
            pages = _unextracted_ancestor_pages(session, run, config) + pages
        for page in pages:
            counters["target_pages"] += 1
            pages_out.append(_extract_page(session, run, source, config, cache_dir,
                                           page, counters))
        run.counters = {**(run.counters or {}), "extraction": counters,
                        "extraction_pages": pages_out}
        flag_modified(run, "counters")
        session.flush()
        return counters
    finally:
        release()


def _extraction_targets(manifest: dict, config: SourceAdapterConfig) -> set[str]:
    """Pages to extract: the expanded targets, plus any seed that is itself a
    product/announcement page. Such a seed was fetched once as a seed and is
    extracted from that observation, never requested a second time."""
    seeds = {u for u in manifest.get("seed_urls", []) if config.kind_of(u) is not None}
    return set(manifest.get("expanded_urls", [])) | seeds


def _unextracted_ancestor_pages(session, run, config) -> list[FetchedPage]:
    """Target pages the resumed chain fetched successfully but never extracted
    with this extractor version (the parent stopped before extraction)."""
    ancestors = [r.id for r in run_chain(session, run)[1:]]
    parent_targets = set()
    for ancestor in run_chain(session, run)[1:]:
        parent_targets.update(_extraction_targets(ancestor.run_manifest or {}, config))
    if not ancestors or not parent_targets:
        return []
    extracted = select(ExtractionResult.fetched_page_id).where(
        ExtractionResult.extractor_key == config.key,
        ExtractionResult.extractor_version == config.version,
    )
    return list(session.scalars(
        select(FetchedPage)
        .where(FetchedPage.crawl_run_id.in_(ancestors), FetchedPage.url.in_(parent_targets),
               FetchedPage.outcome.in_(COMPLETED_OUTCOMES), FetchedPage.id.not_in(extracted))
        .order_by(FetchedPage.retrieved_at, FetchedPage.url)
    ).all())


def _candidate_for(session, source, url) -> DiscoveryCandidate | None:
    return session.scalars(
        select(DiscoveryCandidate).where(
            DiscoveryCandidate.source_id == source.id,
            DiscoveryCandidate.external_ref == url,
        )
    ).first()


def _extracted_before(session, source, config, page) -> bool:
    return session.scalars(
        select(ExtractionResult.id)
        .join(FetchedPage, FetchedPage.id == ExtractionResult.fetched_page_id)
        .where(
            FetchedPage.source_id == source.id, FetchedPage.url == page.url,
            FetchedPage.id != page.id,
            ExtractionResult.extractor_key == config.key,
            ExtractionResult.extractor_version == config.version,
        ).limit(1)
    ).first() is not None


def _body_page(session, source, page) -> FetchedPage | None:
    """The observation whose body is extracted: this one, or for a 304 the latest
    earlier FETCHED observation of the same URL."""
    if page.outcome == "FETCHED":
        return page
    if page.outcome != "NOT_MODIFIED":
        return None
    return session.scalars(
        select(FetchedPage)
        .where(FetchedPage.source_id == source.id, FetchedPage.url == page.url,
               FetchedPage.outcome == "FETCHED", FetchedPage.id != page.id)
        .order_by(FetchedPage.retrieved_at.desc()).limit(1)
    ).first()


def _extract_page(session, run, source, config, cache_dir, page, counters) -> dict:
    kind = config.kind_of(page.url)
    change = classify(session, page)
    line = {"url": page.url, "kind": kind, "change": change, "result": None}
    url = normalize_url(page.url)
    existing = _candidate_for(session, source, url)

    if change == SOURCE_REMOVED:
        counters["removed_pages"] += 1
        line["result"] = "REMOVED"
        if existing is not None and existing.status not in _TERMINAL:
            flag_recheck(session, existing, f"source page removed (HTTP {page.http_status})")
            line["result"] = "REMOVED: candidate flagged RECHECK_REQUIRED"
        return line
    body_page = _body_page(session, source, page)
    if body_page is None:
        line["result"] = f"NOT_EXTRACTED ({page.outcome})"
        return line
    if change == UNCHANGED and _extracted_before(session, source, config, page):
        counters["unchanged_not_reextracted"] += 1
        line["result"] = "UNCHANGED: not re-extracted"
        return line
    if change == CHANGED:
        counters["changed_pages"] += 1
    body = body_cache.read_observed_body(cache_dir, str(body_page.id))
    if body is None:
        counters["extraction_errors"] += 1
        line["result"] = "ERROR: body not in cache"
        _result(session, run, page, config, "ERROR", None, {"error": "body not in cache"})
        return line

    if kind == ANNOUNCEMENT:
        line["result"] = _announcement(session, run, source, config, page, body_page, url,
                                       change, extract_announcement(config, body), existing,
                                       counters)
    else:
        line["result"] = _product(session, run, source, config, page, body_page, url,
                                  change,
                                  extract_product(
                                      config, body,
                                      normalize_url(body_page.final_url or body_page.url)),
                                  existing, counters)
    return line


def _result(session, run, page, config, status, candidate, notes: dict) -> None:
    session.add(ExtractionResult(
        crawl_run_id=page.crawl_run_id, fetched_page_id=page.id,
        candidate_id=candidate.id if candidate is not None else None,
        extractor_key=config.key, extractor_version=config.version,
        entity_type="ROBOT", status=status,
        notes=json.dumps(notes, sort_keys=True, ensure_ascii=False, default=str),
    ))


def _new_candidate(session, source, config, url, name) -> DiscoveryCandidate:
    candidate = DiscoveryCandidate(
        id=uuid.uuid4(), source_id=source.id, entity_type="ROBOT",
        candidate_name=name, candidate_manufacturer=config.manufacturer,
        discovery_url=url, external_ref=url,
        candidate_data={"official_url": url} if source.source_class in OFFICIAL_CLASSES else None,
    )
    session.add(candidate)
    session.flush()
    return candidate


def _resolve(session, candidate, counters, *, is_new: bool) -> str:
    advance(session, candidate)
    identity = candidate.identity_status
    key = {"NEW_ENTITY": "new_entity", "MATCHED_EXISTING": "matched_existing",
           "POSSIBLE_DUPLICATE": "possible_duplicate", "AMBIGUOUS": "ambiguous"}.get(identity)
    if key:
        counters[key] += 1
    if is_new and identity == "MATCHED_EXISTING":
        counters["known_robot_new_url"] += 1
    return identity


def _excerpt(session, source, subject_type, subject_id, body_page, evidence: Evidence) -> None:
    session.add(DiscoveryEvidenceExcerpt(
        subject_type=subject_type, subject_id=subject_id,
        discovery_source_id=source.id, crawl_run_id=body_page.crawl_run_id,
        fetched_page_id=body_page.id, excerpt_text=evidence.excerpt,
        page_url=body_page.final_url or body_page.url, retrieved_at=body_page.retrieved_at,
        page_hash=body_page.content_hash, locator=evidence.locator, ordinal=0,
    ))


def _signal_key(signal) -> tuple:
    if signal.axis == "PRICE":
        return (signal.price_type, signal.price_amount, signal.price_currency, signal.region_code)
    if signal.axis == "OBTAINABILITY":
        return (signal.availability_value, signal.region_code)
    return (signal.maturity_value, signal.region_code)


def _product(session, run, source, config, page, body_page, url, change,
             extraction: ProductExtraction, existing, counters) -> str:
    counters["rejected_or_unsupported"] += len(extraction.rejected)
    notes = {"change": change, "name_method": extraction.name_method,
             "rejected": list(extraction.rejected[:_MAX_LISTED]), "notes": list(extraction.notes)}
    if extraction.status != "EXTRACTED" or not extraction.name:
        _result(session, run, page, config, extraction.status, existing, notes)
        if existing is not None and existing.status not in _TERMINAL:
            flag_recheck(session, existing,
                         f"page no longer yields one product ({extraction.status})")
            return f"{extraction.status}: existing candidate flagged RECHECK_REQUIRED"
        return f"{extraction.status}: no candidate"

    counters["products_extracted"] += 1
    if existing is not None and existing.status in _TERMINAL:
        # Re-checking a promoted/rejected candidate is a new discovery event
        # (pipeline.flag_recheck, H5); the observation is recorded, nothing attached.
        counters["terminal_candidate_observed"] += 1
        _result(session, run, page, config, "EXTRACTED", existing,
                {**notes, "terminal": existing.status})
        return f"TERMINAL candidate ({existing.status}): observation recorded only"

    is_new = existing is None
    candidate = existing or _new_candidate(session, source, config, url, extraction.name)
    if is_new:
        counters["new_product_urls"] += 1
    identity_changed = not is_new and candidate.candidate_name != extraction.name
    if identity_changed:
        counters["identity_changed"] += 1
        notes["identity_changed"] = {"was": candidate.candidate_name, "now": extraction.name}
    candidate.last_seen_at = page.retrieved_at

    # --- claims: one row per distinct (field, value, unit) from this source ---
    prior: dict[str, set] = {}
    for claim in candidate.claims:
        if claim.discovery_source_id == source.id:
            prior.setdefault(claim.field_key, set()).add((claim.claimed_value, claim.unit))
    excerpts: list[tuple[str, uuid.UUID, Evidence]] = []
    for c in extraction.claims:
        seen = prior.setdefault(c.field_key, set())
        if (c.claimed_value, c.unit) in seen:
            counters["claims_unchanged"] += 1
            continue
        if seen:
            counters["changed_specifications"] += 1
        seen.add((c.claimed_value, c.unit))
        claim = CandidateClaim(
            id=uuid.uuid4(), field_key=c.field_key, claimed_value=c.claimed_value, unit=c.unit,
            discovery_source_id=source.id, evidence_url=body_page.final_url or body_page.url,
            extractor_key=config.key, extractor_version=config.version,
            extraction_method=c.method, extraction_confidence=c.confidence,
            crawl_run_id=body_page.crawl_run_id, fetched_page_id=body_page.id,
        )
        candidate.claims.append(claim)
        excerpts.append(("CLAIM", claim.id, c.evidence))
        counters["claims_written"] += 1

    # --- commercial signals: one axis per row, never merged (LIVE.7) ---------
    prior_signals: dict[str, set] = {}
    for s in session.scalars(select(CandidateCommercialSignal).where(
            CandidateCommercialSignal.candidate_id == candidate.id,
            CandidateCommercialSignal.discovery_source_id == source.id)).all():
        prior_signals.setdefault(s.axis, set()).add(_signal_key(s))
    for s in extraction.signals:
        seen = prior_signals.setdefault(s.axis, set())
        key = _signal_key(s)
        if key in seen:
            counters["signals_unchanged"] += 1
            continue
        if seen:
            counters["commercial_status_changes"][s.axis] += 1
            if s.axis == "PRICE":
                counters["price_changes"] += 1
        if s.axis == "OBTAINABILITY" and s.availability_value in _ORDERABLE:
            counters["newly_orderable"] += 1
        if s.axis == "PRICE":
            counters["price_or_quote_signals"] += 1
        seen.add(key)
        signal = CandidateCommercialSignal(
            id=uuid.uuid4(), candidate_id=candidate.id, discovery_source_id=source.id,
            crawl_run_id=body_page.crawl_run_id, fetched_page_id=body_page.id,
            axis=s.axis, maturity_value=s.maturity_value,
            availability_value=s.availability_value, region_code=s.region_code,
            price_type=s.price_type, price_amount=s.price_amount,
            price_currency=s.price_currency, extractor_key=config.key,
            extractor_version=config.version, extraction_method=s.method,
            extraction_confidence=s.confidence,
        )
        session.add(signal)
        excerpts.append(("COMMERCIAL_SIGNAL", signal.id, s.evidence))
        counters["signals_written"] += 1

    # --- image references: URL + retrieval provenance only (LIVE.9, Gate M) ---
    known_images = {im.image_url for im in candidate.images}
    for im in extraction.images:
        if im.image_url in known_images:
            continue
        known_images.add(im.image_url)
        candidate.images.append(CandidateImageRef(
            image_url=im.image_url, discovery_source_id=source.id,
            page_url=body_page.final_url or body_page.url, retrieved_at=body_page.retrieved_at,
            alt_text=im.alt_text, retrieval_source_class=source.source_class,
            crawl_run_id=body_page.crawl_run_id, fetched_page_id=body_page.id,
        ))
        counters["image_refs"] += 1

    session.flush()  # subjects exist before their excerpts (trg_evidence_excerpt_subject)
    for subject_type, subject_id, evidence in excerpts:
        _excerpt(session, source, subject_type, subject_id, body_page, evidence)
    _result(session, run, page, config, "EXTRACTED", candidate, notes)
    identity = _resolve(session, candidate, counters, is_new=is_new)
    if identity_changed:
        flag_recheck(session, candidate,
                     f"product name changed from {notes['identity_changed']['was']!r} "
                     f"to {extraction.name!r}")
    return f"{'NEW' if is_new else 'SEEN'} candidate {candidate.candidate_name!r}: {identity}"


def _announcement(session, run, source, config, page, body_page, url, change,
                  extraction: AnnouncementExtraction, existing, counters) -> str:
    classification = NEW_ANNOUNCEMENT_URL if change == FIRST_OBSERVATION else (
        ANNOUNCEMENT_CHANGED if change == CHANGED else "ANNOUNCEMENT_REEXTRACTED")
    if classification == NEW_ANNOUNCEMENT_URL:
        counters["new_announcement_urls"] += 1
    elif classification == ANNOUNCEMENT_CHANGED:
        counters["announcements_changed"] += 1
    headline = extraction.headline
    if headline and len(headline) > EVIDENCE_EXCERPT_MAX_CHARS:
        headline = None
    notes = {
        "classification": classification, "headline": headline,
        "excerpt": extraction.evidence.excerpt if extraction.evidence else None,
        "locator": extraction.evidence.locator if extraction.evidence else None,
        "page_url": body_page.final_url or body_page.url,
        "retrieved_at": body_page.retrieved_at.isoformat(),
        "page_hash": body_page.content_hash, "notes": list(extraction.notes),
    }
    if extraction.product_name is None:
        # No explicit identity: evidence only, waiting for a human (never a guess).
        _result(session, run, page, config, "AMBIGUOUS", None, notes)
        return f"{classification}: evidence recorded, awaiting human review"
    if existing is not None and existing.status in _TERMINAL:
        counters["terminal_candidate_observed"] += 1
        _result(session, run, page, config, "EXTRACTED", existing, notes)
        return f"{classification}: TERMINAL candidate ({existing.status}), recorded only"
    is_new = existing is None
    candidate = existing or _new_candidate(session, source, config, url, extraction.product_name)
    if is_new:
        counters["announcement_candidates"] += 1
    candidate.last_seen_at = page.retrieved_at
    _result(session, run, page, config, "EXTRACTED", candidate, notes)
    identity = _resolve(session, candidate, counters, is_new=is_new)
    return f"{classification}: candidate {candidate.candidate_name!r}: {identity}"
