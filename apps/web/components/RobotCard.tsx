// RobotCard (§6.11) — the catalogue/summary unit. Proves the three dimensions
// survive repetition: identity lockup (serif name + grotesk code) · manufacturer
// · StatusBadge (Dim 1) · key Metrics · PricingState (Dim 2 price) ·
// AvailabilityState summary · optional Compare affordance. SHORT state labels.
import Link from "next/link";

import type { RobotListItem } from "@/lib/types";
import { AvailabilityBadge } from "./AvailabilityState";
import { DotMatrix } from "./GraphicMarker";
import { MachineCode } from "./MachineCode";
import { Metric } from "./Metric";
import { PriceStateCard } from "./PricingState";
import { StatusBracket } from "./StatusBadge";

// Derive a short machine model token from the canonical slug (presentational —
// derived from a real identifier, not a fabricated fact).
export function deriveModelCode(slug: string, mfrSlug: string): string {
  let token = slug;
  if (mfrSlug && slug.startsWith(`${mfrSlug}-`)) {
    token = slug.slice(mfrSlug.length + 1);
  } else if (slug.includes("-")) {
    token = slug.split("-").slice(1).join("-");
  }
  return token.replace(/-/g, " ").toUpperCase();
}

export function RobotCard({
  robot,
  compareHref,
  inCompare = false,
}: {
  robot: RobotListItem;
  compareHref?: string;
  inCompare?: boolean;
}) {
  const detailHref = `/robots/${robot.slug}`;
  const code = deriveModelCode(robot.slug, robot.manufacturer.slug);
  // Live/active RaaS deployments earn the signal dot; nothing else does.
  const live = robot.commercial_status === "RAAS_DEPLOYMENT";
  return (
    <article className="rcard">
      <div className="rcard-top">
        <MachineCode>{robot.manufacturer.name.toUpperCase()}</MachineCode>
        <DotMatrix signal={live} />
      </div>
      {/* MEDIA-01: verified real image (same image truth as Robot Detail) in the
          smaller catalogue format, or an explicit unavailable tile — never an
          invented/placeholder robot picture. */}
      <Link className="rcard-media" href={detailHref} aria-label={`${robot.name} image`}>
        {robot.primary_image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="rcard-media__img"
            src={robot.primary_image.image_url}
            alt={robot.name}
            loading="lazy"
          />
        ) : (
          <span className="rcard-media__unavailable">IMAGE UNAVAILABLE</span>
        )}
      </Link>
      <div className="rcard-body">
        <div>
          <div className="lockup">
            <Link className="name" href={detailHref}>
              {robot.name}
            </Link>
            {code && code !== robot.name.toUpperCase() && (
              <span className="code">{code}</span>
            )}
          </div>
          <div className="mfr">{robot.manufacturer.name}</div>
        </div>
        <StatusBracket status={robot.commercial_status} />
        <div className="metrics">
          <Metric label="Payload" value={robot.payload_kg} unit="kg" />
          <Metric label="Height" value={robot.height_cm} unit="cm" />
          <Metric label="Mobility" value={robot.mobility} />
        </div>
      </div>
      <div className="rcard-foot">
        <PriceStateCard price={robot.price_display} />
        <div className="foot-actions">
          <AvailabilityBadge modes={robot.available_modes} />
          {compareHref ? (
            // Emergency Compare Traffic Containment — every card on a catalogue
            // page carries a DISTINCT compareHref (one toggled slug apart from
            // every other card's), so on a full-page result set this is up to
            // ~100 combinatorially-different /robots?compare= URLs at once.
            // Next's default Link prefetch fires one of these per card as it
            // enters the viewport with no user action — confirmed the primary
            // amplification source in the 2026-08-22 19:53-19:55 CEST incident.
            // Real navigation on click is unaffected; only the automatic
            // viewport prefetch is disabled.
            <Link
              className="cmp"
              href={compareHref}
              prefetch={false}
              aria-label={inCompare ? "Remove from compare" : "Add to compare"}
            >
              {inCompare ? "In compare ✓" : "Compare +"}
            </Link>
          ) : (
            <Link className="cmp" href={detailHref}>
              Detail →
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}
