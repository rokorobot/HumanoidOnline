// Pure display helpers enforcing the FROZEN state conventions from
// docs/07_VISUAL_SYSTEM.md §6.5/§6.6 and docs/03_DATA_DICTIONARY.md.
//
// HARD LAWS encoded here:
//   - QUOTE_ONLY ("Price on request") is NEVER collapsed into UNKNOWN
//     ("No confirmed pricing"). Different data, different display, both variants.
//   - UNKNOWN (null) never becomes $0 / "free" / "N/A".
//   - Enum labels are rendered verbatim.
//   - Card = SHORT single-line labels; detail/compare = LONG sentences.
import type { PriceDisplay } from "./types";

export type StateTone = "default" | "public" | "estimated" | "quote" | "unknown";
export type LabelVariant = "short" | "long";

export interface PriceState {
  /** The headline text, e.g. "$13,500", "PRICE ON REQUEST", "No confirmed pricing". */
  label: string;
  /** Secondary context tag, e.g. "PUBLIC · Purchase" or "QUOTE_ONLY · RaaS". */
  context: string | null;
  tone: StateTone;
}

const MODE_LABELS: Record<string, string> = {
  PURCHASE: "Purchase",
  RENTAL: "Rental",
  SUBSCRIPTION: "Subscription",
  LEASE: "Lease",
  RAAS: "RaaS",
  PILOT: "Pilot",
  DEVELOPER: "Developer",
  OTHER: "Other",
};

export function modeLabel(mode: string | null | undefined): string {
  if (!mode) return "";
  return MODE_LABELS[mode] ?? mode;
}

