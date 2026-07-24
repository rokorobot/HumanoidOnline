// ============================================================================
// WS4 — Formal comparison policy (single tested source of truth).
// ----------------------------------------------------------------------------
// This module owns the SEMANTICS of comparing two-to-four robots. It is pure
// (no React, no I/O) and unit-tested. React components must NOT re-derive
// comparison logic — they read the answers from here.
//
// FROZEN FRAMING (mirror this copy in the UI, do not soften it):
//   "Best-in-row identifies a metric-specific numeric leader only. It is not a
//    robot ranking, recommendation, fit score, or purchase recommendation."
//   Best-in-row is NOT a match score. WS6 owns matching/scoring — this layer
//   never produces one.
//
// DATA LAW enforced here:
//   - UNKNOWN (null) is NEVER treated as 0 / worst / a penalty. It is simply
//     ineligible for numeric comparison. It never wins and never loses.
//   - QUOTE_ONLY ("price on request") is a KNOWN fact with no number — it is
//     NOT the same as UNKNOWN and is never coerced to a number.
//   - No value is ever inferred or fabricated to fill a gap.
// ============================================================================

export type LeaderDirection = "HIGHER" | "LOWER" | "NONE";

/** How a metric may be compared across robots. */
export type Comparability = "numeric" | "display";

/** Unit dimension used for the presentation-only Metric/Imperial toggle. */
export type Dimension =
  | "length_cm"
  | "mass_kg"
  | "speed_ms"
  | "duration_min"
  | "count"
  | null;

export interface MetricPolicy {
  key: string;
  /**
   * `numeric` = a like-for-like number where deltas are meaningful (eligible for
   * a reference delta). `display` = categorical / boolean / free text — never a
   * numeric leader, never a numeric delta.
   */
  comparability: Comparability;
  /**
   * Best-in-row winner direction. `NONE` means the metric is shown but has no
   * "leader" — e.g. height/weight are numeric and comparable, but taller/heavier
   * is not objectively better, so they are never marked best-in-row.
   */
  leader: LeaderDirection;
  /** Canonical (metric) unit label, or null for unitless / categorical rows. */
  unit: string | null;
  /** Conversion dimension for the Metric/Imperial toggle (null = no conversion). */
  dimension: Dimension;
}

// The authoritative per-metric table. Keys match the API CompareRow `key`
// (apps/api/app/services/reads.py COMPARE_FIELDS) plus the numeric spec keys the
// contract enumerates. Anything not listed defaults to display-only / NONE.
export const METRIC_POLICY: Record<string, MetricPolicy> = {
  // ── Commercial ──────────────────────────────────────────────────────────
  commercial_status: { key: "commercial_status", comparability: "display", leader: "NONE", unit: null, dimension: null },
  // ── Physical ────────────────────────────────────────────────────────────
  // Numeric & comparable (deltas valid) but NO objective leader.
  height_cm: { key: "height_cm", comparability: "numeric", leader: "NONE", unit: "cm", dimension: "length_cm" },
  weight_kg: { key: "weight_kg", comparability: "numeric", leader: "NONE", unit: "kg", dimension: "mass_kg" },
  // Numeric with an objective leader (higher is the metric-specific leader).
  payload_kg: { key: "payload_kg", comparability: "numeric", leader: "HIGHER", unit: "kg", dimension: "mass_kg" },
  walk_speed_ms: { key: "walk_speed_ms", comparability: "numeric", leader: "HIGHER", unit: "m/s", dimension: "speed_ms" },
  runtime_minutes: { key: "runtime_minutes", comparability: "numeric", leader: "HIGHER", unit: "min", dimension: "duration_min" },
  degrees_of_freedom: { key: "degrees_of_freedom", comparability: "numeric", leader: "HIGHER", unit: null, dimension: "count" },
  mobility: { key: "mobility", comparability: "display", leader: "NONE", unit: null, dimension: null },
  // ── Manipulation ────────────────────────────────────────────────────────
  hand_type: { key: "hand_type", comparability: "display", leader: "NONE", unit: null, dimension: null },
  hand_dof: { key: "hand_dof", comparability: "numeric", leader: "HIGHER", unit: null, dimension: "count" },
  has_manipulation: { key: "has_manipulation", comparability: "display", leader: "NONE", unit: null, dimension: null },
  // ── Intelligence ────────────────────────────────────────────────────────
  autonomy: { key: "autonomy", comparability: "display", leader: "NONE", unit: null, dimension: null },
  has_vision: { key: "has_vision", comparability: "display", leader: "NONE", unit: null, dimension: null },
  has_language_ui: { key: "has_language_ui", comparability: "display", leader: "NONE", unit: null, dimension: null },
  // ── Developer ───────────────────────────────────────────────────────────
  has_sdk: { key: "has_sdk", comparability: "display", leader: "NONE", unit: null, dimension: null },
  ros_support: { key: "ros_support", comparability: "display", leader: "NONE", unit: null, dimension: null },
  developer_edition: { key: "developer_edition", comparability: "display", leader: "NONE", unit: null, dimension: null },
};

