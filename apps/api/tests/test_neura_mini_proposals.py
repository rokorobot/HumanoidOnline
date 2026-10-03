"""NEURA 4NE1 Mini — proposal-only structured claim extraction, offline.

The fixture is the captured official page, trimmed (tests/fixtures/neura_mini). The
trimmed fixture, the full 2026-10-03 page and the full 2026-09-26 page were checked to
yield identical proposals when this extractor was written.

Proves: one robot identity with Standard/Pro as subordinate editions; every proposal
keeps provenance; nothing is written or wired into the live adapter; output is
deterministic; navigation/footer changes cannot create claims; and malformed or
missing source structure fails safe instead of being inferred.
"""
from __future__ import annotations

import ast
import html as html_lib
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.session import engine
from app.models.acquisition import CandidateCommercialSignal
from app.models.discovery import CandidateClaim, DiscoveryCandidate
from app.models.evidence import EvidenceSource
from app.models.robot import Robot, RobotVariant
from app.services.discovery.live_adapter import EVIDENCE_EXCERPT_MAX_CHARS
from app.services.discovery.sources import ADAPTERS
from app.services.discovery.sources import neura_mini_proposals as mod
from app.services.discovery.sources.neura_mini_proposals import (
    AMBIGUOUS,
    CLEAN,
    MINI_URL,
    NO_PROPOSALS,
    OUT_OF_SCOPE,
    PARTIAL,
    PROPOSED,
    UNREPRESENTABLE,
    ObservationRef,
    propose_neura_mini_claims,
    render,
)
from app.services.discovery.sources.neura_robotics import CONFIG, extract_neura_product

pytestmark = pytest.mark.usefixtures("no_external_network")

FIXTURE = Path(__file__).parent / "fixtures" / "neura_mini" / "mini_reservation_trimmed.html"
PAGE = FIXTURE.read_text(encoding="utf-8")


def run(page: str | bytes = PAGE, url: str = MINI_URL, observation=None):
    body = page if isinstance(page, bytes) else page.encode("utf-8")
    return propose_neura_mini_claims(body, url, observation)


def kinds(result) -> list[tuple[str, str | None]]:
    return [(p.kind, p.edition) for p in result.proposals]


def by(result, kind: str, edition: str | None):
    [match] = [p for p in result.proposals if p.kind == kind and p.edition == edition]
    return match


def visible_text(page: str) -> str:
    stripped = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", stripped)))


def _widget_pattern(text: str) -> re.Pattern:
    return re.compile(
        r'<div class="[^"]*elementor-widget-text-editor">\s*'
        r'<div class="elementor-widget-container">\s*(?:<p>)?\s*' + re.escape(text)
        + r'\s*(?:</p>)?\s*</div>\s*</div>')


def drop_cell(page: str, text: str, nth: int = 0) -> str:
    """Remove the nth text widget whose content is exactly `text` (a missing cell)."""
    matches = list(_widget_pattern(text).finditer(page))
    assert len(matches) > nth, f"widget {text!r} #{nth} not in fixture"
    m = matches[nth]
    return page[:m.start()] + page[m.end():]


def replace_cell(page: str, text: str, new: str, nth: int = 0) -> str:
    matches = list(_widget_pattern(text).finditer(page))
    assert len(matches) > nth, f"widget {text!r} #{nth} not in fixture"
    m = matches[nth]
    return page[:m.start()] + m.group(0).replace(text, new, 1) + page[m.end():]


# ------------------------------------------------------- 1. one robot identity --


def test_exactly_one_robot_identity_and_two_subordinate_editions():
    result = run()
    assert result.status == PROPOSED and result.robot_name == "4NE1 Mini"
    assert result.editions == ("Standard", "Pro")
    # The production identity-only extractor independently names the same single robot.
    identity = extract_neura_product(CONFIG, PAGE.encode("utf-8"), MINI_URL)
    assert (identity.status, identity.name) == ("EXTRACTED", "4NE1 Mini")
    # Standard and Pro exist only as VARIANT proposals, never as a robot or its name.
    variants = result.of_kind("VARIANT")
    assert [(v.edition, dict(v.structured)["slug"]) for v in variants] == [
        ("Standard", "standard"), ("Pro", "pro")]
    assert all(v.target == "robot_variant" for v in variants)
    assert not [p for p in result.proposals if p.target.startswith("robot[")
                or p.kind in ("ROBOT", "IDENTITY")]
    assert all(p.edition in ("Standard", "Pro", None) for p in result.proposals)
    # The identity is never carried as a claim to rename or create anything.
    assert not [p for p in result.proposals if p.value in ("4NE1 Mini", "4NE1")]