/** Format a money amount with no fractional digits. Short form uses k/m suffixes. */
export function formatMoney(
  amount: number,
  currency: string | null | undefined,
  short = false,
): string {
  const cur = currency ?? "USD";
  if (short && amount >= 1000) {
    const symbol = currencySymbol(cur);
    if (amount >= 1_000_000) {
      const m = amount / 1_000_000;
      return `${symbol}${trimNum(m)}m`;
    }
    const k = amount / 1000;
    return `${symbol}${trimNum(k)}k`;
  }
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currencySymbol(cur)}${Math.round(amount).toLocaleString("en-US")}`;
  }
}

function trimNum(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function currencySymbol(currency: string): string {
  switch (currency) {
    case "USD":
      return "$";
    case "EUR":
      return "€";
    case "GBP":
      return "£";
    case "CNY":
      return "¥";
    default:
      return `${currency} `;
  }
}

/**
 * Resolve a PriceDisplay (or its absence) into a display state.
 * `null`/`undefined` -> UNKNOWN. QUOTE_ONLY stays distinct from UNKNOWN.
 */
export function resolvePriceState(
  pd: PriceDisplay | null | undefined,
  variant: LabelVariant = "short",
): PriceState {
  if (!pd) {
    // No pricing rows at all -> UNKNOWN. Claims nothing.
    return {
      label: variant === "short" ? "NO PRICE DATA" : "No confirmed pricing",
      context: variant === "short" ? "UNKNOWN · no offer rows" : "UNKNOWN",
      tone: "unknown",
    };
  }
  const cur = pd.currency;
  const billing = pd.billing_period && pd.billing_period !== "ONE_TIME"
    ? billingLabel(pd.billing_period)
    : null;
  switch (pd.type) {
    case "PUBLIC":
      return {
        label: pd.amount != null ? formatMoney(pd.amount, cur, false) : "—",
        context: joinCtx("PUBLIC", billing),
        tone: "public",
      };
    case "FROM":
      return {
        label:
          pd.amount != null ? `From ${formatMoney(pd.amount, cur, false)}` : "—",
        context: joinCtx("FROM", billing),
        tone: "default",
      };
    case "RANGE": {
      const lo = pd.amount_min;
      const hi = pd.amount_max;
      if (lo != null && hi != null) {
        const label =
          variant === "short"
            ? `${formatMoney(lo, cur, true)}–${formatMoney(hi, cur, true)}`
            : `${formatMoney(lo, cur, false)} – ${formatMoney(hi, cur, false)}`;
        return { label, context: joinCtx("RANGE", billing), tone: "default" };
      }
      return { label: "—", context: "RANGE", tone: "default" };
    }
    case "ESTIMATED":
      return {
        label:
          pd.amount != null ? `~${formatMoney(pd.amount, cur, false)}` : "~—",
        // The LONG variant must carry the explicit ESTIMATED flag.
        context: variant === "short" ? joinCtx("ESTIMATED", billing) : "ESTIMATED",
        tone: "estimated",
      };
    case "QUOTE_ONLY":
      // A KNOWN commercial model — not unknown. Never a number.
      return {
        label: variant === "short" ? "PRICE ON REQUEST" : "Price on request",
        context: joinCtx("QUOTE_ONLY", billing),
        tone: "quote",
      };
    default:
      // Unrecognised price_type: render the enum verbatim, never a fake number.
      return { label: pd.type, context: pd.type, tone: "default" };
  }
}

function joinCtx(head: string, tail: string | null): string {
  return tail ? `${head} · ${tail}` : head;
}

function billingLabel(billing: string): string {
  const map: Record<string, string> = {
    HOURLY: "per hour",
    DAILY: "per day",
    WEEKLY: "per week",
    MONTHLY: "per month",
    QUARTERLY: "per quarter",
    ANNUAL: "annual",
  };
  return map[billing] ?? billing;
}

export interface AvailabilitySummary {
  label: string;
  tone: StateTone;
  /** Human-readable accessible transaction modes, or [] when unknown. */
  modes: string[];
  isUnknown: boolean;
}

/**
 * Card-level obtainability summary from `available_modes` (canonical
 * commercially_accessible() predicate). Empty list = UNKNOWN (absence),
 * which is NOT the same as NOT_AVAILABLE.
 */
export function resolveAvailabilitySummary(
  modes: string[] | null | undefined,
  variant: LabelVariant = "short",
): AvailabilitySummary {
  const list = (modes ?? []).map(modeLabel);
  if (list.length === 0) {
    return {
      label:
        variant === "short"
          ? "AVAILABILITY UNKNOWN"
          : "No confirmed commercial availability",
      tone: "unknown",
      modes: [],
      isUnknown: true,
    };
  }
  return { label: "AVAILABLE", tone: "default", modes: list, isUnknown: false };
}

// Maturity ladder ordering for the StatusBadge value ramp (§6.4).
export const MATURITY_LADDER = [
  "ANNOUNCED",
  "DEVELOPMENT",
  "PROTOTYPE",
  "PILOT",
  "EARLY_ACCESS",
  "LIMITED_COMMERCIAL",
  "COMMERCIAL",
  "RAAS_DEPLOYMENT",
] as const;

/** Index on the maturity ladder; DISCONTINUED is off-ladder (returns -1). */
export function maturityIndex(status: string): number {
  return MATURITY_LADDER.indexOf(status as (typeof MATURITY_LADDER)[number]);
}

/** Render a boolean capability flag as YES / NO / UNKNOWN (three states). */
export function boolLabel(v: boolean | null | undefined): {
  label: string;
  unknown: boolean;
} {
  if (v == null) return { label: "UNKNOWN", unknown: true };
  return { label: v ? "YES" : "NO", unknown: false };
}

/** Render a numeric/text spec value, or the explicit UNKNOWN state for null. */
export function specValue(
  value: number | string | boolean | null | undefined,
  unit?: string | null,
): { label: string; unknown: boolean } {
  if (value == null) return { label: "UNKNOWN", unknown: true };
  if (typeof value === "boolean") return boolLabel(value);
  const base = typeof value === "number" ? formatNumber(value) : value;
  return { label: unit ? `${base} ${unit}` : base, unknown: false };
}

export function formatNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : String(n);
}

/** Format an ISO date/datetime as YYYY-MM-DD (stable, locale-free). */
export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = iso.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : iso;
}

/** Uppercase machine-set day-month-year, e.g. "24 JUL 2026". */
export function formatObservedDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const months = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
  ];
  return `${String(d.getUTCDate()).padStart(2, "0")} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
