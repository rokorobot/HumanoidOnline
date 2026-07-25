"""Deterministic identity resolution (DATA-D1.6 / DATA-D1.7 / §25-C).

v0.1 matching is DETERMINISTIC — no LLM, no randomness (frozen data law). It
resolves a candidate against canonical robots/manufacturers and other candidates,
and it REFUSES to guess: ambiguity blocks promotion (identity_status stays
AMBIGUOUS / POSSIBLE_DUPLICATE, never MATCHED_EXISTING). An LLM may, in a later
separately-ratified iteration, *propose* a match for human confirmation — it may
never auto-merge identities.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot

# Corporate / generic tokens that carry no model identity.
_GENERIC = {
    "robotics", "robot", "robots", "humanoid", "humanoids", "inc", "ltd", "llc",
    "corp", "corporation", "co", "company", "the", "ai", "technologies",
    "technology", "tech", "dynamics", "labs", "lab", "group",
}


def normalize(value: str | None) -> str:
    if not value:
        return ""
    lowered = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(t for t in lowered.split() if t and t not in _GENERIC)


def _model_key(name: str | None, mfr_key: str) -> str:
    """The model-distinguishing tokens: the normalized name minus manufacturer
    tokens (so 'Unitree Robotics G1' under 'Unitree Robotics' -> 'g1')."""
    mfr_tokens = set(mfr_key.split())
    return " ".join(t for t in normalize(name).split() if t not in mfr_tokens)


def resolve_identity(session: Session, candidate: DiscoveryCandidate) -> str:
    """Set `candidate.identity_status` (+ possible_* links) and return it.

    Reads canonical only; never writes canonical (Gate H).
    """
    mfr_key = normalize(candidate.candidate_manufacturer)
    model_key = _model_key(candidate.candidate_name, mfr_key)

    # Resolve a possible canonical manufacturer (a lead, not a promotion).
    manufacturers = session.execute(select(Manufacturer)).scalars().all()
    mfr_match = next((m for m in manufacturers if normalize(m.name) == mfr_key and mfr_key), None)
    candidate.possible_manufacturer_id = mfr_match.id if mfr_match else None

    rows = session.execute(
        select(Robot, Manufacturer.name).join(
            Manufacturer, Manufacturer.id == Robot.manufacturer_id
        )
    ).all()

    # Exact model matches within the same (normalized) manufacturer.
    exact = [
        robot
        for robot, mfr_name in rows
        if model_key
        and normalize(mfr_name) == mfr_key
        and _model_key(robot.name, mfr_key) == model_key
    ]
    if len(exact) == 1:
        candidate.identity_status = "MATCHED_EXISTING"
        candidate.possible_robot_id = exact[0].id
        return candidate.identity_status
    if len(exact) > 1:
        candidate.identity_status = "AMBIGUOUS"
        candidate.possible_robot_id = None
        return candidate.identity_status

    # No exact model match. An underspecified name (empty model key) that could be
    # several models of a known manufacturer is AMBIGUOUS, not a new entity.
    if model_key == "":
        siblings = [robot for robot, mfr_name in rows if normalize(mfr_name) == mfr_key and mfr_key]
        candidate.identity_status = "AMBIGUOUS" if len(siblings) >= 2 else (
            "POSSIBLE_DUPLICATE" if len(siblings) == 1 else "AMBIGUOUS"
        )
        candidate.possible_robot_id = siblings[0].id if len(siblings) == 1 else None
        return candidate.identity_status

    # Distinct model, no canonical match: check for a duplicate among other
    # candidates before declaring a new entity (DATA-D1.7).
    others = session.execute(
        select(DiscoveryCandidate).where(DiscoveryCandidate.id != candidate.id)
    ).scalars().all()
    dup = any(
        normalize(o.candidate_manufacturer) == mfr_key
        and _model_key(o.candidate_name, mfr_key) == model_key
        for o in others
    )
    candidate.identity_status = "POSSIBLE_DUPLICATE" if dup else "NEW_ENTITY"
    candidate.possible_robot_id = None
    return candidate.identity_status
