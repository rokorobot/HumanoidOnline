// Compare /compare?ids=slug1,slug2[,slug3,slug4] — URL-driven, disciplined band.
// Consumes /api/robots/compare. The API supplies the normalized comparison
// `rows`; price/availability/deployment/evidence display rows are assembled from
// the returned RobotDetail objects (facts from the API — nothing fabricated).
// "best-in-row" only for objectively comparable numeric metrics, never for
// maturity/evidence/autonomy/availability. QUOTE_ONLY ≠ UNKNOWN preserved.
import Link from "next/link";

import { compareRobots } from "@/lib/api-client";
import { modeLabel } from "@/lib/format";
import type { CompareRow, PricingOffer, RobotDetail } from "@/lib/types";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { deriveModelCode } from "@/components/RobotCard";
import { PriceStateLong } from "@/components/PricingState";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { GraphicMarker } from "@/components/GraphicMarker";

export const dynamic = "force-dynamic";

const CONF_RANK: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3, VERIFIED: 4 };
// price_type preference for the headline price (mirrors the API list serializer).
const PRICE_TYPE_RANK: Record<string, number> = {
  PUBLIC: 0,
  FROM: 1,
  ESTIMATED: 2,
  RANGE: 3,
  QUOTE_ONLY: 4,
};
// Availability modes shown as obtainability rows (raw facts, not a derived flag).
const AVAIL_MODES = ["PURCHASE", "RENTAL", "LEASE", "RAAS", "PILOT", "DEVELOPER"];
// Numeric rows where higher is objectively better -> eligible for best-in-row.
const HIGHER_BETTER = new Set([
  "payload_kg",
  "walk_speed_ms",
  "runtime_minutes",
  "degrees_of_freedom",
  "hand_dof",
]);

function headlinePrice(offers: PricingOffer[]) {
  if (offers.length === 0) return null;
  const sorted = [...offers].sort((a, b) => {
    const at = a.transaction_type === "PURCHASE" ? 0 : 1;
    const bt = b.transaction_type === "PURCHASE" ? 0 : 1;
    if (at !== bt) return at - bt;
    return (
      (PRICE_TYPE_RANK[a.price_type] ?? 9) - (PRICE_TYPE_RANK[b.price_type] ?? 9)
    );
  });
  const p = sorted[0];
  return {
    type: p.price_type,
    amount: p.price,
    amount_min: p.price_min,
    amount_max: p.price_max,
    currency: p.currency,
    billing_period: p.billing_period,
  };
}

function comparablePrice(offers: PricingOffer[]): number | null {
  const pd = headlinePrice(offers);
  if (!pd) return null;
  if (pd.type === "QUOTE_ONLY") return null;
  return pd.amount ?? pd.amount_min ?? null;
}

function strongestConf(robot: RobotDetail): string | null {
  const evs = [
    ...robot.pricing_offers.map((p) => p.evidence),
    ...robot.availability_offers.map((a) => a.evidence),
    ...robot.deployments.map((d) => d.evidence),
  ].filter(Boolean);
  let best: string | null = null;
  let rank = 0;
  for (const e of evs) {
    const eff = e!.confidence === "VERIFIED" && !e!.verified_at ? "HIGH" : e!.confidence;
    const r = CONF_RANK[eff] ?? 0;
    if (r > rank) {
      rank = r;
      best = eff;
    }
  }
  return best;
}

