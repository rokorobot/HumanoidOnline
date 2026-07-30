"""MANUAL_BOOTSTRAP (DATA-D1.LIVE §2.1) — the immediate inventory path.

The mode exists because the eligibility assessment found that most manufacturer
sites prohibit automated access, and waiting for permission would leave the
catalogue at seven robots indefinitely. A person reading a public page is not a
crawler, and that is how the current verified catalogue was built.

What these tests hold the line on: MANUAL_BOOTSTRAP fills the *discovery queue*,
not the catalogue. It may record identity and an official-URL lead freely; it may
not record a FACT without evidence, because a fabricated spec typed by hand is
the same defect as a fabricated spec scraped by a bot.
"""
from __future__ import annotations

import json
import pathlib
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import CandidateClaim, DiscoveryCandidate
from app.models.robot import Robot
from app.services.discovery import DiscoveryError
from app.services.discovery.bootstrap import (
    BOOTSTRAP_DIR,
    bootstrap,
    load_dataset,
    register_bootstrap_source,
    validate_dataset,
)

DATASET = "humanoid_radar_v1"


def _batch(size: int = 3) -> list[dict]:
    """A synthetic batch under a unique namespace.

    Ingest dedups by `(source, external_ref)`, so a test asserting "N created"
    against the shipped dataset would depend on the database never having seen it
    — which stops being true the moment anyone runs the CLI. A unique batch keeps
    the assertion about behaviour rather than about database history.
    """
    tag = uuid.uuid4().hex[:8]
    return [
        {
            "external_ref": f"probe-{tag}/robot-{i}",
            "name": f"Probe {i}",
            "manufacturer": f"Probe Robotics {tag}",
            "discovery_url": "https://probe.invalid/",
            "data": {"official_url": "https://probe.invalid/"},
        }
        for i in range(size)
    ]


def _label() -> str:
    """A unique dataset label, so each test owns its own bootstrap source."""
    return f"probe_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


# --------------------------------------------------------------------------- #
# The shipped dataset
# --------------------------------------------------------------------------- #
def test_the_shipped_dataset_is_committed_and_parseable() -> None:
    records = load_dataset(DATASET)
    assert len(records) >= 40, "the radar seed should cover the visible market"
    makers = {r["manufacturer"] for r in records}
    assert len(makers) >= 25


def test_every_entry_has_identity_and_an_official_url_lead() -> None:
    """Identity plus a place to look. That is the whole permitted payload of a
    bootstrap entry — it is a RADAR record, not a spec sheet."""
    for record in load_dataset(DATASET):
        assert record["manufacturer"].strip()
        assert record["name"].strip()
        official = (record.get("data") or {}).get("official_url", "")
        assert official.startswith("https://"), record["external_ref"]


def test_the_shipped_dataset_ingests_end_to_end(dsession) -> None:
    """The real seed, through the real path. Counted RELATIVELY so it holds whether
    or not this database has seen the batch before."""
    records = load_dataset(DATASET)
    before = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()
    source, created = bootstrap(dsession, dataset=DATASET, operator="ops@test")
    after = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()

    present = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
        .where(DiscoveryCandidate.source_id == source.id)
    ).scalar_one()
    assert present == len(records), "every seed entry should be in the queue"
    assert after - before == len(created)


def test_the_shipped_dataset_asserts_no_specifications_or_prices(dsession) -> None:
    """The seed deliberately carries ZERO claims.

    Everything in it is knowable without reading a page: this robot exists, this
    company makes it, here is their site. A height, a payload or a price would be
    a fact, and this dataset has no evidence for one — so it does not state one.
    UNKNOWN stays UNKNOWN.
    """
    for record in load_dataset(DATASET):
        assert not record.get("claims"), (
            f"{record['external_ref']} carries claims with no evidence; the seed "
            "must assert identity only"
        )
        assert not record.get("images"), (
            f"{record['external_ref']} carries an image reference; imagery goes "
            "through MEDIA-01, never a bootstrap seed"
        )


