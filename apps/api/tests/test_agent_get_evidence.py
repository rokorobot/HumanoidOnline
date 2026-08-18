"""AGENT-02.2d — `get_evidence`, closing the provenance loop (`docs/20` §7).

The loop is the point: `get_robot` hands out an opaque reference beside a fact,
and this tool is the only thing that takes one back. So the tests here are mostly
about what a reference is *not*.

* **Not a pointer to a row.** It is a revocable capability. Unpublish the robot
  or supersede the offer and the same string stops disclosing anything, because
  reachability is re-evaluated on every call rather than trusted from issuance.
* **Not a selector.** No evidence id, no `subject_id`, no slug, no offer id is
  accepted as an alternative address, and none comes back in the answer.
* **Not a source of oracles.** Every inaccessible cause — fabricated, unknown,
  unpublished, superseded, unsupported class, retired key — must be one
  indistinguishable `NOT_FOUND`. A caller who can tell "no such evidence" from
  "that robot is unpublished" can enumerate the unpublished catalogue.

The malformed/inaccessible split is structural, not semantic: `INVALID_ARGUMENT`
says "this is not a reference of this format at all", which asserts nothing about
what does or does not exist.
"""
from __future__ import annotations

import sys
import uuid

import pytest
from sqlalchemy import event, text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import (
    CONTRACT_VERSION,
    AgentToolError,
    InvalidArgument,
    NotFound,
    get_evidence,
    get_robot,
)
from app.services.evidence_refs import EvidenceRefKeyring, issue_evidence_ref
from tests.agent_identifier_gate import (
    assert_absent_everywhere,
    assert_no_database_identifier,
    walk,
)

KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([1]) * 64})
OTHER_KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([9]) * 64})

TOOL_MODULE = sys.modules["app.services.agent_tools.get_evidence"]

#: The ratified §7 field list, and nothing beyond it.
EXPECTED_FIELDS = {
    "source_type", "confidence", "observed_at", "verified_at", "published_at",
    "source_url", "subject_type", "evidence_ref",
}


class _NoKeySettings:
    evidence_ref_key = None
    evidence_ref_key_id = "1"
    evidence_ref_previous_keys = ""


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def catalogue():
    """Published robots with real commercial facts and real evidence."""
    robots: list[uuid.UUID] = []
    evidence: list[uuid.UUID] = []

    class Fixtures:
        @staticmethod
        def robot(published: bool = True) -> tuple[str, uuid.UUID]:
            mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
            slug = f"getevidence-probe-{uuid.uuid4().hex[:10]}"
            rid = _exec(
                "INSERT INTO robot (slug, manufacturer_id, name, model_code,"
                " commercial_status, is_published) VALUES (:s, :m, :n, 'MC-1',"
                " CAST('COMMERCIAL' AS commercial_status), :p) RETURNING id",
                s=slug, m=mfr_id, n=slug.upper(), p=published,
            ).scalar_one()
            robots.append(rid)
            return slug, rid

        @staticmethod
        def evidence(subject_type: str, subject_id, **over) -> uuid.UUID:
            eid = _exec(
                "INSERT INTO evidence_source (subject_type, subject_id, source_type,"
                " confidence, observed_at, verified_at, published_at, source_url,"
                " source_title, excerpt, note) VALUES"
                " (CAST(:st AS evidence_subject), :sid, :src, :conf,"
                " COALESCE(CAST(:obs AS timestamptz), now()),"
                " CAST(:ver AS timestamptz), CAST(:pub AS date), :url,"
                " :title, :excerpt, :note) RETURNING id",
                st=subject_type, sid=subject_id,
                src=over.get("source_type", "MANUFACTURER_SITE"),
                conf=over.get("confidence", "HIGH"),
                obs=over.get("observed_at"),
                ver=over.get("verified_at", "2026-02-02T00:00:00Z"),
                pub=over.get("published_at", "2026-01-01"),
                url=over.get("source_url", "https://example.invalid/source"),
                title=over.get("source_title", "INTERNAL TITLE"),
                excerpt=over.get("excerpt", "INTERNAL EXCERPT"),
                note=over.get("note", "INTERNAL NOTE"),
            ).scalar_one()
            evidence.append(eid)
            return eid

        @staticmethod
        def pricing(robot_id, *, current: bool = True) -> uuid.UUID:
            return _exec(
                "INSERT INTO pricing_offer (robot_id, transaction_type, price_type,"
                " currency, price, is_current) VALUES (:r, 'PURCHASE', 'PUBLIC',"
                " 'USD', 1000, :c) RETURNING id", r=robot_id, c=current,
            ).scalar_one()

        @staticmethod
        def availability(robot_id, *, current: bool = True) -> uuid.UUID:
            return _exec(
                "INSERT INTO availability_offer (robot_id, transaction_type,"
                " availability_status, is_current) VALUES (:r, 'PURCHASE',"
                " 'AVAILABLE', :c) RETURNING id", r=robot_id, c=current,
            ).scalar_one()

        @staticmethod
        def deployment(robot_id) -> uuid.UUID:
            return _exec(
                "INSERT INTO deployment (robot_id, customer_name) "
                "VALUES (:r, 'Probe Customer') RETURNING id", r=robot_id,
            ).scalar_one()

        @staticmethod
        def image(robot_id) -> uuid.UUID:
            return _exec(
                "INSERT INTO robot_image (robot_id, image_url, image_type,"
                " source_type, identity_status, rights_status, usage_basis,"
                " is_primary) VALUES (:r, :u, 'FRONT', 'MANUFACTURER',"
                " 'VERIFIED', 'PERMITTED', 'NONE', TRUE) RETURNING id",
                r=robot_id, u=f"https://example.invalid/{uuid.uuid4().hex}.jpg",
            ).scalar_one()

        @staticmethod
        def set_published(robot_id, value: bool) -> None:
            _exec(
                "UPDATE robot SET is_published = :v WHERE id = :i",
                v=value, i=robot_id,
            )

        @staticmethod
        def set_current(table: str, offer_id, value: bool) -> None:
            assert table in {"pricing_offer", "availability_offer"}
            _exec(
                f"UPDATE {table} SET is_current = :v WHERE id = :i",
                v=value, i=offer_id,
            )

        @staticmethod
        def row(evidence_id):
            with SessionLocal() as s:
                from app.models.evidence import EvidenceSource

                return s.get(EvidenceSource, evidence_id)

    yield Fixtures
    for eid in evidence:
        _exec("DELETE FROM evidence_source WHERE id = :i", i=eid)
    for rid in robots:
        _exec("DELETE FROM evidence_source WHERE subject_id = :i", i=rid)
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


