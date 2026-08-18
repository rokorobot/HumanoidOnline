"""AGENT-02.2c — `get_robot`, the full governed detail tool (`docs/20` §6).

Four things are actually at stake here, and most of the file serves them:

* **Provenance must be exact.** Every evidence object carries an `evidence_ref`
  addressing *the row whose metadata is displayed beside it*. A ref that resolves
  to a different row is worse than no ref: it is a confident citation of the
  wrong source. So the refs are resolved back and compared to the selected rows.
* **Publication must not be probeable.** Unknown, unpublished, case-variant and
  non-canonical slugs must be one indistinguishable answer (AGENT-01.7).
* **No database selector may cross the boundary** (§8, §20, §21.10) — checked
  recursively, and against planted real row ids rather than only a pattern.
* **Absence must not read as negation** (§6.1, §9.4). An empty list gets a notice
  saying nothing is on record, never "free", "unavailable" or "never deployed".

The fixtures deliberately build a robot with *two* pricing offers sharing an
identical public shape, and a superseded offer alongside a current one. Both
exist to catch association by value or by luck rather than by identity.
"""
from __future__ import annotations

import re
import sys
import uuid

import pytest
from sqlalchemy import event, text

from app.db.session import SessionLocal, engine
from app.services import reads
from app.services.agent_tools import (
    CONTRACT_VERSION,
    NO_CURRENT_AVAILABILITY_OFFER,
    NO_CURRENT_PRICING_OFFER,
    NO_DISPLAY_ELIGIBLE_IMAGE,
    NO_RECORDED_DEPLOYMENT,
    AgentToolError,
    NotFound,
    get_robot,
)
from app.services.evidence_refs import (
    EvidenceRefKeyring,
    ResolutionFailure,
    resolve_evidence_ref,
)
from tests.agent_identifier_gate import (
    assert_absent_everywhere,
    assert_no_database_identifier,
    walk,
)

KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([1]) * 64})

#: The tool MODULE, not the callable. `agent_tools.get_robot` resolves to the
#: re-exported function (the package convention `search_robots` already follows),
#: so patching its settings lookup has to go through the module object itself.
TOOL_MODULE = sys.modules["app.services.agent_tools.get_robot"]


class _NoKeySettings:
    evidence_ref_key = None
    evidence_ref_key_id = "1"
    evidence_ref_previous_keys = ""


