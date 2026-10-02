"""G2-3 accepted claims — DR-A5 B-prime, sections 5.2, 5.3 and 11.

An accepted claim is created ONLY from an effective ACCEPT decision on a CURRENT,
non-stale proposal, for a field policy that is explicitly registered
(`field_policy.CLAIM_POLICIES`). It is immutable; a mistake is withdrawn by appending a
`claim_retraction` (optionally naming the corrected claim). Creating a claim writes no
catalogue row: the catalogue of record is db/catalogue/ and is changed only by the
reviewed materialization PR and the importer (M2, `materialize.py`).

Nothing is guessed. The human's explicit mapping lives in the decision's resolved choices
(`target_kind`, `variant_slug`, `variant_name`, `spec_key`, `edition_scope`,
`accepted_value`, plus an answer to every review question); a missing or differing value
refuses the claim.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.claim_proposal import (
    AcceptedClaim,
    ClaimRetraction,
    DiscoveryClaimProposal,
    DiscoveryProposalObservation,
)
from app.services.discovery import DiscoveryError
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import (
    CLAIM_POLICIES,
    CLAIM_REGISTRY_VERSION,
    NO_CATALOGUE_HOME,
    SPEC_DEFINITION_KEY,
    ClaimPolicy,
    claim_policy_for,
)
from app.services.discovery.proposal_review import HOME_KEY


def claim_digest(proposal_digest: str, robot_slug: str, variant_slug: str | None,
                 target_kind: str, target_key: str, edition_scope: str | None,
                 accepted_value: str) -> str:
    """Content identity of a claim; rebuilt identically from stored proposals/decisions."""
    payload = json.dumps([proposal_digest, robot_slug, variant_slug, target_kind, target_key,
                          edition_scope, accepted_value], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def active_claims(session: Session, robot_slug: str) -> list[AcceptedClaim]:
    """Accepted claims for a robot that have not been retracted, oldest first."""
    retracted = select(ClaimRetraction.claim_id)
    return list(session.scalars(
        select(AcceptedClaim).where(AcceptedClaim.robot_slug == robot_slug,
                                    AcceptedClaim.id.not_in(retracted))
        .order_by(AcceptedClaim.claim_seq)))


def _need(choices: dict, key: str, expected: str | None = None) -> str:
    value = choices.get(key)
    if value is None or not str(value).strip():
        raise DiscoveryError(
            f"the ACCEPT decision's resolved choices do not record {key!r}; nothing is guessed")
    if expected is not None and value != expected:
        raise DiscoveryError(
            f"resolved choice {key}={value!r} differs from what the registered policy and the "
            f"proposal allow ({expected!r})")
    return value


def _json(value: dict) -> str:
    """Canonical, deterministic JSON for a structured accepted value."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _active_claim(session: Session, robot_slug: str, **where) -> AcceptedClaim | None:
    return session.scalar(
        select(AcceptedClaim).where(
            AcceptedClaim.robot_slug == robot_slug,
            AcceptedClaim.id.not_in(select(ClaimRetraction.claim_id)),
            *[getattr(AcceptedClaim, k) == v for k, v in where.items()])
        .order_by(AcceptedClaim.claim_seq.desc()).limit(1))


def _variant_prerequisite(session: Session, p: DiscoveryClaimProposal, slug: str) -> None:
    if not p.edition:
        raise DiscoveryError("a variant-scoped claim needs an edition")
    variant_claim = _active_claim(session, p.robot_slug, target_kind="robot_variant",
                                  edition_label=p.edition)
    if variant_claim is None or variant_claim.variant_slug != slug:
        raise DiscoveryError(
            f"the {p.edition!r} VARIANT claim must be accepted first and its slug must be "
            f"{slug!r} (prerequisite, DR-A5 section 5.3)")


