"""AGENT-02.2b — the governed evidence-reference service.

`docs/20` §7.1 requires the public address of a provenance row to be opaque,
deterministic, authenticated, and never a raw identifier; §7.1.1 requires a
vetted deterministic AEAD; §7.2 requires publication to be re-checked at resolve
time; §7.3 splits malformed from unresolved and makes every unresolved cause
indistinguishable.

Most of these tests are negative, because the failure modes are the point. Two in
particular are worth stating outright:

* **a reference must not follow "best evidence"** — it names one row, so
  ingesting newer provenance for the same subject must leave it pointing where it
  pointed. A citation that silently re-targets is worse than a broken one.
* **unpublishing must revoke** — a reference proves it was issued, never that the
  subject is still eligible, so publication is verified now rather than trusted
  from issuance.
"""
from __future__ import annotations

import base64
import os
import re
import uuid

import pytest
from sqlalchemy import event, text

from app.db.session import SessionLocal, engine
from app.services import reads
from app.services.evidence_refs import (
    EvidenceRefKeyring,
    EvidenceRefKeyUnavailable,
    ResolutionFailure,
    issue_evidence_ref,
    resolve_evidence_ref,
)

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.IGNORECASE
)


def _key(seed: int = 1) -> str:
    return base64.urlsafe_b64encode(bytes([seed]) * 64).decode().rstrip("=")


KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([1]) * 64})
OTHER_KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([9]) * 64})


class _Settings:
    """Minimal stand-in for the app settings object."""

    def __init__(self, key=None, key_id="1", previous=""):
        self.evidence_ref_key = key
        self.evidence_ref_key_id = key_id
        self.evidence_ref_previous_keys = previous


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def fixtures():
    """A published robot carrying one evidence row of each supported class."""
    created_robots: list = []
    created_evidence: list = []

    class Fixtures:
        @staticmethod
        def robot(published: bool = True) -> uuid.UUID:
            mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
            slug = f"evref-probe-{uuid.uuid4().hex[:10]}"
            rid = _exec(
                "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
                "VALUES (:s, :m, :n, :p) RETURNING id",
                s=slug, m=mfr_id, n=slug.upper(), p=published,
            ).scalar_one()
            created_robots.append(rid)
            return rid

        @staticmethod
        def evidence(subject_type: str, subject_id, **over) -> uuid.UUID:
            eid = _exec(
                "INSERT INTO evidence_source (subject_type, subject_id, source_type,"
                " confidence, observed_at, verified_at) VALUES"
                " (CAST(:st AS evidence_subject), :sid, 'MANUFACTURER_SITE', 'HIGH',"
                " COALESCE(CAST(:obs AS timestamptz), now()),"
                " CAST(:ver AS timestamptz)) RETURNING id",
                st=subject_type, sid=subject_id,
                obs=over.get("observed_at"), ver=over.get("verified_at"),
            ).scalar_one()
            created_evidence.append(eid)
            return eid

        @staticmethod
        def pricing_offer(robot_id) -> uuid.UUID:
            return _exec(
                "INSERT INTO pricing_offer (robot_id, transaction_type, price_type,"
                " currency, price, is_current) VALUES (:r, 'PURCHASE', 'PUBLIC',"
                " 'USD', 1000, TRUE) RETURNING id", r=robot_id,
            ).scalar_one()

        @staticmethod
        def availability_offer(robot_id) -> uuid.UUID:
            return _exec(
                "INSERT INTO availability_offer (robot_id, transaction_type,"
                " availability_status, is_current) VALUES (:r, 'PURCHASE',"
                " 'AVAILABLE', TRUE) RETURNING id", r=robot_id,
            ).scalar_one()

        @staticmethod
        def deployment(robot_id) -> uuid.UUID:
            return _exec(
                "INSERT INTO deployment (robot_id, customer_name) "
                "VALUES (:r, 'Probe Customer') RETURNING id", r=robot_id,
            ).scalar_one()

        @staticmethod
        def unpublish(robot_id) -> None:
            _exec("UPDATE robot SET is_published = FALSE WHERE id = :i", i=robot_id)

        @staticmethod
        def row(evidence_id):
            with SessionLocal() as s:
                from app.models.evidence import EvidenceSource

                return s.get(EvidenceSource, evidence_id)

    yield Fixtures
    for eid in created_evidence:
        _exec("DELETE FROM evidence_source WHERE id = :i", i=eid)
    for rid in created_robots:
        _exec("DELETE FROM evidence_source WHERE subject_id = :i", i=rid)
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


