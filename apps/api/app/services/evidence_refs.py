"""Governed evidence references — the opaque public address of a provenance row.

`docs/20` §7.1 requires that a fact carrying evidence be returned with an
`evidence_ref` that is opaque, deterministic, service-issued, authenticated, and
**never a raw or plaintext database identifier**. §7.1.1 requires a vetted
deterministic/misuse-resistant AEAD rather than an improvised construction.

**Primitive: AES-SIV** (RFC 5297), `cryptography.hazmat.primitives.ciphers.aead.AESSIV`.
Deterministic by design — identical plaintext under an identical key yields
identical ciphertext, which is what makes a reference stable — and authenticated,
so a reference this service did not issue does not decrypt. No nonce is supplied
or invented: SIV derives its synthetic IV from the plaintext itself, which is
precisely why a nonce-critical mode such as plain AES-GCM must never be pressed
into deterministic service here.

**A reference addresses one specific `evidence_source` row** (§7.1), not
`(subject_type, subject_id)` re-resolved at call time. Resolution is a bounded
primary-key lookup and never re-runs best-evidence selection, so ingesting newer
provenance cannot silently re-point a citation that has already been published.

**Publication is re-checked at resolve time** (§7.2). A reference proves issuance,
never continued eligibility: if the owning robot is unpublished afterwards, every
reference to its facts stops resolving.

Transport-independent: no FastAPI, no HTTP status, no agent error vocabulary.
The binding maps `ResolutionFailure.MALFORMED` → `INVALID_ARGUMENT` and
`ResolutionFailure.UNRESOLVED` → `NOT_FOUND` (§7.3). Every unresolved cause
collapses to one value here so no caller can tell an unknown row from an
unpublished subject from a retired key — that distinction would be a publication
and key-state oracle.

Reads only. Issuing and resolving perform no INSERT, UPDATE or DELETE, allocate
no sequence, and need no mapping table or migration.
"""
from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from enum import Enum

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
from app.models.evidence import EvidenceSource
from app.models.robot import Robot

#: Outer envelope marker. Bumped only if the envelope grammar itself changes.
#: Clients must not read it — it is documented here, not in the contract.
TOKEN_FORMAT = "er1"

#: Envelope separator; therefore forbidden inside a key id.
_SEPARATOR = "."

#: Inner payload version, inside the ciphertext. Distinct from the envelope
#: marker so the payload can evolve without changing the outer grammar.
_PAYLOAD_VERSION = 1

#: A raw UUID is 16 bytes; the payload is that plus one version byte.
_PAYLOAD_LEN = 17

#: AES-SIV prepends a 16-byte synthetic IV/tag, so anything shorter than this is
#: structurally impossible rather than merely unauthentic.
_MIN_CIPHERTEXT_LEN = 16 + _PAYLOAD_LEN

#: Domain separator, authenticated as associated data. It binds a token to *this*
#: protocol, so ciphertext issued here can never be replayed into some future use
#: of the same primitive and key. Constant by necessity: anything varying —
#: a timestamp, a nonce — would destroy the determinism §7.1 requires.
_ASSOCIATED_DATA = b"humanoidonline:evidence-ref:v1"

#: The only evidence classes v0.1 references can address (`docs/20` §7.2).
SUPPORTED_SUBJECT_TYPES = (
    "COMMERCIAL_STATUS",
    "PRICING_OFFER",
    "AVAILABILITY_OFFER",
    "DEPLOYMENT",
)

#: AES-SIV accepts 32/48/64 bytes; the contract recommends 512-bit. Required
#: exactly, because silently accepting a weaker key is the kind of downgrade
#: nobody notices.
KEY_BYTES = 64


class EvidenceRefKeyUnavailable(RuntimeError):
    """No usable evidence-reference key — the service fails closed.

    Never degraded into an unauthenticated token or a raw identifier: a missing
    key must stop the feature, not quietly weaken it.
    """