class _BadKeySettings:
    evidence_ref_key = "!!!not-a-key!!!"
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
    """Build published robots with real commercial facts and real evidence."""
    robots: list[uuid.UUID] = []
    evidence: list[uuid.UUID] = []

    class Fixtures:
        @staticmethod
        def robot(published: bool = True, **cols) -> tuple[str, uuid.UUID]:
            mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
            slug = f"getrobot-probe-{uuid.uuid4().hex[:10]}"
            rid = _exec(
                "INSERT INTO robot (slug, manufacturer_id, name, model_code,"
                " commercial_status, is_published, summary, announced_year)"
                " VALUES (:s, :m, :n, :mc, CAST(:cs AS commercial_status), :p,"
                " :sum, :yr) RETURNING id",
                s=slug, m=mfr_id, n=slug.upper(),
                mc=cols.get("model_code", "MC-1"),
                cs=cols.get("commercial_status", "COMMERCIAL"),
                p=published,
                sum=cols.get("summary"), yr=cols.get("announced_year"),
            ).scalar_one()
            robots.append(rid)
            return slug, rid

        @staticmethod
        def evidence(subject_type: str, subject_id, **over) -> uuid.UUID:
            eid = _exec(
                "INSERT INTO evidence_source (subject_type, subject_id, source_type,"
                " confidence, observed_at, verified_at, source_url) VALUES"
                " (CAST(:st AS evidence_subject), :sid, :src, :conf,"
                " COALESCE(CAST(:obs AS timestamptz), now()),"
                " CAST(:ver AS timestamptz), :url) RETURNING id",
                st=subject_type, sid=subject_id,
                src=over.get("source_type", "MANUFACTURER_SITE"),
                conf=over.get("confidence", "HIGH"),
                obs=over.get("observed_at"), ver=over.get("verified_at"),
                url=over.get("source_url", "https://example.invalid/source"),
            ).scalar_one()
            evidence.append(eid)
            return eid

        @staticmethod
        def pricing(robot_id, *, current: bool = True, price: int = 1000) -> uuid.UUID:
            return _exec(
                "INSERT INTO pricing_offer (robot_id, transaction_type, price_type,"
                " currency, price, is_current) VALUES (:r, 'PURCHASE', 'PUBLIC',"
                " 'USD', :p, :c) RETURNING id", r=robot_id, p=price, c=current,
            ).scalar_one()

        @staticmethod
        def availability(robot_id, *, current: bool = True) -> uuid.UUID:
            return _exec(
                "INSERT INTO availability_offer (robot_id, transaction_type,"
                " availability_status, is_current) VALUES (:r, 'PURCHASE',"
                " 'AVAILABLE', :c) RETURNING id", r=robot_id, c=current,
            ).scalar_one()

        @staticmethod
        def deployment(robot_id, name: str = "Probe Customer") -> uuid.UUID:
            return _exec(
                "INSERT INTO deployment (robot_id, customer_name) "
                "VALUES (:r, :n) RETURNING id", r=robot_id, n=name,
            ).scalar_one()

        @staticmethod
        def image(robot_id, *, eligible: bool = True) -> uuid.UUID:
            rights = "PERMITTED" if eligible else "RESTRICTED"
            return _exec(
                "INSERT INTO robot_image (robot_id, image_url, image_type,"
                " source_type, identity_status, rights_status, usage_basis,"
                " is_primary) VALUES (:r, :u, 'FRONT', 'MANUFACTURER',"
                " 'VERIFIED', CAST(:rg AS image_rights_status), 'NONE', TRUE)"
                " RETURNING id",
                r=robot_id, u=f"https://example.invalid/{uuid.uuid4().hex}.jpg",
                rg=rights,
            ).scalar_one()

        @staticmethod
        def unpublish(robot_id) -> None:
            _exec("UPDATE robot SET is_published = FALSE WHERE id = :i", i=robot_id)

    yield Fixtures
    for eid in evidence:
        _exec("DELETE FROM evidence_source WHERE id = :i", i=eid)
    for rid in robots:
        _exec("DELETE FROM evidence_source WHERE subject_id = :i", i=rid)
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


@pytest.fixture
def fully_evidenced(catalogue):
    """One published robot with every supported fact class, each evidenced.

    Two current pricing offers share an identical public shape — same price,
    currency, type, no provider, no region — so nothing downstream can tell them
    apart by value. Their evidence differs only in `source_url`, which is how a
    mis-association becomes visible.
    """
    slug, rid = catalogue.robot(summary="A probe robot", announced_year=2026)
    ids = {"robot": rid}

    ids["price_a"] = catalogue.pricing(rid, price=1000)
    ids["price_b"] = catalogue.pricing(rid, price=1000)
    ids["price_old"] = catalogue.pricing(rid, price=999, current=False)
    ids["avail"] = catalogue.availability(rid)
    ids["avail_old"] = catalogue.availability(rid, current=False)
    ids["deploy"] = catalogue.deployment(rid)
    catalogue.image(rid)

    ev = {
        "COMMERCIAL_STATUS": catalogue.evidence(
            "COMMERCIAL_STATUS", rid, source_url="https://example.invalid/status"
        ),
        "PRICING_OFFER_A": catalogue.evidence(
            "PRICING_OFFER", ids["price_a"], source_url="https://example.invalid/a"
        ),
        "PRICING_OFFER_B": catalogue.evidence(
            "PRICING_OFFER", ids["price_b"], source_url="https://example.invalid/b"
        ),
        "AVAILABILITY_OFFER": catalogue.evidence(
            "AVAILABILITY_OFFER", ids["avail"], source_url="https://example.invalid/av"
        ),
        "DEPLOYMENT": catalogue.evidence(
            "DEPLOYMENT", ids["deploy"], source_url="https://example.invalid/dep"
        ),
        # Evidence for a SUPERSEDED offer. It must never surface: the response
        # does not carry that offer, so it carries no provenance for it either.
        "PRICING_OFFER_OLD": catalogue.evidence(
            "PRICING_OFFER", ids["price_old"], source_url="https://example.invalid/old"
        ),
    }
    return slug, ids, ev