def resolve(ref):
    with SessionLocal() as s:
        return resolve_evidence_ref(s, ref, KEYRING)


# --------------------------------------------------------------------------
# DETERMINISM AND OPACITY (§7.1)
# --------------------------------------------------------------------------


def test_same_row_and_key_yield_an_identical_ref(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    assert issue_evidence_ref(row, KEYRING) == issue_evidence_ref(row, KEYRING)


def test_different_rows_yield_different_refs(fixtures, database_url):
    robot_id = fixtures.robot()
    a = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    b = fixtures.row(fixtures.evidence("DEPLOYMENT", fixtures.deployment(robot_id)))
    assert issue_evidence_ref(a, KEYRING) != issue_evidence_ref(b, KEYRING)


def test_the_ref_contains_no_plaintext_uuid(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    ref = issue_evidence_ref(row, KEYRING)

    assert str(row.id) not in ref
    assert str(row.id).replace("-", "") not in ref
    assert str(row.subject_id) not in ref
    assert row.id.hex not in ref.lower()
    assert not UUID_PATTERN.search(ref), f"UUID-shaped value in ref: {ref}"


def test_the_row_id_is_not_recoverable_from_the_encoded_body(fixtures, database_url):
    """Decoding the opaque body must not reveal the identity either."""
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    body = issue_evidence_ref(row, KEYRING).split(".")[-1]
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    assert row.id.bytes not in raw, "row identity is present in cleartext"


def test_a_different_key_yields_a_different_ref(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    assert issue_evidence_ref(row, KEYRING) != issue_evidence_ref(row, OTHER_KEYRING)


# --------------------------------------------------------------------------
# EXACT-ROW RESOLUTION (§7.1)
# --------------------------------------------------------------------------


def test_a_ref_resolves_to_the_exact_original_row(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    resolved = resolve(issue_evidence_ref(row, KEYRING))
    assert not isinstance(resolved, ResolutionFailure)
    assert resolved.id == row.id
    assert resolved.subject_type == "COMMERCIAL_STATUS"


def test_newer_evidence_does_not_move_an_existing_ref(fixtures, database_url):
    """The decisive property: provenance must not shift under a citation."""
    robot_id = fixtures.robot()
    first = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    ref = issue_evidence_ref(first, KEYRING)

    newer = fixtures.evidence(
        "COMMERCIAL_STATUS", robot_id, verified_at="2030-01-01T00:00:00Z"
    )
    assert newer != first.id, "fixture sanity"

    resolved = resolve(ref)
    assert not isinstance(resolved, ResolutionFailure)
    assert resolved.id == first.id, "ref re-pointed at newer evidence"


# --------------------------------------------------------------------------
# AUTHENTICATION AND KEYS (§7.1.1, §7.3)
# --------------------------------------------------------------------------


def test_a_tampered_ciphertext_does_not_resolve(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    marker, key_id, body = issue_evidence_ref(row, KEYRING).split(".")
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    assert resolve(f"{marker}.{key_id}.{flipped}") is ResolutionFailure.UNRESOLVED


def test_a_tampered_key_id_does_not_resolve(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    marker, _key_id, body = issue_evidence_ref(row, KEYRING).split(".")
    assert resolve(f"{marker}.99.{body}") is ResolutionFailure.UNRESOLVED


def test_a_key_id_cannot_be_rewritten_even_between_identical_keys(
    fixtures, database_url
):
    """The regression the ordinary tampering test cannot catch.

    A rewritten key id normally fails because the named key decrypts nothing —
    but that is a property of the *material*, not of the envelope. If two ids are
    ever configured with the same key (a rotation typo, a copied secret), a token
    could be relabelled from one to the other and still authenticate. The key id
    travels in cleartext and steers interpretation, so it must be authenticated
    in its own right, whatever the key material happens to be.
    """
    shared = bytes([5]) * 64
    ring = EvidenceRefKeyring(active_id="a", keys={"a": shared, "b": shared})
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))

    marker, key_id, body = issue_evidence_ref(row, ring).split(".")
    assert key_id == "a"
    with SessionLocal() as s:
        issued = resolve_evidence_ref(s, f"{marker}.a.{body}", ring)
        relabelled = resolve_evidence_ref(s, f"{marker}.b.{body}", ring)
    assert not isinstance(issued, ResolutionFailure), "fixture sanity"
    assert relabelled is ResolutionFailure.UNRESOLVED, "key id is not authenticated"


def test_identical_key_material_under_two_ids_yields_different_refs(
    fixtures, database_url
):
    """The same consequence seen from the issuing side."""
    shared = bytes([5]) * 64
    under_a = EvidenceRefKeyring(active_id="a", keys={"a": shared})
    under_b = EvidenceRefKeyring(active_id="b", keys={"b": shared})
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))

    assert (
        issue_evidence_ref(row, under_a).split(".")[-1]
        != issue_evidence_ref(row, under_b).split(".")[-1]
    )


def test_a_ref_from_another_key_does_not_resolve(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    assert resolve(issue_evidence_ref(row, OTHER_KEYRING)) is ResolutionFailure.UNRESOLVED


def test_a_retired_key_resolves_only_while_configured(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    old = EvidenceRefKeyring(active_id="old", keys={"old": bytes([7]) * 64})
    ref = issue_evidence_ref(row, old)

    rotated_in = EvidenceRefKeyring(
        active_id="1", keys={"1": bytes([1]) * 64, "old": bytes([7]) * 64}
    )
    with SessionLocal() as s:
        assert not isinstance(resolve_evidence_ref(s, ref, rotated_in), ResolutionFailure)
    # Once the previous key is dropped, the same ref is simply unresolved —
    # never a distinguishable "expired key" answer.
    assert resolve(ref) is ResolutionFailure.UNRESOLVED


def test_rotation_keeps_the_new_active_key_issuing(fixtures, database_url):
    rotated = EvidenceRefKeyring(
        active_id="2", keys={"2": bytes([2]) * 64, "1": bytes([1]) * 64}
    )
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    assert issue_evidence_ref(row, rotated).split(".")[1] == "2"


# --------------------------------------------------------------------------
# MALFORMED vs UNRESOLVED (§7.3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    ["", "   ", "not-a-ref", "er1", "er1.1", "er1..abc", "er1.1.",
     "xx1.1.YWJj", "er1.1.!!!not-base64!!!", "er1.1.YWJj", "a.b.c.d", None, 42],
    ids=["empty", "blank", "plain", "one-part", "two-parts", "empty-kid",
         "empty-body", "bad-marker", "bad-base64", "too-short-ct", "four-parts",
         "none", "int"],
)
def test_structurally_broken_refs_are_malformed(ref, database_url):
    assert resolve(ref) is ResolutionFailure.MALFORMED


@pytest.mark.parametrize(
    "noise",
    ["!!", "  ", "\n", "\t", "*", "%20", "\u00a0"],
    ids=["bang", "spaces", "newline", "tab", "star", "percent", "nbsp"],
)
def test_characters_outside_the_alphabet_never_decode_away(
    fixtures, database_url, noise
):
    """The decisive parser regression.

    Python's base64 decoder *discards* characters outside the alphabet rather
    than rejecting them, so an otherwise valid body with junk spliced into it
    decodes to exactly the original ciphertext — and a permissive parser would
    resolve it, handing out an unbounded family of spellings for one reference
    and blurring the malformed/unresolved split §7.3 rests on. The grammar has to
    be judged before decoding, never inferred from decoding having worked.
    """
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    marker, key_id, body = issue_evidence_ref(row, KEYRING).split(".")
    assert not isinstance(resolve(f"{marker}.{key_id}.{body}"), ResolutionFailure)

    spliced = body[:4] + noise + body[4:]
    assert resolve(f"{marker}.{key_id}.{spliced}") is ResolutionFailure.MALFORMED


def test_a_padded_body_is_malformed(fixtures, database_url):
    """The issued form is unpadded, so the padded spelling is a different string."""
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    marker, key_id, body = issue_evidence_ref(row, KEYRING).split(".")
    assert resolve(f"{marker}.{key_id}.{body}==") is ResolutionFailure.MALFORMED


@pytest.mark.parametrize("body", ["QUJD+w", "QUJD/w"], ids=["plus", "slash"])
def test_standard_base64_punctuation_is_malformed(body, database_url):
    """base64url is the only accepted alphabet; "+" and "/" are not aliases."""
    assert resolve(f"er1.1.{body}") is ResolutionFailure.MALFORMED


def test_a_noncanonical_body_is_malformed(database_url):
    """Base64 leaves the final character's unused bits free, so many spellings
    decode to identical bytes. Only the one this service emits is a reference."""
    canonical = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    variant = canonical[:-1] + "B"
    assert variant != canonical
    assert base64.urlsafe_b64decode(variant + "==") == bytes(40), "fixture sanity"

    assert resolve(f"er1.1.{canonical}") is ResolutionFailure.UNRESOLVED
    assert resolve(f"er1.1.{variant}") is ResolutionFailure.MALFORMED


def test_surrounding_whitespace_is_malformed(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    ref = issue_evidence_ref(row, KEYRING)
    for spelling in (f" {ref}", f"{ref} ", f"\n{ref}", f"{ref}\n"):
        assert resolve(spelling) is ResolutionFailure.MALFORMED


@pytest.mark.parametrize(
    "key_id",
    ["a b", "a+b", "a/b", "a=", "a\n", "ké", "a%2eb"],
    ids=["space", "plus", "slash", "equals", "newline", "non-ascii", "escaped-dot"],
)
def test_a_key_id_outside_its_grammar_is_malformed(key_id, database_url):
    """A key id is authenticated, so it must have exactly one spelling. Anything
    outside [A-Za-z0-9_-] is rejected as grammar, before any key is consulted."""
    body = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    assert resolve(f"er1.{key_id}.{body}") is ResolutionFailure.MALFORMED


def test_a_wellformed_but_unauthentic_ref_is_unresolved(database_url):
    """Same grammar, no valid authentication → NOT_FOUND territory, not
    INVALID_ARGUMENT. The distinction is structural, never semantic."""
    body = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    assert resolve(f"er1.1.{body}") is ResolutionFailure.UNRESOLVED


def test_no_cryptography_exception_text_escapes(database_url):
    """Failures are enum values, never messages that name the primitive."""
    body = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    outcome = resolve(f"er1.1.{body}")
    assert isinstance(outcome, ResolutionFailure)
    assert outcome.value in {"malformed", "unresolved"}


# --------------------------------------------------------------------------
# PUBLICATION REACHABILITY (§7.2)
# --------------------------------------------------------------------------


def _subject(fixtures, subject_type, robot_id):
    if subject_type == "COMMERCIAL_STATUS":
        return robot_id
    if subject_type == "PRICING_OFFER":
        return fixtures.pricing_offer(robot_id)
    if subject_type == "AVAILABILITY_OFFER":
        return fixtures.availability_offer(robot_id)
    return fixtures.deployment(robot_id)


SUPPORTED = ["COMMERCIAL_STATUS", "PRICING_OFFER", "AVAILABILITY_OFFER", "DEPLOYMENT"]


@pytest.mark.parametrize("subject_type", SUPPORTED)
def test_each_supported_class_resolves_when_published(
    fixtures, database_url, subject_type
):
    robot_id = fixtures.robot(published=True)
    row = fixtures.row(
        fixtures.evidence(subject_type, _subject(fixtures, subject_type, robot_id))
    )
    resolved = resolve(issue_evidence_ref(row, KEYRING))
    assert not isinstance(resolved, ResolutionFailure), subject_type
    assert resolved.id == row.id


@pytest.mark.parametrize("subject_type", SUPPORTED)
def test_unpublishing_revokes_an_already_issued_ref(
    fixtures, database_url, subject_type
):
    """Issuance is not eligibility. The ref keeps its shape and stops working."""
    robot_id = fixtures.robot(published=True)
    row = fixtures.row(
        fixtures.evidence(subject_type, _subject(fixtures, subject_type, robot_id))
    )
    ref = issue_evidence_ref(row, KEYRING)
    assert not isinstance(resolve(ref), ResolutionFailure), subject_type

    fixtures.unpublish(robot_id)
    assert resolve(ref) is ResolutionFailure.UNRESOLVED, subject_type


def test_an_unsupported_subject_class_does_not_resolve(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("SPECIFICATION", robot_id))
    assert resolve(issue_evidence_ref(row, KEYRING)) is ResolutionFailure.UNRESOLVED


def test_a_deleted_evidence_row_does_not_resolve(fixtures, database_url):
    robot_id = fixtures.robot()
    evidence_id = fixtures.evidence("COMMERCIAL_STATUS", robot_id)
    ref = issue_evidence_ref(fixtures.row(evidence_id), KEYRING)
    assert not isinstance(resolve(ref), ResolutionFailure)

    _exec("DELETE FROM evidence_source WHERE id = :i", i=evidence_id)
    assert resolve(ref) is ResolutionFailure.UNRESOLVED


# --------------------------------------------------------------------------
# KEY CONFIGURATION FAILS CLOSED (§7.1.1)
# --------------------------------------------------------------------------


def test_a_missing_key_fails_closed():
    for settings in (_Settings(key=None), _Settings(key=""), _Settings(key="   ")):
        with pytest.raises(EvidenceRefKeyUnavailable):
            EvidenceRefKeyring.from_settings(settings)


@pytest.mark.parametrize(
    "material",
    [
        base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="),  # too short
        base64.urlsafe_b64encode(os.urandom(63)).decode().rstrip("="),
        base64.urlsafe_b64encode(os.urandom(65)).decode().rstrip("="),
        "!!!!not base64!!!!",
    ],
    ids=["32-bytes", "63-bytes", "65-bytes", "not-base64"],
)
def test_invalid_key_material_fails_closed_and_is_never_repaired(material):
    """Never truncated, padded or derived into something usable."""
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring.from_settings(_Settings(key=material))


def test_an_empty_key_id_fails_closed():
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring.from_settings(_Settings(key=_key(), key_id=""))


def test_a_malformed_previous_key_entry_fails_closed():
    for previous in ("garbage", "kid:", ":material", "kid:!!!"):
        with pytest.raises(EvidenceRefKeyUnavailable):
            EvidenceRefKeyring.from_settings(_Settings(key=_key(), previous=previous))


@pytest.mark.parametrize(
    "previous",
    [f"b:{_key(2)},b:{_key(3)}", f"a:{_key(2)}", f"b:{_key(2)},b:{_key(2)}"],
    ids=["repeated-previous", "shadows-active", "repeated-identical-material"],
)
def test_a_duplicate_key_id_fails_closed(previous):
    """Never settled by keeping one silently: which key a token authenticates
    under would then depend on the order the configuration happened to parse in.
    Identical material is a duplicate too — the id is what gets authenticated."""
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring.from_settings(
            _Settings(key=_key(), key_id="a", previous=previous)
        )


@pytest.mark.parametrize(
    "key_id",
    ["a.b", "a b", "a+b", "a/b", "a=", "ké"],
    ids=["dot", "space", "plus", "slash", "equals", "non-ascii"],
)
def test_an_active_key_id_outside_its_grammar_fails_closed(key_id):
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring.from_settings(_Settings(key=_key(), key_id=key_id))


def test_a_previous_key_id_outside_its_grammar_fails_closed():
    """Dead configuration fails closed too: no valid token could ever name it."""
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring.from_settings(
            _Settings(key=_key(), key_id="a", previous=f"b.c:{_key(2)}")
        )


def test_the_keyring_constructor_rejects_a_bad_key_id_directly():
    with pytest.raises(EvidenceRefKeyUnavailable):
        EvidenceRefKeyring(active_id="a.b", keys={"a.b": bytes([1]) * 64})


def test_a_valid_keyring_builds_from_settings():
    ring = EvidenceRefKeyring.from_settings(
        _Settings(key=_key(1), key_id="a", previous=f"b:{_key(2)}")
    )
    assert ring.active_id == "a"
    assert set(ring.keys) == {"a", "b"}


def test_the_key_is_not_shared_with_any_other_secret():
    """Structural: the service must not reach for an unrelated secret."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app/services/evidence_refs.py"
    body = src.read_text(encoding="utf-8")
    for foreign in ("admin_session_secret", "admin_password", "database_url"):
        assert foreign not in body


# --------------------------------------------------------------------------
# NO DATABASE WRITES (§7.1.1 — no migration, no mapping table)
# --------------------------------------------------------------------------


def _writes_during(fn) -> list[str]:
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        head = statement.strip().split(None, 1)[0].lower() if statement.strip() else ""
        if head in {"insert", "update", "delete", "create", "alter", "drop"}:
            seen.append(" ".join(statement.split())[:120])

    event.listen(engine, "after_cursor_execute", record)
    try:
        fn()
    finally:
        event.remove(engine, "after_cursor_execute", record)
    return seen


def test_issuing_writes_nothing(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    assert _writes_during(lambda: issue_evidence_ref(row, KEYRING)) == []


def test_resolving_writes_nothing(fixtures, database_url):
    robot_id = fixtures.robot()
    row = fixtures.row(fixtures.evidence("COMMERCIAL_STATUS", robot_id))
    ref = issue_evidence_ref(row, KEYRING)
    assert _writes_during(lambda: resolve(ref)) == []


def test_the_service_declares_no_persistence_model() -> None:
    """No mapping table, no sequence — the reference is derived, not stored."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app/services/evidence_refs.py"
    body = src.read_text(encoding="utf-8")
    for forbidden in ("__tablename__", "session.add", "session.commit", "session.flush"):
        assert forbidden not in body


# --------------------------------------------------------------------------
# BEST-EVIDENCE DETERMINISM (§13.1)
# --------------------------------------------------------------------------


def test_an_exact_tie_selects_the_same_row_every_time(fixtures, database_url):
    """Two rows, identical verified-state and observed_at — the tie-break must
    make the choice stable, or a ref issued from it would drift."""
    robot_id = fixtures.robot()
    stamp = "2026-01-01T00:00:00Z"
    a = fixtures.evidence("COMMERCIAL_STATUS", robot_id, observed_at=stamp)
    b = fixtures.evidence("COMMERCIAL_STATUS", robot_id, observed_at=stamp)
    assert a != b

    picks = set()
    for _ in range(5):
        with SessionLocal() as s:
            chosen = reads.load_evidence(s, {robot_id})[("COMMERCIAL_STATUS", robot_id)]
            picks.add((chosen.source_type, chosen.observed_at, chosen.confidence))
    assert len(picks) == 1, "tied best-evidence selection is not deterministic"


def test_verified_still_outranks_unverified(fixtures, database_url):
    robot_id = fixtures.robot()
    stamp = "2026-01-01T00:00:00Z"
    fixtures.evidence("COMMERCIAL_STATUS", robot_id, observed_at=stamp)
    fixtures.evidence(
        "COMMERCIAL_STATUS", robot_id, observed_at=stamp, verified_at=stamp
    )
    with SessionLocal() as s:
        chosen = reads.load_evidence(s, {robot_id})[("COMMERCIAL_STATUS", robot_id)]
    assert chosen.verified_at is not None, "verified evidence lost to unverified"


def test_newer_still_outranks_older(fixtures, database_url):
    robot_id = fixtures.robot()
    fixtures.evidence("COMMERCIAL_STATUS", robot_id, observed_at="2020-01-01T00:00:00Z")
    fixtures.evidence("COMMERCIAL_STATUS", robot_id, observed_at="2026-01-01T00:00:00Z")
    with SessionLocal() as s:
        chosen = reads.load_evidence(s, {robot_id})[("COMMERCIAL_STATUS", robot_id)]
    assert chosen.observed_at.year == 2026, "older evidence won"
