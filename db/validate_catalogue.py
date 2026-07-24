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
    "commercial_status": """
        SELECT r.slug
        FROM robot r
        WHERE r.is_published
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
    "deployment": """
        SELECT r.slug
        FROM robot r JOIN deployment d ON d.robot_id = r.id
        WHERE r.is_published
          AND NOT EXISTS (SELECT 1 FROM evidence_source e
                          WHERE e.subject_type='DEPLOYMENT' AND e.subject_id=d.id)
    """,
}


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

        print(
            f"catalogue summary: robots={robots_total} (published={robots_pub}) "
            f"pricing_offers={pricing} availability_offers={availability} "
            f"deployments={deployments} evidence_rows={evidence} verified={verified}"
        )

        gaps: dict[str, list[str]] = {}
        for label, sql in GAP_QUERIES.items():
            offenders = sorted({row[0] for row in conn.execute(sql).fetchall()})
            if offenders:
                gaps[label] = offenders

    if gaps:
        print("\nG2 VIOLATION — published commercial fact(s) without evidence:")
        for label, slugs in gaps.items():
            print(f"  {label}: {', '.join(slugs)}")
        sys.exit(1)

    print("G2 OK: every published commercial fact carries an evidence_source row.")


if __name__ == "__main__":
    main()
