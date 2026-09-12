"""`robot_image` — MEDIA-01 verified product imagery (mirror of db/schema.sql).

The single image-truth system for a named robot. The DDL is canonical; this
model mirrors it and never generates DDL. `robot.hero_image_url` is dormant and
is NOT the read path.

The one place the display-eligibility rule lives is `is_display_eligible` —
**exactly one implementation** (WS8.3 / R11 removed a duplicate SQL form that no
query used; two copies of a governed gate can only diverge, and the second copy
already lacked the attribution rule below). THREE independent dimensions, never
collapsed:
  - identity_status: does it depict THIS exact robot;
  - rights_status: legal/licensing EVIDENCE for reuse;
  - usage_basis: platform display POLICY (why we display absent a formal license).

`usage_basis` has two policy bases. OFFICIAL_MANUFACTURER_MEDIA covers official
manufacturer product media. OWNER_APPROVED_DISPLAY covers an explicit owner
decision to display an asset — including distributor-sourced photography —
where no source granted anything. Neither is evidence of a licence, so
`rights_status` stays UNKNOWN and RESTRICTED still blocks.

A REPRESENTATIVE image (`is_representative`) depicts the product line/chassis
rather than the exact edition. It keeps `identity_status = UNVERIFIED` and is
displayable only under OWNER_APPROVED_DISPLAY with a `representative_note`
caption, so the reader is told what is actually shown.
`attribution` is NOT a fourth dimension — it is the credit OBLIGATION attached to
the `ATTRIBUTION_REQUIRED` rights state (schema: "required credit line when
ATTRIBUTION_REQUIRED"). An image is shown ONLY when identity VERIFIED AND
rights_status != RESTRICTED AND (rights_status PERMITTED/ATTRIBUTION_REQUIRED OR
usage_basis OFFICIAL_MANUFACTURER_MEDIA) AND, whenever rights_status is
ATTRIBUTION_REQUIRED, a credit line exists. A non-NULL image_url is NEVER
sufficient; RESTRICTED always blocks; UNKNOWN rights never behaves like PERMITTED
(MEDIA-01.5, §H2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    image_identity_status,
    image_rights_status,
    image_source_type,
    image_type,
    image_usage_basis,
)

# Rights values that on their own permit display (a real reuse basis on record).
DISPLAYABLE_RIGHTS = ("PERMITTED", "ATTRIBUTION_REQUIRED")
# Usage-policy bases that permit display absent a formal license. Both are
# DISPLAY POLICY, never evidence of a licence: `rights_status` stays whatever the
# evidence actually supports (usually UNKNOWN), and RESTRICTED still blocks.
DISPLAYABLE_USAGE = ("OFFICIAL_MANUFACTURER_MEDIA", "OWNER_APPROVED_DISPLAY")


class RobotImage(Base):
    __tablename__ = "robot_image"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(image_source_type, nullable=False)
    image_type: Mapped[str] = mapped_column(
        image_type, nullable=False, server_default=text("'FRONT'")
    )
    identity_status: Mapped[str] = mapped_column(
        image_identity_status, nullable=False, server_default=text("'UNVERIFIED'")
    )
    rights_status: Mapped[str] = mapped_column(
        image_rights_status, nullable=False, server_default=text("'UNKNOWN'")
    )
    usage_basis: Mapped[str] = mapped_column(
        image_usage_basis, nullable=False, server_default=text("'NONE'")
    )
    is_official: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    attribution: Mapped[str | None] = mapped_column(Text)
    # Representative imagery: depicts the product line/chassis, not this exact
    # edition. Such a row keeps identity_status = UNVERIFIED — the caption, not a
    # false identity value, is what makes it honest.
    is_representative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    representative_note: Mapped[str | None] = mapped_column(Text)
    # Who approved display absent a reuse licence, and when. Attribution of the
    # DECISION — never a grant of rights by the source.
    display_approved_by: Mapped[str | None] = mapped_column(Text)
    display_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[date | None] = mapped_column(Date)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="images")  # noqa: F821

    def is_display_eligible(self) -> bool:
        """MEDIA-01 display gate. The ONE rule — never `bool(image_url)`.

        Identity must be VERIFIED; RESTRICTED rights always block; otherwise a
        real reuse basis (PERMITTED/ATTRIBUTION_REQUIRED) OR an approved display
        policy (usage_basis OFFICIAL_MANUFACTURER_MEDIA) is required.

        WS8.3 / R11 (gap Q14): when `rights_status` is ATTRIBUTION_REQUIRED, a
        missing credit line makes the image **ineligible**. The schema
        documented the requirement in a comment and enforced nothing, so such an
        image rendered with no credit at all — a live rights exposure, not a
        latent one. Enforced here rather than by DDL, so no migration is needed
        and L7's database-enforcement clause is not engaged.

        The obligation holds **regardless of `usage_basis`**. `usage_basis` is a
        platform *display policy*; it is not a mechanism for overriding a known
        legal condition recorded in `rights_status`. Official manufacturer media
        whose licence is genuinely unknown is modelled as
        `rights_status=UNKNOWN` + `usage_basis=OFFICIAL_MANUFACTURER_MEDIA`
        precisely so that an attribution licence is never falsely asserted —
        so ATTRIBUTION_REQUIRED always means a credit is owed.
        """
        # Identity: normally VERIFIED. A REPRESENTATIVE image is the one
        # exception, and it is not a loophole: it is displayable only under an
        # explicit owner display approval AND only with a caption saying what is
        # actually shown, so identity uncertainty reaches the reader instead of
        # being silently upgraded to "this exact robot".
        if self.identity_status != "VERIFIED":
            if not (self.is_representative and self.usage_basis == "OWNER_APPROVED_DISPLAY"):
                return False
            if not (self.representative_note or "").strip():
                return False
        if self.rights_status == "RESTRICTED":
            return False

        has_rights_basis = self.rights_status in DISPLAYABLE_RIGHTS
        has_usage_basis = self.usage_basis in DISPLAYABLE_USAGE
        if not (has_rights_basis or has_usage_basis):
            return False

        # A representative image must always carry its caption, whatever its
        # identity or rights state — an unlabelled stand-in reads as a claim
        # about the exact edition.
        if self.is_representative and not (self.representative_note or "").strip():
            return False

        if self.rights_status == "ATTRIBUTION_REQUIRED":
            return bool((self.attribution or "").strip())
        return True