@pytest.mark.parametrize("url", [
    "https://neura-robotics.com/products/mipa",
    "https://neura-robotics.com/product/4ne1-reservation",
    "https://neura-robotics.com/products/4ne1",
    "https://neura-robotics.com/products/maira",
    "https://other.example/product/4ne1-mini-reservation",
    "not a url",
    None,
])
def test_only_the_mini_page_is_in_scope(url):
    result = run(url=url)
    assert result.status == OUT_OF_SCOPE and result.proposals == ()


def test_mini_url_spellings_normalize_to_the_one_page():
    for spelling in (MINI_URL + "/", MINI_URL + "/?utm_source=x", MINI_URL.upper().replace(
            "HTTPS", "https")):
        assert run(url=spelling).status in (PROPOSED, OUT_OF_SCOPE)
    assert run(url=MINI_URL + "/").status == PROPOSED
    assert run(url=MINI_URL + "/?utm_source=x").status == PROPOSED


# --------------------------------------------------- 2. editions are subordinate --


def test_per_edition_values_are_carried_per_edition_exactly_as_stated():
    result = run()
    prices = {e: dict(by(result, "PRICE_ESTIMATE", e).structured) for e in ("Standard", "Pro")}
    assert prices["Standard"]["amount"] == "19999.00" and prices["Pro"]["amount"] == "29999.00"
    assert all(p["currency"] == "EUR" and p["basis"] == "excluding taxes and shipping"
               for p in prices.values())
    assert by(result, "SPECIFICATION", "Standard").value == "Not included"
    assert by(result, "SPECIFICATION", "Pro").value == "12 DoF dexterous hands"
    assert {dict(by(result, "RESERVATION_FEE", e).structured)["amount"]
            for e in ("Standard", "Pro")} == {"100.00"}
    # Identical cells in both editions stay two proposals; they are not collapsed.
    integration = result.of_kind("INTEGRATION")
    assert [(p.edition, p.value) for p in integration] == [
        ("Standard", "Full connection"), ("Pro", "Full connection")]
    # Page order is kept within a group: Common interfaces before Additional interfaces.
    pro_interfaces = [dict(p.structured)["row"] for p in result.of_kind("INTERFACES")
                      if p.edition == "Pro"]
    assert pro_interfaces == ["Common interfaces", "Additional interfaces"]


def test_nothing_is_inferred_from_the_cells():
    result = run()
    targets = " ".join(p.target for p in result.proposals)
    for invented in ("has_manipulation", "hand_dof", "has_sdk", "ros_support",
                     "has_teleoperation", "simulation_support", "commercial_status",
                     "price_type", "availability_status"):
        assert invented not in targets
    for p in result.of_kind("PRICE_ESTIMATE"):
        assert "price_type" not in dict(p.structured)
        assert "transaction_type" not in dict(p.structured)
        assert "region" not in dict(p.structured)
    for p in result.of_kind("AVAILABILITY"):
        assert "availability_status" not in dict(p.structured)
        assert dict(p.structured) == {"expected_year": "2026"}
    # The "/" placeholder is not read as "none"; nothing is proposed for it.
    assert not [p for p in result.of_kind("INTERFACES")
                if p.edition == "Standard" and dict(p.structured)["row"] == "Additional interfaces"]
    assert ("Additional interfaces / Standard" in " ".join(item for item, _ in result.rejected))


def test_representability_is_stated_for_every_proposal():
    result = run()
    by_class = {}
    for p in result.proposals:
        by_class.setdefault(p.representability, set()).add(p.kind)
    assert by_class[CLEAN] == {"VARIANT"}
    assert by_class[PARTIAL] == {"SPECIFICATION", "PRICE_ESTIMATE", "AVAILABILITY",
                                 "DATASHEET_REFERENCE", "INTERFACES"}
    assert by_class[UNREPRESENTABLE] == {"RESERVATION_FEE", "RESERVATION_TERMS", "DESIGN_CAVEAT",
                                         "USE_CASES", "INTEGRATION"}
    for p in result.proposals:
        if p.representability != CLEAN:
            assert p.gap, p.kind
    price = by(result, "PRICE_ESTIMATE", "Pro")
    assert "price_type" in price.gap and "price_type decision" in price.review_required
    sheet = result.of_kind("DATASHEET_REFERENCE")[0]
    assert "not the approved NEURA host" in sheet.gap and "not fetched" in sheet.gap
    assert dict(sheet.structured)["host"] == "neurarobotics.px.media"