const DEFAULT_POLICY: MetricPolicy = {
  key: "",
  comparability: "display",
  leader: "NONE",
  unit: null,
  dimension: null,
};

/** Policy for a metric key. Unknown keys default to display-only / no leader. */
export function policyFor(key: string): MetricPolicy {
  return METRIC_POLICY[key] ?? { ...DEFAULT_POLICY, key };
}

/**
 * Best-in-row eligibility: a metric is eligible ONLY when it is numeric AND has a
 * real leader direction. Categorical / maturity / availability / autonomy /
 * evidence-confidence rows are never eligible.
 */
export function isBestInRowEligible(key: string): boolean {
  const p = policyFor(key);
  return p.comparability === "numeric" && p.leader !== "NONE";
}

export type RowValues = Record<string, number | boolean | string | null>;

/**
 * Objective best-in-row. Returns the winning slug(s) for a metric, or [] when
 * there is no objective leader.
 *
 * Rules:
 *   - Only numeric, leader-bearing metrics are considered (else []).
 *   - UNKNOWN (null / non-number) is INELIGIBLE — never 0, never worst.
 *   - Requires at least two numeric candidates (a leader needs a field to lead).
 *   - ALL legitimate ties are returned (every slug at the leading value).
 */
export function bestInRow(key: string, values: RowValues): string[] {
  const p = policyFor(key);
  if (p.comparability !== "numeric" || p.leader === "NONE") return [];

  const numeric: { slug: string; v: number }[] = [];
  for (const [slug, raw] of Object.entries(values)) {
    if (typeof raw === "number" && Number.isFinite(raw)) numeric.push({ slug, v: raw });
  }
  if (numeric.length < 2) return [];

  const target =
    p.leader === "HIGHER"
      ? Math.max(...numeric.map((n) => n.v))
      : Math.min(...numeric.map((n) => n.v));
  return numeric.filter((n) => n.v === target).map((n) => n.slug);
}

/** A factual delta of a numeric metric against the reference robot. */
export type DeltaKind = "self" | "numeric" | "unknown" | "incomparable";
export interface MetricDelta {
  kind: DeltaKind;
  /** Signed delta in canonical units (target − reference), when kind === "numeric". */
  value?: number;
  unit: string | null;
}

/**
 * Factual numeric delta of a metric vs the reference robot. No qualitative
 * verdicts — a signed number in canonical units, or an explicit non-answer.
 *   - target IS the reference          → "self"
 *   - metric is not numeric/comparable → "incomparable"
 *   - either side is UNKNOWN           → "unknown" (UNKNOWN stays UNKNOWN)
 *   - otherwise                        → signed canonical delta
 */
export function metricDelta(
  key: string,
  referenceValue: number | boolean | string | null,
  targetValue: number | boolean | string | null,
  isReferenceColumn: boolean,
): MetricDelta {
  const p = policyFor(key);
  if (isReferenceColumn) return { kind: "self", unit: p.unit };
  if (p.comparability !== "numeric") return { kind: "incomparable", unit: p.unit };
  if (typeof referenceValue !== "number" || typeof targetValue !== "number") {
    return { kind: "unknown", unit: p.unit };
  }
  return { kind: "numeric", value: targetValue - referenceValue, unit: p.unit };
}

// ============================================================================
// PRICE COMPARISON — a price leader appears ONLY when offers are truly
// like-for-like. Wording is "LOWEST COMPARABLE PRICE" (never "best price").
// ============================================================================

/**
 * price_types that carry a single numeric `amount` with COMPATIBLE semantics.
 * RANGE (two bounds, no single value), QUOTE_ONLY (known, no number) and the
 * absence of any offer (UNKNOWN) are all excluded by construction.
 */
export const COMPARABLE_PRICE_TYPES = new Set(["PUBLIC", "FROM", "ESTIMATED"]);

const PRICE_TYPE_RANK: Record<string, number> = {
  PUBLIC: 0,
  FROM: 1,
  ESTIMATED: 2,
  RANGE: 3,
  QUOTE_ONLY: 4,
};

export interface NormalizedOffer {
  transaction_type: string;
  price_type: string;
  /** Single comparable amount, or null when the offer has no single number. */
  amount: number | null;
  currency: string | null;
  billing_period: string | null;
}

export interface OfferLike {
  transaction_type: string;
  price_type: string;
  price?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  currency: string | null;
  billing_period: string | null;
}

/**
 * The headline offer for a robot: PURCHASE first, then by price_type quality.
 * Mirrors the API/base-compare headline selection so display stays consistent.
 * `amount` is a single number only for single-value price types; RANGE and
 * QUOTE_ONLY resolve to null (no single comparable number).
 */