@pytest.fixture
def loop(catalogue):
    """One published robot with every supported fact class, each evidenced."""
    slug, rid = catalogue.robot()
    ids = {"robot": rid}
    ids["pricing"] = catalogue.pricing(rid)
    ids["availability"] = catalogue.availability(rid)
    ids["deployment"] = catalogue.deployment(rid)
    catalogue.image(rid)

    ev = {
        "COMMERCIAL_STATUS": catalogue.evidence(
            "COMMERCIAL_STATUS", rid, source_url="https://example.invalid/status"
        ),
        "PRICING_OFFER": catalogue.evidence(
            "PRICING_OFFER", ids["pricing"], source_url="https://example.invalid/p"
        ),
        "AVAILABILITY_OFFER": catalogue.evidence(
            "AVAILABILITY_OFFER", ids["availability"],
            source_url="https://example.invalid/a",
        ),
        "DEPLOYMENT": catalogue.evidence(
            "DEPLOYMENT", ids["deployment"], source_url="https://example.invalid/d"
        ),
    }
    return slug, ids, ev


def robot_detail(slug: str):
    with SessionLocal() as s:
        return get_robot(s, slug, keyring=KEYRING).data


def redeem(ref, **kw):
    with SessionLocal() as s:
        return get_evidence(s, ref, keyring=kw.pop("keyring", KEYRING), **kw)


def refs_from_get_robot(slug: str) -> dict[str, str]:
    """Every reference `get_robot` emits, keyed by subject class."""
    data = robot_detail(slug)
    found = {"COMMERCIAL_STATUS": data.commercial_status_evidence.evidence_ref}
    found["PRICING_OFFER"] = data.pricing_offers[0].evidence.evidence_ref
    found["AVAILABILITY_OFFER"] = data.availability_offers[0].evidence.evidence_ref
    found["DEPLOYMENT"] = data.deployments[0].evidence.evidence_ref
    return found


# --------------------------------------------------------------------------
# TEST 1 / 7 — THE LOOP, FOR EVERY SUBJECT CLASS (§7)
# --------------------------------------------------------------------------


SUBJECTS = ["COMMERCIAL_STATUS", "PRICING_OFFER", "AVAILABILITY_OFFER", "DEPLOYMENT"]


