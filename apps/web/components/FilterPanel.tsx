"use client";

// FilterPanel — conventional, usable filter rail (tier-2 controls, §1 gradient).
// URL-addressable: every change rewrites the URL query; the server page re-reads
// searchParams and re-queries the API. Works as a plain GET form without JS
// (Apply button), and auto-applies on change when JS is on. It never computes
// facts — it only forwards filter params to /api/robots.
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { modeLabel } from "@/lib/format";
import { autonomyLabel, mobilityLabel, statusLabel } from "@/lib/labels";
import {
  PRICE_CURRENCIES,
  PRICE_CURRENCY,
  asArray,
  asString,
  type RawSearchParams,
} from "@/lib/search-params";
import { GraphicMarker } from "./GraphicMarker";

const COMMERCIAL_STATUS = [
  "COMMERCIAL",
  "RAAS_DEPLOYMENT",
  "LIMITED_COMMERCIAL",
  "EARLY_ACCESS",
  "PILOT",
  "PROTOTYPE",
  "DEVELOPMENT",
  "ANNOUNCED",
  "DISCONTINUED",
  // Last, and off the maturity ladder: UNKNOWN is not a rung between ANNOUNCED
  // and DISCONTINUED, it is the absence of a verified maturity. Selecting any
  // other status excludes it, exactly as selecting COMMERCIAL excludes PILOT;
  // with no status selected the catalogue still shows every published robot.
  "UNKNOWN",
];
const TRANSACTION_TYPES = [
  "PURCHASE",
  "RENTAL",
  "SUBSCRIPTION",
  "LEASE",
  "RAAS",
  "PILOT",
  "DEVELOPER",
];
const REGIONS = ["US", "EU", "CN", "DE", "UK", "NO", "CA"];
// Offer market is NOT a second region filter. `region` asks where a robot is
// offered as the record states it; this asks which market's storefronts to
// search, and an economic zone admits its member countries' suppliers — an EU
// buyer should find what a German distributor lists. Only zones with member
// regions on record appear: for a plain country the two questions collapse into
// one, and a second control would imply a distinction that isn't there.
// Unset by default — no listing is hidden until the buyer narrows.
const OFFER_MARKETS = ["EU"];
const MOBILITY = ["BIPEDAL", "WHEELED", "HYBRID", "QUADRUPED", "STATIONARY", "OTHER"];
const AUTONOMY = [
  "TELEOPERATED",
  "ASSISTED",
  "SUPERVISED_AUTONOMY",
  "TASK_AUTONOMOUS",
  "HIGHLY_AUTONOMOUS",
];

// UX-02D - wording derived from the real predicates (apps/api/app/services/robot_filters.py,
// regions.py). `region` = a CURRENT, NEW, commercially-accessible AVAILABILITY offer whose
// region is the chosen region, an ancestor of it, GLOBAL, or unspecified (NULL). `offered_in`
// = a CURRENT pricing OR availability record (any status) whose region is the market, an
// ancestor, a descendant (member country), GLOBAL, or unspecified. Neither asserts delivery.
export const REGION_HELP =
  "Shows robots with a current, accessible availability offer that applies to this region: " +
  "an offer for the region itself, for a wider area that includes it (for example the EU for " +
  "Germany), a worldwide offer, or an offer with no region recorded. An offer being recorded " +
  "for a region is not proof that the robot can be bought there, and it does not establish " +
  "shipping, customs or delivery eligibility. Missing regional information is unknown, not " +
  "unavailable.";
export const MARKET_HELP =
  "Shows robots with a recorded price or availability entry tied to this market, including " +
  "entries for member countries of an economic zone (for example a German supplier for the EU), " +
  "worldwide entries and entries with no region recorded, whatever the entry's status. It says " +
  "only that such an entry exists: not that the robot can be ordered, shipped or cleared " +
  "through customs there. Missing market information is unknown, not unavailable.";

