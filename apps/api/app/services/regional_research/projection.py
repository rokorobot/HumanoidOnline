"""JSON projection of a `RegionalAvailability` (pure; ADR-027 §8, §9, §11).

The single source for every machine/human surface: the HTML page, the JSON
endpoint and the JSON-LD are all built from this dict, so they cannot drift.
All text here is template-generated from the read model; none is authored.
`readiness` (the publication gate) is review-only and omitted by default.
"""
from __future__ import annotations

from dataclasses import asdict

from .readmodel import (
    QUALIFYING,
    QualifyingOffer,
    RegionalAvailability,
    RegionalDeployment,
)

REGION_SLUGS = {"europe": "EUROPE", "north-america": "NORTH_AMERICA", "asia": "ASIA"}

# Coverage statements for a region whose catalogue membership departs from its
# reference classification. Fixed text about the hierarchy (db/catalogue/regions.json),
# never a commercial fact; appended to the methodology's region_membership.
_MEMBERSHIP_NOTES = {
    "ASIA": (
        " It follows the UN M49 Asia classification (Central, Eastern, South-eastern, "
        "Southern and Western Asia) with two disclosed exceptions: Cyprus is counted in "
        "Europe with the European Union, not here, and Taiwan, coded separately as a "
        "commercial destination, is included. Russia is counted in Europe; Australia, New "
        "Zealand and the Pacific (Asia-Pacific) are not included."
    ),
}