def _plan(session: Session, p: DiscoveryClaimProposal, policy: ClaimPolicy,
          choices: dict) -> dict:
    """Validate the human's explicit mapping against the registered policy and the
    proposal; return the claim's catalogue-facing fields."""
    _need(choices, "target_kind", policy.target_kind)
    verbatim = p.value
    structured = dict(p.structured or {})
    if policy.target_kind == "NO_CATALOGUE_HOME":
        # Accepted knowledge with provenance; it authorizes no catalogue write and is never
        # materialized. The human must state both the target kind and the home explicitly.
        _need(choices, HOME_KEY, NO_CATALOGUE_HOME)
        value = _need(choices, "accepted_value", verbatim)
        return {"variant_slug": p.edition.lower() if p.edition else None,
                "accepted_value": value,
                "edition_scope": "THIS_EDITION" if p.edition else None,
                "target_key": policy.target_key}
    if policy.target_kind == "robot_variant":
        slug_from_source = structured.get("slug")
        if not slug_from_source or not p.edition:
            raise DiscoveryError("the VARIANT proposal carries no slug or edition")
        slug = _need(choices, "variant_slug", slug_from_source)
        name = _need(choices, "variant_name", verbatim)
        return {"variant_slug": slug, "accepted_value": name, "edition_scope": None,
                "target_key": policy.target_key}
    slug = _need(choices, "variant_slug")
    _variant_prerequisite(session, p, slug)
    if policy.target_kind == "specification":
        _need(choices, "spec_key", policy.target_key)
        _need(choices, "edition_scope", policy.edition_scope)
        value = _need(choices, "accepted_value", verbatim)
        return {"variant_slug": slug, "accepted_value": value,
                "edition_scope": policy.edition_scope, "target_key": policy.target_key}
    if policy.target_kind == "pricing_offer":
        # Owner decision (G2-4): the maker's own numeric estimate, a one-time purchase price,
        # region and provider unspecified, tax and shipping excluded as stated. Everything
        # is checked against the proposal's source text; nothing is defaulted.
        if structured.get("basis") != "excluding taxes and shipping":
            raise DiscoveryError("the source no longer states 'excluding taxes and shipping'; "
                                 "the price basis cannot be preserved, so nothing is claimed")
        for key, expected in (("price_type", "MANUFACTURER_ESTIMATE"),
                              ("transaction_type", "PURCHASE"), ("billing_period", "ONE_TIME"),
                              ("region", "UNSPECIFIED"), ("provider", "NONE"),
                              ("edition_confirmed", "true"),
                              ("currency", structured.get("currency")),
                              ("price", structured.get("amount"))):
            _need(choices, key, expected)
        offer = {"billing_period": "ONE_TIME", "currency": structured["currency"],
                 "edition_confirmed": True, "price": structured["amount"],
                 "price_basis": structured["basis"], "price_type": "MANUFACTURER_ESTIMATE",
                 "transaction_type": "PURCHASE"}
        return {"variant_slug": slug, "accepted_value": _json(offer), "edition_scope": None,
                "target_key": policy.target_key}
    if policy.target_kind == "availability_offer":
        year = structured.get("expected_year")
        if not year:
            raise DiscoveryError("the source states no expected year; nothing is claimed")
        for key, expected in (("availability_status", "WAITLIST"),
                              ("transaction_type", "PURCHASE"), ("available_from", "NULL"),
                              ("region", "UNSPECIFIED"), ("provider", "NONE"),
                              ("delivery_estimate_label", f"Expected in {year}")):
            _need(choices, key, expected)
        # WAITLIST rests on the manufacturer's reservation statement: it must be accepted
        # (as governed knowledge) first. No date is manufactured from the year.
        if _active_claim(session, p.robot_slug, target_kind="NO_CATALOGUE_HOME",
                         target_key="reservation_terms") is None:
            raise DiscoveryError("the RESERVATION_TERMS statement must be accepted first: it is "
                                 "the stated basis of the WAITLIST status (prerequisite)")
        offer = {"availability_status": "WAITLIST", "available_from": None,
                 "delivery_estimate_label": f"Expected in {year}", "seller_wording": verbatim,
                 "transaction_type": "PURCHASE"}
        return {"variant_slug": slug, "accepted_value": _json(offer), "edition_scope": None,
                "target_key": policy.target_key}
    raise DiscoveryError(f"no planner for target kind {policy.target_kind!r}")


