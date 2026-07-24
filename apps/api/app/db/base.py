"""Declarative base for ORM models.

Every model maps to the canonical `humanoid` schema. Per AGENTS.md rule 2 and
02_ARCHITECTURE.md rule 1, `db/schema.sql` is the single source of truth: these
models *mirror* the DDL. We never call `create_all()` / autogenerate DDL, and PG
enums are declared with `create_type=False` so the ORM never owns them.
"""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(schema=get_settings().db_schema)
