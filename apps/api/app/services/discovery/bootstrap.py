"""MANUAL_BOOTSTRAP — DATA-D1.LIVE §2.1 acquisition mode (docs/16, RATIFIED v0.1).

The immediate inventory path, and the one that needs nobody's permission: a named
human reads an official source and records what it says. That is how the current
verified catalogue of seven robots was built, and anti-robot clauses in a site's
terms govern *automated* access — not a person reading a public page.

**No network. No traversal. No adapter.** This module reads a local bootstrap
file and writes discovery-layer rows through the existing, ratified `ingest`
path (`services/discovery/adapters.py`). It deliberately adds no second writer:
the DATA-D1.10 shadow-data allowlist, the R3 image-reference rules and the
`(source, external_ref)` dedup all apply unchanged.

What a bootstrap record may carry, and what it may not:

    identity        manufacturer + model name           -> candidate
    official_url    a LEAD to the manufacturer's page   -> candidate_data
    claims          ONLY with an evidence excerpt and a retrieval timestamp

A bootstrap entry with no claims is the honest default. It asserts that a robot
appears to exist and where to look — nothing about its height, price or
availability. Those are facts, and a fact needs evidence (LIVE.6 / G2). The
`RADAR -> CANDIDATE -> TRACE -> VERIFY -> PROMOTE` pipeline is unchanged: nothing
here reaches the catalogue without a human confirming a trace and promoting it.

Why a MANUAL_BOOTSTRAP source is radar-eligible: `radar_eligible` gates
*crawling*. Manual entry accesses nobody's site automatically, so
`robots_status = NOT_APPLICABLE` is literally true and `tos_status = ALLOWED` is
not a claim about any third party's terms — it is the statement that no automated
access occurs. The review is still attributed to the operator, because an
unattributed record is not a record (DATA-D1.9).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery.adapters import FixtureAdapter, ingest

#: The one source class that describes a human-entered inventory record. It is
#: NOT `MANUFACTURER`: we did not read the manufacturer's site automatically, and
#: claiming otherwise would misstate provenance.
BOOTSTRAP_SOURCE_CLASS = "OTHER"

#: Bootstrap datasets live here, committed and reviewable in a diff.
#: parents: discovery -> services -> app -> api -> apps -> <repo root>
BOOTSTRAP_DIR = Path(__file__).resolve().parents[5] / "db" / "discovery" / "bootstrap"


def bootstrap_source_key(dataset: str) -> str:
    """One source per dataset, so a batch can be audited and re-run as a unit."""
    return f"manual-bootstrap:{dataset}"


def register_bootstrap_source(
    session: Session, *, dataset: str, operator: str
) -> DiscoverySource:
    """Create (or return) the MANUAL_BOOTSTRAP source for `dataset`.

    `operator` is recorded as the eligibility reviewer — the named human of
    LIVE.4. It is required: an unattributed inventory record cannot be audited,
    and "who entered this" is the first question anyone will ask of a fact that
    turns out to be wrong.
    """
    if not operator or not operator.strip():
        raise DiscoveryError(
            "MANUAL_BOOTSTRAP requires a named operator — an unattributed "
            "inventory record is not auditable (LIVE.4 / DATA-D1.9)"
        )

    key = bootstrap_source_key(dataset)
    existing = session.execute(
        select(DiscoverySource).where(DiscoverySource.key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    source = DiscoverySource(
        key=key,
        name=f"Manual bootstrap — {dataset}",
        source_class=BOOTSTRAP_SOURCE_CLASS,
        # No automated access occurs, so there is no robots policy to obey and no
        # third party's terms being relied upon. Both statements are literally
        # true for a human-entered record; neither is a claim about a website.
        tos_status="ALLOWED",
        robots_status="NOT_APPLICABLE",
        eligibility_reviewed_at=datetime.now(UTC),
        eligibility_reviewed_by=operator.strip(),
        is_enabled=True,
        notes=(
            "MANUAL_BOOTSTRAP (DATA-D1.LIVE §2.1). Human-entered inventory: no "
            "automated traversal, no fetching, no adapter. Candidates carry "
            "identity plus an official-URL LEAD; every fact still requires "
            "evidence, a trace and human promotion."
        ),
    )
    session.add(source)
    session.flush()
    return source


def load_dataset(dataset: str) -> list[dict]:
    """Read a committed bootstrap dataset by name."""
    path = BOOTSTRAP_DIR / f"{dataset}.json"
    if not path.is_file():
        available = sorted(p.stem for p in BOOTSTRAP_DIR.glob("*.json"))
        raise DiscoveryError(
            f"no bootstrap dataset {dataset!r} in {BOOTSTRAP_DIR}; available: {available}"
        )
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise DiscoveryError(f"bootstrap dataset {dataset!r} must be a JSON array")
    return records


def validate_dataset(records: list[dict]) -> None:
    """Refuse a dataset that asserts facts it cannot support.

    This is the line MANUAL_BOOTSTRAP must not cross. Entering "this robot
    appears to exist, here is the maker's page" is a lead a human can stand
    behind. Entering "it is 170 cm tall and costs $30,000" without a quoted
    passage and a retrieval time is the invention of market data — the exact
    failure the contract was written to prevent, arriving by keyboard instead of
    by crawler.
    """
    seen: set[str] = set()
    for index, record in enumerate(records):
        where = f"record {index} ({record.get('external_ref', '?')})"
        for field in ("external_ref", "name", "manufacturer"):
            if not str(record.get(field) or "").strip():
                raise DiscoveryError(f"{where}: {field} is required")

        ref = str(record["external_ref"])
        if ref in seen:
            raise DiscoveryError(f"{where}: duplicate external_ref {ref!r}")
        seen.add(ref)

        for claim in record.get("claims") or []:
            if not str(claim.get("evidence_url") or "").strip():
                raise DiscoveryError(
                    f"{where}: claim {claim.get('field_key')!r} has no evidence_url. "
                    "A bootstrap entry may carry identity and an official-URL lead "
                    "with no claims at all; a CLAIM without evidence is invented "
                    "market data (LIVE.6 / G2)."
                )


def bootstrap(
    session: Session,
    *,
    dataset: str,
    operator: str,
    records: list[dict] | None = None,
) -> tuple[DiscoverySource, list[DiscoveryCandidate]]:
    """Ingest a bootstrap dataset. Re-running is safe: `ingest` dedups by
    `(source, external_ref)` and only refreshes `last_seen_at`.

    `records` supplies an in-memory batch instead of reading the committed file —
    used to review an uncommitted batch, and by the tests, so that a batch is
    always validated by the same code path that writes it.
    """
    if records is None:
        records = load_dataset(dataset)
    validate_dataset(records)
    source = register_bootstrap_source(session, dataset=dataset, operator=operator)
    created = ingest(session, source, FixtureAdapter(records=records))
    return source, created