def create_claim(session: Session, proposal_ref: str, *, created_by: str
                 ) -> tuple[AcceptedClaim, bool]:
    """Create the accepted claim for one proposal. Returns (claim, created); repeating it
    for the same effective ACCEPT decision is a no-op."""
    if not created_by or not created_by.strip():
        raise DiscoveryError("a claim must name the human who made it (--by)")
    p = pr.resolve_proposal(session, proposal_ref)
    [state] = pr.derive_states(session, [p])
    eff = state.effective
    if eff is None or eff.decision != pr.ACCEPT:
        raise DiscoveryError("an accepted claim needs an effective ACCEPT decision on this "
                             "proposal; the newest decision is "
                             f"{eff.decision if eff else 'none'}")
    if state.superseded:
        raise DiscoveryError("this proposal is SUPERSEDED; no claim can be made from it")
    if state.stale:
        raise DiscoveryError("this proposal is STALE; no claim can be made from it: "
                             + "; ".join(state.stale_reasons))
    policy = claim_policy_for(p.kind, p.target, p.evidence_locator, p.structured)
    if policy is None:
        raise DiscoveryError(
            f"no registered field policy for {p.kind} / {p.target!r}; unregistered proposals "
            "are refused (DR-A5 section 11.3)")
    choices = dict(eff.resolved_choices)
    plan = _plan(session, p, policy, choices)

    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                    {"k": f"accepted-claim:{eff.id}:{policy.key}:{plan['variant_slug']}"})
    existing = session.scalar(select(AcceptedClaim).where(
        AcceptedClaim.decision_id == eff.id, AcceptedClaim.target_kind == policy.target_kind,
        AcceptedClaim.target_key == policy.target_key,
        AcceptedClaim.variant_slug == plan["variant_slug"]))
    if existing is not None:
        return existing, False

    page = pr.latest_content_page(session, p)
    sighting = session.scalar(
        select(DiscoveryProposalObservation).where(
            DiscoveryProposalObservation.proposal_id == p.id,
            DiscoveryProposalObservation.content_hash == page.content_hash)
        .order_by(DiscoveryProposalObservation.observation_seq.desc()).limit(1))
    if sighting is None:     # cannot happen for a non-stale proposal; fail closed anyway
        raise DiscoveryError("no sighting confirms this proposal on the page's current content")
    claim = AcceptedClaim(
        claim_digest=claim_digest(p.digest, p.robot_slug, plan["variant_slug"],
                                  policy.target_kind, policy.target_key, plan["edition_scope"],
                                  plan["accepted_value"]),
        decision_id=eff.id, proposal_id=p.id, proposal_digest=p.digest,
        observation_id=sighting.id, observation_content_hash=sighting.content_hash,
        observed_at=sighting.retrieved_at, source_id=p.source_id, source_url=p.source_url,
        robot_slug=p.robot_slug, variant_slug=plan["variant_slug"], edition_label=p.edition,
        target_kind=policy.target_kind, target_key=policy.target_key,
        value_type=policy.value_type, accepted_value=plan["accepted_value"],
        edition_scope=plan["edition_scope"], verbatim_value=p.value,
        evidence_excerpt=p.evidence_excerpt, evidence_locator=p.evidence_locator,
        policy_key=policy.key, registry_version=CLAIM_REGISTRY_VERSION,
        resolved_choices=choices, created_by=created_by.strip())
    session.add(claim)
    session.flush()
    return claim, True


def retract_claim(session: Session, claim_id: str, *, retracted_by: str, reason: str,
                  replacement_id: str | None = None) -> ClaimRetraction:
    """Withdraw an accepted claim by appending a retraction (never an edit)."""
    if not retracted_by.strip() or not reason.strip():
        raise DiscoveryError("a retraction needs a named human and a reason")
    claim = session.get(AcceptedClaim, uuid.UUID(claim_id))
    if claim is None:
        raise DiscoveryError(f"unknown accepted claim {claim_id!r}")
    if session.scalar(select(ClaimRetraction).where(ClaimRetraction.claim_id == claim.id)):
        raise DiscoveryError("this claim is already retracted")
    replacement = None
    if replacement_id:
        replacement = session.get(AcceptedClaim, uuid.UUID(replacement_id))
        if replacement is None or replacement.id == claim.id:
            raise DiscoveryError("the replacement must be a different, existing accepted claim")
        if (replacement.robot_slug, replacement.target_kind, replacement.target_key,
                replacement.variant_slug) != (claim.robot_slug, claim.target_kind,
                                              claim.target_key, claim.variant_slug):
            raise DiscoveryError("the replacement must address the same robot and target")
    row = ClaimRetraction(claim_id=claim.id,
                          replacement_claim_id=replacement.id if replacement else None,
                          retracted_by=retracted_by.strip(), reason=reason.strip())
    session.add(row)
    session.flush()
    return row


def render_claims(session: Session, robot_slug: str) -> list[str]:
    retracted = {r.claim_id: r for r in session.scalars(select(ClaimRetraction))}
    rows = list(session.scalars(select(AcceptedClaim).where(AcceptedClaim.robot_slug == robot_slug)
                                .order_by(AcceptedClaim.claim_seq)))
    lines = [f"ACCEPTED CLAIMS for {robot_slug} ({len(rows)}); read-only"]
    for c in rows:
        r = retracted.get(c.id)
        lines.append(
            f"  #{c.claim_seq} {str(c.id)[:8]} {'RETRACTED' if r else 'ACTIVE':<9} "
            f"{c.target_kind}[{c.target_key}] variant={c.variant_slug} "
            f"scope={c.edition_scope} value={c.accepted_value!r} proposal={c.proposal_digest[:12]}"
            f" obs-hash={c.observation_content_hash[:12]} by {c.created_by}")
    return lines


__all__ = ["create_claim", "retract_claim", "active_claims", "claim_digest", "render_claims",
           "CLAIM_POLICIES", "SPEC_DEFINITION_KEY"]