@pytest.mark.parametrize("subject", SUBJECTS)
def test_a_get_robot_reference_redeems(database_url, loop, subject):
    """get_robot → evidence_ref → get_evidence, for all four classes."""
    slug, _ids, ev = loop
    result = redeem(refs_from_get_robot(slug)[subject])

    assert result.contract_version == CONTRACT_VERSION
    assert result.data.subject_type == subject
    with SessionLocal() as s:
        from app.models.evidence import EvidenceSource

        assert s.get(EvidenceSource, ev[subject]) is not None, "fixture sanity"


@pytest.mark.parametrize("subject", SUBJECTS)
def test_the_redeemed_row_is_the_one_get_robot_cited(database_url, loop, catalogue, subject):
    """The decisive correspondence: the metadata `get_robot` displayed beside a
    fact and the metadata `get_evidence` returns must be the same row."""
    slug, _ids, ev = loop
    row = catalogue.row(ev[subject])
    redeemed = redeem(refs_from_get_robot(slug)[subject]).data

    assert redeemed.source_url == row.source_url
    assert redeemed.source_type == row.source_type
    assert redeemed.confidence == row.confidence
    assert redeemed.observed_at == row.observed_at
    assert redeemed.verified_at == row.verified_at
    assert redeemed.published_at == row.published_at
    assert redeemed.subject_type == row.subject_type


def test_the_returned_reference_is_the_one_presented(database_url, loop):
    """Issuance is deterministic, so the echo is exact — and it is derived from
    the resolved row, so a response can never cite evidence it did not return."""
    slug, _ids, _ev = loop
    for ref in refs_from_get_robot(slug).values():
        assert redeem(ref).data.evidence_ref == ref


def test_the_two_tools_agree_field_for_field(database_url, loop):
    """One shape wherever provenance appears (§9.5)."""
    slug, _ids, _ev = loop
    embedded = robot_detail(slug).pricing_offers[0].evidence
    assert redeem(embedded.evidence_ref).data == embedded


# --------------------------------------------------------------------------
# TEST 6 — EXACTLY THE RATIFIED FIELD LIST (§7)
# --------------------------------------------------------------------------


def test_the_payload_is_the_ratified_field_list(database_url, loop):
    slug, _ids, _ev = loop
    body = redeem(refs_from_get_robot(slug)["PRICING_OFFER"]).data.model_dump()
    assert set(body) == EXPECTED_FIELDS


def test_internal_record_detail_is_not_published(database_url, loop):
    """§7 — `source_title`, `excerpt` and `note` are internal record detail this
    contract has never published. The fixture writes recognisable values into all
    three so their absence is proven rather than assumed."""
    slug, _ids, _ev = loop
    for ref in refs_from_get_robot(slug).values():
        result = redeem(ref)
        body = result.data.model_dump(mode="json")
        assert "source_title" not in body
        assert "excerpt" not in body
        assert "note" not in body and "notes" not in body
        for blob in (repr(body), repr(result)):
            assert "INTERNAL TITLE" not in blob
            assert "INTERNAL EXCERPT" not in blob
            assert "INTERNAL NOTE" not in blob


def test_verified_at_stays_a_timestamp(database_url, loop):
    """§7/§13 — `verified_at: null` means "not re-checked at source", never
    "unverified data". It is reported as the timestamp it is, and never collapsed
    into a status string that would assert something the catalogue never recorded.
    """
    slug, _ids, _ev = loop
    data = redeem(refs_from_get_robot(slug)["DEPLOYMENT"]).data
    assert data.verified_at is not None
    assert not isinstance(data.verified_at, str)
    assert "verification_status" not in data.model_dump()


def test_an_unverified_row_reports_null_not_a_status(database_url, catalogue):
    slug, rid = catalogue.robot()
    catalogue.evidence("COMMERCIAL_STATUS", rid, verified_at=None)
    ref = robot_detail(slug).commercial_status_evidence.evidence_ref
    assert redeem(ref).data.verified_at is None


# --------------------------------------------------------------------------
# TEST 2 / 3 — REVOCATION AND RESTORATION (§7.2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("subject", SUBJECTS)
def test_unpublishing_revokes_a_previously_valid_reference(
    database_url, loop, catalogue, subject
):
    """The architectural invariant, stated as a test: a reference is a revocable
    capability, not a permanent pointer to a row."""
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)[subject]
    assert redeem(ref).data.subject_type == subject, "fixture sanity"

    catalogue.set_published(ids["robot"], False)
    with pytest.raises(NotFound):
        redeem(ref)


