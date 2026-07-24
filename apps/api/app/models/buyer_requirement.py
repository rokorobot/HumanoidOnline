"""`buyer_requirement` — the permanent Phase-2 buyer-intent object (mirror of
db/schema.sql, SECTION 4).

WS5 writes this table (the platform's first write path). Matching (`match_result`)
and lead capture (`commercial_lead`) are later workstreams and are intentionally
absent. The DDL is frozen — this model mirrors it and never generates DDL.

Data laws honoured by the write path (see the router), reflected in the column
types here:
  - `manipulation_required` is a real tri-state BOOLEAN | NULL — a known FALSE is
    a genuine answer and must persist as FALSE (never dropped by truthiness).
  - `budget_currency` has a DB DEFAULT 'USD'; on a no-budget requirement the
    router writes NULL explicitly so the default never manufactures a currency.
  - `raw_input` (JSONB) preserves the full versioned wizard answers, including the
    UNKNOWN vs SKIPPED distinction that the nullable structured columns cannot.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, Boolean, Date, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import autonomy_level, buyer_type, transaction_preference


class BuyerRequirement(Base):
    __tablename__ = "buyer_requirement"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    # who (light-touch; anonymous in WS5 — the wizard collects no contact fields)
    buyer_type: Mapped[str] = mapped_column(
        buyer_type, nullable=False, server_default=text("'UNKNOWN'")
    )
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    country_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )

    # what they need the robot to do
    use_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("use_case.id", ondelete="SET NULL")
    )
    industry: Mapped[str | None] = mapped_column(Text)
    task_description: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)

    # structured requirements (nullable — ANSWERED -> value, UNKNOWN/SKIPPED -> NULL)
    payload_min_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    operating_hours_day: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    manipulation_required: Mapped[bool | None] = mapped_column(Boolean)
    autonomy_required: Mapped[str | None] = mapped_column(autonomy_level)
    # NOTE: the DDL column carries DEFAULT 'USD', but the ORM model deliberately
    # omits server_default here. With a server_default, SQLAlchemy treats a
    # Python None as "unset" and lets the DB default fire — which would fabricate
    # a 'USD' currency on a no-budget requirement. Omitting it means the router's
    # explicit None is written as SQL NULL (UNKNOWN != a defaulted 0/USD).
    budget_currency: Mapped[str | None] = mapped_column(CHAR(3))
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    required_by: Mapped[date | None] = mapped_column(Date)

    # transaction preference captured now, before Rent/Buy/Lease launch
    preferred_transaction: Mapped[str] = mapped_column(
        transaction_preference, nullable=False, server_default=text("'UNKNOWN'")
    )

    raw_input: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BuyerRequirement id={self.id!r} use_case_id={self.use_case_id!r}>"
