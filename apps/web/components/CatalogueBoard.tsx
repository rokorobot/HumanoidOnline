// DR-UI2 — catalogue Board view: a denser reading of the SAME list items the cards
// show (RobotListItem). Nothing is hidden or re-derived: maturity, obtainable modes
// (canonical available_modes), the headline price with its seller/region/terms, and
// the three card metrics, each with its explicit UNKNOWN state.
import Link from "next/link";

import { AvailabilityBadge } from "@/components/AvailabilityState";
import { CompareLink } from "@/components/CompareLink";
import { PriceStateCard } from "@/components/PricingState";
import { RobotThumb } from "@/components/RobotThumb";
import { StatusBracket } from "@/components/StatusBadge";
import { modeLabel, specValue } from "@/lib/format";
import { mobilityLabel } from "@/lib/labels";
import type { RobotListItem } from "@/lib/types";

function Spec({
  value,
  unit,
  rawEnum,
}: {
  value: number | string | null | undefined;
  unit?: string;
  rawEnum?: string | null;
}) {
  const r = specValue(value, unit);
  return (
    <span
      className={r.unknown ? "cb-spec unk" : "cb-spec"}
      {...(rawEnum && !r.unknown ? { "data-enum": rawEnum } : {})}
    >
      {r.label}
    </span>
  );
}

export function CatalogueBoard({
  robots,
  compareHref,
  compareSlugs,
}: {
  robots: RobotListItem[];
  compareHref: (slug: string) => string;
  compareSlugs: string[];
}) {
  return (
    <div className="cat-board" tabIndex={0} role="group" aria-label="Robots, board view">
      <table>
        <thead>
          <tr>
            <th scope="col">Robot</th>
            <th scope="col">Maturity</th>
            <th scope="col">Obtainable as</th>
            <th scope="col">Headline price</th>
            <th scope="col">Height</th>
            <th scope="col">Payload</th>
            <th scope="col">Mobility</th>
            <th scope="col">
              <span className="sr-only">Compare</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {robots.map((r) => {
            const inCompare = compareSlugs.includes(r.slug);
            return (
              <tr key={r.slug}>
                <td>
                  <div className="cb-robot">
                    <RobotThumb slug={r.slug} name={r.name} image={r.primary_image} />
                    <div>
                      <Link className="cb-name" href={`/robots/${r.slug}`}>
                        {r.name}
                      </Link>
                      <span className="cb-mfr">{r.manufacturer.name}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <StatusBracket status={r.commercial_status} />
                </td>
                <td>
                  {r.available_modes.length > 0 ? (
                    <span className="cb-modes" data-enum={r.available_modes.join(",")}>
                      {r.available_modes.map((m) => (
                        <span key={m} className="ob-flap">
                          {modeLabel(m)}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <AvailabilityBadge modes={r.available_modes} />
                  )}
                </td>
                <td>
                  <PriceStateCard price={r.price_display} />
                </td>
                <td>
                  <Spec value={r.height_cm} unit="cm" />
                </td>
                <td>
                  <Spec value={r.payload_kg} unit="kg" />
                </td>
                <td>
                  <Spec value={r.mobility ? mobilityLabel(r.mobility) : null} rawEnum={r.mobility} />
                </td>
                <td>
                  <CompareLink
                    className="cmp"
                    href={compareHref(r.slug)}
                    ariaLabel={inCompare ? `Remove ${r.name} from compare` : `Add ${r.name} to compare`}
                  >
                    {inCompare ? "In compare ✓" : "Compare +"}
                  </CompareLink>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
