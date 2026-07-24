"use client";

// ============================================================================
// WS4 — Advanced compare / decision. Client shell that EXTENDS the WS3 base
// comparison matrix (it is not a redesign): same grouped matrix, sticky row
// labels, best-in-row, legend. Adds — driven entirely by the canonical URL:
//   • Metric/Imperial presentation toggle (units=)         — presentation only
//   • Reference robot with factual numeric deltas (ref=)   — no verdicts
//   • Matrix / Evidence view switch (view=)                — deep evidence
//   • Share link + device-local Saved Views (localStorage) — no persistence/API
//
// All comparison SEMANTICS live in lib/comparison-policy.ts (tested). This file
// only renders the answers. UNKNOWN stays UNKNOWN; QUOTE_ONLY ≠ UNKNOWN.
// ============================================================================
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { modeLabel } from "@/lib/format";
import type { CompareResponse, CompareRow, PricingOffer, RobotDetail } from "@/lib/types";
import {
  bestInRow,
  computePriceLeader,
  headlineOffer,
  isBestInRowEligible,
  metricDelta,
  policyFor,
  priceDelta,
  type MetricDelta,
  type NormalizedOffer,
  type PriceDelta,
} from "@/lib/comparison-policy";
import { displayMetricValue, isUnitSystem, type UnitSystem } from "@/lib/units";
import {
  deleteView,
  loadSavedViews,
  saveView,
  type SavedView,
} from "@/lib/saved-views";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { EvidenceStamp } from "@/components/EvidenceStamp";
import { GraphicMarker } from "@/components/GraphicMarker";
import { deriveModelCode } from "@/components/RobotCard";
import { PriceStateLong } from "@/components/PricingState";

// Best-in-row framing — FROZEN copy. Mirrors the comment in comparison-policy.ts.
const BEST_IN_ROW_FRAMING =
  "Best-in-row identifies a metric-specific numeric leader only. It is not a robot ranking, recommendation, fit score, or purchase recommendation.";

const AVAIL_MODES = ["PURCHASE", "RENTAL", "LEASE", "RAAS", "PILOT", "DEVELOPER"];
const CONF_RANK: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3, VERIFIED: 4 };

type ViewMode = "matrix" | "evidence";

interface ViewState {
  ref: string | null;
  units: UnitSystem;
  view: ViewMode;
}

// ── URL is canonical ─────────────────────────────────────────────────────────
// A saved view / share link is nothing more than this string. Params are only
// emitted when they differ from the default so the base URL stays clean.
export function buildCompareUrl(ids: string[], s: ViewState): string {
  const usp = new URLSearchParams();
  usp.set("ids", ids.join(","));
  if (s.ref) usp.set("ref", s.ref);
  if (s.units !== "metric") usp.set("units", s.units);
  if (s.view !== "matrix") usp.set("view", s.view);
  return `/compare?${usp.toString()}`;
}

export function CompareView({
  data,
  ids,
  state,
}: {
  data: CompareResponse;
  ids: string[];
  state: ViewState;
}) {
  const router = useRouter();
  const robots = data.robots;
  const slugs = robots.map((r) => r.slug);
  // A stale ref (slug no longer in the set) is ignored — fail safe.
  const refSlug = state.ref && slugs.includes(state.ref) ? state.ref : null;

  function go(next: Partial<ViewState>) {
    const merged: ViewState = { ...state, ref: refSlug, ...next };
    router.push(buildCompareUrl(ids, merged), { scroll: false });
  }

  return (
    <>
      <CompareToolbar ids={ids} state={{ ...state, ref: refSlug }} onGo={go} />

      <RobotSelectRow robots={robots} refSlug={refSlug} onGo={go} />

      {state.view === "matrix" ? (
        <CompareMatrix data={data} slugs={slugs} units={state.units} refSlug={refSlug} />
      ) : (
        <EvidenceCompare robots={robots} refSlug={refSlug} />
      )}

      <Legend />
    </>
  );
}