def test_revocation_does_not_disclose_that_the_robot_exists(
    database_url, loop, catalogue
):
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)["COMMERCIAL_STATUS"]
    catalogue.set_published(ids["robot"], False)

    with pytest.raises(NotFound) as revoked:
        redeem(ref)
    message = str(revoked.value)
    assert slug not in message
    assert str(ids["robot"]) not in message


def test_republishing_restores_access(database_url, loop, catalogue):
    """No persistent revocation state exists — reachability is re-evaluated, so
    restoring publication restores access to the same reference."""
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)["COMMERCIAL_STATUS"]

    catalogue.set_published(ids["robot"], False)
    with pytest.raises(NotFound):
        redeem(ref)

    catalogue.set_published(ids["robot"], True)
    assert redeem(ref).data.evidence_ref == ref


# --------------------------------------------------------------------------
# TEST 8 — SUPERSEDED COMMERCIAL OBJECTS (§7.2, revocable-capability invariant)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table,key,subject",
    [
        ("pricing_offer", "pricing", "PRICING_OFFER"),
        ("availability_offer", "availability", "AVAILABILITY_OFFER"),
    ],
)
def test_superseding_an_offer_revokes_its_evidence(
    database_url, loop, catalogue, table, key, subject
):
    """The row still exists; that is not authorization.

    Once an offer is no longer current the governed read model stops serving it,
    so its provenance stops being redeemable at the same moment. Otherwise an
    agent holding an old reference could keep reading the source behind a price
    the catalogue has withdrawn.
    """
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)[subject]
    assert redeem(ref).data.subject_type == subject, "fixture sanity"

    catalogue.set_current(table, ids[key], False)
    with pytest.raises(NotFound):
        redeem(ref)


def test_a_superseded_offer_row_still_exists(database_url, loop, catalogue):
    """Guards the guard: the revocation above must come from the reachability
    rule, not from the fixture having deleted the row."""
    slug, ids, _ev = loop
    catalogue.set_current("pricing_offer", ids["pricing"], False)
    still_there = _exec(
        "SELECT count(*) FROM pricing_offer WHERE id = :i", i=ids["pricing"]
    ).scalar_one()
    assert still_there == 1


def test_restoring_currency_restores_access(database_url, loop, catalogue):
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)["PRICING_OFFER"]

    catalogue.set_current("pricing_offer", ids["pricing"], False)
    with pytest.raises(NotFound):
        redeem(ref)

    catalogue.set_current("pricing_offer", ids["pricing"], True)
    assert redeem(ref).data.evidence_ref == ref


def test_get_robot_and_get_evidence_agree_on_what_is_exposed(
    database_url, loop, catalogue
):
    """The two tools must not disagree about which facts are public: an offer
    `get_robot` no longer lists must not stay inspectable through its old ref."""
    slug, ids, _ev = loop
    ref = refs_from_get_robot(slug)["PRICING_OFFER"]
    catalogue.set_current("pricing_offer", ids["pricing"], False)

    assert robot_detail(slug).pricing_offers == []
    with pytest.raises(NotFound):
        redeem(ref)


# --------------------------------------------------------------------------
# TEST 4 / 5 — ERROR TAXONOMY (§7.3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    ["", "   ", "not-a-ref", "er1", "er1.1", "er1..abc", "er1.1.",
     "xx1.1.YWJj", "er1.1.!!!bad!!!", "er1.1.YWJj", "a.b.c.d", "er1.1.QUJD+w",
     None, 42, 3.5, [], {}, uuid.uuid4()],
    ids=["empty", "blank", "plain", "one-part", "two-parts", "empty-kid",
         "empty-body", "bad-marker", "bad-base64", "too-short", "four-parts",
         "plus-alphabet", "none", "int", "float", "list", "dict", "uuid-object"],
)
def test_a_malformed_reference_is_invalid_argument(database_url, ref):
    with pytest.raises(InvalidArgument) as exc:
        redeem(ref)
    assert exc.value.code == "INVALID_ARGUMENT"


def test_a_raw_uuid_is_not_an_address(database_url, loop):
    """§7 — the opaque reference is the sole public locator. A database id, in
    either spelling, is simply not a reference of this format."""
    _slug, _ids, ev = loop
    row_id = ev["COMMERCIAL_STATUS"]
    for spelling in (str(row_id), str(row_id).replace("-", "")):
        with pytest.raises(InvalidArgument):
            redeem(spelling)


