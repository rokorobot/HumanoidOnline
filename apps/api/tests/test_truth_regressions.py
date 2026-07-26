"""WS8.3 — data/truth regressions (R11–R15), proven by injection.

The rule this file is written to: **absence is proven by planting a forbidden
value and failing to find it in a real serialized response** — never by grepping
field names or route declarations. A test that asserts `"contact_email" not in
body` passes just as happily when the endpoint is broken as when it is correct;
a test that plants `pii-probe-9f3c@example.com` and then reads every public
response actually exercises the boundary.

Every fixture here is created inside the test and removed afterwards, so the
shared seeded database is left exactly as found.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine
from app.models.robot_image import RobotImage

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _public_surfaces(client) -> list[tuple[str, str]]:
    """(url, body) for every unauthenticated GET a crawler could reach."""
    urls = [
        "/",
        "/api/robots?limit=100",
        "/api/manufacturers?limit=100",
        "/api/use-cases?limit=100",
        "/api/regions",
        "/api/market-snapshot",
    ]
    robots = client.get("/api/robots", params={"limit": 100}).json().get("items", [])
    urls += [f"/api/robots/{r['slug']}" for r in robots]
    mfrs = client.get("/api/manufacturers", params={"limit": 100}).json().get("items", [])
    urls += [f"/api/manufacturers/{m['slug']}" for m in mfrs]
    ucs = client.get("/api/use-cases", params={"limit": 100}).json().get("items", [])
    urls += [f"/api/use-cases/{u['slug']}" for u in ucs]

    out = []
    for url in urls:
        resp = client.get(url)
        if resp.status_code == 200:
            out.append((url, resp.text))
    return out


# ==========================================================================
# R11 — MEDIA-01
# ==========================================================================

IDENTITY = ("VERIFIED", "UNVERIFIED")
RIGHTS = ("PERMITTED", "ATTRIBUTION_REQUIRED", "UNKNOWN", "RESTRICTED")
USAGE = ("NONE", "OFFICIAL_MANUFACTURER_MEDIA")


def _image(identity: str, rights: str, usage: str, attribution: str | None = "© Someone"):
    return RobotImage(
        robot_id=uuid.uuid4(),
        image_url="https://example.invalid/x.jpg",
        source_type="MANUFACTURER",
        image_type="FRONT",
        identity_status=identity,
        rights_status=rights,
        usage_basis=usage,
        attribution=attribution,
    )


def _expected_eligible(identity: str, rights: str, usage: str, attribution: str | None) -> bool:
    """The frozen MEDIA-01 rule, restated independently of the implementation."""
    if identity != "VERIFIED":
        return False
    if rights == "RESTRICTED":
        return False
    has_usage = usage == "OFFICIAL_MANUFACTURER_MEDIA"
    if not (rights in ("PERMITTED", "ATTRIBUTION_REQUIRED") or has_usage):
        return False
    # The credit obligation attaches to the rights state and is NOT overridable
    # by usage_basis (a display policy). ATTRIBUTION_REQUIRED always owes a credit.
    if rights == "ATTRIBUTION_REQUIRED":
        return bool((attribution or "").strip())
    return True


@pytest.mark.parametrize("identity", IDENTITY)
@pytest.mark.parametrize("rights", RIGHTS)
@pytest.mark.parametrize("usage", USAGE)
def test_r11_full_eligibility_matrix(identity: str, rights: str, usage: str) -> None:
    """All 16 identity x rights x usage cells (gap Q5 covered 9).

    Asserted against a restatement of the law rather than the implementation, so
    the test fails if the code changes meaning — not merely if it changes shape.
    """
    img = _image(identity, rights, usage)
    assert img.is_display_eligible() is _expected_eligible(
        identity, rights, usage, "© Someone"
    ), f"{identity}/{rights}/{usage}"


def test_r11_restricted_always_blocks_even_with_official_media() -> None:
    """RESTRICTED is absolute: no display policy can override a rights refusal."""
    assert not _image("VERIFIED", "RESTRICTED", "OFFICIAL_MANUFACTURER_MEDIA").is_display_eligible()


def test_r11_unknown_rights_never_behaves_like_permitted() -> None:
    assert not _image("VERIFIED", "UNKNOWN", "NONE").is_display_eligible()
    # ...but an official-media basis is an independent, sufficient reason.
    assert _image("VERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA").is_display_eligible()


def test_r11_a_non_null_image_url_is_never_sufficient() -> None:
    img = _image("UNVERIFIED", "PERMITTED", "NONE")
    assert img.image_url and not img.is_display_eligible()


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_r11_attribution_required_without_attribution_is_ineligible(missing) -> None:
    """Gap Q14: the schema documented this in a comment and enforced nothing, so
    such an image displayed with no credit — a live rights exposure."""
    assert not _image(
        "VERIFIED", "ATTRIBUTION_REQUIRED", "NONE", attribution=missing
    ).is_display_eligible()
    # With a credit line it is displayable again.
    assert _image("VERIFIED", "ATTRIBUTION_REQUIRED", "NONE", "© Figure AI").is_display_eligible()


def test_r11_attribution_required_is_not_overridden_by_official_media() -> None:
    """`usage_basis` is a platform display POLICY, not a licence override.

    An ATTRIBUTION_REQUIRED image with no credit is INELIGIBLE even when
    usage_basis is OFFICIAL_MANUFACTURER_MEDIA — the credit obligation attaches
    to the KNOWN rights state and a display policy cannot waive it. (Official
    media whose licence is genuinely unknown is modelled as rights_status=UNKNOWN
    + usage OFFICIAL_MANUFACTURER_MEDIA, exactly so no attribution licence is
    falsely asserted; that path stands on its own — see the UNKNOWN test above.)
    """
    assert not _image(
        "VERIFIED", "ATTRIBUTION_REQUIRED", "OFFICIAL_MANUFACTURER_MEDIA", attribution=None
    ).is_display_eligible()
    # With a credit line it is displayable.
    assert _image(
        "VERIFIED", "ATTRIBUTION_REQUIRED", "OFFICIAL_MANUFACTURER_MEDIA", "© Maker"
    ).is_display_eligible()


def test_r11_exactly_one_eligibility_implementation_exists() -> None:
    """The dead SQL twin is gone (gap Q5). Two copies of a governed gate can only
    diverge — and the removed one already lacked the attribution rule."""
    import app.models.robot_image as module

    assert not hasattr(module, "DISPLAY_ELIGIBLE_CLAUSE")
    assert hasattr(module.RobotImage, "is_display_eligible")


def test_r11_hero_image_url_cannot_bypass_the_gate(client, database_url) -> None:
    """Gap Q6, proven through the real serialized response.

    Plant an un-cleared URL in `robot.hero_image_url` — the field that was
    serialized raw on both read paths — and prove it cannot reach the API.
    """
    forbidden = f"https://uncleared.invalid/{_uniq('hero')}.jpg"
    slug = _exec("SELECT slug FROM robot WHERE is_published LIMIT 1").scalar_one()
    original = _exec(
        "SELECT hero_image_url FROM robot WHERE slug = :s", s=slug
    ).scalar_one()
    try:
        _exec(
            "UPDATE robot SET hero_image_url = :u WHERE slug = :s", u=forbidden, s=slug
        )
        detail = client.get(f"/api/robots/{slug}")
        assert detail.status_code == 200
        assert forbidden not in detail.text, "un-cleared hero URL reached robot detail"
        assert detail.json()["hero_image_url"] is None

        listing = client.get("/api/robots", params={"limit": 100})
        assert forbidden not in listing.text, "un-cleared hero URL reached the catalogue"

        for url, body in _public_surfaces(client):
            assert forbidden not in body, f"un-cleared hero URL surfaced on {url}"
    finally:
        _exec("UPDATE robot SET hero_image_url = :u WHERE slug = :s", u=original, s=slug)


def test_r11_ineligible_image_never_reaches_the_api(client, database_url) -> None:
    """Plant a RESTRICTED image on a published robot and prove no surface shows it."""
    forbidden = f"https://restricted.invalid/{_uniq('img')}.jpg"
    robot_id = _exec("SELECT id FROM robot WHERE is_published LIMIT 1").scalar_one()
    slug = _exec("SELECT slug FROM robot WHERE id = :i", i=robot_id).scalar_one()
    _exec(
        "INSERT INTO robot_image (robot_id, image_url, source_type, image_type, "
        "identity_status, rights_status, usage_basis) VALUES "
        "(:r, :u, 'MANUFACTURER', 'FRONT', 'VERIFIED', 'RESTRICTED', 'NONE')",
        r=robot_id,
        u=forbidden,
    )
    try:
        detail = client.get(f"/api/robots/{slug}")
        assert detail.status_code == 200
        assert forbidden not in detail.text
        for url, body in _public_surfaces(client):
            assert forbidden not in body, f"restricted image surfaced on {url}"
    finally:
        _exec("DELETE FROM robot_image WHERE image_url = :u", u=forbidden)


def test_r11_attribution_required_without_credit_never_reaches_the_api(
    client, database_url
) -> None:
    """Q14 end-to-end: an uncredited ATTRIBUTION_REQUIRED image is not served."""
    forbidden = f"https://uncredited.invalid/{_uniq('img')}.jpg"
    robot_id = _exec("SELECT id FROM robot WHERE is_published LIMIT 1").scalar_one()
    slug = _exec("SELECT slug FROM robot WHERE id = :i", i=robot_id).scalar_one()
    _exec(
        "INSERT INTO robot_image (robot_id, image_url, source_type, image_type, "
        "identity_status, rights_status, usage_basis, attribution) VALUES "
        "(:r, :u, 'EDITORIAL', 'FRONT', 'VERIFIED', 'ATTRIBUTION_REQUIRED', 'NONE', NULL)",
        r=robot_id,
        u=forbidden,
    )
    try:
        detail = client.get(f"/api/robots/{slug}")
        assert forbidden not in detail.text
    finally:
        _exec("DELETE FROM robot_image WHERE image_url = :u", u=forbidden)


def test_r11_every_served_image_carries_its_required_attribution(
    client, database_url
) -> None:
    """Whole-catalogue sweep: nothing display-eligible is served uncredited."""
    for item in client.get("/api/robots", params={"limit": 100}).json()["items"]:
        detail = client.get(f"/api/robots/{item['slug']}").json()
        for img in detail.get("images", []):
            rows = _exec(
                "SELECT rights_status, usage_basis, attribution FROM robot_image "
                "WHERE image_url = :u",
                u=img["image_url"],
            ).all()
            for rights, usage, attribution in rows:
                if rights == "ATTRIBUTION_REQUIRED" and usage != "OFFICIAL_MANUFACTURER_MEDIA":
                    assert (attribution or "").strip(), img["image_url"]
                    assert (img.get("attribution") or "").strip(), img["image_url"]


# ==========================================================================
# R12 — DATA-D1 isolation, proven at the response body
# ==========================================================================


def test_r12_candidate_data_never_appears_in_any_public_response_body(
    client, database_url
) -> None:
    """Gap Q7. The existing DATA-D1 test asserts route-path substrings, which
    would not catch discovery data leaking through an EXISTING canonical route.

    So: create a real discovery source + candidate + claim carrying unmistakable
    sentinel strings, then read every public surface and prove none of them
    appear anywhere in the serialized bodies.
    """
    sentinel_name = _uniq("CANDIDATE-ROBOT")
    sentinel_mfr = _uniq("CANDIDATE-MAKER")
    sentinel_claim = _uniq("CANDIDATE-CLAIM")
    key = _uniq("ws83-src")

    source_id = _exec(
        "INSERT INTO discovery_source (key, name, source_class) "
        "VALUES (:k, :n, 'COMPETITOR_DIRECTORY') RETURNING id",
        k=key,
        n=f"WS8.3 probe {key}",
    ).scalar_one()
    candidate_id = _exec(
        "INSERT INTO discovery_candidate (source_id, external_ref, candidate_name, "
        "candidate_manufacturer, entity_type) VALUES (:s, :e, :n, :m, 'ROBOT') RETURNING id",
        s=source_id,
        e=key,
        n=sentinel_name,
        m=sentinel_mfr,
    ).scalar_one()
    _exec(
        "INSERT INTO candidate_claim (candidate_id, field_key, claimed_value) "
        "VALUES (:c, 'height_cm', :v)",
        c=candidate_id,
        v=sentinel_claim,
    )
    try:
        surfaces = _public_surfaces(client)
        assert surfaces, "expected public surfaces to read"
        for url, body in surfaces:
            for sentinel in (sentinel_name, sentinel_mfr, sentinel_claim, key):
                assert sentinel not in body, f"discovery data leaked via {url}"
    finally:
        _exec("DELETE FROM candidate_claim WHERE candidate_id = :c", c=candidate_id)
        _exec("DELETE FROM discovery_candidate WHERE id = :c", c=candidate_id)
        _exec("DELETE FROM discovery_source WHERE id = :s", s=source_id)


def test_r12_promotion_docs_match_implemented_gates() -> None:
    """Gap Q8a: three call sites advertised "P1-P8" while a subset was enforced.
    Documentation that overstates a governance gate is worse than none."""
    from app.services import discovery
    from app.services.discovery import promotion

    assert "P1-P8" not in (promotion.__doc__ or "")
    assert "P1-P8" not in (discovery.PromotionError.__doc__ or "")
    gate_doc = promotion.check_gates.__doc__ or ""
    # It must name what is enforced AND what is not.
    for enforced in ("P1", "P2", "P4", "P6"):
        assert enforced in gate_doc
    assert "P3, P5 and P7 are NOT implemented" in gate_doc


def test_r12_deferred_gates_are_still_deferred() -> None:
    """WS8 must not implement P3/P5/P7 (ACCEPT-DEFER, DATA-D1 scope)."""
    import inspect

    from app.services.discovery import promotion

    source = inspect.getsource(promotion.check_gates)
    for absent in ("P3 ", "P5 ", "P7 "):
        assert absent not in source.replace("P3, P5 and P7 are NOT implemented", "")


# ==========================================================================
# R13 — no live crawling from any public flow
# ==========================================================================


def test_r13_no_http_client_is_importable_from_the_discovery_layer() -> None:
    """A network adapter cannot exist without a client to make requests with."""
    import inspect

    from app.services.discovery import adapters

    source = inspect.getsource(adapters)
    for client in ("requests", "httpx", "urllib.request", "aiohttp", "socket"):
        assert client not in source, f"{client} reachable from the discovery adapter"


def test_r13_only_a_fixture_adapter_exists() -> None:
    """`SourceAdapter` is the Protocol; the only CONCRETE implementation must be
    the offline fixture reader. A live network adapter is a separately-gated
    DATA-D1 slice (each source needs an affirmative DATA-D1.9 review) and must
    not appear as a side effect of hardening."""
    import typing

    from app.services.discovery import adapters

    concrete = {
        name
        for name, obj in vars(adapters).items()
        if isinstance(obj, type)
        and name.endswith("Adapter")
        and typing.Protocol not in getattr(obj, "__bases__", ())
    }
    assert concrete == {"FixtureAdapter"}, concrete


def test_r13_public_request_flow_opens_no_outbound_connection(
    client, database_url, monkeypatch
) -> None:
    """Adversarial: make any outbound socket fatal, then exercise public reads.

    The database connection is already established through the engine pool, so
    a public read needs no new socket. If any public flow tried to crawl, this
    would raise instead of quietly succeeding.
    """
    import socket

    client.get("/api/robots", params={"limit": 1})  # warm the pool first

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("public flow attempted an outbound network connection")

    monkeypatch.setattr(socket, "create_connection", _forbidden)
    for url in (
        "/",
        "/api/robots?limit=100",
        "/api/manufacturers?limit=100",
        "/api/use-cases?limit=100",
        "/api/market-snapshot",
    ):
        assert client.get(url).status_code == 200


# ==========================================================================
# R14 — AGENT-01: unpublished absence, UNKNOWN preservation
# ==========================================================================


def test_r14_unpublished_robot_is_absent_from_every_public_surface(
    client, database_url
) -> None:
    """Negative proof by injection (gap Q9): create a real unpublished robot with
    sentinel identifiers and prove it appears nowhere a machine can read.

    This is the DATA-D1 promotion default — promoted robots start unpublished —
    so a leak here would publish unverified market data as canonical fact.
    """
    slug = _uniq("unpublished-probe")
    name = _uniq("UNPUBLISHED-PROBE-NAME")
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
        "VALUES (:s, :m, :n, false) RETURNING id",
        s=slug,
        m=mfr_id,
        n=name,
    ).scalar_one()
    try:
        # Direct fetch must 404 — not 200-with-content.
        assert client.get(f"/api/robots/{slug}").status_code == 404
        for url, body in _public_surfaces(client):
            assert slug not in body, f"unpublished slug surfaced on {url}"
            assert name not in body, f"unpublished name surfaced on {url}"
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


def test_r14_unpublished_robot_is_absent_from_matching_and_leads(
    client, database_url
) -> None:
    """The same entity must not reach the decision or commercial layers either."""
    slug = _uniq("unpublished-match-probe")
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
        "VALUES (:s, :m, :n, false) RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("UNPUBLISHED-MATCH"),
    ).scalar_one()
    rid = None
    try:
        created = client.post(
            "/api/buyer-requirements",
            json={
                "country": "US",
                "preferred_transaction": "UNKNOWN",
                "raw_input": {
                    "wizard_version": 1,
                    "answers": {"country": {"state": "ANSWERED", "value": "US"}},
                },
            },
        )
        assert created.status_code == 201, created.text
        rid = created.json()["id"]
        matches = client.get(f"/api/buyer-requirements/{rid}/matches")
        assert matches.status_code == 200
        assert slug not in matches.text

        # And it cannot be attached to a lead.
        refused = client.post(
            "/api/commercial-leads",
            json={
                "requirement_id": rid,
                "contact_email": f"{_uniq('probe')}@example.com",
                "robot_slugs": [slug],
            },
        )
        assert refused.status_code == 422, refused.text
    finally:
        if rid:
            _exec("DELETE FROM match_result WHERE requirement_id = :i", i=rid)
            _exec("DELETE FROM buyer_requirement WHERE id = :i", i=rid)
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


def test_r14_unknown_specs_stay_null_and_are_never_coerced(client, database_url) -> None:
    """UNKNOWN must arrive as null — never 0, false, "" or "unknown"."""
    slug = _uniq("unknown-probe")
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, "
        "commercial_status) VALUES (:s, :m, :n, true, 'ANNOUNCED') RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("UNKNOWN-PROBE"),
    ).scalar_one()
    try:
        detail = client.get(f"/api/robots/{slug}")
        assert detail.status_code == 200
        body = detail.json()
        for field in ("payload_kg", "height_cm", "mobility"):
            value = body.get("specs", {}).get(field, body.get(field))
            assert value is None or value == {}, (field, value)
        # No pricing rows -> price_display is null, NOT a zero price.
        assert body.get("price_display") is None
        # No availability rows -> empty list, never a fabricated "unavailable".
        assert body.get("availability_offers") == []
        assert "unavailable" not in detail.text.lower()
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


# ==========================================================================
# R15 — whole-surface truth umbrella
# ==========================================================================


def test_r15_price_trichotomy_holds_across_the_catalogue(client, database_url) -> None:
    """UNKNOWN vs QUOTE_ONLY vs a known price are three different facts, and the
    API must never collapse them. Checked for every published robot, not one."""
    for item in client.get("/api/robots", params={"limit": 100}).json()["items"]:
        price = item.get("price_display")
        if price is None:
            continue  # unknown: no pricing rows at all
        assert price["type"] in ("PUBLIC", "ESTIMATED", "QUOTE_ONLY", "FROM", "RANGE")
        if price["type"] == "QUOTE_ONLY":
            # Known commercial model, unknown amount — must not become 0 or a price.
            assert price["amount"] is None
        else:
            assert price["amount"] is None or price["amount"] > 0


def test_r15_three_dimensions_never_collapse(client, database_url) -> None:
    """maturity != obtainability != evidence, on real serialized detail."""
    for item in client.get("/api/robots", params={"limit": 100}).json()["items"]:
        detail = client.get(f"/api/robots/{item['slug']}").json()
        assert detail["commercial_status"], item["slug"]  # maturity always present
        assert isinstance(detail["availability_offers"], list)  # obtainability
        assert isinstance(detail["deployments"], list)  # evidence
        # A robot may be mature and unobtainable, or deployed and unpurchasable.
        # The API must not invent an `available` boolean anywhere.
        assert "available" not in detail


def test_r15_g2_every_published_commercial_fact_carries_evidence(database_url) -> None:
    """The G2 invariant, asserted against the live database rather than trusting
    the importer that last wrote it."""
    gaps = _exec(
        "SELECT count(*) FROM deployment d JOIN robot r ON r.id = d.robot_id "
        "WHERE r.is_published AND NOT EXISTS ("
        "  SELECT 1 FROM evidence_source e "
        "  WHERE e.subject_type = 'DEPLOYMENT' AND e.subject_id = d.id)"
    ).scalar_one()
    assert gaps == 0, f"{gaps} published deployment(s) without evidence"


def test_r15_evidence_carries_provenance_not_just_a_flag(client, database_url) -> None:
    for item in client.get("/api/robots", params={"limit": 100}).json()["items"]:
        detail = client.get(f"/api/robots/{item['slug']}").json()
        for dep in detail.get("deployments", []):
            evidence = dep.get("evidence")
            if evidence:
                assert evidence.get("observed_at"), item["slug"]
                assert "source_type" in evidence and "confidence" in evidence
