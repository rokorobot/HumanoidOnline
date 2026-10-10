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
// UX-03 — the SAME matrix, made usable on a phone. Below 721px the table's rows
// are laid out as a label band over aligned robot columns (CSS only: one DOM, so
// the desktop table is untouched and nothing is rendered twice), the robot header
// is pinned, and each robot gains an "Offers & evidence" sheet holding every
// recorded offer row in full. Optional Buyer context (region= / offered_in=)
// ANNOTATES recorded offers; it never hides, filters or rewrites one.
//
// All comparison SEMANTICS live in lib/comparison-policy.ts (tested). This file
// only renders the answers. UNKNOWN stays UNKNOWN; QUOTE_ONLY ≠ UNKNOWN.
// ============================================================================
import { ResolvedFactCell } from "@/components/ResolvedFactCell";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  accessibleModes,
  commercialSummary,
  priceDisplayFromHeadline,
  selectHeadline,
} from "@/lib/commercial-summary";
import { formatObservedDate, modeLabel } from "@/lib/format";
import {
  autonomyLabel,
  availabilityLabel,
  confidenceLabel,
  mobilityLabel,
  priceTypeLabel,
  statusLabel,
} from "@/lib/labels";
import type { CompareResponse, CompareRow, RobotDetail } from "@/lib/types";
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
import { NavLink } from "@/components/NavLink";
import { GraphicMarker } from "@/components/GraphicMarker";
import { deriveModelCode } from "@/lib/model-code";
import { PriceStateLong } from "@/components/PricingState";
import { CompareEvidenceSheet } from "@/components/CompareEvidenceSheet";
import { EvidenceDates } from "@/components/EvidenceDates";
import {
  contextCounts,
  eligibleForRegion,
  inScope,
  MARKET_HELP,
  NO_BUYER_CONTEXT,
  OFFER_MARKETS,
  REGION_HELP,
  REGIONS,
  scopedRegions,
  type BuyerContext,
} from "@/lib/buyer-context";
import { providerLabel } from "@/lib/providers";
import type { AvailabilityOffer } from "@/lib/types";

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
  // UX-03 Buyer context — optional, URL-canonical like the rest of the view state.
  region?: string | null;
  market?: string | null;
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
  // Same parameter names as the catalogue filters, so the two surfaces agree.
  if (s.region) usp.set("region", s.region);
  if (s.market) usp.set("offered_in", s.market);
  return `/compare?${usp.toString()}`;
}

/**
 * Narrow-viewport paging. When the compared set is too wide for the screen (four
 * robots on a phone, three on a very small one) two columns are shown at a time
 * rather than squeezing every column unreadably thin. A reference robot stays
 * pinned so its deltas are always read against a visible column. CSS decides
 * WHEN paging applies; this only decides WHICH two columns a page shows.
 */
export function visiblePair(slugs: string[], refSlug: string | null, page: number): string[] {
  if (slugs.length <= 2) return slugs;
  if (refSlug) {
    const others = slugs.filter((s) => s !== refSlug);
    return [refSlug, others[page % others.length]];
  }
  const i = page % (slugs.length - 1);
  return [slugs[i], slugs[i + 1]];
}

/** Column class for one robot: " c-off" when paged out on a narrow viewport. */
type ColCls = (slug: string) => string;