// ── Toolbar: units / view / share / save ─────────────────────────────────────
function CompareToolbar({
  ids,
  state,
  onGo,
}: {
  ids: string[];
  state: ViewState;
  onGo: (n: Partial<ViewState>) => void;
}) {
  const router = useRouter();
  const [views, setViews] = useState<SavedView[]>([]);
  const [showSaves, setShowSaves] = useState(false);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [copied, setCopied] = useState(false);

  // localStorage is device-local & client-only — read after mount.
  useEffect(() => {
    setViews(loadSavedViews());
  }, []);

  const currentUrl = buildCompareUrl(ids, state);

  async function share() {
    const abs =
      typeof window !== "undefined" ? window.location.origin + currentUrl : currentUrl;
    try {
      await navigator.clipboard.writeText(abs);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  function commitSave() {
    const next = saveView(name, currentUrl);
    setViews(next);
    setName("");
    setNaming(false);
    setShowSaves(true);
  }

  function apply(v: SavedView) {
    router.push(v.url, { scroll: false });
    setShowSaves(false);
  }

  function remove(n: string) {
    setViews(deleteView(n));
  }

  return (
    <div className="cmp-toolbar">
      <div className="cmp-controls">
        <Segmented
          label="Units"
          value={state.units}
          options={[
            { value: "metric", label: "METRIC" },
            { value: "imperial", label: "IMPERIAL" },
          ]}
          onChange={(v) => onGo({ units: v as UnitSystem })}
        />
        <Segmented
          label="View"
          value={state.view}
          options={[
            { value: "matrix", label: "MATRIX" },
            { value: "evidence", label: "EVIDENCE" },
          ]}
          onChange={(v) => onGo({ view: v as ViewMode })}
        />
      </div>

      <div className="cmp-actions">
        <button type="button" className="btn" onClick={share} aria-live="polite">
          {copied ? "LINK COPIED ✓" : "SHARE LINK"}
        </button>
        {naming ? (
          <span className="cmp-nameform">
            <input
              className="cmp-nameinput"
              aria-label="Saved view name"
              placeholder="Name this view"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitSave();
                if (e.key === "Escape") setNaming(false);
              }}
              autoFocus
            />
            <button type="button" className="btn btn--signal" onClick={commitSave} disabled={!name.trim()}>
              SAVE
            </button>
            <button type="button" className="btn" onClick={() => setNaming(false)}>
              CANCEL
            </button>
          </span>
        ) : (
          <button type="button" className="btn" onClick={() => setNaming(true)}>
            SAVE VIEW
          </button>
        )}
        <button
          type="button"
          className="btn"
          onClick={() => setShowSaves((s) => !s)}
          aria-expanded={showSaves}
        >
          SAVED VIEWS ({views.length})
        </button>
      </div>

      {showSaves && (
        <div className="cmp-saves" data-testid="saved-views">
          {views.length === 0 ? (
            <span className="ho-syslabel">NO SAVED VIEWS ON THIS DEVICE</span>
          ) : (
            <ul>
              {views.map((v) => (
                <li key={v.name}>
                  <button type="button" className="cmp-save-apply" onClick={() => apply(v)}>
                    {v.name}
                  </button>
                  <span className="ho-syslabel">{v.created_at.slice(0, 10)}</span>
                  <button type="button" className="cmp-save-del" onClick={() => remove(v.name)} aria-label={`Delete ${v.name}`}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="ho-syslabel cmp-saves-note">
            SAVED ON THIS DEVICE ONLY (localStorage) — NOT SYNCED, NO ACCOUNT.
          </p>
        </div>
      )}
    </div>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="cmp-seg">
      <span className="ho-syslabel">{label}</span>
      <div className="cmp-seg-btns" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className={`cmp-seg-btn${o.value === value ? " on" : ""}`}
            aria-pressed={o.value === value}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Robot header row + reference selector ────────────────────────────────────
function RobotSelectRow({
  robots,
  refSlug,
  onGo,
}: {
  robots: RobotDetail[];
  refSlug: string | null;
  onGo: (n: Partial<ViewState>) => void;
}) {
  const cols = `190px repeat(${robots.length}, 1fr)`;
  return (
    <div className="selrow-wrap">
      <div className="selrow" style={{ gridTemplateColumns: cols }}>
        <div className="cell rowlab">
          <span className="ho-syslabel">Robots ×{robots.length}</span>
        </div>
        {robots.map((r) => {
          const isRef = r.slug === refSlug;
          return (
            <div className={`cell robotpick${isRef ? " is-ref" : ""}`} key={r.slug}>
              <div className="lockup">
                <Link className="name" href={`/robots/${r.slug}`}>
                  {r.name}
                </Link>
                <span className="code">{deriveModelCode(r.slug, r.manufacturer.slug)}</span>
              </div>
              <div className="mfr">
                {r.manufacturer.name}
                {r.manufacturer.country ? ` · ${r.manufacturer.country}` : ""}
              </div>
              {isRef ? (
                <button
                  type="button"
                  className="cmp-ref-btn on"
                  onClick={() => onGo({ ref: null })}
                >
                  <GraphicMarker signal /> REFERENCE — CLEAR
                </button>
              ) : (
                <button
                  type="button"
                  className="cmp-ref-btn"
                  onClick={() => onGo({ ref: r.slug })}
                >
                  SET AS REFERENCE
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Matrix (base, extended) ──────────────────────────────────────────────────
function CompareMatrix({
  data,
  slugs,
  units,
  refSlug,
}: {
  data: CompareResponse;
  slugs: string[];
  units: UnitSystem;
  refSlug: string | null;
}) {
  const robots = data.robots;
  const rowsByGroup = new Map<string, CompareRow[]>();
  for (const row of data.rows) {
    const list = rowsByGroup.get(row.group) ?? [];
    list.push(row);
    rowsByGroup.set(row.group, list);
  }

  // Price row model (headline offer per robot) + like-for-like leader.
  const headlines = new Map<string, NormalizedOffer | null>(
    robots.map((r) => [r.slug, headlineOffer(r.pricing_offers)]),
  );
  const priceLeader = computePriceLeader(
    robots.map((r) => ({ slug: r.slug, offer: headlines.get(r.slug) ?? null })),
  );
  const priceWinners = new Set(priceLeader.winners);
  const refOffer = refSlug ? headlines.get(refSlug) ?? null : null;

  return (
    <div className="cmp-scroll">
      <table className="cmatrix" style={{ minWidth: 640 }}>
        <colgroup>
          <col className="lab" />
          {robots.map((r) => (
            <col key={r.slug} />
          ))}
        </colgroup>
        <tbody>
          <GroupHeader span={robots.length + 1}>① Commercial — maturity · obtainability</GroupHeader>
          {(rowsByGroup.get("commercial") ?? []).map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} />
          ))}

          {/* Price — leader only when truly like-for-like ("LOWEST COMPARABLE PRICE"). */}
          <tr>
            <th className="rowlab">Price</th>
            {robots.map((r) => {
              const win = priceWinners.has(r.slug);
              const d = priceDelta(refOffer, headlines.get(r.slug) ?? null, r.slug === refSlug);
              return (
                <td className={`cell${win ? " best" : ""}`} key={r.slug}>
                  <PriceStateLong price={headlinePriceDisplay(r.pricing_offers)} variant="long" />
                  {refSlug && <PriceDeltaTag d={d} />}
                </td>
              );
            })}
          </tr>
          {priceLeader.comparable && priceWinners.size > 0 && (
            <tr className="cmp-annot">
              <th className="rowlab" />
              <td className="cell" colSpan={robots.length}>
                <span className="ho-syslabel">
                  <GraphicMarker signal /> LOWEST COMPARABLE PRICE — like-for-like offers only
                  (same transaction type, currency &amp; billing basis)
                </span>
              </td>
            </tr>
          )}

          {AVAIL_MODES.map((mode) => {
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

          <GroupHeader span={robots.length + 1}>② Physical</GroupHeader>
          {(rowsByGroup.get("physical") ?? []).map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} />
          ))}

          <GroupHeader span={robots.length + 1}>③ Manipulation · intelligence · developer</GroupHeader>
          {[
            ...(rowsByGroup.get("manipulation") ?? []),
            ...(rowsByGroup.get("intelligence") ?? []),
            ...(rowsByGroup.get("developer") ?? []),
          ].map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} />
          ))}

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
  );
}

function GroupHeader({ span, children }: { span: number; children: React.ReactNode }) {
  return (
    <tr className="grouprow">
      <th colSpan={span}>{children}</th>
    </tr>
  );
}

// Render an API-provided comparison row through the policy layer.
function ApiRow({
  row,
  slugs,
  units,
  refSlug,
}: {
  row: CompareRow;
  slugs: string[];
  units: UnitSystem;
  refSlug: string | null;
}) {
  const winners = isBestInRowEligible(row.key)
    ? new Set(bestInRow(row.key, row.values))
    : null;
  const numeric = policyFor(row.key).comparability === "numeric";
  const refVal = refSlug ? row.values[refSlug] ?? null : null;

  return (
    <tr>
      <th className="rowlab">{row.label}</th>
      {slugs.map((slug) => {
        const v = row.values[slug];
        if (v == null) {
          return (
            <td className="cell unk" key={slug}>
              <span className="hatch">UNKNOWN</span>
              {refSlug && slug !== refSlug && numeric && (
                <span className="cmp-delta unk">Δ UNKNOWN</span>
              )}
            </td>
          );
        }
        const isBest = winners != null && winners.has(slug);
        let body: React.ReactNode;
        let canonical: string | null = null;
        if (typeof v === "boolean") {
          body = v ? "YES" : "NO";
        } else if (typeof v === "number") {
          const dv = displayMetricValue(row.key, v, units);
          body = dv.primary;
          canonical = dv.canonical;
        } else {
          body = v; // enum / free text — verbatim
        }
        const delta =
          refSlug && numeric ? metricDelta(row.key, refVal, v, slug === refSlug) : null;
        return (
          <td className={`cell${isBest ? " best" : ""}`} key={slug}>
            {body}
            {canonical && <span className="cmp-canon">{canonical}</span>}
            {delta && <DeltaTag d={delta} />}
          </td>
        );
      })}
    </tr>
  );
}

// ── Delta tags (factual, no verdicts) ────────────────────────────────────────
function DeltaTag({ d }: { d: MetricDelta }) {
  if (d.kind === "self") return <span className="cmp-delta ref">REFERENCE</span>;
  if (d.kind === "unknown") return <span className="cmp-delta unk">Δ UNKNOWN</span>;
  if (d.kind === "incomparable") return null;
  const v = d.value ?? 0;
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  const mag = Math.abs(v);
  return (
    <span className="cmp-delta">
      {sign}
      {mag}
      {d.unit ? ` ${d.unit}` : ""}
    </span>
  );
}

function PriceDeltaTag({ d }: { d: PriceDelta }) {
  if (d.kind === "self") return <span className="cmp-delta ref">REFERENCE</span>;
  if (d.kind === "incomparable") return <span className="cmp-delta unk">NO COMPARABLE OFFER</span>;
  const v = d.value ?? 0;
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  const mag = Math.abs(v).toLocaleString("en-US");
  const cur = d.currency ?? "";
  return (
    <span className="cmp-delta">
      {sign}
      {cur ? `${cur} ` : ""}
      {mag}
    </span>
  );
}

// ── Evidence comparison (view=evidence) ──────────────────────────────────────
function EvidenceCompare({ robots, refSlug }: { robots: RobotDetail[]; refSlug: string | null }) {
  return (
    <div className="cmp-evidence">
      <p className="note cmp-ev-intro">
        // FACT-LEVEL PROVENANCE, SIDE BY SIDE. Value · source · confidence ·
        dates · link — straight from the catalogue. No synthetic evidence score.
        UNKNOWN facts read &quot;NO CONFIRMED FACT&quot;.
      </p>

      <EvidenceBlock title="Pricing — headline offer">
        {robots.map((r) => {
          const o = headlineOffer(r.pricing_offers);
          const headline = r.pricing_offers.find(Boolean);
          const value = o
            ? o.amount != null
              ? `${o.currency ?? ""} ${o.amount.toLocaleString("en-US")} · ${o.price_type} · ${modeLabel(o.transaction_type)}`
              : `${o.price_type} · ${modeLabel(o.transaction_type)}`
            : null;
          return (
            <FactRow
              key={r.slug}
              robot={r}
              isRef={r.slug === refSlug}
              value={value}
              evidence={headline?.evidence}
            />
          );
        })}
      </EvidenceBlock>

      <EvidenceBlock title="Availability — obtainability">
        {robots.map((r) => {
          const a = r.availability_offers.find(
            (x) => x.availability_status !== "NOT_AVAILABLE" && x.availability_status !== "DISCONTINUED",
          ) ?? r.availability_offers[0];
          const value = a ? `${a.availability_status} · ${modeLabel(a.transaction_type)}` : null;
          return (
            <FactRow key={r.slug} robot={r} isRef={r.slug === refSlug} value={value} evidence={a?.evidence} />
          );
        })}
      </EvidenceBlock>

      <EvidenceBlock title="Deployments — field evidence">
        {robots.map((r) => {
          const d = r.deployments[0];
          const n = r.deployments.length;
          const value = n > 0 ? `${n} on record${d?.customer_name ? ` · ${d.customer_name}` : ""}` : null;
          return (
            <FactRow key={r.slug} robot={r} isRef={r.slug === refSlug} value={value} evidence={d?.evidence} />
          );
        })}
      </EvidenceBlock>
    </div>
  );
}

function EvidenceBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="cmp-ev-block">
      <h3 className="cmp-ev-h">{title}</h3>
      <div className="ev">{children}</div>
    </section>
  );
}

function FactRow({
  robot,
  isRef,
  value,
  evidence,
}: {
  robot: RobotDetail;
  isRef: boolean;
  value: string | null;
  evidence?: import("@/lib/types").Evidence | null;
}) {
  return (
    <div className={`evrow${isRef ? " is-ref" : ""}`}>
      <div className="subj">
        {robot.name}
        {isRef && <span className="cmp-delta ref"> REFERENCE</span>}
        <span className="cmp-factval">
          {value ?? <span className="hatch">NO CONFIRMED FACT</span>}
        </span>
      </div>
      <div className="src">
        <EvidenceStamp evidence={evidence} />
      </div>
      <div className="conf-cell">
        {evidence ? (
          <ConfidenceIndicator level={evidence.confidence} verifiedAt={evidence.verified_at} />
        ) : (
          <span className="ho-syslabel">—</span>
        )}
      </div>
    </div>
  );
}

// ── Legend ───────────────────────────────────────────────────────────────────
function Legend() {
  return (
    <>
      <div className="legend">
        <span>
          <GraphicMarker signal /> best-in-row (numeric metrics with a leader only)
        </span>
        <span>— = not applicable / no offer in this mode</span>
        <span>
          <span style={{ border: "1px dashed var(--ho-grey-400)", padding: "0 5px" }}>UNKNOWN</span>{" "}
          = no data (never 0/false)
        </span>
        <span>
          <span className="ho-badge ho-badge--caution" style={{ padding: "1px 6px" }}>
            QUOTE
          </span>{" "}
          = price on request ≠ unknown
        </span>
      </div>
      <p className="note cmp-framing">// {BEST_IN_ROW_FRAMING} Reference deltas are factual differences in canonical units, not verdicts. Matching / fit scoring is out of scope (WS6).</p>
    </>
  );
}

// ── shared helpers (kept identical in spirit to the WS3 base) ─────────────────
const PRICE_TYPE_RANK: Record<string, number> = { PUBLIC: 0, FROM: 1, ESTIMATED: 2, RANGE: 3, QUOTE_ONLY: 4 };

function headlinePriceDisplay(offers: PricingOffer[]) {
  if (offers.length === 0) return null;
  const sorted = [...offers].sort((a, b) => {
    const at = a.transaction_type === "PURCHASE" ? 0 : 1;
    const bt = b.transaction_type === "PURCHASE" ? 0 : 1;
    if (at !== bt) return at - bt;
    return (PRICE_TYPE_RANK[a.price_type] ?? 9) - (PRICE_TYPE_RANK[b.price_type] ?? 9);
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

function availabilityFor(robot: RobotDetail, mode: string): string | null {
  const rows = robot.availability_offers.filter((a) => a.transaction_type === mode);
  if (rows.length === 0) return null;
  const accessible = rows.find(
    (a) => a.availability_status !== "NOT_AVAILABLE" && a.availability_status !== "DISCONTINUED",
  );
  return (accessible ?? rows[0]).availability_status;
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

function bestDeployments(robots: RobotDetail[], target: RobotDetail): boolean {
  const counts = robots.map((r) => r.deployments.length);
  const max = Math.max(...counts);
  return max > 0 && target.deployments.length === max && counts.filter((c) => c === max).length === 1;
}
