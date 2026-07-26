"""`robot_image` — MEDIA-01 verified product imagery (mirror of db/schema.sql).

The single image-truth system for a named robot. The DDL is canonical; this
model mirrors it and never generates DDL. `robot.hero_image_url` is dormant and
is NOT the read path.

The one place the display-eligibility rule lives is `is_display_eligible` —
**exactly one implementation** (WS8.3 / R11 removed a duplicate SQL form that no
query used; two copies of a governed gate can only diverge, and the second copy
already lacked the attribution rule below). FOUR dimensions, never collapsed:
  - identity_status: does it depict THIS exact robot;
  - rights_status: legal/licensing EVIDENCE for reuse;
  - usage_basis: platform display POLICY (why we display absent a formal license).
  - attribution: present whenever ATTRIBUTION_REQUIRED is the basis of display.
An image is shown ONLY when identity VERIFIED AND rights_status != RESTRICTED AND
(rights_status PERMITTED/ATTRIBUTION_REQUIRED OR usage_basis
OFFICIAL_MANUFACTURER_MEDIA) AND, where the basis is ATTRIBUTION_REQUIRED, an
attribution string exists. A non-NULL image_url is NEVER sufficient; RESTRICTED
always blocks; UNKNOWN rights never behaves like PERMITTED (MEDIA-01.5, §H2).
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
# Usage-policy bases that permit display absent a formal license.
DISPLAYABLE_USAGE = ("OFFICIAL_MANUFACTURER_MEDIA",)


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

        WS8.3 / R11 (gap Q14): where ATTRIBUTION_REQUIRED is what makes the
        image displayable, a missing attribution makes it **ineligible**. The
        schema documented the requirement in a comment and enforced nothing, so
        such an image rendered with no credit at all — a live rights exposure,
        not a latent one. Enforced here rather than by DDL so no migration is
        needed and L7's database-enforcement clause is not engaged.
        """
        if self.identity_status != "VERIFIED":
            return False
        if self.rights_status == "RESTRICTED":
            return False

        has_rights_basis = self.rights_status in DISPLAYABLE_RIGHTS
        has_usage_basis = self.usage_basis in DISPLAYABLE_USAGE
        if not (has_rights_basis or has_usage_basis):
            return False

        # If the ONLY thing permitting display is "attribution required", the
        # attribution has to exist. An official-manufacturer-media basis stands
        # on its own and does not depend on a credit line.
        if self.rights_status == "ATTRIBUTION_REQUIRED" and not has_usage_basis:
            return bool((self.attribution or "").strip())
        return True
