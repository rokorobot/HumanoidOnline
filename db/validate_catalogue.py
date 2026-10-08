#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Catalogue-level G2 gate: no published commercial fact without evidence.

Asserts, for the imported WS2B catalogue, that EVERY published robot's
commercial facts carry a backing evidence_source row:

  1. each is_published robot's commercial_status  -> evidence(subject=COMMERCIAL_STATUS, robot.id)
  2. each pricing_offer on a published robot       -> evidence(subject=PRICING_OFFER, offer.id)
  3. each availability_offer on a published robot   -> evidence(subject=AVAILABILITY_OFFER, offer.id)
  4. each deployment on a published robot           -> evidence(subject=DEPLOYMENT, deployment.id)

and, because every manufacturer profile is public, that each asserted company
claim is attributed to a MANUFACTURER evidence row naming that field in
`claim_fields` (migration 0013):

  5. manufacturer.deployment_status (other than UNKNOWN)
  6. manufacturer.is_public_company (TRUE or FALSE; NULL asserts nothing)
  7. manufacturer.parent_company

Exits non-zero if any published commercial fact lacks evidence (this is the
same "no commercial fact without evidence" contract the seed enforces, applied
to the independently sourced catalogue). Prints a summary either way.

Connection: $DATABASE_URL ('+psycopg' driver token tolerated).
"""
from __future__ import annotations

import os
import sys

import psycopg

# (label, SQL returning the offending rows for published robots lacking evidence)
GAP_QUERIES = {
    # G2 demands evidence for an ASSERTED maturity. `UNKNOWN` asserts nothing —
    # it is the explicit "not yet verified" value — so it is the one status with
    # nothing for evidence to support. Every other value, ANNOUNCED included,
    # keeps its obligation in full: the exclusion is `<> 'UNKNOWN'`, never a
    # relaxation of the rule itself.
    "commercial_status": """
        SELECT r.slug
        FROM robot r
        WHERE r.is_published
          AND r.commercial_status <> 'UNKNOWN'
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='COMMERCIAL_STATUS' AND e.subject_id=r.id)
    """,
    "pricing_offer": """
        SELECT r.slug
        FROM robot r JOIN pricing_offer p ON p.robot_id = r.id
        WHERE r.is_published
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='PRICING_OFFER' AND e.subject_id=p.id)
    """,
    "availability_offer": """
        SELECT r.slug
        FROM robot r JOIN availability_offer a ON a.robot_id = r.id
        WHERE r.is_published
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='AVAILABILITY_OFFER' AND e.subject_id=a.id)
    """,
    # A MANUFACTURER_ESTIMATE (migration 0020/0021) is a positive commercial fact asserted
    # from the manufacturer's own publication, so it needs MANUFACTURER evidence whether or
    # not the robot is published: it is never a bare number.
    "pricing_offer (MANUFACTURER_ESTIMATE needs manufacturer evidence)": """
        SELECT r.slug
        FROM robot r JOIN pricing_offer p ON p.robot_id = r.id
        WHERE p.price_type = 'MANUFACTURER_ESTIMATE'
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='PRICING_OFFER' AND e.subject_id=p.id
                            AND e.source_type IN ('MANUFACTURER_SITE','MANUFACTURER_STORE')
                            AND e.source_url IS NOT NULL AND e.excerpt IS NOT NULL)
    """,
    "deployment": """
        SELECT r.slug
        FROM robot r JOIN deployment d ON d.robot_id = r.id
        WHERE r.is_published
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='DEPLOYMENT' AND e.subject_id=d.id)
    """,
}


def _manufacturer_claim_gap(condition: str, field: str) -> str:
    """Manufacturers asserting `condition` with no MANUFACTURER evidence row for `field`."""
    return f"""
        SELECT m.slug
        FROM manufacturer m
        WHERE {condition}
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='MANUFACTURER' AND e.subject_id=m.id
                            AND '{field}' = ANY(e.claim_fields))
    """


GAP_QUERIES.update({
    # Same UNKNOWN exclusion as robot commercial_status above.
    "manufacturer.deployment_status": _manufacturer_claim_gap(
        "m.deployment_status IS NOT NULL AND m.deployment_status <> 'UNKNOWN'",
        "deployment_status",
    ),
    # FALSE is a claim ("this entity is not listed"), so it needs a source as
    # much as TRUE does; only NULL (unknown) is free.
    "manufacturer.is_public_company": _manufacturer_claim_gap(
        "m.is_public_company IS NOT NULL", "is_public_company"
    ),
    "manufacturer.parent_company": _manufacturer_claim_gap(
        "m.parent_company IS NOT NULL", "parent_company"
    ),
})


# Use-case coverage (docs/audit/USE_CASE_ENRICHMENT_REVIEW_2026-10-08.md). A published
# robot that is commercially accessible -- the canonical predicate: a current NEW
# availability offer for which commercially_accessible() holds, exactly as
# robot_commercial_snapshot.is_obtainable computes it -- should be reachable from at
# least one use-case page. REPORTED on every run; it fails the run only with
# --enforce-use-case-coverage, which stays off until the owner has approved and
# imported the enrichment. A robot with no defensible use case is an evidence gap,
# never a reason to invent a fit.
USE_CASE_COVERAGE_FLAG = "--enforce-use-case-coverage"
USE_CASE_COVERAGE_GAP_SQL = """
    SELECT r.slug
    FROM robot r JOIN robot_commercial_snapshot s ON s.id = r.id
    WHERE r.is_published AND s.is_obtainable
      AND NOT EXISTS (SELECT 1 FROM use_case_fit f WHERE f.robot_id = r.id)
