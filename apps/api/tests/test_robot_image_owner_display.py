"""Owner-approved display and representative imagery (MEDIA-01, docs/09 §4).

MEDIA-01 could express two display decisions: a real licence on record, or the
policy of showing OFFICIAL manufacturer media whose licence is unknown. Two
facts about real assets fit neither, and the tempting workarounds are both lies:

* a DISTRIBUTOR's photograph is not official manufacturer media, and recording
  it as such — or inventing a `rights_status` licence — would assert something
  no source granted;
* an image of the product LINE is not an image of the exact edition, and the
  only way to display it before was to write `identity_status = VERIFIED`,
  claiming a verification nobody performed.

`OWNER_APPROVED_DISPLAY` + `is_representative` exist so both can be recorded
truthfully. These tests pin the honesty properties, not the happy path:

* the new basis never becomes evidence of a licence;
* RESTRICTED still blocks, exactly as for the older policy basis;
* a representative image is displayable ONLY with a caption, so an unlabelled
  stand-in can never read as a claim about the exact edition;
* the pre-existing eligibility matrix is unchanged.

No database: the gate is one pure method on the model.
"""
from __future__ import annotations

from app.models.robot_image import RobotImage


def image(**kwargs) -> RobotImage:
    """A RobotImage with the schema's defaults made explicit."""
    defaults = dict(
        image_url="/robots/example.png",
        source_url="https://example.invalid/product",
        source_name="Example Source",
        source_type="MANUFACTURER",
        image_type="FRONT",
        identity_status="VERIFIED",
        rights_status="UNKNOWN",
        usage_basis="NONE",
        is_official=False,
        is_primary=False,
        attribution=None,
        is_representative=False,
        representative_note=None,
        display_approved_by=None,
        display_approved_at=None,
    )
    defaults.update(kwargs)
    return RobotImage(**defaults)


# --- the new policy basis ----------------------------------------------------

def test_owner_approved_display_permits_display_without_any_licence():
    """The decision this exists for: a distributor asset nobody licensed, shown
    because the owner decided to show it — with rights_status still UNKNOWN."""
    img = image(
        source_type="DISTRIBUTOR",
        rights_status="UNKNOWN",
        usage_basis="OWNER_APPROVED_DISPLAY",
        display_approved_by="robert@humanoid.company",
    )
    assert img.is_display_eligible() is True
    # The row must not have acquired a licence along the way.
    assert img.rights_status == "UNKNOWN"


def test_owner_approval_does_not_override_restricted_rights():
    """A policy basis is not a licence, and never outranks known restriction."""
    img = image(rights_status="RESTRICTED", usage_basis="OWNER_APPROVED_DISPLAY")
    assert img.is_display_eligible() is False


def test_owner_approval_still_requires_a_credit_when_attribution_is_owed():
    """If a source DID impose attribution, the owner decision cannot waive it."""
    owed = image(
        rights_status="ATTRIBUTION_REQUIRED",
        usage_basis="OWNER_APPROVED_DISPLAY",
        attribution=None,
    )
    assert owed.is_display_eligible() is False
    credited = image(
        rights_status="ATTRIBUTION_REQUIRED",
        usage_basis="OWNER_APPROVED_DISPLAY",
        attribution="© Example Source",
    )
    assert credited.is_display_eligible() is True


# --- representative imagery --------------------------------------------------

def test_representative_image_displays_without_claiming_exact_identity():
    """The point of the designation: shown, captioned, and still UNVERIFIED."""
    img = image(
        identity_status="UNVERIFIED",
        usage_basis="OWNER_APPROVED_DISPLAY",
        is_representative=True,
        representative_note="H2 chassis shown; EDU package may vary.",
    )
    assert img.is_display_eligible() is True
    assert img.identity_status == "UNVERIFIED", "identity must not be upgraded"


def test_representative_image_without_a_caption_is_ineligible():
    """An unlabelled stand-in is indistinguishable from a claim about the exact
    edition, so absence of the caption must block display — not soften it."""
    for note in (None, "", "   "):
        img = image(
            identity_status="UNVERIFIED",
            usage_basis="OWNER_APPROVED_DISPLAY",
            is_representative=True,
            representative_note=note,
        )
        assert img.is_display_eligible() is False, note


def test_a_verified_representative_image_still_needs_its_caption():
    """The caption obligation attaches to the designation, not to the identity
    state: even a verified asset flagged representative must say so."""
    img = image(
        identity_status="VERIFIED",
        usage_basis="OFFICIAL_MANUFACTURER_MEDIA",
        is_representative=True,
        representative_note=None,
    )
    assert img.is_display_eligible() is False


def test_unverified_identity_is_not_displayable_without_the_designation():
    """The representative path is the ONLY relaxation of the identity gate; a
    plain UNVERIFIED image stays hidden however it is approved."""
    img = image(identity_status="UNVERIFIED", usage_basis="OWNER_APPROVED_DISPLAY")
    assert img.is_display_eligible() is False
    img2 = image(identity_status="UNVERIFIED", usage_basis="OFFICIAL_MANUFACTURER_MEDIA")
    assert img2.is_display_eligible() is False


def test_representative_flag_alone_does_not_unlock_display():
    """Without the owner approval, a representative row is still ineligible —
    the designation is a label, not a basis."""
    img = image(
        identity_status="UNVERIFIED",
        usage_basis="NONE",
        is_representative=True,
        representative_note="T2 chassis shown; equipment varies by edition.",
    )
    assert img.is_display_eligible() is False


# --- the pre-existing matrix must be untouched -------------------------------

def test_existing_eligibility_matrix_is_unchanged():
    """Every case MEDIA-01 already decided, decided the same way."""
    matrix = [
        ("VERIFIED", "PERMITTED", "NONE", True),
        ("VERIFIED", "ATTRIBUTION_REQUIRED", "NONE", False),  # no credit line -> blocked
        ("VERIFIED", "UNKNOWN", "NONE", False),
        ("VERIFIED", "RESTRICTED", "NONE", False),
        ("UNVERIFIED", "PERMITTED", "NONE", False),
        ("UNVERIFIED", "UNKNOWN", "NONE", False),
        ("VERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", True),
        ("VERIFIED", "RESTRICTED", "OFFICIAL_MANUFACTURER_MEDIA", False),
        ("UNVERIFIED", "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", False),
    ]
    for identity, rights, usage, expected in matrix:
        img = image(identity_status=identity, rights_status=rights, usage_basis=usage)
        assert img.is_display_eligible() is expected, (identity, rights, usage)