function availabilityFor(robot: RobotDetail, mode: string): string | null {
  const rows = robot.availability_offers.filter((a) => a.transaction_type === mode);
  if (rows.length === 0) return null;
  // Prefer an accessible status if present; otherwise show the first.
  const accessible = rows.find(
    (a) =>
      a.availability_status !== "NOT_AVAILABLE" &&
      a.availability_status !== "DISCONTINUED",
  );
  return (accessible ?? rows[0]).availability_status;
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string | string[] }>;
}) {
  const sp = await searchParams;
  const idsRaw = Array.isArray(sp.ids) ? sp.ids.join(",") : (sp.ids ?? "");
  const ids = idsRaw.split(",").map((s) => s.trim()).filter(Boolean);
  const data = ids.length >= 2 ? await compareRobots(ids) : null;

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
              Select <strong>2 to 4 robots</strong> to compare. Add them from the{" "}
              <Link href="/robots" style={{ textDecoration: "underline" }}>
                catalogue
              </Link>{" "}
              using <em>Compare +</em>, or pass slugs directly, e.g.{" "}
              <code>/compare?ids=unitree-g1,agility-digit</code>.
            </p>
          </div>
        ) : (
          <CompareMatrix data={data} />
        )}
      </div>
      <SiteFooter />
    </>
  );
}