"""


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")

    with psycopg.connect(normalize_url(url)) as conn:
        conn.execute("SET search_path TO humanoid, public")

        def scalar(sql: str, *args) -> int:
            return conn.execute(sql, args).fetchone()[0]

        robots_total = scalar("SELECT count(*) FROM robot")
        robots_pub = scalar("SELECT count(*) FROM robot WHERE is_published")
        pricing = scalar("SELECT count(*) FROM pricing_offer")
        availability = scalar("SELECT count(*) FROM availability_offer")
        deployments = scalar("SELECT count(*) FROM deployment")
        evidence = scalar("SELECT count(*) FROM evidence_source")
        verified = scalar("SELECT count(*) FROM evidence_source WHERE confidence='VERIFIED'")
        manufacturers = scalar("SELECT count(*) FROM manufacturer")
        manufacturer_sources = scalar(
            "SELECT count(*) FROM evidence_source WHERE subject_type='MANUFACTURER'"
        )

        print(
            f"catalogue summary: robots={robots_total} (published={robots_pub}) "
            f"pricing_offers={pricing} availability_offers={availability} "
            f"deployments={deployments} evidence_rows={evidence} verified={verified} "
            f"manufacturers={manufacturers} manufacturer_sources={manufacturer_sources}"
        )

        gaps: dict[str, list[str]] = {}
        for label, sql in GAP_QUERIES.items():
            offenders = sorted({row[0] for row in conn.execute(sql).fetchall()})
            if offenders:
                gaps[label] = offenders

        # MEDIA-01 imagery gate. Display-eligibility mirrors RobotImage.is_display_eligible
        # (docs/09_MEDIA_CONTRACT.md section 4): (identity VERIFIED OR a valid
        # representative-image exception) AND rights <> RESTRICTED AND (rights
        # PERMITTED/ATTRIBUTION_REQUIRED OR usage_basis OFFICIAL_MANUFACTURER_MEDIA /
        # OWNER_APPROVED_DISPLAY). Every display-eligible image must carry provenance
        # (source_url + source_name), and an ATTRIBUTION_REQUIRED image must carry
        # attribution. (The DB enum already forbids a GENERATED source outright.)
        eligible_sql = (
            "(identity_status = 'VERIFIED' "
            " OR (is_representative AND usage_basis = 'OWNER_APPROVED_DISPLAY' "
            "     AND btrim(coalesce(representative_note, '')) <> '')) "
            "AND rights_status <> 'RESTRICTED' "
            "AND (rights_status IN ('PERMITTED','ATTRIBUTION_REQUIRED') "
            "     OR usage_basis IN ('OFFICIAL_MANUFACTURER_MEDIA', 'OWNER_APPROVED_DISPLAY')) "
            "AND (NOT is_representative OR btrim(coalesce(representative_note, '')) <> '')"
        )
        media_offenders = sorted({
            row[0] for row in conn.execute(
                f"""
                SELECT r.slug
                FROM robot_image i JOIN robot r ON r.id = i.robot_id
                WHERE ({eligible_sql})
                  AND (
                        i.source_url IS NULL OR i.source_name IS NULL
                     OR (i.rights_status = 'ATTRIBUTION_REQUIRED' AND i.attribution IS NULL)
                  )
                """
            ).fetchall()
        })
        images_total = scalar("SELECT count(*) FROM robot_image")
        images_eligible = scalar(f"SELECT count(*) FROM robot_image WHERE {eligible_sql}")
        print(
            f"imagery summary (MEDIA-01): robot_images={images_total} "
            f"display_eligible={images_eligible}"
        )

        coverage_gaps = sorted(
            row[0] for row in conn.execute(USE_CASE_COVERAGE_GAP_SQL).fetchall()
        )
        accessible = scalar(
            "SELECT count(*) FROM robot r JOIN robot_commercial_snapshot s ON s.id = r.id "
            "WHERE r.is_published AND s.is_obtainable"
        )
        print(
            f"use-case coverage: commercially_accessible={accessible} "
            f"without_use_case={len(coverage_gaps)}"
            + (f" ({', '.join(coverage_gaps)})" if coverage_gaps else "")
        )

    if gaps:
        print("\nG2 VIOLATION — commercial fact(s) without the evidence they require:")
        for label, slugs in gaps.items():
            print(f"  {label}: {', '.join(slugs)}")
        sys.exit(1)

    if media_offenders:
        print("\nMEDIA-01 VIOLATION — display-eligible image(s) lacking provenance/attribution:")
        print(f"  {', '.join(media_offenders)}")
        sys.exit(1)

    if coverage_gaps and USE_CASE_COVERAGE_FLAG in sys.argv[1:]:
        print("\nUSE-CASE COVERAGE VIOLATION — commercially accessible robot(s) with no use case:")
        print(f"  {', '.join(coverage_gaps)}")
        sys.exit(1)

    print("G2 OK: every published commercial fact carries an evidence_source row.")
    print("G2 OK: every asserted manufacturer status, listing and parent claim is attributed.")
    print("MEDIA-01 OK: every display-eligible image carries provenance (+ attribution).")


if __name__ == "__main__":
    main()