// A disclosure button (works on touch and keyboard, no hover). The text is rendered only
// while open, so it adds nothing to the delivered document until a buyer asks for it.
function Help({ id, label, text }: { id: string; label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="fhelp-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
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

export function FilterPanel({
  params,
  resultCount,
  activeCount = 0,
}: {
  params: RawSearchParams;
  resultCount: number;
  /** Number of active filters (shown on the mobile toggle). */
  activeCount?: number;
}) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  // Mobile (<= 820px) collapses the rail behind a "Filters" button; on desktop
  // the toggle is hidden by CSS and the rail is always shown, so `open` is inert.
  const [open, setOpen] = useState(false);

  function openPanel() {
    setOpen(true);
    // Move focus into the panel once it is displayed.
    requestAnimationFrame(() => formRef.current?.focus());
  }
  function closePanel() {
    setOpen(false);
    toggleRef.current?.focus();
  }
  // Escape closes the mobile disclosure and returns focus to its button.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function currentStatus() {
    return asArray(params.commercial_status);
  }
  function currentTxn() {
    return asArray(params.transaction_type);
  }

  function submitForm() {
    const form = formRef.current;
    if (!form) return;
    const fd = new FormData(form);
    const usp = new URLSearchParams();
    for (const [k, v] of fd.entries()) {
      const val = String(v);
      if (val !== "") usp.append(k, val);
    }
    // `price_max` and `price_currency` are a contract pair: the API rejects
    // either alone. Appending the denomination here rather than rendering a
    // hidden field keeps them inseparable — a hidden input is never "empty", so
    // it would survive the filter above and emit a lone `price_currency` the
    // moment the price box is cleared. Clearing the price therefore drops both.
    if (usp.has("price_max")) {
      if (!usp.get("price_currency")) usp.set("price_currency", PRICE_CURRENCY);
    } else {
      usp.delete("price_currency");
    }
    router.push(`/robots?${usp.toString()}`, { scroll: false });
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submitForm();
    // An explicit Apply on mobile dismisses the panel and shows the results.
    if (open) closePanel();
  }

  // Auto-apply on discrete controls (checkbox/select). Free-text number inputs
  // apply on Enter or the Apply button, so we don't re-navigate per keystroke.
  function onChange(e: FormEvent<HTMLFormElement>) {
    const target = e.target as HTMLElement;
    if (
      target instanceof HTMLInputElement &&
      (target.type === "number" || target.type === "text")
    ) {
      return;
    }
    submitForm();
  }

  function reset() {
    router.push("/robots", { scroll: false });
    if (open) closePanel();
  }

  const sort = asString(params.sort) ?? "name";
  const q = asString(params.q) ?? "";

  return (
    <div className={`filters-wrap${open ? " is-open" : ""}`}>
    <button
      ref={toggleRef}
      type="button"
      className="filters-toggle"
      aria-expanded={open}
      aria-controls={panelId}
      onClick={() => (open ? closePanel() : openPanel())}
    >
      <span className="ft-label">
        Filters{activeCount > 0 ? ` · ${activeCount} active` : ""}
      </span>
      <span className="ft-count">
        {resultCount} {resultCount === 1 ? "result" : "results"}
      </span>
    </button>
    <noscript>
      <style>{".filters-toggle{display:none!important}.filters{display:block!important}"}</style>
    </noscript>
    <form
      id={panelId}
      ref={formRef}
      tabIndex={-1}
      className="filters"
      aria-label="Filters"
      action="/robots"
      method="get"
      onSubmit={onSubmit}
      onChange={onChange}
    >
      {/* Preserve orthogonal state (search text, sort, compare tray) across
          filter changes. */}
      <input type="hidden" name="q" value={q} />
      <input type="hidden" name="sort" value={sort} />
      {asString(params.compare) ? (
        <input type="hidden" name="compare" value={asString(params.compare)} />
      ) : null}

      <div className="fhead">
        <span className="ho-syslabel">Filters</span>
        <span className="ho-chip">{resultCount} RESULTS</span>
      </div>

      <fieldset className="fgroup">
        <legend>
          <GraphicMarker /> Commercial status
        </legend>
        {COMMERCIAL_STATUS.map((s) => {
          const active = currentStatus().includes(s);
          return (
            <label className={`opt${active ? " active" : ""}`} key={s}>
              <input
                type="checkbox"
                name="commercial_status"
                value={s}
                defaultChecked={active}
              />{" "}
              {statusLabel(s)}
            </label>
          );
        })}
      </fieldset>

      <fieldset className="fgroup">
        <legend>
          <GraphicMarker /> Transaction
        </legend>
        {TRANSACTION_TYPES.map((t) => {
          const active = currentTxn().includes(t);
          return (
            <label className={`opt${active ? " active" : ""}`} key={t}>
              <input
                type="checkbox"
                name="transaction_type"
                value={t}
                defaultChecked={active}
              />{" "}
              {modeLabel(t)}
            </label>
          );
        })}
      </fieldset>

      <div className="fgroup">
        <div className="field">
          <label htmlFor="f-region">Region</label>
          <select id="f-region" name="region" defaultValue={asString(params.region) ?? ""}>
            <option value="">Any region</option>
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <Help id="f-region-help" label="Region help" text={REGION_HELP} />
        </div>
        <div className="field">
          <label htmlFor="f-offered-in">Offer market</label>
          <select
            id="f-offered-in"
            name="offered_in"
            defaultValue={asString(params.offered_in) ?? ""}
            aria-describedby="f-offered-in-help"
          >
            <option value="">Any market</option>
            {OFFER_MARKETS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <span className="ho-syslabel" id="f-offered-in-help">
            Where the offer is sold from, including suppliers in member countries.
            Not a delivery guarantee, and not a claim about the robot&apos;s edition.
          </span>
          <Help id="f-market-help" label="Offer market help" text={MARKET_HELP} />
        </div>
        <div className="field">
          <label htmlFor="f-price">Max purchase price (no conversion)</label>
          <div className="range">
            <input
              id="f-price"
              type="number"
              name="price_max"
              min={0}
              placeholder="e.g. 50000"
              defaultValue={asString(params.price_max) ?? ""}
            />
            <select
              id="f-currency"
              name="price_currency"
              aria-label="Price currency"
              defaultValue={(asString(params.price_currency) ?? PRICE_CURRENCY).toUpperCase()}
            >
              {PRICE_CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

        </div>
      </div>

      <div className="fgroup">
        <span className="ho-syslabel" style={{ display: "block", marginBottom: 10 }}>
          <GraphicMarker /> Physical
        </span>
        <div className="range">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="f-payload">Payload min (kg)</label>
            <input
              id="f-payload"
              type="number"
              name="payload_min"
              min={0}
              placeholder="min"
              defaultValue={asString(params.payload_min) ?? ""}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="f-height">Height min (cm)</label>
            <input
              id="f-height"
              type="number"
              name="height_min"
              min={0}
              placeholder="min"
              defaultValue={asString(params.height_min) ?? ""}
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="f-mobility">Mobility</label>
          <select
            id="f-mobility"
            name="mobility"
            defaultValue={asString(params.mobility) ?? ""}
          >
            <option value="">Any</option>
            {MOBILITY.map((m) => (
              <option key={m} value={m}>
                {mobilityLabel(m)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="fgroup">
        <legend>
          <GraphicMarker /> Intelligence / developer
        </legend>
        <div className="field">
          <label htmlFor="f-autonomy">Autonomy (minimum)</label>
          <select
            id="f-autonomy"
            name="autonomy_min"
            defaultValue={asString(params.autonomy_min) ?? ""}
          >
            <option value="">Any</option>
            {AUTONOMY.map((a) => (
              <option key={a} value={a}>
                {autonomyLabel(a)}
              </option>
            ))}
          </select>
        </div>
        {(
          [
            ["has_sdk", "Has SDK"],
            ["ros_support", "ROS support"],
            ["developer_edition", "Developer edition"],
            ["has_manipulation", "Manipulation"],
          ] as const
        ).map(([name, label]) => {
          const active = asString(params[name]) === "true";
          return (
            <label className={`opt${active ? " active" : ""}`} key={name}>
              <input
                type="checkbox"
                name={name}
                value="true"
                defaultChecked={active}
              />{" "}
              {label}
            </label>
          );
        })}
      </fieldset>

      <div className="frow">
        <button className="fbtn" type="button" onClick={reset}>
          Reset
        </button>
        <button className="fbtn primary" type="submit">
          Apply
        </button>
      </div>
    </form>
    </div>
  );
}