class ResolutionFailure(Enum):
    """Why a reference produced no evidence row.

    Exactly two values, because the contract exposes exactly two outcomes.
    `MALFORMED` means the outer envelope is not a reference of this format at
    all; `UNRESOLVED` covers every other cause — bad authentication, retired key,
    missing row, unsupported class, unpublished subject — deliberately
    indistinguishable (§7.3).
    """

    MALFORMED = "malformed"
    UNRESOLVED = "unresolved"


def _decode_key(material: str) -> bytes:
    """Decode one base64url key, or fail closed.

    Never truncates, pads, derives or otherwise repairs bad material.
    """
    try:
        raw = base64.urlsafe_b64decode(material.strip() + "=" * (-len(material.strip()) % 4))
    except (binascii.Error, ValueError) as exc:
        raise EvidenceRefKeyUnavailable("evidence-ref key is not valid base64url") from exc
    if len(raw) != KEY_BYTES:
        raise EvidenceRefKeyUnavailable(
            f"evidence-ref key must decode to exactly {KEY_BYTES} bytes; got {len(raw)}"
        )
    return raw


@dataclass(frozen=True)
class EvidenceRefKeyring:
    """The active issuing key plus any keys still accepted for resolution.

    The smallest abstraction that supports rotation (§7.1.1): issue with the
    active key, resolve with the active key or an explicitly configured previous
    one. A token naming a key outside this set is `UNRESOLVED`, never a
    distinguishable "retired key" answer.
    """

    active_id: str
    keys: dict[str, bytes]

    def __post_init__(self) -> None:
        if self.active_id not in self.keys:
            raise EvidenceRefKeyUnavailable("active evidence-ref key id is not in the keyring")
        if _SEPARATOR in self.active_id:
            raise EvidenceRefKeyUnavailable(
                f"evidence-ref key id must not contain {_SEPARATOR!r}"
            )

    @classmethod
    def from_settings(cls, settings) -> EvidenceRefKeyring:
        """Build from application settings, failing closed when unconfigured."""
        material = (settings.evidence_ref_key or "").strip()
        if not material:
            raise EvidenceRefKeyUnavailable(
                "EVIDENCE_REF_KEY is required for agent evidence references"
            )
        active_id = (settings.evidence_ref_key_id or "").strip()
        if not active_id:
            raise EvidenceRefKeyUnavailable("EVIDENCE_REF_KEY_ID must not be empty")

        keys = {active_id: _decode_key(material)}
        for entry in (settings.evidence_ref_previous_keys or "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            key_id, _, previous = entry.partition(":")
            key_id = key_id.strip()
            if not key_id or not previous.strip():
                raise EvidenceRefKeyUnavailable(
                    "EVIDENCE_REF_PREVIOUS_KEYS entries must be '<key_id>:<base64url>'"
                )
            keys.setdefault(key_id, _decode_key(previous))
        return cls(active_id=active_id, keys=keys)


def issue_evidence_ref(evidence: EvidenceSource, keyring: EvidenceRefKeyring) -> str:
    """The opaque, deterministic reference addressing this exact evidence row.

    The plaintext holds only what resolution needs — a payload version byte and
    the row's identity — so nothing about the robot, source or timing leaks even
    to an attacker who somehow recovers it. That identity lives *inside*
    authenticated ciphertext, which is what §7.1 permits; what it forbids is a
    raw identifier outside one.
    """
    payload = bytes([_PAYLOAD_VERSION]) + evidence.id.bytes
    ciphertext = AESSIV(keyring.keys[keyring.active_id]).encrypt(payload, [_ASSOCIATED_DATA])
    encoded = base64.urlsafe_b64encode(ciphertext).decode("ascii").rstrip("=")
    return f"{TOKEN_FORMAT}{_SEPARATOR}{keyring.active_id}{_SEPARATOR}{encoded}"


def _parse_envelope(ref: object) -> tuple[str, bytes] | ResolutionFailure:
    """Split the outer envelope, distinguishing *malformed* from *unresolved*.

    Only the token's grammar is judged here. Anything that is not a reference of
    this format is `MALFORMED`; whether a well-formed one authenticates is a
    separate question, answered later, so the binding can return
    `INVALID_ARGUMENT` for the first and `NOT_FOUND` for the second (§7.3).
    """
    if not isinstance(ref, str):
        return ResolutionFailure.MALFORMED
    parts = ref.strip().split(_SEPARATOR)
    if len(parts) != 3:
        return ResolutionFailure.MALFORMED
    marker, key_id, encoded = parts
    if marker != TOKEN_FORMAT or not key_id or not encoded:
        return ResolutionFailure.MALFORMED
    try:
        ciphertext = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (binascii.Error, ValueError):
        return ResolutionFailure.MALFORMED
    if len(ciphertext) < _MIN_CIPHERTEXT_LEN:
        return ResolutionFailure.MALFORMED
    return key_id, ciphertext


def _decrypt(
    key_id: str, ciphertext: bytes, keyring: EvidenceRefKeyring
) -> uuid.UUID | ResolutionFailure:
    """Authenticate and decrypt, yielding the addressed row's identity.

    An unknown key id and a failed tag are the same answer on purpose: telling
    them apart would report whether a key had been retired.
    """
    key = keyring.keys.get(key_id)
    if key is None:
        return ResolutionFailure.UNRESOLVED
    try:
        payload = AESSIV(key).decrypt(ciphertext, [_ASSOCIATED_DATA])
    except InvalidTag:
        # Deliberately no detail: the exception text is never surfaced.
        return ResolutionFailure.UNRESOLVED
    if len(payload) != _PAYLOAD_LEN or payload[0] != _PAYLOAD_VERSION:
        return ResolutionFailure.UNRESOLVED
    return uuid.UUID(bytes=payload[1:])


def _subject_is_published(session: Session, subject_type: str, subject_id: uuid.UUID) -> bool:
    """Is this evidence's subject reachable from a currently published robot?

    Evaluated now, never trusted from issuance time (§7.2) — unpublishing a robot
    must revoke every reference already handed out for its facts.
    """
    if subject_type == "COMMERCIAL_STATUS":
        stmt = select(Robot.id).where(Robot.id == subject_id)
    elif subject_type == "PRICING_OFFER":
        stmt = select(Robot.id).join(
            PricingOffer, PricingOffer.robot_id == Robot.id
        ).where(PricingOffer.id == subject_id)
    elif subject_type == "AVAILABILITY_OFFER":
        stmt = select(Robot.id).join(
            AvailabilityOffer, AvailabilityOffer.robot_id == Robot.id
        ).where(AvailabilityOffer.id == subject_id)
    elif subject_type == "DEPLOYMENT":
        stmt = select(Robot.id).join(
            Deployment, Deployment.robot_id == Robot.id
        ).where(Deployment.id == subject_id)
    else:
        return False
    stmt = stmt.where(Robot.is_published.is_(True))
    return bool(session.execute(select(stmt.exists())).scalar_one())


def resolve_evidence_ref(
    session: Session, ref: object, keyring: EvidenceRefKeyring
) -> EvidenceSource | ResolutionFailure:
    """The exact evidence row a reference addresses, or why it produced none.

    Resolution is a bounded primary-key lookup of the addressed row. It does
    **not** re-run best-evidence selection: the reference names a row, and newer
    provenance for the same subject must not move it (§7.1).
    """
    parsed = _parse_envelope(ref)
    if isinstance(parsed, ResolutionFailure):
        return parsed
    key_id, ciphertext = parsed

    evidence_id = _decrypt(key_id, ciphertext, keyring)
    if isinstance(evidence_id, ResolutionFailure):
        return evidence_id

    evidence = session.get(EvidenceSource, evidence_id)
    if evidence is None:
        return ResolutionFailure.UNRESOLVED
    if evidence.subject_type not in SUPPORTED_SUBJECT_TYPES:
        return ResolutionFailure.UNRESOLVED
    if not _subject_is_published(session, evidence.subject_type, evidence.subject_id):
        return ResolutionFailure.UNRESOLVED
    return evidence
