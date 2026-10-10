// Compare /compare?ids=slug1,slug2[,slug3,slug4] — URL-driven decision surface.
// WS4 extends the WS3 base matrix with URL-canonical view state:
//   &ref=<slug>     reference robot for factual numeric deltas
//   &units=imperial Metric/Imperial presentation toggle (presentation only)
//   &view=evidence  deep fact-level evidence comparison
//   &region=<code> / &offered_in=<code>  optional Buyer context (UX-03): annotates
//                   recorded offers with the catalogue filters' own two questions
// The URL is the single source of truth — every bit of view state round-trips
// through reload / back / forward / share, and device-local Saved Views simply
// reconstruct one of these URLs (localStorage only; no persistence/API/schema).
//
// Facts come from /api/robots/compare (the API supplies normalized `rows` +
// full RobotDetail objects). Nothing here is fabricated; UNKNOWN stays UNKNOWN
// and QUOTE_ONLY ≠ UNKNOWN. All comparison SEMANTICS live in
// lib/comparison-policy.ts (tested); this page only fetches + delegates.
import Link from "next/link";

import { compareRobots, getRegionScope } from "@/lib/api-client";
import {
  OFFER_MARKETS,
  parseContextCode,
  REGIONS,
  type BuyerContext,
} from "@/lib/buyer-context";
import { isUnitSystem, type UnitSystem } from "@/lib/units";
import type { CompareResponse, ResolvedFact } from "@/lib/types";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { CompareView } from "./CompareView";

export const dynamic = "force-dynamic";

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

// WS8.5 / R22 — specific per-route title (static; not query-state-dependent).
export const metadata = {
  title: "Compare Robots",
  description:
    "Side-by-side comparison of humanoid robots across capabilities, pricing and availability.",
};

// G4: send the client only what it renders. The view shows a scoped state (uniform / varies /
// partial / conflict) from `rows[].resolved`; a product value or a truly unknown property renders
// from `values` exactly as before, so those entries (and the per-robot `resolved_facts` copy) are
// not delivered. Pure selection by the API-provided state; nothing is resolved here.
function slimForClient(data: CompareResponse): CompareResponse {
  const scoped = (f: ResolvedFact) => f.state !== "PRODUCT_VALUE" && f.state !== "UNKNOWN";
  return {
    robots: data.robots.map((r) => ({ ...r, resolved_facts: undefined })),
    rows: data.rows.map((row) => ({
      ...row,
      resolved: row.resolved
        ? Object.fromEntries(Object.entries(row.resolved).filter(([, f]) => scoped(f)))
        : row.resolved,
    })),
  };
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{
    ids?: string | string[];
    ref?: string | string[];
    units?: string | string[];
    view?: string | string[];
    region?: string | string[];
    offered_in?: string | string[];
  }>;
}) {
  const sp = await searchParams;
  const idsRaw = Array.isArray(sp.ids) ? sp.ids.join(",") : (sp.ids ?? "");
  const ids = idsRaw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const data = ids.length >= 2 ? await compareRobots(ids) : null;

  // Parse view state defensively — unknown values fall back to defaults.
  const unitsParam = first(sp.units);
  const units: UnitSystem = isUnitSystem(unitsParam) ? unitsParam : "metric";
  const viewParam = first(sp.view);
  const view = viewParam === "evidence" ? "evidence" : "matrix";
  const ref = first(sp.ref) ?? null;

  // Buyer context. A value outside the offered lists is ignored (unset), and the
  // scope itself comes from the API's canonical region resolvers — this page
  // derives no geography. No scope (unknown code) leaves that question unasked.
  const region = parseContextCode(first(sp.region), REGIONS);
  const market = parseContextCode(first(sp.offered_in), OFFER_MARKETS);
  const [regionScope, marketScope] = data
    ? await Promise.all([
        region ? getRegionScope(region) : null,
        market ? getRegionScope(market) : null,
      ])
    : [null, null];
  const context: BuyerContext = {
    region: regionScope ? region : null,
    market: marketScope ? market : null,
    applicable: regionScope?.applicable ?? null,
    marketCodes: marketScope?.market ?? null,
  };

  return (
    <>
      <SystemHeader
        title="COMPARISON MATRIX"
        fields={[
          { value: data ? data.robots.length : ids.length, label: "" },
          { value: "PLATFORMS SELECTED", label: "" },
        ]}
      />
      <div className="wrap">
        <SiteNav active="compare" />

        <div className="pagebar">
          <div>
            <SectionIndex>COMPARE — SIDE BY SIDE</SectionIndex>
            <h1>Comparison matrix</h1>
          </div>
        </div>

        {!data ? (
          <div className="empty-state" style={{ marginBottom: "var(--ho-sp-8)" }}>
            <p>
              Add robots to compare from the{" "}
              <Link href="/robots" style={{ textDecoration: "underline" }}>
                catalogue
              </Link>
              . Select <strong>2 to 4 robots</strong> using <em>Compare +</em> to see them side by
              side.
            </p>
          </div>
        ) : (
          <CompareView
            // G4: the scoped resolution travels once, on the rows (`rows[].resolved`). The per-robot
            // copy in `robots[].resolved_facts` is not needed by this view, and sending it twice
            // would only grow the delivered document (perf budget).
            data={slimForClient(data)}
            ids={data.robots.map((r) => r.slug)}
            state={{ ref, units, view, region: context.region, market: context.market }}
            context={context}
          />
        )}
      </div>
    </>
  );
}
