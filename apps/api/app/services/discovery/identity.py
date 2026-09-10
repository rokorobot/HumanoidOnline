"""Deterministic identity resolution (DATA-D1.6 / DATA-D1.7 / §25-C).

v0.1 matching is DETERMINISTIC — no LLM, no randomness (frozen data law). It
resolves a candidate against canonical robots/manufacturers and other candidates,
and it REFUSES to guess: ambiguity blocks promotion (identity_status stays
AMBIGUOUS / POSSIBLE_DUPLICATE, never MATCHED_EXISTING). An LLM may, in a later
separately-ratified iteration, *propose* a match for human confirmation — it may
never auto-merge identities.

A canonical robot matches on its own name or on a *confirmed* alias from the
committed register (`db/discovery/identity_aliases.json`) — DATA-D1.7's "known
aliases". Both are EXACT normalized equality; an alias widens which names a
record answers to, never how closely a name must match. Without it, a record
renamed or qualified by the product owner ("G1" -> "G1 Basic") is reported as
NEW_ENTITY — a promotable verdict for a robot that is already catalogued.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TypeVar

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

ALIASES_PATH = (
    Path(__file__).resolve().parents[5] / "db" / "discovery" / "identity_aliases.json"
)
_ALIAS_FIELDS = frozenset(
    {"robot_slug", "alias", "basis", "proposed_at", "confirmed_by", "confirmed_at"}
)

K = TypeVar("K")


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


def load_confirmed_aliases(path: Path = ALIASES_PATH) -> dict[str, tuple[str, ...]]:
    """Robot slug -> the aliases a human has confirmed for it.

    An entry with null `confirmed_by`/`confirmed_at` is a proposal and is ignored
    (docs/16 §11: aliases are proposals, not merges). The shape is checked
    fail-closed: a malformed register raises rather than quietly matching less,
    because a missed match is exactly how a duplicate NEW_ENTITY is born.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc.get("aliases") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path.name}: expected an object with an 'aliases' list")
    confirmed: dict[str, list[str]] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != _ALIAS_FIELDS:
            raise ValueError(f"{path.name}: entry {i} must carry exactly {sorted(_ALIAS_FIELDS)}")
        for field in ("robot_slug", "alias"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ValueError(f"{path.name}: entry {i} has an empty {field}")
        by, at = entry["confirmed_by"], entry["confirmed_at"]
        if by is None and at is None:
            continue
        if not (isinstance(by, str) and by.strip() and isinstance(at, str)):
            raise ValueError(
                f"{path.name}: entry {i} is half-confirmed; set both confirmed_by and "
                "confirmed_at, or neither"
            )
        date.fromisoformat(at)  # raises ValueError on a malformed date
        confirmed.setdefault(entry["robot_slug"], []).append(entry["alias"])
    return {slug: tuple(aliases) for slug, aliases in confirmed.items()}


def canonical_matches(
    mfr_key: str,
    model_key: str,
    canonical: Iterable[tuple[K, str, str | None, str | None]],
    aliases: Mapping[str, Sequence[str]],
) -> list[K]:
    """Exact model matches within the same (normalized) manufacturer.

    `canonical` rows are `(key, robot_slug, robot_name, manufacturer_name)`. A
    robot matches on its own name or on one of its confirmed aliases, both by
    EXACT model-key equality — so "G1" still does not reach "G1 EDU" and "H1"
    still does not reach "H1-2" (DATA-D1.6).
    """
    if not model_key:
        return []
    return [
        key
        for key, slug, name, mfr_name in canonical
        if normalize(mfr_name) == mfr_key
        and any(_model_key(n, mfr_key) == model_key for n in (name, *aliases.get(slug, ())))
    ]


def resolve_identity(
    session: Session,
    candidate: DiscoveryCandidate,
    *,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Set `candidate.identity_status` (+ possible_* links) and return it.

    Reads canonical only; never writes canonical (Gate H). `aliases` defaults to
    the confirmed entries of the committed register.
    """
    if aliases is None:
        aliases = load_confirmed_aliases()
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

    exact = canonical_matches(
        mfr_key, model_key,
        ((robot, robot.slug, robot.name, mfr_name) for robot, mfr_name in rows),
        aliases,
    )
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