# ------------------------------------------------------------- 3. provenance --


def test_every_proposal_keeps_provenance_and_bounded_verbatim_evidence():
    obs = ObservationRef(fetched_page_id="fp-1", crawl_run_id="run-1",
                         retrieved_at="2026-10-02T08:54:00+00:00", content_hash="facefce4")
    result = run(observation=obs)
    page_text = visible_text(PAGE)
    assert result.observation == obs and result.proposals
    for p in result.proposals:
        assert p.source_url == MINI_URL and p.observation == obs
        assert p.method == "SELECTOR" and p.confidence in ("HIGH", "MEDIUM")
        assert 0 < len(p.evidence.excerpt) <= EVIDENCE_EXCERPT_MAX_CHARS and p.evidence.locator
        # The excerpt is verbatim page text, not a paraphrase.
        assert p.evidence.excerpt in page_text, (p.kind, p.evidence.excerpt)
        assert p.claim_status == "NOT_VERIFIED" and p.review_required or p.kind == "VARIANT" \
            or p.representability in (UNREPRESENTABLE, PARTIAL)
    assert len({p.digest for p in result.proposals}) == len(result.proposals)
    # Locators are logical, never Elementor element ids.
    assert not [p for p in result.proposals if "elementor-element-" in p.evidence.locator]
    as_dict = result.as_dict()
    assert as_dict["writes_catalogue"] is False and as_dict["writes_candidate_claims"] is False
    assert as_dict["proposals"][0]["observation"]["fetched_page_id"] == "fp-1"
    json.dumps(as_dict)   # serializable as-is


def test_no_proposal_is_ever_verified():
    for p in run().proposals:
        assert p.claim_status == "NOT_VERIFIED" and p.confidence != "VERIFIED"


# ------------------------------------------------------ 4. nothing is written --


def test_the_module_imports_no_database_or_orm_and_does_no_io():
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = [m for m in imported if m.startswith(("sqlalchemy", "app.db", "app.models",
                                                      "httpx", "requests", "socket", "os",
                                                      "pathlib", "subprocess"))]
    assert forbidden == []
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)}
    assert not calls & {"open", "exec", "eval", "compile", "__import__"}
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                and n.attr in ("add", "flush", "commit", "execute", "write_text", "write_bytes")]


def test_the_live_adapter_is_untouched_and_the_proposals_are_not_wired_in():
    assert CONFIG.version == "0.3.0"
    assert CONFIG.product_extractor is extract_neura_product
    assert set(ADAPTERS) == {"neura-robotics-official", "xpeng-official"}   # + XPENG, 2026-10-03
    assert ADAPTERS["neura-robotics-official"] is CONFIG
    # The production path still extracts identity only: no claim, signal or image.
    identity = extract_neura_product(CONFIG, PAGE.encode("utf-8"), MINI_URL)
    assert (identity.claims, identity.signals, identity.images) == ((), (), ())
    assert "propose" not in Path(mod.__file__).with_name("neura_robotics.py").read_text(
        encoding="utf-8")


def test_running_it_changes_no_database_row(database_url):
    models = (Robot, RobotVariant, EvidenceSource, DiscoveryCandidate, CandidateClaim,
              CandidateCommercialSignal)

    def counts():
        with engine.connect() as conn:
            return [conn.scalar(select(func.count()).select_from(m)) for m in models]

    before = counts()
    result = run()
    render(result)
    assert result.status == PROPOSED and counts() == before


# ----------------------------------------------- 5. deterministic / idempotent --


def test_repeated_extraction_is_identical():
    first, second = run(), run()
    assert first == second and first.digest == second.digest
    assert json.dumps(first.as_dict(), sort_keys=True) == json.dumps(
        second.as_dict(), sort_keys=True)
    assert render(first) == render(second)
    assert [p.digest for p in first.proposals] == [p.digest for p in second.proposals]
    assert render(first).splitlines()[2].startswith("PROPOSALS ONLY")


def test_the_observation_never_changes_a_proposals_identity():
    a = run(observation=ObservationRef("fp-1", "run-1", "2026-10-02T08:54:00+00:00", "h1"))
    b = run(observation=ObservationRef("fp-2", "run-2", "2026-10-05T06:40:00+00:00", "h2"))
    assert a.digest == b.digest
    assert [p.digest for p in a.proposals] == [p.digest for p in b.proposals]
    assert a.proposals[0].observation != b.proposals[0].observation


# ----------------------------------- 6. navigation/footer cannot create claims --


