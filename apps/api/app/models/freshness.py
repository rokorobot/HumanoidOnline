"""DATA-D1 Scheduled Freshness — docs/22_DATA_D1_SCHEDULED_FRESHNESS_
IMPLEMENTATION_CONTRACT.md, RATIFIED v0.1 (amends docs/16 LIVE.4 per
docs/21_DATA_D1_LIVE_AMENDMENT_A2_SCHEDULED_FRESHNESS.md, RATIFIED v0.1).

Mirror of db/schema.sql / db/migrations/0010_add_freshness_layer.sql. The DDL
is canonical (AGENTS.md rule 2); these models mirror it and never generate DDL.

FOUNDATION SLICE: this is bookkeeping only. No adapter, no HTTP client, no
scheduler exists because of this module, and nothing here can perform a
fetch. AUTO_CHECK target count is, and must remain, zero until a later,
separately-gated slice performs DATA-D1.9 eligibility reviews and registers
targets (docs/22 Phase 10).

Structural isolation (DATA-D1.10 / Gate K), preserved exactly as the rest of
the discovery layer: `FreshnessTarget.robot_id` and
`FreshnessTarget.discovery_source_id` point OUT to canonical/discovery;
`FreshnessObservation.discovery_candidate_id` points OUT to
`discovery_candidate`. Nothing in `robot` or `discovery_candidate` points back
— neither gains a column because of this module (docs/22 Phase 2, correction
2 in the ratified contract).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    freshness_execution_mode,
    freshness_fact_area,
    freshness_result,
    freshness_trigger,
)

#: DATA-D1 Scheduled Freshness Amendment A2 §2 — the ratified weekly ceiling.
#: A `CHECK (interval_days >= 7)` makes loosening it a schema change, not a
#: config flag (mirrors LIVE.4's own "visible schema change" principle).
FRESHNESS_INTERVAL_DAYS_DEFAULT = 7


class FreshnessTarget(Base):
    """One exact URL, registered for one canonical robot, re-checked on a
    schedule. Stores **durable intent/config only** — `active`,
    `manual_override`, `purpose`, `interval_days`, plus factual
    history-cache fields (`last_checked_at`, `last_result`, `etag`,
    `last_modified`, `content_fingerprint`, `last_change_detected_at`).

    Deliberately carries **no `execution_mode` column** (docs/22 Phase 3,
    correction 3): what a target's mode currently is depends on its
    `DiscoverySource`'s eligibility, which can change without this row ever
    being written to. Persisting a verdict here would let it silently go
    stale. Effective mode is always computed fresh — see
    `app.services.freshness.eligibility.compute_execution_mode`.
    """

    __tablename__ = "freshness_target"
    __table_args__ = (
        CheckConstraint("interval_days >= 7", name="ck_freshness_target_interval"),
        UniqueConstraint("robot_id", "url", name="uq_freshness_target_robot_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    discovery_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(freshness_fact_area, nullable=False)
    #: Durable config, human-set at registration. Forces MANUAL_CHECK
    #: unconditionally — eligibility is never even consulted. This is how the
    #: robotshop.com / eu.robotshop.com operational rule is enforced
    #: (docs/22 Phase 10) — it is not a DB constraint keyed on the URL,
    #: because that would be brittle; it is a human decision at registration.
    manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text(str(FRESHNESS_INTERVAL_DAYS_DEFAULT))
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[str | None] = mapped_column(freshness_result)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    content_fingerprint: Mapped[str | None] = mapped_column(Text)
    last_change_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    observations: Mapped[list[FreshnessObservation]] = relationship(
        "FreshnessObservation",
        back_populates="target",
        cascade="all, delete-orphan",
        order_by="FreshnessObservation.checked_at.desc()",
        # No lazy="selectin": a target's observation history can grow
        # unboundedly over months/years, and nothing in the due-target
        # scheduler query needs it eagerly loaded. Callers that need history
        # (the manual queue report, an audit lookup) query it explicitly.
    )


class FreshnessObservation(Base):
    """One check attempt (manual or scheduled) against one `FreshnessTarget`.

    Append-only by convention (application-level for v0.1 — same honest scope
    as `PromotionAudit`'s ORM enforcement: this stops `session.*`, not raw
    SQL). Carries the **only** stored copy of `execution_mode_at_check` — an
    immutable, observation-time snapshot of what
    `compute_execution_mode()` returned at the instant this attempt ran
    (docs/22 Phase 3, correction 3). `discovery_candidate_id` is the explicit
    observation -> governed-work lineage FK (docs/22 Phase 2/6, correction
    2) — set only when this observation created or reused a `RECHECK_REQUIRED`
    `DiscoveryCandidate`; `discovery_candidate` itself gains no column.
    """

    __tablename__ = "freshness_observation"
    __table_args__ = (
        CheckConstraint(
            "error_detail IS NULL OR char_length(error_detail) <= 1000",
            name="ck_freshness_observation_error_detail_len",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    freshness_target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("freshness_target.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(freshness_trigger, nullable=False)
    execution_mode_at_check: Mapped[str] = mapped_column(
        freshness_execution_mode, nullable=False
    )
    result: Mapped[str] = mapped_column(freshness_result, nullable=False)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    content_fingerprint: Mapped[str | None] = mapped_column(Text)
    detected_change_type: Mapped[str | None] = mapped_column(freshness_fact_area)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_detail: Mapped[str | None] = mapped_column(Text)
    discovery_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_candidate.id", ondelete="SET NULL"),
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    target: Mapped[FreshnessTarget] = relationship(
        "FreshnessTarget", back_populates="observations"
    )