export function CompareView({
  data,
  ids,
  state,
  context = NO_BUYER_CONTEXT,
}: {
  data: CompareResponse;
  ids: string[];
  state: ViewState;
  context?: BuyerContext;
}) {
  const router = useRouter();
  const robots = data.robots;
  const slugs = robots.map((r) => r.slug);
  // A stale ref (slug no longer in the set) is ignored — fail safe.
  const refSlug = state.ref && slugs.includes(state.ref) ? state.ref : null;
  const [page, setPage] = useState(0);
  const [sheetSlug, setSheetSlug] = useState<string | null>(null);

  function go(next: Partial<ViewState>) {
    const merged: ViewState = { ...state, ref: refSlug, ...next };
    router.push(buildCompareUrl(ids, merged), { scroll: false });
  }

  const pages = Math.max(1, slugs.length - 1);
  const shown = visiblePair(slugs, refSlug, page % pages);
  const col: ColCls = (slug) => (shown.includes(slug) ? "" : " c-off");
  const sheetRobot = sheetSlug ? robots.find((r) => r.slug === sheetSlug) ?? null : null;

  return (
    <div
      className="cmp-root"
      data-n={robots.length}
      style={{ "--cmp-n": robots.length } as React.CSSProperties}
    >
      <CompareToolbar ids={ids} state={{ ...state, ref: refSlug }} onGo={go} />

      <BuyerContextPanel robots={robots} context={context} onGo={go} />

      <RobotSelectRow
        robots={robots}
        refSlug={refSlug}
        onGo={go}
        col={col}
        pager={{
          label: robots
            .filter((r) => shown.includes(r.slug))
            .map((r) => r.name)
            .join(" · "),
          page: page % pages,
          pages,
          onStep: (d) => setPage((p) => (((p + d) % pages) + pages) % pages),
        }}
      />

      {state.view === "matrix" ? (
        <CompareMatrix
          data={data}
          slugs={slugs}
          units={state.units}
          refSlug={refSlug}
          col={col}
          context={context}
          onOpenSheet={setSheetSlug}
        />
      ) : (
        <EvidenceCompare robots={robots} refSlug={refSlug} />
      )}

      <Legend />

      {sheetRobot && (
        <CompareEvidenceSheet
          key={sheetRobot.slug}
          robot={sheetRobot}
          context={context}
          onClose={() => setSheetSlug(null)}
        />
      )}
    </div>
  );
}

