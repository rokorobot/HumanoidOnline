"""`robot_image` — MEDIA-01 verified product imagery (mirror of db/schema.sql).

The single image-truth system for a named robot. The DDL is canonical; this
model mirrors it and never generates DDL. `robot.hero_image_url` is dormant and
is NOT the read path.

The one place the display-eligibility rule lives is `is_display_eligible` /
`DISPLAY_ELIGIBLE_CLAUSE`. THREE independent dimensions, never collapsed:
  - identity_status: does it depict THIS exact robot;
  - rights_status: legal/licensing EVIDENCE for reuse;
  - usage_basis: platform display POLICY (why we display absent a formal license).
An image is shown ONLY when identity VERIFIED AND rights_status != RESTRICTED AND
(rights_status PERMITTED/ATTRIBUTION_REQUIRED OR usage_basis
OFFICIAL_MANUFACTURER_MEDIA). A non-NULL image_url is NEVER sufficient; RESTRICTED
always blocks; UNKNOWN rights never behaves like PERMITTED (MEDIA-01.5, §H2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Text, and_, or_, text
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
        policy (usage_basis OFFICIAL_MANUFACTURER_MEDIA) is required."""
        if self.identity_status != "VERIFIED":
            return False
        if self.rights_status == "RESTRICTED":
            return False
        return (
            self.rights_status in DISPLAYABLE_RIGHTS
            or self.usage_basis in DISPLAYABLE_USAGE
        )


# SQL form of the same gate, for filtering in queries (identical semantics).
DISPLAY_ELIGIBLE_CLAUSE = and_(
    RobotImage.identity_status == "VERIFIED",
    RobotImage.rights_status != "RESTRICTED",
    or_(
        RobotImage.rights_status.in_(DISPLAYABLE_RIGHTS),
        RobotImage.usage_basis.in_(DISPLAYABLE_USAGE),
    ),
)
