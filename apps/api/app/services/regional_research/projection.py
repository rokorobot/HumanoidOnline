"""JSON projection of a `RegionalAvailability` (pure; ADR-027 §8, §9, §11).

The single source for every machine/human surface: the HTML page, the JSON
endpoint and the JSON-LD are all built from this dict, so they cannot drift.
All text here is template-generated from the read model; none is authored.
`readiness` (the publication gate) is review-only and omitted by default.
"""
from __future__ import annotations

from dataclasses import asdict

from .readmodel import QUALIFYING, QualifyingOffer, RegionalAvailability, RegionalDeployment

REGION_SLUGS = {"europe": "EUROPE"}

_REASON_LABELS = {
    "CONFIRMED_NOT_OBTAINABLE": "Evidence on file that it is not currently obtainable here",
    "STALE_OR_NON_CURRENT": (
        "Regional offer on file is non-current or its evidence is older than the freshness window"
    ),
    "OFFER_WITHOUT_EVIDENCE": "Regional offer on file without supporting evidence",
    "UNRESOLVED_REGION": "Offer on file whose region is not resolved",
    "PRICE_ONLY": "Regional price on file but no availability offer",
    "GLOBAL_ONLY": "Global offer only; no region-specific offer",
    "OTHER_REGION_ONLY": "Offers on file for other regions only",
    "NO_OFFERS": "No offer on file",
}


def _offer_dict(o: QualifyingOffer) -> dict:
    return {
        "robot_slug": o.robot_slug,
        "robot_name": o.robot_name,
        "manufacturer_slug": o.manufacturer_slug,
        "manufacturer_name": o.manufacturer_name,
        "provider_slug": o.provider_slug,
        "provider_type": o.provider_type,
        "region_code": o.region_code,
        "transaction_type": o.transaction_type,
        "availability_status": o.availability_status,
        "evidence_date": o.evidence_date.isoformat(),
        "confidence": o.confidence,
        "human_verified": o.human_verified,
        "source_urls": list(o.source_urls),
        "prices": [asdict(p) for p in o.prices],
    }


def _deployment_dict(d: RegionalDeployment) -> dict:
    return {
        "robot_slug": d.robot_slug,
        "robot_name": d.robot_name,
        "manufacturer_slug": d.manufacturer_slug,
        "manufacturer_name": d.manufacturer_name,
        "region_code": d.region_code,
        "customer_name": d.customer_name,
        "provider_slug": d.provider_slug,
        "transaction_type": d.transaction_type,
        "unit_count": d.unit_count,
        "started_on": d.started_on.isoformat() if d.started_on else None,
        "status": d.status,
        "evidence_date": d.evidence_date.isoformat(),
        "confidence": d.confidence,
        "human_verified": d.human_verified,
        "source_urls": list(d.source_urls),
    }


def _names(offers: list[QualifyingOffer], pred) -> list[str]:
    seen: dict[str, str] = {}
    for o in offers:
        if pred(o):
            seen.setdefault(o.robot_slug, o.robot_name)
    return [seen[s] for s in sorted(seen)]