// ── Buyer context: Region / Offer market (optional, collapsed) ───────────────
// Two different questions, kept as two controls with the catalogue's own help
// text. Collapsed by default and rendered only when opened, so it costs the
// matrix no space and the document no weight until a buyer asks for it.
function BuyerContextPanel({
  robots,
  context,
  onGo,
}: {
  robots: RobotDetail[];
  context: BuyerContext;
  onGo: (n: Partial<ViewState>) => void;
}) {
  const [open, setOpen] = useState(false);
  const counts = contextCounts(robots, context);
  const n = robots.length;
  return (
    <div className="cmp-bctx">
      <button
        type="button"
        className="cmp-bctx-toggle"
        aria-expanded={open}
        aria-controls="cmp-bctx-body"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="ho-syslabel">Buyer context</span>
        <span className="cmp-bctx-sum">
          Region: {context.region ?? "any"} · Offer market: {context.market ?? "any"}
        </span>
        <span className="cmp-bctx-act">{open ? "CLOSE" : "CHANGE"}</span>
      </button>
      {open && (
        <div id="cmp-bctx-body" className="cmp-bctx-body">
          <p className="note">
            Optional. These add notes to the recorded offers below; they never hide, filter or
            change one.
          </p>
          <div className="field">
            <label htmlFor="cmp-region">Region — where an availability offer applies</label>
            <select
              id="cmp-region"
              value={context.region ?? ""}
              onChange={(e) => onGo({ region: e.target.value || null })}
            >
              <option value="">Any region</option>
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            {counts.region != null && (
              <span className="ho-syslabel cmp-bctx-count">
                {counts.region} of {n} robots: an availability offer applies to {context.region}.
                An offer recorded for a narrower area does not apply to a wider region.
              </span>
            )}
            <ContextHelp id="cmp-region-help" label="Region help" text={REGION_HELP} />
          </div>
          <div className="field">
            <label htmlFor="cmp-market">Offer market — where a seller&apos;s offer originates</label>
            <select
              id="cmp-market"
              value={context.market ?? ""}
              onChange={(e) => onGo({ market: e.target.value || null })}
            >
              <option value="">Any market</option>
              {OFFER_MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            {counts.market != null && (
              <span className="ho-syslabel cmp-bctx-count">
                {counts.market} of {n} robots: a price or availability entry is tied to the{" "}
                {context.market} market, including member-country suppliers. Not a delivery
                guarantee.
              </span>
            )}
            <ContextHelp id="cmp-market-help" label="Offer market help" text={MARKET_HELP} />
          </div>
        </div>
      )}
    </div>
  );
}

function ContextHelp({ id, label, text }: { id: string; label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="fhelp-btn"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      {open && (
        <p id={id} className="fhelp-text">
          {text}
        </p>
      )}
    </>
  );
}

/**
 * What the Buyer context's region says about one mode's availability entries.
 * Annotation only, and precise about WHICH entry it speaks of: a cell shows one
 * entry's status (`shown`) while a robot may hold several entries for the mode,
 * recorded for different regions. "Applies" is said of the shown entry only when
 * that entry itself is in scope; when a different entry is the one in scope, the
 * note says so and names the region it is recorded for.
 */
function RegionNote({
  shown,
  offers,
  context,
}: {
  shown: AvailabilityOffer;
  offers: AvailabilityOffer[];
  context: BuyerContext;
}) {
  if (!context.region || !context.applicable || offers.length === 0) return null;
  const scope = context.applicable;
  const where = (a: AvailabilityOffer) => a.region ?? "no region";
  if (offers.includes(shown) && inScope(shown.region, scope)) {
    return <span className="cmp-ctx">Applies to {context.region}</span>;
  }
  const other = offers.filter((a) => a !== shown && inScope(a.region, scope));
  if (other.length > 0) {
    const regions = [...new Set(other.map(where))].join(", ");
    return (
      <span className="cmp-ctx">
        Another entry ({regions}) applies to {context.region}; this one is recorded for{" "}
        {where(shown)}
      </span>
    );
  }
  const recorded = [...new Set(offers.map(where))].join(", ");
  return (
    <span className="cmp-ctx no">
      Recorded for {recorded}; does not apply to {context.region}
    </span>
  );
}

function MarketNote({
  offers,
  context,
}: {
  offers: { region?: string | null }[];
  context: BuyerContext;
}) {
  if (!context.market || !context.marketCodes || offers.length === 0) return null;
  const inMarket = offers.filter((o) => inScope(o.region, context.marketCodes!));
  if (inMarket.length === 0) {
    return <span className="cmp-ctx no">No {context.market} market entry</span>;
  }
  const codes = scopedRegions(inMarket, context.marketCodes);
  return (
    <span className="cmp-ctx">
      In {context.market} market{codes.length ? ` (${codes.join(", ")})` : ""}
    </span>
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
  // WS8.4 / R17: focus the name input when the inline naming control opens.
  // Programmatic focus is the accessible equivalent of the `autoFocus` prop
  // (jsx-a11y/no-autofocus): it moves focus only in response to the user's
  // "Save view" action, not on initial page render.
  const nameInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (naming) nameInputRef.current?.focus();
  }, [naming]);
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
              ref={nameInputRef}
              className="cmp-nameinput"
              aria-label="Saved view name"
              placeholder="Name this view"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitSave();
                if (e.key === "Escape") setNaming(false);
              }}
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
  col,
  pager,
}: {
  robots: RobotDetail[];
  refSlug: string | null;
  onGo: (n: Partial<ViewState>) => void;
  col: ColCls;
  pager: { label: string; page: number; pages: number; onStep: (d: number) => void };
}) {
  return (
    <div className="selrow-wrap">
      <div className="selrow">
        <div className="cell rowlab">
          <span className="ho-syslabel">Robots ×{robots.length}</span>
        </div>
        {robots.map((r) => {
          const isRef = r.slug === refSlug;
          return (
            <div className={`cell robotpick${isRef ? " is-ref" : ""}${col(r.slug)}`} key={r.slug}>
              <div className="lockup">
                <NavLink className="name" href={`/robots/${r.slug}`}>
                  {r.name}
                </NavLink>
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
      {/* Paging can only apply to three or more robots; CSS decides where it shows
          (see .cmp-pager in globals.css). Two robots never carry the markup. */}
      {robots.length > 2 && (
      <div className="cmp-pager">
        <button type="button" className="btn" onClick={() => pager.onStep(-1)} aria-label="Show previous robot">
          ‹ PREV
        </button>
        <span className="ho-syslabel" aria-live="polite">
          {pager.label} · {pager.page + 1}/{pager.pages}
        </span>
        <button type="button" className="btn" onClick={() => pager.onStep(1)} aria-label="Show next robot">
          NEXT ›
        </button>
      </div>
      )}
    </div>
  );
}

// ── Matrix (base, extended) ──────────────────────────────────────────────────
function CompareMatrix({
  data,
  slugs,
  units,
  refSlug,
  col,
  context,
  onOpenSheet,
}: {
  data: CompareResponse;
  slugs: string[];
  units: UnitSystem;
  refSlug: string | null;
  col: ColCls;
  context: BuyerContext;
  onOpenSheet: (slug: string) => void;
}) {
  const robots = data.robots;
  const availModes = AVAIL_MODES.filter((mode) =>
    robots.some((r) => r.availability_offers.some((a) => a.transaction_type === mode)),
  );
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

  // WS8.4 / R17: the comparison matrix scrolls horizontally on narrow
  // viewports, so the scroll container is keyboard-focusable (WCAG 2.1.1).
  return (
    <div className="cmp-scroll" tabIndex={0} role="group" aria-label="Comparison matrix">
      <table className="cmatrix">
        <colgroup>
          <col className="lab" />
          {robots.map((r) => (
            <col key={r.slug} />
          ))}
        </colgroup>
        <tbody>
          <GroupHeader span={robots.length + 1}>① Commercial — maturity · obtainability</GroupHeader>
          {(rowsByGroup.get("commercial") ?? []).map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} col={col} />
          ))}

          {/* Price — leader only when truly like-for-like ("LOWEST COMPARABLE PRICE"). */}
          <tr>
            <th className="rowlab">Price</th>
            {robots.map((r) => {
              const win = priceWinners.has(r.slug);
              const d = priceDelta(refOffer, headlines.get(r.slug) ?? null, r.slug === refSlug);
              return (
                <td className={`cell${win ? " best" : ""}${col(r.slug)}`} key={r.slug}>
                  <ComparePriceCell robot={r} />
                  {refSlug && <PriceDeltaTag d={d} />}
                  <PriceCellExtras robot={r} context={context} onOpen={() => onOpenSheet(r.slug)} />
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
                  {Array.from(headlines.values()).some((h) => h?.variant) &&
                    "; each price is for the configuration shown in its column"}
                </span>
              </td>
            </tr>
          )}

          {/* One row per transaction mode on record. A robot with no availability
              entry at all reads "Availability not recorded" (missing evidence, not
              unavailability); "—" stays "no offer in this mode". */}
          {(availModes.length > 0 ? availModes : [null]).map((mode) => (
            <tr key={mode ?? "none"}>
              <th className="rowlab">{mode ? modeLabel(mode) : "Availability"}</th>
              {robots.map((r) => (
                <AvailabilityCell key={r.slug} robot={r} mode={mode} context={context} cls={col(r.slug)} />
              ))}
            </tr>
          ))}

          <GroupHeader span={robots.length + 1}>② Physical</GroupHeader>
          {(rowsByGroup.get("physical") ?? []).map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} col={col} />
          ))}

          <GroupHeader span={robots.length + 1}>③ Manipulation · intelligence · developer</GroupHeader>
          {[
            ...(rowsByGroup.get("manipulation") ?? []),
            ...(rowsByGroup.get("intelligence") ?? []),
            ...(rowsByGroup.get("developer") ?? []),
          ].map((row) => (
            <ApiRow key={row.key} row={row} slugs={slugs} units={units} refSlug={refSlug} col={col} />
          ))}

          <GroupHeader span={robots.length + 1}>④ Deployment — evidence</GroupHeader>
          <tr>
            <th className="rowlab">Deployments</th>
            {robots.map((r) => {
              const n = r.deployments.length;
              const best = bestDeployments(robots, r);
              return (
                <td className={`cell${best ? " best" : ""}${n === 0 ? " unk" : ""}${col(r.slug)}`} key={r.slug}>
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
                <td className={`cell${col(r.slug)}`} key={r.slug}>
                  {conf ? (
                    <span className={conf === "VERIFIED" ? "v" : ""} data-enum={conf}>
                      {confidenceLabel(conf)}
                    </span>
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
  col,
}: {
  row: CompareRow;
  slugs: string[];
  units: UnitSystem;
  refSlug: string | null;
  col: ColCls;
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
        // G4: a scoped state is shown as such, never collapsed to a plain UNKNOWN or YES/NO.
        const rf = row.resolved?.[slug];
        if (rf && rf.state !== "PRODUCT_VALUE" && rf.state !== "UNKNOWN") {
          return (
            <td className={`cell${col(slug)}`} key={slug}>
              <ResolvedFactCell fact={rf} />
            </td>
          );
        }
        if (v == null) {
          return (
            <td className={`cell unk${col(slug)}`} key={slug}>
              <span className="hatch">UNKNOWN</span>
              {refSlug && slug !== refSlug && numeric && (
                <span className="cmp-delta unk">Δ UNKNOWN</span>
              )}
            </td>
          );
        }
        const isBest = winners != null && winners.has(slug);
        let body: React.ReactNode;
        let rawEnum: string | null = null;
        let canonical: string | null = null;
        if (typeof v === "boolean") {
          body = v ? "YES" : "NO";
        } else if (typeof v === "number") {
          const dv = displayMetricValue(row.key, v, units);
          body = dv.primary;
          canonical = dv.canonical;
        } else {
          // Enum rows get their buyer-facing label (raw enum kept in data-enum);
          // anything else is free text and stays verbatim.
          const label = ENUM_ROW_LABEL[row.key];
          if (label) rawEnum = String(v);
          body = label ? label(v) : v;
        }
        const delta =
          refSlug && numeric ? metricDelta(row.key, refVal, v, slug === refSlug) : null;
        return (
          <td className={`cell${isBest ? " best" : ""}${col(slug)}`} key={slug} {...(rawEnum ? { "data-enum": rawEnum } : {})}>
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
        Fact-level provenance, side by side: value, source, confidence, dates and link, straight from the catalogue. No synthetic evidence score. Facts we cannot confirm read &quot;NO CONFIRMED FACT&quot;.
      </p>

      <EvidenceBlock title="Pricing — headline offer">
        {robots.map((r) => {
          const o = headlineOffer(r.pricing_offers);
          // The evidence belongs to the SAME offer row the price cell displays.
          const headline = selectHeadline(r.pricing_offers)?.offer;
          const cfg = o?.variant ? ` · ${o.variant} configuration` : "";
          const value = o
            ? o.amount != null
              ? `${o.currency ?? ""} ${o.amount.toLocaleString("en-US")} · ${priceTypeLabel(o.price_type)} · ${modeLabel(o.transaction_type)}${cfg}`
              : `${priceTypeLabel(o.price_type)} · ${modeLabel(o.transaction_type)}${cfg}`
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
          const value = a ? `${availabilityLabel(a.availability_status)} · ${modeLabel(a.transaction_type)}` : null;
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
        <EvidenceDates evidence={evidence} />
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
          <span style={{ border: "1px dashed var(--ho-grey-400)", padding: "0 5px" }}>
            Availability not recorded
          </span>{" "}
          = no availability entry in the catalogue (not a statement that it is unavailable)
        </span>
        <span>
          <span style={{ border: "1px dashed var(--ho-grey-400)", padding: "0 5px" }}>UNKNOWN</span>{" "}
          = no data (never 0/false)
        </span>
        <span>
          <span className="ho-badge ho-badge--caution" style={{ padding: "1px 6px" }}>
            Quote
          </span>{" "}
          = price on request ≠ unknown
        </span>
      </div>
      <p className="note cmp-framing">
        {BEST_IN_ROW_FRAMING} Reference deltas are factual differences in
        canonical units, not verdicts. Fit scoring is not part of this view.
      </p>
    </>
  );
}

// ── shared helpers (kept identical in spirit to the WS3 base) ─────────────────
// Labels for the enum-valued API rows (visible text only; data-enum keeps the raw value).
const ENUM_ROW_LABEL: Partial<Record<string, (v: string) => string>> = {
  commercial_status: statusLabel,
  mobility: mobilityLabel,
  autonomy: autonomyLabel,
};

/**
 * The compare price cell. Everything shown - amount, configuration, "From ... /
 * N configurations priced", basis, order note - is read from the SAME offer row,
 * so a configuration-scoped amount never appears without its configuration. The
 * one-line commercial summary is the same helper the catalogue card uses.
 */
export function ComparePriceCell({ robot }: { robot: RobotDetail }) {
  const h = selectHeadline(robot.pricing_offers);
  const price = priceDisplayFromHeadline(h);
  const summary = commercialSummary(price, accessibleModes(robot.availability_offers));
  return (
    <>
      <PriceStateLong
        price={price}
        variant="long"
        detailed
        fromLowest={(h?.configurationsPriced ?? 0) > 1}
        configurationsPriced={h?.configurationsPriced ?? 0}
      />
      <span className={summary.unknown ? "ho-syslabel d-blk cmp-csum csum--unk" : "ho-syslabel d-blk cmp-csum"}>
        {summary.line}
      </span>
    </>
  );
}

/**
 * Everything the matrix adds beside the headline price on a narrow viewport: who
 * sells it and where (from the SAME offer row as the amount), what the Buyer
 * context says about this robot's price entries, and the way into the full
 * record. The full terms stay in the "Offers & evidence" sheet.
 */
function PriceCellExtras({
  robot,
  context,
  onOpen,
}: {
  robot: RobotDetail;
  context: BuyerContext;
  onOpen: () => void;
}) {
  const offer = selectHeadline(robot.pricing_offers)?.offer;
  const seller = offer?.provider ? providerLabel(offer.provider, null, offer.provider_name).text : null;
  const where = [offer?.region, seller].filter(Boolean).join(" · ");
  return (
    <>
      {where && (
        <span className="ho-syslabel d-blk cmp-m" data-provider={offer?.provider ?? undefined}>
          {where}
        </span>
      )}
      <MarketNote offers={robot.pricing_offers} context={context} />
      <button
        type="button"
        className="cmp-detail cmp-m"
        onClick={onOpen}
        aria-label={`Offers and evidence: ${robot.name}`}
      >
        OFFERS &amp; EVIDENCE
      </button>
    </>
  );
}

function isAccessible(a: AvailabilityOffer): boolean {
  return a.availability_status !== "NOT_AVAILABLE" && a.availability_status !== "DISCONTINUED";
}

/** The availability row a mode's cell displays: the first accessible one, else the first. */
function availabilityRowFor(robot: RobotDetail, mode: string): AvailabilityOffer | null {
  const rows = robot.availability_offers.filter((a) => a.transaction_type === mode);
  if (rows.length === 0) return null;
  return rows.find(isAccessible) ?? rows[0];
}

/**
 * One availability cell. The status is the catalogue's record as of the date it
 * was observed (shown beside it) — never presented as a live stock check.
 */
function AvailabilityCell({
  robot,
  mode,
  context,
  cls,
}: {
  robot: RobotDetail;
  mode: string | null;
  context: BuyerContext;
  cls: string;
}) {
  if (robot.availability_offers.length === 0) {
    return (
      <td className={`cell unk${cls}`}>
        <span className="hatch">Availability not recorded</span>
      </td>
    );
  }
  const row = mode ? availabilityRowFor(robot, mode) : null;
  if (!row) return <td className={`cell na${cls}`}>—</td>;
  const observed = formatObservedDate(row.evidence?.observed_at);
  const modeRows = robot.availability_offers.filter((a) => a.transaction_type === mode);
  return (
    <td className={`cell${cls}`} data-enum={row.availability_status}>
      {availabilityLabel(row.availability_status)}
      {observed && <span className="cmp-obs">observed {observed}</span>}
      <RegionNote shown={row} offers={modeRows.filter(eligibleForRegion)} context={context} />
      <MarketNote offers={modeRows} context={context} />
    </td>
  );
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