export function headlineOffer(offers: OfferLike[]): NormalizedOffer | null {
  if (offers.length === 0) return null;
  const sorted = [...offers].sort((a, b) => {
    const at = a.transaction_type === "PURCHASE" ? 0 : 1;
    const bt = b.transaction_type === "PURCHASE" ? 0 : 1;
    if (at !== bt) return at - bt;
    return (PRICE_TYPE_RANK[a.price_type] ?? 9) - (PRICE_TYPE_RANK[b.price_type] ?? 9);
  });
  const o = sorted[0];
  const amount = COMPARABLE_PRICE_TYPES.has(o.price_type) ? (o.price ?? null) : null;
  return {
    transaction_type: o.transaction_type,
    price_type: o.price_type,
    amount,
    currency: o.currency,
    billing_period: o.billing_period,
  };
}

export interface PriceLeaderInput {
  slug: string;
  offer: NormalizedOffer | null;
}

export interface PriceLeaderResult {
  /** True only when EVERY compared robot has a like-for-like numeric offer. */
  comparable: boolean;
  /** Winning slug(s) at the lowest comparable price (ties included), else []. */
  winners: string[];
  /** Machine-ish reason for the outcome (for UI copy / debugging). */
  reason: string;
}

/**
 * Determine the LOWEST COMPARABLE PRICE across the compared set. A winner is
 * emitted ONLY when the entire set is like-for-like:
 *   - every robot has a headline offer with an actual numeric amount,
 *   - identical transaction_type,
 *   - identical currency,
 *   - identical billing basis (billing_period),
 *   - identical, comparable price semantics (same price_type in the comparable set).
 * Any QUOTE_ONLY, UNKNOWN, or mixed-semantics offer → NO winner.
 */
export function computePriceLeader(inputs: PriceLeaderInput[]): PriceLeaderResult {
  if (inputs.length < 2) {
    return { comparable: false, winners: [], reason: "NEED_AT_LEAST_TWO" };
  }
  // Any missing/UNKNOWN offer (no offer rows at all) blocks comparison.
  if (inputs.some((i) => i.offer == null)) {
    return { comparable: false, winners: [], reason: "UNKNOWN_PRICE_PRESENT" };
  }
  const offers = inputs.map((i) => i.offer as NormalizedOffer);

  // Every offer must carry a single comparable number (excludes QUOTE_ONLY/RANGE).
  if (offers.some((o) => o.amount == null || !COMPARABLE_PRICE_TYPES.has(o.price_type))) {
    return { comparable: false, winners: [], reason: "NON_NUMERIC_OFFER_PRESENT" };
  }
  // Like-for-like: same transaction_type, currency, billing basis, price semantics.
  const first = offers[0];
  const homogeneous = offers.every(
    (o) =>
      o.transaction_type === first.transaction_type &&
      o.currency === first.currency &&
      o.billing_period === first.billing_period &&
      o.price_type === first.price_type,
  );
  if (!homogeneous) {
    return { comparable: false, winners: [], reason: "MIXED_OFFER_SEMANTICS" };
  }

  const min = Math.min(...offers.map((o) => o.amount as number));
  const winners = inputs.filter((i) => (i.offer as NormalizedOffer).amount === min).map((i) => i.slug);
  return { comparable: true, winners, reason: "LOWEST_COMPARABLE_PRICE" };
}

/** Kind of a price delta vs the reference robot. */
export type PriceDeltaKind = "self" | "numeric" | "incomparable";
export interface PriceDelta {
  kind: PriceDeltaKind;
  /** Signed amount (target − reference) when kind === "numeric". */
  value?: number;
  currency?: string | null;
}

/**
 * Factual price delta vs the reference robot. Only produced when both offers are
 * like-for-like numeric (same txn type, currency, billing basis, price
 * semantics). Anything else → "incomparable" ("no comparable offer").
 */
export function priceDelta(
  reference: NormalizedOffer | null,
  target: NormalizedOffer | null,
  isReferenceColumn: boolean,
): PriceDelta {
  if (isReferenceColumn) return { kind: "self" };
  if (!reference || !target) return { kind: "incomparable" };
  if (reference.amount == null || target.amount == null) return { kind: "incomparable" };
  if (
    !COMPARABLE_PRICE_TYPES.has(reference.price_type) ||
    !COMPARABLE_PRICE_TYPES.has(target.price_type)
  ) {
    return { kind: "incomparable" };
  }
  const likeForLike =
    reference.transaction_type === target.transaction_type &&
    reference.currency === target.currency &&
    reference.billing_period === target.billing_period &&
    reference.price_type === target.price_type;
  if (!likeForLike) return { kind: "incomparable" };
  return { kind: "numeric", value: target.amount - reference.amount, currency: target.currency };
}