def _list(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _faq(r: RegionalAvailability) -> list[dict]:
    kf = r.key_figures
    region = r.region_name
    date_s = r.snapshot_date.isoformat()
    offers = list(r.qualifying_offers)
    purchase = _names(offers, lambda o: o.transaction_type == "PURCHASE")
    priced = _names(
        offers,
        lambda o: o.transaction_type == "PURCHASE"
        and any(p.kind == "PUBLISHED" for p in o.prices),
    )
    available = dict(kf.purchase_by_best_status).get("AVAILABLE", 0)
    if purchase:
        q1 = (
            f"As of {date_s}, {len(purchase)} published humanoid "
            f"{'robot has' if len(purchase) == 1 else 'robots have'} a confirmed purchase "
            f"offer on file in {region}: {_list(purchase)}. Of these, {available} "
            f"{'is' if available == 1 else 'are'} listed as available and the "
            f"rest are limited, waitlist, preorder or on request. See the offers table for "
            f"each status, seller and evidence."
        )
    else:
        q1 = (
            f"As of {date_s}, HumanoidOnline has no confirmed purchase offer on file in "
            f"{region}. This describes the evidence on file, not the market."
        )
    if priced:
        q2 = (
            f"As of {date_s}, published purchase prices are on file for: {_list(priced)}. "
            "Prices are shown as published by each seller, with currency and basis; they are "
            "not converted or adjusted."
        )
    else:
        q2 = (
            f"As of {date_s}, no published purchase price is on file for a confirmed "
            f"{region} offer."
        )
    return [
        {"question": f"Can I buy a humanoid robot in {region}?", "answer": q1},
        {"question": f"Which humanoid robots in {region} have a published price?", "answer": q2},
        {
            "question": f"What does \"no confirmed {region} offer\" mean?",
            "answer": (
                f"It means HumanoidOnline has no qualifying {region} evidence on file for that "
                f"robot. It never means the robot is not available in {region}."
            ),
        },
        {
            "question": "How current is this data?",
            "answer": (
                f"The snapshot date is {date_s}. An offer counts only when its latest evidence "
                f"is within {r.freshness_days} days of the snapshot. Confidence is shown per "
                "offer and is never upgraded by publication; human verification is not "
                "required, and a row without a verification date has none recorded."
            ),
        },
    ]


def build_projection(
    r: RegionalAvailability, region_slug: str, *, include_readiness: bool = False
) -> dict:
    kf = r.key_figures
    offers = list(r.qualifying_offers)
    out = {
        "region": {"slug": region_slug, "code": r.region_code, "name": r.region_name},
        "snapshot_date": r.snapshot_date.isoformat(),
        "freshness_days": r.freshness_days,
        "latest_evidence_date": (
            max(o.evidence_date for o in offers).isoformat() if offers else None
        ),
        "direct_answer": r.direct_answer,
        "key_figures": {
            "published_population": kf.population,
            "robots_with_confirmed_offer": kf.qualifying_robots,
            "manufacturers_with_confirmed_offer": kf.qualifying_manufacturers,
            "robots_without_confirmed_offer": kf.no_confirmed_offer,
            "purchase_robots": kf.purchase_robots,
            "purchase_by_best_status": [
                {"status": s, "robots": c} for s, c in kf.purchase_by_best_status
            ],
            "robots_by_other_transaction": [
                {"transaction_type": t, "robots": c}
                for t, c in kf.robots_by_other_transaction
            ],
            "purchase_robots_with_published_price": kf.purchase_robots_with_published_price,
            "purchase_robots_price_on_request": kf.purchase_robots_price_on_request,
            "purchase_robots_price_not_published": kf.purchase_robots_price_not_published,
        },
        "offers": [_offer_dict(o) for o in offers],
        # Deployment evidence (use), kept apart from offers (purchasability).
        "deployments": [_deployment_dict(d) for d in r.deployments],
        "no_confirmed_offer": [
            {
                "reason": g.reason,
                "label": _REASON_LABELS[g.reason],
                "robots": [
                    {"slug": x.slug, "name": x.name, "manufacturer_slug": x.manufacturer_slug}
                    for x in g.robots
                ],
            }
            for g in r.groups
            if g.reason != QUALIFYING and g.robots
        ],
        "methodology": {
            "population": "Published humanoid robots in the HumanoidOnline catalogue.",
            "region_membership": (
                f"{r.region_name} = the {r.region_code} region and every region beneath it in "
                f"the catalogue hierarchy ({len(r.member_region_codes)} regions). Global "
                "offers are not counted as regional availability."
            ),
            "qualifying_offer": (
                "A region-specific availability offer that is current, linked to evidence, "
                f"has evidence dated within {r.freshness_days} days of the snapshot, and has "
                "an obtainable status (available, limited, preorder, waitlist or on request). "
                "A price on its own is not an availability offer."
            ),
            "unknown_treatment": (
                "Unknown values stay unknown: a missing price is shown as not published, "
                "quote-only as price on request, and estimates are never shown as published "
                "prices."
            ),
            "confidence": (
                "Confidence is shown per offer exactly as recorded and is not upgraded by "
                "publication. Human verification is not required for inclusion."
            ),
            "deployments": (
                "Deployments are evidence that a robot has been used in the region. They are "
                "listed separately and never make a robot purchasable; an evidenced deployment "
                "is shown regardless of age, with its evidence date."
            ),
            "calculation": "Deterministic and reproducible from the declared snapshot.",
        },
        "faq": _faq(r),
        "member_region_codes": list(r.member_region_codes),
    }
    if include_readiness:
        g = r.gate
        out["readiness"] = {
            "gate_passes": g.passes,
            "qualifying_robots": g.qualifying_robots,
            "qualifying_manufacturers": g.qualifying_manufacturers,
            "min_robots": g.min_robots,
            "min_manufacturers": g.min_manufacturers,
            "failures": list(g.failures),
            "groups_reconcile": r.reconciles,
        }
    return out
