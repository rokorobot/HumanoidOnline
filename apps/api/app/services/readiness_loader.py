"""Loads `RobotRecord`s (services/readiness.py) from the canonical database.

Plain DB-API: it needs only a cursor whose `execute(sql, params)` accepts `%s` placeholders and
whose
rows are tuples (psycopg, or `session.connection().connection.cursor()` under SQLAlchemy). It is
used by
the importer's publication transition, the CI gate and the audit CLI, so none of them needs the ORM.

It reads. It never writes. A fixed number of queries, whatever the number of robots.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection

from app.services.readiness import (
    AvailabilityRow,
    ClaimRow,
    ImageRow,
    PricingRow,
    RobotRecord,
    SpecRow,
)

TERMINAL_CANDIDATE_STATES = ("PROMOTED", "REJECTED")
UNRESOLVED_IDENTITY = ("POSSIBLE_DUPLICATE", "AMBIGUOUS")


def _rows(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _s(v):
    return str(v) if v is not None else None


def load_records(cur, slugs: Collection[str] | None = None) -> list[RobotRecord]:
    cur.execute("SET search_path TO humanoid, public")
    where, params = "", ()
    if slugs is not None:
        if not slugs:
            return []
        where, params = "WHERE r.slug = ANY(%s)", (sorted(slugs),)
    robots = _rows(
        cur,
        "SELECT r.*, m.slug AS _manufacturer_slug FROM robot r "
        "LEFT JOIN manufacturer m ON m.id = r.manufacturer_id " + where + " ORDER BY r.slug",
        params,
    )
    if not robots:
        return []
    ids = [r["id"] for r in robots]

    variants = defaultdict(list)
    slug_by_variant: dict = {}
    for v in _rows(
        cur,
        "SELECT id, robot_id, slug, name FROM robot_variant WHERE robot_id = ANY(%s) ORDER BY slug",
        (ids,),
    ):
        variants[v["robot_id"]].append((v["slug"], v["name"]))
        slug_by_variant[v["id"]] = v["slug"]

    specs = defaultdict(list)
    for s in _rows(
        cur,
        "SELECT s.robot_id, s.variant_id, d.key, d.label, s.value_text, "
        "s.value_number, s.value_bool FROM specification s "
        "JOIN spec_definition d ON d.id = s.definition_id "
        "WHERE s.robot_id = ANY(%s) ORDER BY d.key",
        (ids,),
    ):
        specs[s["robot_id"]].append(
            SpecRow(
                slug_by_variant.get(s["variant_id"]),
                s["key"],
                s["label"],
                s["value_text"],
                float(s["value_number"]) if s["value_number"] is not None else None,
                s["value_bool"],
            )
        )

    evidence = {
        (e["subject_type"], e["subject_id"])
        for e in _rows(
            cur,
            "SELECT DISTINCT subject_type::text AS subject_type, subject_id FROM evidence_source "
            "WHERE subject_type::text IN ('COMMERCIAL_STATUS','PRICING_OFFER',"
            "'AVAILABILITY_OFFER','DEPLOYMENT')",
        )
    }

    pricing = defaultdict(list)
    for p in _rows(
        cur,
        "SELECT id, robot_id, variant_id, price_type::text AS price_type, price "
        "FROM pricing_offer WHERE robot_id = ANY(%s) AND is_current",
        (ids,),
    ):
        pricing[p["robot_id"]].append(
            PricingRow(
                slug_by_variant.get(p["variant_id"]),
                p["price_type"],
                float(p["price"]) if p["price"] is not None else None,
                ("PRICING_OFFER", p["id"]) in evidence,
            )
        )
    availability = defaultdict(list)
    for a in _rows(
        cur,
        "SELECT id, robot_id, variant_id, availability_status::text AS status, "
        "available_from, delivery_estimate_label, seller_wording FROM "
        "availability_offer WHERE robot_id = ANY(%s) AND is_current",
        (ids,),
    ):
        availability[a["robot_id"]].append(
            AvailabilityRow(
                slug_by_variant.get(a["variant_id"]),
                a["status"],
                _s(a["available_from"]),
                a["delivery_estimate_label"],
                a["seller_wording"],
                ("AVAILABILITY_OFFER", a["id"]) in evidence,
            )
        )
    deployments = defaultdict(list)
    for d in _rows(cur, "SELECT id, robot_id FROM deployment WHERE robot_id = ANY(%s)", (ids,)):
        deployments[d["robot_id"]].append(("DEPLOYMENT", d["id"]) in evidence)

    images = defaultdict(list)
    for i in _rows(
        cur,
        "SELECT robot_id, image_url, source_url, source_name, "
        "identity_status::text AS identity_status, rights_status::text AS "
        "rights_status, usage_basis::text AS usage_basis, attribution, "
        "is_representative, representative_note FROM robot_image "
        "WHERE robot_id = ANY(%s)",
        (ids,),
    ):
        images[i["robot_id"]].append(
            ImageRow(
                i["image_url"],
                i["source_url"],
                i["source_name"],
                i["identity_status"],
                i["rights_status"],
                i["usage_basis"],
                i["attribution"],
                bool(i["is_representative"]),
                i["representative_note"],
            )
        )

    slugs_in = [r["slug"] for r in robots]
    claims = defaultdict(list)
    for c in _rows(
        cur,
        "SELECT c.id, c.robot_slug, c.variant_slug, c.target_kind, c.target_key, "
        "c.accepted_value FROM accepted_claim c WHERE c.robot_slug = ANY(%s) "
        "AND NOT EXISTS (SELECT 1 FROM claim_retraction x WHERE x.claim_id = c.id) "
        "ORDER BY c.claim_seq",
        (slugs_in,),
    ):
        claims[c["robot_slug"]].append(
            ClaimRow(
                str(c["id"]),
                c["target_kind"],
                c["target_key"],
                c["variant_slug"],
                c["accepted_value"],
            )
        )

    # CURRENT identity state only: the candidate's effective identity_status/status, never the
    # append-only decision history. A resolved ambiguity leaves a historical row and no open item.
    open_identity = defaultdict(list)
    for o in _rows(
        cur,
        "SELECT c.possible_robot_id, c.promoted_robot_id, c.candidate_name, "
        "c.identity_status::text AS identity_status, c.status::text AS status "
        "FROM discovery_candidate c WHERE c.identity_status::text = ANY(%s) "
        "AND c.status::text <> ALL(%s) AND (c.possible_robot_id = ANY(%s) "
        "OR c.promoted_robot_id = ANY(%s))",
        (list(UNRESOLVED_IDENTITY), list(TERMINAL_CANDIDATE_STATES), ids, ids),
    ):
        for rid in (o["possible_robot_id"], o["promoted_robot_id"]):
            if rid in set(ids):
                open_identity[rid].append(
                    f"candidate {o['candidate_name']!r} is {o['identity_status']} ({o['status']})"
                )

    pending: dict[str, int] = {
        r["robot_slug"]: r["n"]
        for r in _rows(
            cur,
            "SELECT p.robot_slug, count(*) AS n FROM discovery_claim_proposal p "
            "WHERE p.robot_slug = ANY(%s) AND NOT EXISTS (SELECT 1 FROM "
            "discovery_proposal_decision "
            "d WHERE d.proposal_id = p.id) AND p.proposal_seq = (SELECT max(q.proposal_seq) FROM "
            "discovery_claim_proposal q WHERE q.slot_key = p.slot_key) GROUP BY p.robot_slug",
            (slugs_in,),
        )
    }

    out: list[RobotRecord] = []
    for r in robots:
        rid, slug = r["id"], r["slug"]
        core = {
            k: (float(v) if hasattr(v, "as_tuple") else v)
            for k, v in r.items()
            if not k.startswith("_")
        }
        out.append(
            RobotRecord(
                slug=slug,
                name=r.get("name"),
                manufacturer_slug=r["_manufacturer_slug"],
                is_published=bool(r["is_published"]),
                summary=r.get("summary"),
                commercial_status=str(r["commercial_status"]),
                official_url=r.get("official_url"),
                core=core,
                spec_caveats=list(r.get("spec_caveats") or []),
                variants=variants.get(rid, []),
                specs=specs.get(rid, []),
                status_evidence=1 if ("COMMERCIAL_STATUS", rid) in evidence else 0,
                pricing=pricing.get(rid, []),
                availability=availability.get(rid, []),
                deployments=deployments.get(rid, []),
                images=images.get(rid, []),
                claims=claims.get(slug, []),
                open_identity=open_identity.get(rid, []),
                not_yet_reviewed=pending.get(slug, 0),
                source_count=len(claims.get(slug, [])) + sum(1 for s in specs.get(rid, [])),
            )
        )
    return out
