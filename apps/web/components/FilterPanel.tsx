"use client";

// FilterPanel — conventional, usable filter rail (tier-2 controls, §1 gradient).
// URL-addressable: every change rewrites the URL query; the server page re-reads
// searchParams and re-queries the API. Works as a plain GET form without JS
// (Apply button), and auto-applies on change when JS is on. It never computes
// facts — it only forwards filter params to /api/robots.
import { useRouter } from "next/navigation";
import { useRef, type FormEvent } from "react";

import { asArray, asString, type RawSearchParams } from "@/lib/search-params";
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
const MOBILITY = ["BIPEDAL", "WHEELED", "HYBRID", "QUADRUPED", "STATIONARY", "OTHER"];
const AUTONOMY = [
  "TELEOPERATED",
  "ASSISTED",
  "SUPERVISED_AUTONOMY",
  "TASK_AUTONOMOUS",
  "HIGHLY_AUTONOMOUS",
];

export function FilterPanel({
  params,
  resultCount,
}: {
  params: RawSearchParams;
  resultCount: number;
}) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);

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
    router.push(`/robots?${usp.toString()}`, { scroll: false });
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submitForm();
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
  }

  const sort = asString(params.sort) ?? "name";
  const q = asString(params.q) ?? "";

  return (
    <form
      ref={formRef}
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
              {s}
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
              {t}
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
        </div>
        <div className="field">
          <label htmlFor="f-price">Max purchase price (USD)</label>
          <input
            id="f-price"
            type="number"
            name="price_max"
            min={0}
            placeholder="e.g. 90000"
            defaultValue={asString(params.price_max) ?? ""}
          />
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
                {m}
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
                {a}
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
  );
}