def _not_found(ref) -> tuple[str, str]:
    with pytest.raises(NotFound) as exc:
        redeem(ref)
    return exc.value.code, str(exc.value)


def test_a_fabricated_but_wellformed_reference_is_not_found(database_url):
    import base64

    body = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    assert _not_found(f"er1.1.{body}")[0] == "NOT_FOUND"


def test_every_inaccessible_cause_is_indistinguishable(
    database_url, loop, catalogue
):
    """The oracle test. Six different reasons, one identical external answer —
    otherwise a caller could enumerate the unpublished catalogue one ref at a
    time, or map which offers had been withdrawn."""
    import base64

    slug, ids, ev = loop
    # Captured before anything is mutated: each cause below removes a fact from
    # the governed read model, so the references have to be taken while they are
    # all still being emitted.
    issued = refs_from_get_robot(slug)
    answers = set()

    # 1. fabricated but well-formed
    fabricated = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    answers.add(_not_found(f"er1.1.{fabricated}"))

    # 2. issued under a key this service does not hold
    foreign = issue_evidence_ref(catalogue.row(ev["DEPLOYMENT"]), OTHER_KEYRING)
    answers.add(_not_found(foreign))

    # 3. unsupported subject class
    unsupported = catalogue.evidence("SPECIFICATION", ids["robot"])
    answers.add(_not_found(issue_evidence_ref(catalogue.row(unsupported), KEYRING)))

    # 4. superseded offer
    catalogue.set_current("pricing_offer", ids["pricing"], False)
    answers.add(_not_found(issued["PRICING_OFFER"]))

    # 5. superseded availability offer
    catalogue.set_current("availability_offer", ids["availability"], False)
    answers.add(_not_found(issued["AVAILABILITY_OFFER"]))

    # 6. deleted evidence row
    _exec("DELETE FROM evidence_source WHERE id = :i", i=ev["DEPLOYMENT"])
    answers.add(_not_found(issued["DEPLOYMENT"]))

    # 7. unpublished robot
    catalogue.set_published(ids["robot"], False)
    answers.add(_not_found(issued["COMMERCIAL_STATUS"]))

    assert len(answers) == 1, f"NOT_FOUND causes are distinguishable: {answers}"


def test_no_error_leaks_internal_detail(database_url, loop, catalogue):
    """§7.3/§20 — no subject type, UUID, table name, key or crypto detail."""
    slug, ids, ev = loop
    ref = refs_from_get_robot(slug)["PRICING_OFFER"]
    catalogue.set_published(ids["robot"], False)

    _code, message = _not_found(ref)
    lowered = message.lower()
    for leak in (
        "pricing", "offer", "robot", "publish", "unpublish", "current",
        "evidence_source", "subject", "uuid", "aes", "siv", "key", "decrypt",
        "table", "select", "sql", slug.lower(),
    ):
        assert leak not in lowered, f"{leak!r} leaked into {message!r}"
    for identifier in (ids["robot"], ids["pricing"], ev["PRICING_OFFER"]):
        assert str(identifier) not in message


def test_malformed_and_not_found_stay_distinct(database_url, loop):
    """The one distinction that IS allowed: structural, and it asserts nothing
    about what exists."""
    import base64

    body = base64.urlsafe_b64encode(bytes(40)).decode().rstrip("=")
    with pytest.raises(InvalidArgument):
        redeem("not-a-ref")
    with pytest.raises(NotFound):
        redeem(f"er1.1.{body}")


# --------------------------------------------------------------------------
# TEST 9 — IDENTIFIER SAFETY (§8, §20, §21.10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("subject", SUBJECTS)
def test_no_database_identifier_at_any_depth(database_url, loop, subject):
    slug, _ids, _ev = loop
    result = redeem(refs_from_get_robot(slug)[subject])
    assert_no_database_identifier(result.data.model_dump(mode="json"))
    assert_no_database_identifier({"warnings": result.warnings})


@pytest.mark.parametrize("subject", SUBJECTS)
def test_every_planted_identity_is_absent(database_url, loop, subject):
    """Real robot, offer, deployment and evidence ids — hyphenated and bare hex,
    across the model, both dump modes, and `repr`."""
    slug, ids, ev = loop
    planted = [*ids.values(), *ev.values()]
    result = redeem(refs_from_get_robot(slug)[subject])

    for payload in (
        result,
        result.data,
        result.data.model_dump(),
        result.data.model_dump(mode="json"),
    ):
        assert_absent_everywhere(payload, *planted)


