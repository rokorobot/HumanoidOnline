// Compare /compare?ids=slug1,slug2[,slug3,slug4] — URL-driven decision surface.
// WS4 extends the WS3 base matrix with URL-canonical view state:
//   &ref=<slug>     reference robot for factual numeric deltas
//   &units=imperial Metric/Imperial presentation toggle (presentation only)
//   &view=evidence  deep fact-level evidence comparison
// The URL is the single source of truth — every bit of view state round-trips
// through reload / back / forward / share, and device-local Saved Views simply
// reconstruct one of these URLs (localStorage only; no persistence/API/schema).
//
// Facts come from /api/robots/compare (the API supplies normalized `rows` +
// full RobotDetail objects). Nothing here is fabricated; UNKNOWN stays UNKNOWN
// and QUOTE_ONLY ≠ UNKNOWN. All comparison SEMANTICS live in
// lib/comparison-policy.ts (tested); this page only fetches + delegates.
import Link from "next/link";

import { compareRobots } from "@/lib/api-client";
import { isUnitSystem, type UnitSystem } from "@/lib/units";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { CompareView } from "./CompareView";

export const dynamic = "force-dynamic";

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{
    ids?: string | string[];
    ref?: string | string[];
    units?: string | string[];
    view?: string | string[];
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
            data={data}
            ids={data.robots.map((r) => r.slug)}
            state={{ ref, units, view }}
          />
        )}
      </div>
    </>
  );
}