def test_external_refs_are_unique_and_namespaced() -> None:
    refs = [r["external_ref"] for r in load_dataset(DATASET)]
    assert len(refs) == len(set(refs))
    for ref in refs:
        assert "/" in ref, f"{ref} should be maker-namespaced for dependable dedup"


def test_the_dataset_covers_the_manufacturers_already_in_the_catalogue() -> None:
    """The seed should overlap the verified catalogue, so identity resolution has
    something real to match and a wrong match is visible immediately."""
    makers = {r["manufacturer"] for r in load_dataset(DATASET)}
    for known in ("Unitree Robotics", "Agility Robotics", "Engineered Arts", "Figure AI"):
        assert known in makers


# --------------------------------------------------------------------------- #
# Validation refuses invented market data
# --------------------------------------------------------------------------- #
def test_a_claim_without_evidence_is_refused() -> None:
    """The line MANUAL_BOOTSTRAP must not cross. Typing an unsourced spec is the
    same defect as scraping one — it just arrives by keyboard."""
    with pytest.raises(DiscoveryError) as exc:
        validate_dataset([{
            "external_ref": "x/y", "name": "Y", "manufacturer": "X",
            "claims": [{"field_key": "height_cm", "claimed_value": "170"}],
        }])
    assert "invented market data" in str(exc.value)


def test_a_claim_with_evidence_is_accepted() -> None:
    validate_dataset([{
        "external_ref": "x/y", "name": "Y", "manufacturer": "X",
        "claims": [{
            "field_key": "height_cm", "claimed_value": "170",
            "evidence_url": "https://maker.invalid/y/specs",
        }],
    }])


@pytest.mark.parametrize("missing", ["external_ref", "name", "manufacturer"])
def test_identity_is_mandatory(missing: str) -> None:
    record = {"external_ref": "x/y", "name": "Y", "manufacturer": "X"}
    del record[missing]
    with pytest.raises(DiscoveryError):
        validate_dataset([record])


def test_duplicate_external_refs_are_refused() -> None:
    record = {"external_ref": "x/y", "name": "Y", "manufacturer": "X"}
    with pytest.raises(DiscoveryError) as exc:
        validate_dataset([record, dict(record)])
    assert "duplicate" in str(exc.value)


def test_an_unknown_dataset_is_refused() -> None:
    with pytest.raises(DiscoveryError) as exc:
        load_dataset("no-such-dataset")
    assert "available" in str(exc.value)


# --------------------------------------------------------------------------- #
# The source record is truthful about what it is
# --------------------------------------------------------------------------- #
def test_the_bootstrap_source_requires_a_named_operator(dsession) -> None:
    """LIVE.4 / DATA-D1.9: "who entered this" is the first question anyone asks of
    a fact that turns out to be wrong."""
    with pytest.raises(DiscoveryError) as exc:
        register_bootstrap_source(dsession, dataset=_label(), operator="  ")
    assert "named operator" in str(exc.value)


def test_the_bootstrap_source_does_not_claim_to_be_the_manufacturer(dsession) -> None:
    """Provenance must not be overstated. We did not read the manufacturer's site
    automatically, so the source class is not MANUFACTURER — claiming otherwise
    would give a hand-typed lead the authority of an official reading."""
    source = register_bootstrap_source(dsession, dataset=_label(), operator="ops@test")
    assert source.source_class == "OTHER"
    assert source.key.startswith("manual-bootstrap:")


def test_the_bootstrap_source_states_no_automated_access(dsession) -> None:
    """`robots_status = NOT_APPLICABLE` is literally true for a human-entered
    record, and `tos_status = ALLOWED` asserts that no automated access occurs —
    not that any third party permitted anything."""
    source = register_bootstrap_source(dsession, dataset=_label(), operator="ops@test")
    assert source.robots_status == "NOT_APPLICABLE"
    assert source.eligibility_reviewed_by == "ops@test"
    assert source.radar_eligible is True
    assert "no automated traversal" in source.notes