function CompareMatrix({ data }: { data: { robots: RobotDetail[]; rows: CompareRow[] } }) {
  const robots = data.robots;
  const slugs = robots.map((r) => r.slug);
  const rowsByGroup = new Map<string, CompareRow[]>();
  for (const row of data.rows) {
    const list = rowsByGroup.get(row.group) ?? [];
    list.push(row);
    rowsByGroup.set(row.group, list);
  }

  const cols = `190px repeat(${robots.length}, 1fr)`;

  return (
    <>
      <div className="selrow-wrap">
        <div className="selrow" style={{ gridTemplateColumns: cols }}>
          <div className="cell rowlab">
            <span className="ho-syslabel">Robots ×{robots.length}</span>
          </div>
          {robots.map((r) => (
            <div className="cell robotpick" key={r.slug}>
              <div className="lockup">
                <Link className="name" href={`/robots/${r.slug}`}>
                  {r.name}
                </Link>
                <span className="code">
                  {deriveModelCode(r.slug, r.manufacturer.slug)}
                </span>
              </div>
              <div className="mfr">
                {r.manufacturer.name}
                {r.manufacturer.country ? ` · ${r.manufacturer.country}` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="cmp-scroll">
        <table className="cmatrix" style={{ minWidth: 640 }}>
          <colgroup>
            <col className="lab" />
            {robots.map((r) => (
              <col key={r.slug} />
            ))}
          </colgroup>
          <tbody>
            {/* ① COMMERCIAL — maturity · obtainability */}
            <GroupHeader span={robots.length + 1}>
              ① Commercial — maturity · obtainability
            </GroupHeader>
            {(rowsByGroup.get("commercial") ?? []).map((row) => (
              <ApiRow key={row.key} row={row} slugs={slugs} />
            ))}
            <tr>
              <th className="rowlab">Price</th>
              {robots.map((r) => {
                const best = bestPrice(robots, r);
                return (
                  <td className={`cell${best ? " best" : ""}`} key={r.slug}>
                    <PriceStateLong price={headlinePrice(r.pricing_offers)} variant="long" />
                  </td>
                );
              })}
            </tr>
            {AVAIL_MODES.map((mode) => {
              // Only show a mode row if at least one robot has an offer for it.
              const any = robots.some((r) => availabilityFor(r, mode) !== null);
              if (!any) return null;
              return (
                <tr key={mode}>
                  <th className="rowlab">{modeLabel(mode)}</th>
                  {robots.map((r) => {
                    const status = availabilityFor(r, mode);
                    return status ? (
                      <td className="cell" key={r.slug}>
                        {status}
                      </td>
                    ) : (
                      <td className="cell na" key={r.slug}>
                        —
                      </td>
                    );
                  })}
                </tr>
              );
            })}

            {/* ② PHYSICAL */}
            <GroupHeader span={robots.length + 1}>② Physical</GroupHeader>
            {(rowsByGroup.get("physical") ?? []).map((row) => (
              <ApiRow key={row.key} row={row} slugs={slugs} />
            ))}

            {/* ③ Manipulation · intelligence · developer */}
            <GroupHeader span={robots.length + 1}>
              ③ Manipulation · intelligence · developer
            </GroupHeader>
            {[
              ...(rowsByGroup.get("manipulation") ?? []),
              ...(rowsByGroup.get("intelligence") ?? []),
              ...(rowsByGroup.get("developer") ?? []),
            ].map((row) => (
              <ApiRow key={row.key} row={row} slugs={slugs} />
            ))}

            {/* ④ Deployment — evidence */}
            <GroupHeader span={robots.length + 1}>④ Deployment — evidence</GroupHeader>
            <tr>
              <th className="rowlab">Deployments</th>
              {robots.map((r) => {
                const n = r.deployments.length;
                const best = bestDeployments(robots, r);
                return (
                  <td className={`cell${best ? " best" : ""}${n === 0 ? " unk" : ""}`} key={r.slug}>
                    {n > 0 ? n : <span className="hatch">UNKNOWN</span>}
                  </td>
                );
              })}
            </tr>
            <tr>
              <th className="rowlab">Evidence confidence</th>
              {robots.map((r) => {
                const conf = strongestConf(r);
                return (
                  <td className="cell" key={r.slug}>
                    {conf ? (
                      <span className={conf === "VERIFIED" ? "v" : ""}>{conf}</span>
                    ) : (
                      <span className="hatch">UNKNOWN</span>
                    )}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="legend">
        <span>
          <GraphicMarker signal /> best-in-row (numeric metrics only)
        </span>
        <span>— = not applicable / no offer in this mode</span>
        <span>
          <span style={{ border: "1px dashed var(--ho-grey-400)", padding: "0 5px" }}>
            UNKNOWN
          </span>{" "}
          = no data (never 0/false)
        </span>
        <span>
          <span className="ho-badge ho-badge--caution" style={{ padding: "1px 6px" }}>
            QUOTE
          </span>{" "}
          = price on request ≠ unknown
        </span>
      </div>
    </>
  );
}

function GroupHeader({ span, children }: { span: number; children: React.ReactNode }) {
  return (
    <tr className="grouprow">
      <th colSpan={span}>{children}</th>
    </tr>
  );
}

// Render an API-provided comparison row. best-in-row applies ONLY to numeric
// keys where higher is objectively better; never to enums/booleans.
function ApiRow({ row, slugs }: { row: CompareRow; slugs: string[] }) {
  const numericBest = HIGHER_BETTER.has(row.key) ? bestNumeric(row) : null;
  return (
    <tr>
      <th className="rowlab">{row.label}</th>
      {slugs.map((slug) => {
        const v = row.values[slug];
        if (v == null) {
          return (
            <td className="cell unk" key={slug}>
              <span className="hatch">UNKNOWN</span>
            </td>
          );
        }
        const isBest = numericBest != null && v === numericBest;
        const display = typeof v === "boolean" ? (v ? "YES" : "NO") : String(v);
        return (
          <td className={`cell${isBest ? " best" : ""}`} key={slug}>
            {display}
          </td>
        );
      })}
    </tr>
  );
}

function bestNumeric(row: CompareRow): number | null {
  const nums = Object.values(row.values).filter(
    (v): v is number => typeof v === "number",
  );
  if (nums.length < 2) return null;
  return Math.max(...nums);
}

function bestPrice(robots: RobotDetail[], target: RobotDetail): boolean {
  const prices = robots
    .map((r) => comparablePrice(r.pricing_offers))
    .filter((n): n is number => n != null);
  if (prices.length < 2) return false;
  const min = Math.min(...prices);
  return comparablePrice(target.pricing_offers) === min;
}

function bestDeployments(robots: RobotDetail[], target: RobotDetail): boolean {
  const counts = robots.map((r) => r.deployments.length);
  const max = Math.max(...counts);
  return max > 0 && target.deployments.length === max && counts.filter((c) => c === max).length === 1;
}
