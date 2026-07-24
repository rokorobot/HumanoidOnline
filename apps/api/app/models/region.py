"""`region` — hierarchical geography (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The enum type already exists (created by db/schema.sql). create_type=False so
# the ORM never CREATEs/DROPs it — the canonical schema owns it.
region_type_enum = ENUM(
    "GLOBAL",
    "CONTINENT",
    "ECONOMIC_ZONE",
    "COUNTRY",
    "SUBREGION",
    name="region_type",
    schema="humanoid",
    create_type=False,
)


class Region(Base):
    __tablename__ = "region"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("region.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(region_type_enum, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    iso_country: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Region code={self.code!r} type={self.type!r}>"