def test_registering_twice_reuses_the_same_source(dsession) -> None:
    label = _label()
    first = register_bootstrap_source(dsession, dataset=label, operator="ops@test")
    second = register_bootstrap_source(dsession, dataset=label, operator="ops@test")
    assert first.id == second.id


# --------------------------------------------------------------------------- #
# Ingest behaviour
# --------------------------------------------------------------------------- #
def test_bootstrap_creates_candidates_for_every_entry(dsession) -> None:
    records = _batch(4)
    _, created = bootstrap(
        dsession, dataset=_label(), operator="ops@test", records=records
    )
    assert len(created) == len(records)
    for candidate in created:
        assert candidate.status == "DISCOVERED"
        assert candidate.identity_status == "UNRESOLVED"
        assert candidate.entity_type == "ROBOT"


def test_bootstrap_is_idempotent(dsession) -> None:
    """Re-running a batch must not duplicate the market. `(source, external_ref)`
    dedup only refreshes `last_seen_at`."""
    label, records = _label(), _batch()
    bootstrap(dsession, dataset=label, operator="ops@test", records=records)
    before = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()
    _, created_again = bootstrap(
        dsession, dataset=label, operator="ops@test", records=records
    )
    after = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()
    assert created_again == []
    assert after == before


def test_bootstrap_writes_no_claims_and_no_canonical_row(dsession) -> None:
    """The invariant that matters: filling the queue is not filling the catalogue."""
    robots_before = dsession.execute(select(func.count()).select_from(Robot)).scalar_one()
    claims_before = dsession.execute(
        select(func.count()).select_from(CandidateClaim)
    ).scalar_one()

    bootstrap(dsession, dataset=_label(), operator="ops@test", records=_batch())

    robots_after = dsession.execute(select(func.count()).select_from(Robot)).scalar_one()
    claims_after = dsession.execute(
        select(func.count()).select_from(CandidateClaim)
    ).scalar_one()
    assert robots_after == robots_before, "bootstrap must not write canonical rows"
    assert claims_after == claims_before, "the seed asserts no facts"


def test_the_official_url_is_a_lead_not_a_confirmed_trace(dsession) -> None:
    """H2, unchanged: a discovered official URL is a lead. Only an explicit
    `record_trace(...)` by a human confirms it, and promotion needs that."""
    _, created = bootstrap(
        dsession, dataset=_label(), operator="ops@test", records=_batch()
    )
    for candidate in created:
        assert candidate.trace_state == "NOT_TRACED"
        assert candidate.trace_verified_by is None
        assert (candidate.candidate_data or {}).get("official_url")


def test_nothing_bootstrapped_is_promotable_without_a_trace(dsession) -> None:
    """The promotion gate is untouched: a full queue changes nothing about what it
    takes to reach the catalogue."""
    from app.services.discovery.promotion import build_proposal

    _, created = bootstrap(
        dsession, dataset=_label(), operator="ops@test", records=_batch()
    )
    proposal = build_proposal(dsession, created[0])
    assert proposal["gates_failed"], "a bootstrapped candidate must not be promotable"
    assert any("P2" in gate for gate in proposal["gates_failed"]), proposal["gates_failed"]


# --------------------------------------------------------------------------- #
# No fetching machinery entered with this slice
# --------------------------------------------------------------------------- #
def test_the_bootstrap_module_performs_no_network_access() -> None:
    source = (pathlib.Path(__file__).resolve().parents[1]
              / "app" / "services" / "discovery" / "bootstrap.py").read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "urllib.request", "socket", "aiohttp"):
        assert forbidden not in source, f"MANUAL_BOOTSTRAP must not fetch: {forbidden}"


def test_the_dataset_directory_contains_only_json() -> None:
    for path in BOOTSTRAP_DIR.iterdir():
        assert path.suffix == ".json", f"unexpected file in bootstrap dir: {path.name}"
        json.loads(path.read_text(encoding="utf-8"))