_REASON_LABELS = {
    "CONFIRMED_NOT_OBTAINABLE": "Evidence on file that it is not currently obtainable here",
    "STALE_OR_NON_CURRENT": "Regional offer on file was withdrawn (recorded as no longer current)",
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


_STATUS_LABELS = {
    "LIMITED": "limited",
    "PREORDER": "preorder",
    "WAITLIST": "waitlist",
    "ON_REQUEST": "on request",
}

_TX_LABELS = {"PURCHASE": "purchase", "RENTAL": "rental", "LEASE": "lease", "RAAS": "RaaS"}


def _tx_words(types: set[str]) -> str:
    return _list(sorted(_TX_LABELS.get(t, t.lower()) for t in types))


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
    by_status = dict(kf.purchase_by_best_status)
    available = by_status.get("AVAILABLE", 0)
    if purchase:
        # Name only the statuses actually on file, never the full vocabulary.
        parts = [f"{available} {'is' if available == 1 else 'are'} listed as available"] + [
            f"{n} as {_STATUS_LABELS[s]}"
            for s, n in kf.purchase_by_best_status
            if s != "AVAILABLE" and n
        ]
        q1 = (
            f"As of {date_s}, {len(purchase)} published humanoid "
            f"{'robot has' if len(purchase) == 1 else 'robots have'} a confirmed purchase "
            f"offer on file in {region}: {_list(purchase)}. Of these, {_list(parts)}. "
            f"See the offers table for each status, seller and evidence."
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
    # Directness is per transaction type: a robot that can be rented directly but only
    # bought on request is "rental only" on the direct side and "purchase" on the gated.
    direct_tx: dict[str, set[str]] = {}
    gated_tx: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for o in offers:
        names[o.robot_slug] = o.robot_name
        if o.availability_status in ("AVAILABLE", "LIMITED"):
            direct_tx.setdefault(o.robot_slug, set()).add(o.transaction_type)
    for o in offers:
        if o.transaction_type not in direct_tx.get(o.robot_slug, set()):
            gated_tx.setdefault(o.robot_slug, set()).add(o.transaction_type)
    direct = [
        names[s] + ("" if "PURCHASE" in direct_tx[s] else f" ({_tx_words(direct_tx[s])} only)")
        for s in sorted(direct_tx)
    ]
    gated = [
        names[s] + (f" ({_tx_words(gated_tx[s])})" if s in direct_tx else "")
        for s in sorted(gated_tx)
    ]
    if offers:
        q_direct = (
            f"As of {date_s}, offers that can be ordered directly (available or limited) are on "
            f"file for: {_list(direct) or 'none'}. Offers that need a preorder, a waitlist place, "
            f"a quote or a sales contact are on file for: {_list(gated) or 'none'}. A quote or "
            "contact-sales offer confirms a sales route, not stock or a delivery date."
        )
    else:
        q_direct = f"As of {date_s}, no confirmed {region} offer of either kind is on file."

    by_type: dict[str, set[str]] = {}
    for o in offers:
        kind = "manufacturer" if o.provider_type == "OEM" else "third-party seller"
        by_type.setdefault(kind, set()).add(o.robot_name)
    if offers:
        parts = [
            f"{label}: {_list(sorted(by_type[label]))}"
            for label in ("manufacturer", "third-party seller")
            if label in by_type
        ]
        q_seller = (
            f"As of {date_s}, confirmed {region} offers on file come from the "
            f"{'; and from the '.join(parts)}. A third-party seller is a distributor, "
            "reseller or integrator, not the manufacturer; each offer names its seller."
        )
    else:
        q_seller = f"As of {date_s}, no confirmed {region} offer is on file from any seller."

    if r.offer_regions:
        q_where = (
            f"As of {date_s}, confirmed offers on file name: "
            f"{_list([name for _, name in r.offer_regions])}. HumanoidOnline holds no "
            f"confirmed offer for any other {region} country or territory; that is a gap in "
            "the evidence, not proof that robots cannot be obtained there. An offer counts "
            "only for the country its seller documents."
        )
    else:
        q_where = f"As of {date_s}, no confirmed offer is on file for any {region} country."

    deployed = sorted({d.robot_name for d in r.deployments})
    q_deploy = (
        "No. A deployment is evidence that a robot has been used in a region, for example in "
        "a pilot or under a service contract with one customer. It is not an offer a new "
        f"buyer can take up, so deployments never count toward {region} availability."
        + (
            f" As of {date_s}, evidenced {region} deployments are on file for: "
            f"{_list(deployed)}; they are listed separately from the offers."
            if deployed else ""
        )
    )

    return [
        {"question": f"Can I buy a humanoid robot in {region}?", "answer": q1},
        {"question": f"Which humanoid robots in {region} have a published price?", "answer": q2},
        {
            "question": f"Which humanoid robots can be ordered directly in {region}, and which "
                        "need a quote, preorder or sales contact?",
            "answer": q_direct,
        },
        {
            "question": f"Are {region} humanoid robot offers sold by manufacturers or by "
                        "resellers?",
            "answer": q_seller,
        },
        {"question": f"In which {region} countries is a humanoid robot offer confirmed?",
         "answer": q_where},
        {
            "question": f"Does a humanoid robot deployment in {region} mean I can buy it there?",
            "answer": q_deploy,
        },
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
                f"The snapshot date is {date_s}. An offer stays current until newer evidence "
                "replaces it, so each offer shows the date it was last observed; check that "
                "date before relying on it. Confidence is shown per offer and is never "
                "upgraded by publication; human verification is not required, and a row "
                "without a verification date has none recorded."
            ),
        },
    ]


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _health(r: RegionalAvailability) -> dict:
    """Public, deterministic evidence health (not the review-only gate object).

    CURRENT: the normal publication threshold (robots / manufacturers with a current
    offer) is met. LIMITED_EVIDENCE: it is not. Evidence age alone never downgrades
    health: an offer stays current until newer evidence replaces it (owner decision
    2026-10-23), and each offer shows its last-observed date instead.
    """
    g = r.gate
    reasons = []
    if g.qualifying_robots < g.min_robots:
        reasons.append(
            f"{g.qualifying_robots} qualifying {_plural(g.qualifying_robots, 'robot', 'robots')}; "
            f"minimum {g.min_robots}"
        )
    if g.qualifying_manufacturers < g.min_manufacturers:
        reasons.append(
            f"{g.qualifying_manufacturers} "
            f"{_plural(g.qualifying_manufacturers, 'manufacturer', 'manufacturers')}; "
            f"minimum {g.min_manufacturers}"
        )
    return {
        "status": "LIMITED_EVIDENCE" if reasons else "CURRENT",
        "reasons": reasons,
    }


def build_projection(
    r: RegionalAvailability, region_slug: str, *, include_readiness: bool = False
) -> dict:
    kf = r.key_figures
    offers = list(r.qualifying_offers)
    out = {
        "region": {"slug": region_slug, "code": r.region_code, "name": r.region_name},
        "snapshot_date": r.snapshot_date.isoformat(),
        "latest_evidence_date": (
            max(o.evidence_date for o in offers).isoformat() if offers else None
        ),
        "direct_answer": r.direct_answer,
        "publication_health": _health(r),
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
                    {
                        "slug": x.slug,
                        "name": x.name,
                        "manufacturer_slug": x.manufacturer_slug,
                        "manufacturer_name": x.manufacturer_name,
                    }
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
                + _MEMBERSHIP_NOTES.get(r.region_code, "")
            ),
            "qualifying_offer": (
                "A region-specific availability offer that is current, linked to evidence and "
                "has an obtainable status (available, limited, preorder, waitlist or on "
                "request). A price on its own is not an availability offer."
            ),
            "evidence_age": (
                "An offer and its price stay current until newer evidence replaces them: an "
                "offer recorded as withdrawn or not obtainable stops counting, but age alone "
                "never removes one. Each offer shows the date it was last observed."
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
