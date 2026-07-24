import { describe, expect, it } from "vitest";

import {
  bestInRow,
  computePriceLeader,
  headlineOffer,
  isBestInRowEligible,
  metricDelta,
  policyFor,
  priceDelta,
  type OfferLike,
} from "../lib/comparison-policy";

describe("policyFor / eligibility", () => {
  it("classifies numeric leaders, comparable-but-no-leader, and display-only", () => {
    expect(policyFor("payload_kg").leader).toBe("HIGHER");
    expect(isBestInRowEligible("payload_kg")).toBe(true);
    expect(isBestInRowEligible("runtime_minutes")).toBe(true);
    expect(isBestInRowEligible("walk_speed_ms")).toBe(true);
    expect(isBestInRowEligible("degrees_of_freedom")).toBe(true);

    // Numeric & comparable but NO objective leader → not best-in-row.
    expect(policyFor("height_cm").comparability).toBe("numeric");
    expect(policyFor("height_cm").leader).toBe("NONE");
    expect(isBestInRowEligible("height_cm")).toBe(false);
    expect(isBestInRowEligible("weight_kg")).toBe(false);

    // Categorical / maturity / autonomy / booleans → never eligible.
    for (const k of ["commercial_status", "autonomy", "mobility", "has_sdk", "has_vision"]) {
      expect(isBestInRowEligible(k)).toBe(false);
    }
    // Unknown keys default to display-only.
    expect(isBestInRowEligible("evidence_confidence")).toBe(false);
  });
});

describe("bestInRow — objective numeric leader only", () => {
  it("marks the single HIGHER leader", () => {
    expect(bestInRow("payload_kg", { a: 10, b: 25, c: 5 })).toEqual(["b"]);
  });

  it("marks ALL legitimate ties", () => {
    expect(bestInRow("payload_kg", { a: 25, b: 25, c: 5 }).sort()).toEqual(["a", "b"]);
  });

  it("UNKNOWN (null) is INELIGIBLE — never 0/worst, never wins or loses", () => {
    // b is UNKNOWN. It must not count as 0 (which would make a/c win by penalty),
    // and it must never itself win.
    const winners = bestInRow("payload_kg", { a: 10, b: null, c: 30 });
    expect(winners).toEqual(["c"]);
    expect(winners).not.toContain("b");
    // All-but-one UNKNOWN → fewer than two candidates → no leader.
    expect(bestInRow("payload_kg", { a: 10, b: null, c: null })).toEqual([]);
  });

  it("never marks categorical/leaderless rows", () => {
    expect(bestInRow("height_cm", { a: 170, b: 150 })).toEqual([]);
    expect(bestInRow("commercial_status", { a: "COMMERCIAL", b: "PROTOTYPE" })).toEqual([]);
    expect(bestInRow("autonomy", { a: "SUPERVISED", b: "TELEOPERATED" })).toEqual([]);
  });

  it("needs at least two numeric candidates", () => {
    expect(bestInRow("payload_kg", { a: 10 })).toEqual([]);
  });
});

describe("metricDelta — factual deltas vs reference (no verdicts)", () => {
  it("signed canonical delta for numeric metrics", () => {
    expect(metricDelta("payload_kg", 10, 14, false)).toEqual({ kind: "numeric", value: 4, unit: "kg" });
    expect(metricDelta("height_cm", 175, 170, false)).toEqual({ kind: "numeric", value: -5, unit: "cm" });
  });
  it("the reference column itself is 'self'", () => {
    expect(metricDelta("payload_kg", 10, 10, true).kind).toBe("self");
  });
  it("UNKNOWN on either side stays UNKNOWN", () => {
    expect(metricDelta("runtime_minutes", null, 120, false).kind).toBe("unknown");
    expect(metricDelta("runtime_minutes", 90, null, false).kind).toBe("unknown");
  });
  it("categorical metrics are incomparable (no numeric delta)", () => {
    expect(metricDelta("autonomy", "SUPERVISED", "TELEOPERATED", false).kind).toBe("incomparable");
  });
});

// ── Price comparison ────────────────────────────────────────────────────────

function offer(partial: Partial<OfferLike>): OfferLike {
  return {
    transaction_type: "PURCHASE",
    price_type: "PUBLIC",
    price: null,
    price_min: null,
    price_max: null,
    currency: "USD",
    billing_period: "ONE_TIME",
    ...partial,
  };
}