def test_navigation_and_footer_changes_do_not_change_or_create_claims():
    baseline = run()
    changed = PAGE
    for old, new in (("Healthcare", "Medical"), ("NEURA Group", "Company Newsletter Blog"),
                     ("MAiRA</a>", "MAiRA S</a> <a href=\"/products/maira-l/\">MAiRA L</a>"),
                     ("News</a>", "Press and 19,999 € offers</a>")):
        assert old in changed
        changed = changed.replace(old, new, 1)
    result = run(changed)
    assert result.digest == baseline.digest and result.proposals == baseline.proposals
    assert not [p for p in result.proposals if "Press and" in p.value or "Medical" in p.value]


def test_the_real_2_october_style_change_creates_no_product_claim():
    # Menu/footer labels switched language and order, as on the real 2026-10-02 change.
    changed = PAGE.replace("Healthcare", "Medical").replace(
        "<span>NEURA Group</span>", "<span>Unternehmen</span> <span>Newsletter</span>")
    assert changed != PAGE and run(changed).digest == run().digest


def test_a_real_content_change_is_noticed():
    changed = replace_cell(PAGE, "29,999 € (excluding taxes and shipping)",
                           "27,999 € (excluding taxes and shipping)")
    after = run(changed)
    assert dict(by(after, "PRICE_ESTIMATE", "Pro").structured)["amount"] == "27999.00"
    assert after.digest != run().digest
    assert by(after, "PRICE_ESTIMATE", "Standard").digest == by(
        run(), "PRICE_ESTIMATE", "Standard").digest


# ------------------------------------------- 7. malformed / missing fails safe --


def _assert_no_unsafe(result):
    """No proposal may carry a row label as a value, or a value shifted into another row."""
    labels = set(mod._KNOWN_LABELS) | set(mod._HEADER)
    assert not [p for p in result.proposals if p.kind != "VARIANT" and p.value in labels]


def test_missing_or_reordered_header_proposes_nothing():
    swapped = PAGE.replace("<h4><strong>Standard</strong></h4>", "<h4><strong>TMP</strong></h4>"
                           ).replace("<h4><strong>Pro</strong></h4>",
                                     "<h4><strong>Standard</strong></h4>").replace(
        "<h4><strong>TMP</strong></h4>", "<h4><strong>Pro</strong></h4>")
    assert swapped != PAGE
    for page in (swapped, PAGE.replace("<h4><strong>Feature</strong></h4>", "")):
        result = run(page)
        assert result.status == AMBIGUOUS and result.proposals == ()
        assert "column meaning not assumed" in " ".join(result.notes)


def test_a_third_edition_or_renamed_column_is_not_guessed():
    renamed = PAGE.replace("<h4><strong>Pro</strong></h4>", "<h4><strong>Pro Max</strong></h4>")
    assert renamed != PAGE
    result = run(renamed)
    assert result.status == AMBIGUOUS and result.proposals == ()


def test_no_grid_and_duplicate_grids_are_not_guessed():
    no_grid = PAGE.replace("feature-grid-cs-3", "something-else")
    assert (run(no_grid).status, run(no_grid).proposals) == (NO_PROPOSALS, ())
    start = PAGE.index('<div class="elementor-element')
    grid_end = PAGE.index("A reservation fee secures")
    doubled = PAGE[:grid_end] + PAGE[start:grid_end] + PAGE[grid_end:]
    result = run(doubled)
    assert result.status == AMBIGUOUS and result.proposals == ()


def test_a_missing_cell_never_shifts_values_into_the_wrong_row():
    # Drop the Pro "Full connection" cell: every later cell is now one position early.
    page = drop_cell(PAGE, "Full connection", nth=1)
    result = run(page)
    _assert_no_unsafe(result)
    assert any("misaligned" in why or "unknown row label" in why for _, why in result.rejected)
    # Rows before the break are still proposed; nothing after it is.
    assert result.of_kind("SPECIFICATION")
    assert not result.of_kind("PRICE_ESTIMATE") and not result.of_kind("RESERVATION_FEE")
    assert not [p for p in result.of_kind("INTERFACES")]


def test_an_unknown_row_label_stops_the_grid_instead_of_continuing():
    page = replace_cell(PAGE, "Common interfaces", "Battery life")
    result = run(page)
    assert any("unknown row label" in why for _, why in result.rejected)
    assert not result.of_kind("INTERFACES") and not result.of_kind("PRICE_ESTIMATE")
    assert result.of_kind("SPECIFICATION")