def test_the_error_surface_carries_no_identity(database_url, loop, catalogue):
    slug, ids, ev = loop
    ref = refs_from_get_robot(slug)["DEPLOYMENT"]
    catalogue.set_published(ids["robot"], False)

    with pytest.raises(NotFound) as exc:
        redeem(ref)
    assert_absent_everywhere(
        {"message": str(exc.value), "code": exc.value.code}, *ids.values(), *ev.values()
    )


def test_no_identifier_key_names_appear(database_url, loop):
    slug, _ids, _ev = loop
    for _path, key, _value in walk(
        redeem(refs_from_get_robot(slug)["PRICING_OFFER"]).data.model_dump(mode="json")
    ):
        assert key not in {"id", "subject_id", "robot_id", "evidence_id", "offer_id"}


def test_the_evidence_ref_is_scanned_like_any_other_value(database_url, loop):
    """No exemption: if a raw identifier ever ended up inside the reference, the
    gate must catch it there too."""
    slug, _ids, ev = loop
    ref = redeem(refs_from_get_robot(slug)["COMMERCIAL_STATUS"]).data.evidence_ref
    assert_no_database_identifier({"evidence_ref": ref})
    assert_absent_everywhere({"evidence_ref": ref}, ev["COMMERCIAL_STATUS"])


# --------------------------------------------------------------------------
# FAIL CLOSED, AND TEST 10 — ARCHITECTURE BOUNDARY
# --------------------------------------------------------------------------


def test_an_unusable_key_fails_closed_as_internal(
    database_url, loop, monkeypatch
):
    """`INTERNAL`, never `NOT_FOUND`: a misconfigured key means this service
    cannot answer, and claiming "no such evidence" would assert something false
    about the catalogue."""
    slug, _ids, _ev = loop
    ref = refs_from_get_robot(slug)["COMMERCIAL_STATUS"]
    monkeypatch.setattr(TOOL_MODULE, "get_settings", lambda: _NoKeySettings())

    with pytest.raises(AgentToolError) as exc:
        with SessionLocal() as s:
            get_evidence(s, ref)
    assert exc.value.code == "INTERNAL"
    assert not isinstance(exc.value, NotFound)


def test_the_key_failure_leaks_no_configuration(database_url, loop, monkeypatch):
    slug, _ids, _ev = loop
    ref = refs_from_get_robot(slug)["COMMERCIAL_STATUS"]
    monkeypatch.setattr(TOOL_MODULE, "get_settings", lambda: _NoKeySettings())

    with pytest.raises(AgentToolError) as exc:
        with SessionLocal() as s:
            get_evidence(s, ref)
    message = str(exc.value).lower()
    for secret in (
        "evidence_ref_key", "env", "base64", "aes", "siv", "keyring", "key id",
        "cryptography", "512", "64 bytes",
    ):
        assert secret not in message


def test_the_agent_layer_does_not_import_the_router() -> None:
    """§6 — the agent sits behind the governed services, not behind HTTP."""
    from pathlib import Path

    agent = Path(__file__).resolve().parents[1] / "app/services/agent_tools"
    for path in agent.rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert "app.routers" not in body, f"{path.name} imports a router"
        assert "_load_detail" not in body, f"{path.name} uses a router private"


def test_no_second_selection_algorithm_was_introduced() -> None:
    """§13.1 — `get_evidence` performs a bounded lookup of the row a reference
    names. It must not re-run best evidence, or a citation could silently
    re-point at newer provenance after it was published."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    hits = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "verified_at else 0" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["services/reads.py"], f"selection rule duplicated in {hits}"

    # Parsed rather than grepped: the module's own prose explains *why* it does
    # not select, and a substring check would trip over the explanation.
    import ast

    tool = (root / "services/agent_tools/get_evidence.py").read_text(encoding="utf-8")
    called = {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(tool))
        if isinstance(node, ast.Call)
    }
    assert not any("load_evidence" in name for name in called), (
        f"get_evidence re-runs evidence selection: {called}"
    )


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


def test_get_evidence_writes_nothing(database_url, loop):
    slug, _ids, _ev = loop
    ref = refs_from_get_robot(slug)["PRICING_OFFER"]
    assert _writes_during(lambda: redeem(ref)) == []
