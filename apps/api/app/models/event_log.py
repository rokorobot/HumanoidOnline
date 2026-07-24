"""`event_log` — lightweight product analytics (mirror of db/schema.sql).

`robot_id` / `requirement_id` are real foreign keys in the DDL, but the ORM
models them as plain columns here so WS1 need not pull in the (WS2) `robot` and
`buyer_requirement` tables. Referential integrity is enforced by the database.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    robot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