@pytest.mark.parametrize("cell", [
    "19.999,00 € (excluding taxes and shipping)", "TBD", "19,999 €",
    "19,999 € (including taxes)", "from 19,999 € (excluding taxes and shipping)",
    "19,99 € (excluding taxes and shipping)", "$19,999 (excluding taxes and shipping)",
    "19,999 USD (excluding taxes and shipping)",
])
def test_a_malformed_price_produces_no_price_proposal_for_that_edition(cell):
    page = replace_cell(PAGE, "19,999 € (excluding taxes and shipping)", cell)
    result = run(page)
    assert not [p for p in result.of_kind("PRICE_ESTIMATE") if p.edition == "Standard"]
    assert by(result, "PRICE_ESTIMATE", "Pro")      # the other column is unaffected
    assert any(item.startswith("Estimated price / Standard") for item, _ in result.rejected)


@pytest.mark.parametrize("cell", ["100 USD", "€100", "about 100€", "100.50€", "free"])
def test_a_malformed_reservation_fee_is_rejected(cell):
    result = run(replace_cell(PAGE, "100€", cell))
    assert not [p for p in result.of_kind("RESERVATION_FEE") if p.edition == "Standard"]
    assert by(result, "RESERVATION_FEE", "Pro")


@pytest.mark.parametrize("sentence", [
    "Only 4NE1 Mini Pro is expected to be available in 2026.",
    "Both 4NE1 Mini Standard and 4NE1 Mini Pro are expected to be available soon.",
    "Both 4NE1 Mini Standard and 4NE1 Mini Pro are available now.",
])
def test_an_availability_sentence_that_differs_proposes_no_availability(sentence):
    old = "Both 4NE1 Mini Standard and 4NE1 Mini Pro are expected to be available in 2026."
    assert old in PAGE
    result = run(PAGE.replace(old, sentence))
    assert not result.of_kind("AVAILABILITY")
    assert ("availability year", "expected sentence not found verbatim") in result.rejected
    assert result.of_kind("PRICE_ESTIMATE")


def test_reservation_terms_and_caveat_are_only_proposed_when_present_verbatim():
    page = PAGE.replace("This fee is fully refundable", "This fee may be refundable")
    result = run(page)
    assert not result.of_kind("RESERVATION_TERMS")
    assert ("reservation terms", "expected sentences not found verbatim") in result.rejected
    no_caveat = run(PAGE.replace("we may introduce refinements", "we will not change"))
    assert not no_caveat.of_kind("DESIGN_CAVEAT")


def test_a_datasheet_link_that_is_not_https_is_rejected():
    page = PAGE.replace("https://neurarobotics.px.media/plk/Jj/4NE1Minidatasheet.pdf",
                        "javascript:alert(1)")
    result = run(page)
    assert not result.of_kind("DATASHEET_REFERENCE")
    assert ("datasheet link", "href is missing or not an https URL") in result.rejected


@pytest.mark.parametrize("mutation", [
    lambda p: p.replace("Reserve 4NE1 Mini:", "Reserve 4NE1 Max:"),
    lambda p: p.replace("single-product", "archive"),
    # No title, og:title or breadcrumb left: the URL slug alone is not an identity.
    lambda p: re.sub(r"<title>.*?</title>|<meta property=\"og:title\"[^>]*>|"
                     r"<script type=\"application/ld\+json\".*?</script>", "", p, flags=re.S),
])
def test_if_the_identity_is_not_confirmed_nothing_is_proposed(mutation):
    page = mutation(PAGE)
    assert page != PAGE
    result = run(page)
    assert result.status in (NO_PROPOSALS, AMBIGUOUS) and result.proposals == ()
    assert "identity not confirmed" in " ".join(result.notes)


@pytest.mark.parametrize("body", [
    b"", b"   ", b"<html>", b"\xff\xfe\x00garbage", b"<html><body><div class='"
    b"feature-grid-cs-3'><div", b"plain text, no markup", PAGE.encode("utf-8")[:2000],
    PAGE.encode("utf-8")[:9000],
])
def test_garbage_or_truncated_bytes_fail_safely(body):
    result = run(body)
    assert result.proposals == () or result.status == PROPOSED
    if result.status != PROPOSED:
        assert result.proposals == ()
    _assert_no_unsafe(result)


def test_a_truncated_page_keeps_only_what_it_still_proves():
    cut = PAGE[:PAGE.index("Estimated price")]     # the grid ends mid-way, before the price row
    result = run(cut)
    assert not result.of_kind("PRICE_ESTIMATE") and not result.of_kind("RESERVATION_FEE")
    _assert_no_unsafe(result)
