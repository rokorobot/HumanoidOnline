import { describe, expect, it } from "vitest";

import {
  boolLabel,
  countryName,
  formatRobotCount,
  maturityIndex,
  regionLabel,
  resolveAvailabilitySummary,
  resolvePriceState,
  specValue,
  formatObservedDate,
} from "../lib/format";
import type { PriceDisplay } from "../lib/types";

describe("resolvePriceState — the six frozen price states", () => {
  it("PUBLIC renders the number as-is", () => {
    const pd: PriceDisplay = {
      type: "PUBLIC",
      amount: 13500,
      currency: "USD",
      billing_period: "ONE_TIME",
    };
    expect(resolvePriceState(pd, "short").label).toBe("$13,500");
    expect(resolvePriceState(pd, "short").tone).toBe("public");
  });

  it("FROM prefixes 'From'", () => {
    const pd: PriceDisplay = { type: "FROM", amount: 5900, currency: "USD" };
    expect(resolvePriceState(pd).label).toBe("From $5,900");
  });

  it("RANGE uses k-notation on cards, full on detail", () => {
    const pd: PriceDisplay = {
      type: "RANGE",
      amount_min: 120000,
      amount_max: 200000,
      currency: "USD",
    };
    expect(resolvePriceState(pd, "short").label).toBe("$120k–$200k");
    expect(resolvePriceState(pd, "long").label).toBe("$120,000 – $200,000");
  });

  it("ESTIMATED is marked with ~ and amber tone", () => {
    const pd: PriceDisplay = { type: "ESTIMATED", amount: 30000, currency: "USD" };
    expect(resolvePriceState(pd).label).toBe("~$30,000");
    expect(resolvePriceState(pd).tone).toBe("estimated");
  });

  it("QUOTE_ONLY is 'Price on request' — never a number, distinct from unknown", () => {
    const pd: PriceDisplay = { type: "QUOTE_ONLY", amount: null, currency: "USD" };
    expect(resolvePriceState(pd, "short").label).toBe("PRICE ON REQUEST");
    expect(resolvePriceState(pd, "long").label).toBe("Price on request");
    expect(resolvePriceState(pd, "short").tone).toBe("quote");
  });

  it("UNKNOWN (null) is 'No confirmed pricing' — never $0/free, distinct from quote", () => {
    const short = resolvePriceState(null, "short");
    const long = resolvePriceState(undefined, "long");
    expect(short.label).toBe("NO PRICE DATA");
    expect(long.label).toBe("No confirmed pricing");
    expect(short.tone).toBe("unknown");
  });

  it("QUOTE_ONLY and UNKNOWN never collapse into the same label or tone", () => {
    const quote = resolvePriceState({ type: "QUOTE_ONLY", currency: "USD" }, "long");
    const unknown = resolvePriceState(null, "long");
    expect(quote.label).not.toBe(unknown.label);
    expect(quote.tone).not.toBe(unknown.tone);
  });
});

describe("resolveAvailabilitySummary", () => {
  it("empty modes -> explicit UNKNOWN (not NOT_AVAILABLE)", () => {
    const s = resolveAvailabilitySummary([], "short");
    expect(s.label).toBe("AVAILABILITY UNKNOWN");
    expect(s.isUnknown).toBe(true);
  });
  it("modes present -> accessible with the modes listed", () => {
    const s = resolveAvailabilitySummary(["PURCHASE", "DEVELOPER"], "short");
    expect(s.isUnknown).toBe(false);
    expect(s.modes).toContain("Purchase");
  });
});

describe("boolean & spec value states (NULL != false/0)", () => {
  it("null boolean is UNKNOWN, not NO", () => {
    expect(boolLabel(null).label).toBe("UNKNOWN");
    expect(boolLabel(false).label).toBe("NO");
    expect(boolLabel(true).label).toBe("YES");
  });
  it("null spec is UNKNOWN, never 0", () => {
    expect(specValue(null, "kg").unknown).toBe(true);
    expect(specValue(0, "kg").label).toBe("0 kg");
  });
});

describe("maturityIndex", () => {
  it("orders the ladder and puts DISCONTINUED off-ladder", () => {
    expect(maturityIndex("COMMERCIAL")).toBeGreaterThan(maturityIndex("PILOT"));
    expect(maturityIndex("DISCONTINUED")).toBe(-1);
  });
});

describe("formatRobotCount — singular/plural grammar", () => {
  it("uses the singular for exactly 1", () => {
    expect(formatRobotCount(1)).toBe("1 ROBOT");
  });
  it("uses the plural for 0 and N>1", () => {
    expect(formatRobotCount(0)).toBe("0 ROBOTS");
    expect(formatRobotCount(2)).toBe("2 ROBOTS");
    expect(formatRobotCount(11)).toBe("11 ROBOTS");
  });
});

describe("region labels", () => {
  it("maps known codes to names", () => {
    expect(countryName("NO")).toBe("Norway");
    expect(countryName("xx")).toBeNull();
  });
  it("detail label is 'NAME / CODE', card keeps the code", () => {
    expect(regionLabel("NO")).toBe("NORWAY / NO");
    expect(regionLabel("ZZ")).toBe("ZZ");
    expect(regionLabel(null)).toBeNull();
  });
});

describe("formatObservedDate", () => {
  it("renders uppercase DD MON YYYY", () => {
    expect(formatObservedDate("2026-07-24T00:00:00Z")).toBe("24 JUL 2026");
    expect(formatObservedDate(null)).toBeNull();
  });
});