def call(slug: str, **kw):
    with SessionLocal() as s:
        return get_robot(s, slug, keyring=kw.pop("keyring", KEYRING), **kw)


def dumped(slug: str) -> dict:
    return call(slug).data.model_dump(mode="json")


def resolve(ref: str):
    with SessionLocal() as s:
        return resolve_evidence_ref(s, ref, KEYRING)


# --------------------------------------------------------------------------
# THE HAPPY PATH AND ITS IDENTITY (§6, §8)
# --------------------------------------------------------------------------


def test_a_published_slug_returns_the_detail(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    result = call(slug)
    assert result.data.slug == slug
    assert result.contract_version == CONTRACT_VERSION


def test_canonical_url_is_the_slug_address(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert call(slug).data.canonical_url == f"/robots/{slug}"


def test_manufacturer_is_slug_and_name_only(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert set(dumped(slug)["manufacturer"]) == {"slug", "name"}


def test_model_code_arrives_through_the_shared_detail(database_url, fully_evidenced):
    """§6 requires `model_code`, and requires it via the SHARED read — so the
    agent value must be the governed detail's value, not a separate column read."""
    slug, _ids, _ev = fully_evidenced
    with SessionLocal() as s:
        robot = reads.load_detail(s, slug)
        governed = reads.serialize_detail(s, robot)
    assert governed.model_code == "MC-1"
    assert call(slug).data.model_code == governed.model_code


def test_governed_detail_fields_are_carried(database_url, fully_evidenced):
    """`get_robot` is the full-detail tool, not the compact list projection."""
    slug, _ids, _ev = fully_evidenced
    body = dumped(slug)
    for key in (
        "summary", "description", "hero_image_url", "announced_year",
        "status_history", "specs", "extended_specs", "capabilities",
        "variants", "use_case_fits", "images",
    ):
        assert key in body, key
    assert body["summary"] == "A probe robot"
    assert body["announced_year"] == 2026


def test_unknown_specs_are_null_not_zero(database_url, fully_evidenced):
    """§9.1 — an unrecorded fact is `null`, and the key is never omitted."""
    slug, _ids, _ev = fully_evidenced
    specs = dumped(slug)["specs"]
    assert "height_cm" in specs and specs["height_cm"] is None
    assert "payload_kg" in specs and specs["payload_kg"] is None
    assert specs["has_sdk"] is None


def test_commercial_status_stays_a_plain_value(database_url, fully_evidenced):
    """§6 — the status is never turned into an object; provenance is a sibling."""
    slug, _ids, _ev = fully_evidenced
    body = dumped(slug)
    assert body["commercial_status"] == "COMMERCIAL"
    assert isinstance(body["commercial_status"], str)


# --------------------------------------------------------------------------
# NOT_FOUND IS ONE ANSWER (§6, AGENT-01.7)
# --------------------------------------------------------------------------


def _failure(slug: str) -> tuple[str, str]:
    with pytest.raises(NotFound) as exc:
        call(slug)
    return exc.value.code, str(exc.value)


def test_an_unknown_slug_is_not_found(database_url):
    assert _failure(f"no-such-robot-{uuid.uuid4().hex}")[0] == "NOT_FOUND"


def test_unpublished_is_indistinguishable_from_unknown(
    database_url, catalogue
):
    """The decisive publication test: same code AND same message, so a caller
    cannot learn that a slug exists by reading the difference."""
    slug, rid = catalogue.robot(published=True)
    assert call(slug).data.slug == slug, "fixture sanity"

    catalogue.unpublish(rid)
    unpublished = _failure(slug)
    unknown = _failure(f"no-such-robot-{uuid.uuid4().hex}")
    assert unpublished == unknown


def test_a_case_variant_is_not_found(database_url, fully_evidenced):
    """Matching is exact and case-sensitive; no alias exists (§6)."""
    slug, _ids, _ev = fully_evidenced
    assert _failure(slug.upper()) == _failure(f"missing-{uuid.uuid4().hex}")


@pytest.mark.parametrize(
    "form", ["/robots/{slug}", "{slug}/", " {slug}", "{slug}?x=1", "{slug}#a"],
    ids=["path", "trailing-slash", "leading-space", "query", "fragment"],
)
def test_non_canonical_addressing_is_not_found(
    database_url, fully_evidenced, form
):
    slug, _ids, _ev = fully_evidenced
    assert _failure(form.format(slug=slug))[0] == "NOT_FOUND"


def test_a_non_string_slug_is_not_found(database_url):
    """§6 admits exactly one addressing form, so a UUID is not an address."""
    for value in (uuid.uuid4(), 42, None, ["x"]):
        with pytest.raises(NotFound):
            with SessionLocal() as s:
                get_robot(s, value, keyring=KEYRING)


# --------------------------------------------------------------------------
# EVIDENCE — REFS ADDRESS THE EXACT SELECTED ROW (§7.1, §9.5)
# --------------------------------------------------------------------------


def test_commercial_status_evidence_resolves_to_its_row(
    database_url, fully_evidenced
):
    slug, _ids, ev = fully_evidenced
    obj = call(slug).data.commercial_status_evidence
    assert obj is not None
    assert obj.subject_type == "COMMERCIAL_STATUS"
    resolved = resolve(obj.evidence_ref)
    assert not isinstance(resolved, ResolutionFailure)
    assert resolved.id == ev["COMMERCIAL_STATUS"]


def test_each_pricing_offer_cites_its_own_evidence(database_url, fully_evidenced):
    """The association test that matters.

    Both current offers have an identical public shape, so an implementation
    matching on price, currency or provider would attach the same evidence twice
    — or swap them — and no assertion about a single offer would notice. The
    check is that the two refs resolve to the two *distinct* expected rows.
    """
    slug, _ids, ev = fully_evidenced
    offers = call(slug).data.pricing_offers
    assert len(offers) == 2, "only current offers are exposed"

    resolved = {resolve(o.evidence.evidence_ref).id for o in offers}
    assert resolved == {ev["PRICING_OFFER_A"], ev["PRICING_OFFER_B"]}


def test_availability_evidence_resolves_to_its_row(database_url, fully_evidenced):
    slug, _ids, ev = fully_evidenced
    offers = call(slug).data.availability_offers
    assert len(offers) == 1
    assert offers[0].evidence.subject_type == "AVAILABILITY_OFFER"
    assert resolve(offers[0].evidence.evidence_ref).id == ev["AVAILABILITY_OFFER"]


def test_deployment_evidence_resolves_to_its_row(database_url, fully_evidenced):
    slug, _ids, ev = fully_evidenced
    deployments = call(slug).data.deployments
    assert len(deployments) == 1
    assert deployments[0].evidence.subject_type == "DEPLOYMENT"
    assert resolve(deployments[0].evidence.evidence_ref).id == ev["DEPLOYMENT"]


def test_displayed_metadata_matches_the_row_the_ref_addresses(
    database_url, fully_evidenced
):
    """A ref is only useful if it points where the visible metadata came from.

    `source_url` differs per row here precisely so a swap would be legible.
    """
    slug, _ids, _ev = fully_evidenced
    data = call(slug).data
    objects = [data.commercial_status_evidence]
    objects += [o.evidence for o in data.pricing_offers]
    objects += [o.evidence for o in data.availability_offers]
    objects += [d.evidence for d in data.deployments]

    for obj in objects:
        row = resolve(obj.evidence_ref)
        assert not isinstance(row, ResolutionFailure)
        assert obj.source_url == row.source_url
        assert obj.source_type == row.source_type
        assert obj.confidence == row.confidence
        assert obj.subject_type == row.subject_type


def test_evidence_for_a_superseded_offer_is_never_surfaced(
    database_url, fully_evidenced
):
    """Provenance attaches only to facts the response actually carries."""
    slug, _ids, ev = fully_evidenced
    data = call(slug).data
    refs = [o.evidence.evidence_ref for o in data.pricing_offers]
    resolved = {resolve(r).id for r in refs}
    assert ev["PRICING_OFFER_OLD"] not in resolved
    assert "https://example.invalid/old" not in repr(data.model_dump(mode="json"))


def test_refs_are_deterministic_across_calls(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    first, second = dumped(slug), dumped(slug)
    assert first == second


def test_an_unevidenced_fact_carries_null_not_a_fabricated_ref(
    database_url, catalogue
):
    """§9.5 — a reference is never invented to make a fact look sourced."""
    slug, rid = catalogue.robot()
    catalogue.pricing(rid)
    catalogue.deployment(rid)

    data = call(slug).data
    assert data.commercial_status_evidence is None
    assert data.pricing_offers[0].evidence is None
    assert data.deployments[0].evidence is None


def test_the_evidence_object_exposes_no_row_identity(database_url, fully_evidenced):
    """§9.5 — neither `evidence_source.id` nor `subject_id`, at any depth."""
    slug, _ids, _ev = fully_evidenced
    for path, key, _value in walk(dumped(slug)):
        assert key not in {"id", "subject_id", "evidence_id"}, path


def test_a_tied_selection_yields_a_stable_ref(database_url, catalogue):
    """§13.1 — a tie must resolve the same way every call, or a published
    citation would drift the next time the query planner changed its mind."""
    slug, rid = catalogue.robot()
    stamp = "2026-01-01T00:00:00Z"
    catalogue.evidence("COMMERCIAL_STATUS", rid, observed_at=stamp)
    catalogue.evidence("COMMERCIAL_STATUS", rid, observed_at=stamp)

    refs = {call(slug).data.commercial_status_evidence.evidence_ref for _ in range(5)}
    assert len(refs) == 1, "tied best-evidence selection is not stable"


# --------------------------------------------------------------------------
# CURRENCY OF FACTS (§10, §11)
# --------------------------------------------------------------------------


def test_only_current_pricing_offers_are_exposed(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert [o.price for o in call(slug).data.pricing_offers] == [1000.0, 1000.0]


def test_only_current_availability_offers_are_exposed(
    database_url, fully_evidenced
):
    slug, _ids, _ev = fully_evidenced
    assert len(call(slug).data.availability_offers) == 1


def test_the_governed_lists_match_the_http_detail(database_url, fully_evidenced):
    """Nothing is re-selected: the agent lists mirror the governed serialization
    element for element, differing only in the shape of `evidence`."""
    slug, _ids, _ev = fully_evidenced
    with SessionLocal() as s:
        governed = reads.serialize_detail(s, reads.load_detail(s, slug))
    data = call(slug).data

    assert [o.price for o in data.pricing_offers] == [
        o.price for o in governed.pricing_offers
    ]
    assert [o.availability_status for o in data.availability_offers] == [
        o.availability_status for o in governed.availability_offers
    ]
    assert [d.customer_name for d in data.deployments] == [
        d.customer_name for d in governed.deployments
    ]
    assert [i.image_url for i in data.images] == [i.image_url for i in governed.images]


def test_media01_gating_is_the_governed_one(database_url, catalogue):
    """An ineligible image is absent here for exactly the reason it is absent
    from the website: MEDIA-01, evaluated once in the governed read."""
    slug, rid = catalogue.robot()
    catalogue.image(rid, eligible=False)

    assert call(slug).data.images == []
    assert NO_DISPLAY_ELIGIBLE_IMAGE in call(slug).warnings


# --------------------------------------------------------------------------
# ABSENCE NOTICES (§6.1, §9.4)
# --------------------------------------------------------------------------


def test_a_bare_robot_reports_all_four_absences(database_url, catalogue):
    slug, _rid = catalogue.robot()
    assert call(slug).warnings == sorted(
        [
            NO_CURRENT_PRICING_OFFER,
            NO_CURRENT_AVAILABILITY_OFFER,
            NO_RECORDED_DEPLOYMENT,
            NO_DISPLAY_ELIGIBLE_IMAGE,
        ]
    )


def test_a_fully_populated_robot_reports_none(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert call(slug).warnings == []


@pytest.mark.parametrize(
    "populate,absent",
    [
        ("pricing", NO_CURRENT_PRICING_OFFER),
        ("availability", NO_CURRENT_AVAILABILITY_OFFER),
        ("deployment", NO_RECORDED_DEPLOYMENT),
        ("image", NO_DISPLAY_ELIGIBLE_IMAGE),
    ],
)
def test_each_notice_tracks_its_own_list(
    database_url, catalogue, populate, absent
):
    slug, rid = catalogue.robot()
    getattr(catalogue, populate)(rid)
    assert absent not in call(slug).warnings


def test_a_superseded_offer_still_counts_as_absent(database_url, catalogue):
    """The notice is about the *exposed* list, so a non-current offer does not
    suppress it — but it also never says "unpriced" or "never priced"."""
    slug, rid = catalogue.robot()
    catalogue.pricing(rid, current=False)
    assert NO_CURRENT_PRICING_OFFER in call(slug).warnings


def test_warnings_are_sorted_and_deduplicated(database_url, catalogue):
    slug, _rid = catalogue.robot()
    warnings = call(slug).warnings
    assert warnings == sorted(warnings)
    assert len(warnings) == len(set(warnings))


def test_warnings_carry_no_counts_or_identities(database_url, catalogue):
    """§6.1/§15 — machine-readable codes only, never smuggled payload."""
    slug, rid = catalogue.robot()
    for code in call(slug).warnings:
        assert re.fullmatch(r"[a-z_]+", code), code
        assert str(rid) not in code


# --------------------------------------------------------------------------
# IDENTIFIER SAFETY (§8, §20, §21.10)
# --------------------------------------------------------------------------


def test_no_database_identifier_at_any_depth(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert_no_database_identifier(dumped(slug))


def test_no_top_level_id(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert "id" not in dumped(slug)


def test_every_planted_row_identity_is_absent(database_url, fully_evidenced):
    """The strongest form: real robot, offer, deployment and evidence ids."""
    slug, ids, ev = fully_evidenced
    body = dumped(slug)
    assert_absent_everywhere(body, *ids.values(), *ev.values())
    assert_absent_everywhere(call(slug).data, *ids.values(), *ev.values())


def test_the_bare_robot_is_also_clean(database_url, catalogue):
    """A leak could hide in the branch where evidence and offers are absent."""
    slug, rid = catalogue.robot()
    body = dumped(slug)
    assert_no_database_identifier(body)
    assert_absent_everywhere(body, rid)


def test_the_safety_gate_would_catch_a_planted_leak() -> None:
    """Guards the guard, on the exact shapes this tool emits."""
    planted = str(uuid.uuid4())
    with pytest.raises(AssertionError):
        assert_no_database_identifier({"deployments": [{"evidence": {"id": "x"}}]})
    with pytest.raises(AssertionError):
        assert_no_database_identifier(
            {"pricing_offers": [{"evidence": {"source_url": planted}}]}
        )
    with pytest.raises(AssertionError):
        assert_absent_everywhere({"nested": [{"x": planted}]}, planted)
    with pytest.raises(AssertionError):
        assert_absent_everywhere({"x": planted.replace("-", "")}, planted)


def test_the_evidence_ref_is_opaque(database_url, fully_evidenced):
    """It must carry no plaintext identity, and must not itself look like one."""
    slug, _ids, ev = fully_evidenced
    ref = call(slug).data.commercial_status_evidence.evidence_ref
    row_id = ev["COMMERCIAL_STATUS"]
    assert str(row_id) not in ref
    assert str(row_id).replace("-", "") not in ref
    assert_no_database_identifier({"evidence_ref": ref})


# --------------------------------------------------------------------------
# FAIL CLOSED ON THE EVIDENCE KEY (§7.1, §17, §20)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "settings", [_NoKeySettings, _BadKeySettings], ids=["missing", "invalid"]
)
def test_an_unusable_key_fails_the_call_closed(
    database_url, fully_evidenced, monkeypatch, settings
):
    """Never a partial answer.

    Dropping `evidence_ref`, or returning the metadata without it, would leave an
    agent holding provenance it cannot verify — and returning the raw identifier
    instead is the exact thing §7.1 forbids. So the call fails.
    """
    slug, _ids, _ev = fully_evidenced
    monkeypatch.setattr(TOOL_MODULE, "get_settings", lambda: settings())
    with pytest.raises(AgentToolError) as exc:
        with SessionLocal() as s:
            get_robot(s, slug)
    assert exc.value.code == "INTERNAL"


@pytest.mark.parametrize(
    "settings", [_NoKeySettings, _BadKeySettings], ids=["missing", "invalid"]
)
def test_the_failure_leaks_no_configuration_detail(
    database_url, fully_evidenced, monkeypatch, settings
):
    """§20 — an agent must not read key or config state out of an error."""
    slug, _ids, _ev = fully_evidenced
    monkeypatch.setattr(TOOL_MODULE, "get_settings", lambda: settings())
    with pytest.raises(AgentToolError) as exc:
        with SessionLocal() as s:
            get_robot(s, slug)

    message = str(exc.value).lower()
    for secret in (
        "evidence_ref_key", "env", "base64", "aes", "siv", "key id", "keyring",
        "cryptography", "512", "64 bytes",
    ):
        assert secret not in message, f"{secret!r} leaked into the public message"


def test_an_unusable_key_fails_before_any_detail_is_built(
    database_url, catalogue, monkeypatch
):
    """Uniformly, for a robot with no evidence at all.

    Deferring the key until the first evidenced fact would make success depend on
    whether *this* robot happens to have provenance — a weak oracle about
    catalogue contents, and a silent way to serve detail with provenance stripped.
    """
    slug, _rid = catalogue.robot()
    monkeypatch.setattr(TOOL_MODULE, "get_settings", lambda: _NoKeySettings())
    with pytest.raises(AgentToolError):
        with SessionLocal() as s:
            get_robot(s, slug)


# --------------------------------------------------------------------------
# ONE SELECTION, ONE ALGORITHM (§13.1)
# --------------------------------------------------------------------------


def test_the_best_evidence_rule_is_stated_exactly_once() -> None:
    """Structural. Two implementations of "best evidence" would eventually mean
    the website and the agent citing different rows for the same fact."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    hits = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "verified_at else 0" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["services/reads.py"], f"selection rule duplicated in {hits}"


def test_the_agent_layer_does_not_import_the_router() -> None:
    """§6 — agent code sits behind the governed services, not behind the HTTP
    binding, so it must not reach for a router-private helper."""
    from pathlib import Path

    agent = Path(__file__).resolve().parents[1] / "app/services/agent_tools"
    for path in agent.rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert "app.routers" not in body, f"{path.name} imports a router"
        assert "_load_detail" not in body, f"{path.name} uses a router private"


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


def test_get_robot_writes_nothing(database_url, fully_evidenced):
    slug, _ids, _ev = fully_evidenced
    assert _writes_during(lambda: call(slug)) == []


def test_evidence_is_selected_once_per_call(database_url, fully_evidenced):
    """`serialize_detail` must reuse the rows it is handed rather than running a
    second best-evidence pass over the same subjects."""
    slug, _ids, _ev = fully_evidenced
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "evidence_source" in statement.lower():
            seen.append(statement)

    event.listen(engine, "after_cursor_execute", record)
    try:
        call(slug)
    finally:
        event.remove(engine, "after_cursor_execute", record)
    assert len(seen) == 1, f"{len(seen)} evidence queries in one call"
