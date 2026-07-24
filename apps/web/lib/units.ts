// ============================================================================
// WS4 — Presentation-only unit conversion (Metric ⇄ Imperial).
// ----------------------------------------------------------------------------
// PRESENTATION ONLY. The catalogue's canonical value (cm, kg, m/s, minutes) is
// never changed, inferred, or fabricated — conversions are exact restatements
// of the same fact, and the canonical raw value stays visible/traceable in the
// UI. UNKNOWN is not passed here (callers render UNKNOWN before conversion).
// ============================================================================
import { policyFor, type Dimension } from "./comparison-policy";

export type UnitSystem = "metric" | "imperial";

export function isUnitSystem(v: string | null | undefined): v is UnitSystem {
  return v === "metric" || v === "imperial";
}

const CM_PER_INCH = 2.54;
const LB_PER_KG = 2.2046226218;
const MPH_PER_MS = 2.2369362921;

/** 132 cm → "4 ft 4 in" (rounded to the nearest inch, carrying into feet). */
export function cmToFtIn(cm: number): string {
  const totalInches = Math.round(cm / CM_PER_INCH);
  const ft = Math.floor(totalInches / 12);
  const inch = totalInches % 12;
  return `${ft} ft ${inch} in`;
}

/** 35 kg → "77 lb" (nearest pound). */
export function kgToLb(kg: number): string {
  return `${Math.round(kg * LB_PER_KG)} lb`;
}

/** 1.5 m/s → "3.4 mph" (one decimal). */
export function msToMph(ms: number): string {
  return `${round1(ms * MPH_PER_MS)} mph`;
}

function round1(n: number): string {
  return (Math.round(n * 10) / 10).toString();
}

function trim(n: number): string {
  return Number.isInteger(n) ? String(n) : String(n);
}

export interface DisplayValue {
  /** Primary text for the active unit system, e.g. "4 ft 4 in" or "132 cm". */
  primary: string;
  /**
   * The canonical (metric) restatement to keep the raw fact traceable when the
   * primary is a converted imperial value. `null` when primary already IS the
   * canonical value (metric system, or a dimensionless / non-convertible metric).
   */
  canonical: string | null;
}

function canonicalText(value: number, unit: string | null): string {
  return unit ? `${trim(value)} ${unit}` : trim(value);
}

/**
 * Render a numeric metric value in the requested unit system.
 * Only length/mass/speed convert; counts and durations have no imperial form and
 * are shown identically in both systems (canonical stays null → no redundant sub).
 */
export function displayMetricValue(
  key: string,
  value: number,
  system: UnitSystem,
): DisplayValue {
  const p = policyFor(key);
  const canonical = canonicalText(value, p.unit);
  if (system === "metric") return { primary: canonical, canonical: null };

  const dim: Dimension = p.dimension;
  switch (dim) {
    case "length_cm":
      return { primary: cmToFtIn(value), canonical };
    case "mass_kg":
      return { primary: kgToLb(value), canonical };
    case "speed_ms":
      return { primary: msToMph(value), canonical };
    // duration_min and count have no distinct imperial form.
    case "duration_min":
    case "count":
    case null:
    default:
      return { primary: canonical, canonical: null };
  }
}