describe("headlineOffer", () => {
  it("prefers PURCHASE, then best price_type; RANGE/QUOTE_ONLY have no single amount", () => {
    const h = headlineOffer([
      offer({ transaction_type: "RENTAL", price_type: "PUBLIC", price: 500 }),
      offer({ transaction_type: "PURCHASE", price_type: "PUBLIC", price: 13500 }),
    ]);
    expect(h?.transaction_type).toBe("PURCHASE");
    expect(h?.amount).toBe(13500);

    expect(headlineOffer([offer({ price_type: "QUOTE_ONLY", price: null })])?.amount).toBeNull();
    expect(
      headlineOffer([offer({ price_type: "RANGE", price: null, price_min: 1, price_max: 2 })])?.amount,
    ).toBeNull();
    expect(headlineOffer([])).toBeNull();
  });
});

describe("computePriceLeader — LOWEST COMPARABLE PRICE, like-for-like only", () => {
  const lead = (offers: (OfferLike[] | null)[], slugs = ["a", "b", "c"]) =>
    computePriceLeader(
      offers.map((o, i) => ({ slug: slugs[i], offer: o == null ? null : headlineOffer(o) })),
    );

  it("marks the lowest when all offers are like-for-like PUBLIC/USD/ONE_TIME/PURCHASE", () => {
    const r = lead([
      [offer({ price: 13500 })],
      [offer({ price: 20000 })],
      [offer({ price: 13500 })],
    ]);
    expect(r.comparable).toBe(true);
    expect(r.winners.sort()).toEqual(["a", "c"]); // tie at the low value, both marked
    expect(r.reason).toBe("LOWEST_COMPARABLE_PRICE");
  });

  it("the frozen example {G1 $13,500 PUBLIC, H1 QUOTE_ONLY, Digit UNKNOWN} → NO winner", () => {
    const r = lead([
      [offer({ price: 13500 })], // G1 PUBLIC
      [offer({ price_type: "QUOTE_ONLY", price: null })], // H1 price on request
      null, // Digit: no price data (UNKNOWN)
    ]);
    expect(r.comparable).toBe(false);
    expect(r.winners).toEqual([]);
  });

  it("mixed transaction_type (PURCHASE vs RENTAL) → NO winner", () => {
    const r = lead([
      [offer({ transaction_type: "PURCHASE", price: 10000 })],
      [offer({ transaction_type: "RENTAL", price: 500, billing_period: "MONTHLY" })],
    ], ["a", "b"]);
    expect(r.comparable).toBe(false);
  });

  it("mixed currency → NO winner", () => {
    const r = lead([
      [offer({ price: 10000, currency: "USD" })],
      [offer({ price: 9000, currency: "EUR" })],
    ], ["a", "b"]);
    expect(r.comparable).toBe(false);
  });

  it("mixed price semantics (PUBLIC vs FROM) → NO winner", () => {
    const r = lead([
      [offer({ price_type: "PUBLIC", price: 10000 })],
      [offer({ price_type: "FROM", price: 9000 })],
    ], ["a", "b"]);
    expect(r.comparable).toBe(false);
    expect(r.reason).toBe("MIXED_OFFER_SEMANTICS");
  });

  it("QUOTE_ONLY is not UNKNOWN, yet neither is numeric → still no winner", () => {
    const r = lead([
      [offer({ price_type: "QUOTE_ONLY", price: null })],
      [offer({ price_type: "QUOTE_ONLY", price: null })],
    ], ["a", "b"]);
    expect(r.comparable).toBe(false);
  });
});

describe("priceDelta — factual, like-for-like only", () => {
  it("signed delta when both are like-for-like numeric", () => {
    const ref = headlineOffer([offer({ price: 13500 })]);
    const tgt = headlineOffer([offer({ price: 20000 })]);
    expect(priceDelta(ref, tgt, false)).toEqual({ kind: "numeric", value: 6500, currency: "USD" });
  });
  it("reference column is 'self'", () => {
    const ref = headlineOffer([offer({ price: 13500 })]);
    expect(priceDelta(ref, ref, true).kind).toBe("self");
  });
  it("QUOTE_ONLY / UNKNOWN / mismatched basis → incomparable", () => {
    const ref = headlineOffer([offer({ price: 13500 })]);
    const quote = headlineOffer([offer({ price_type: "QUOTE_ONLY", price: null })]);
    expect(priceDelta(ref, quote, false).kind).toBe("incomparable");
    expect(priceDelta(ref, null, false).kind).toBe("incomparable");
    const rental = headlineOffer([offer({ transaction_type: "RENTAL", price: 500, billing_period: "MONTHLY" })]);
    expect(priceDelta(ref, rental, false).kind).toBe("incomparable");
  });
});
