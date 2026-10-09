// UX-01 / P0-A - one shared commercial summary + headline selection.
import { describe, expect, it } from "vitest";

import {
  accessibleModes,
  commercialSummary,
  hasPublishedAmount,
  priceDisplayFromHeadline,
  selectHeadline,
  shortBasisTag,
  type HeadlineOfferInput,
} from "../lib/commercial-summary";
import { headlineOffer } from "../lib/comparison-policy";
import type { PriceDisplay } from "../lib/types";

const pub: PriceDisplay = { type: "PUBLIC", amount: 29900, currency: "USD", billing_period: "ONE_TIME" };
const quote: PriceDisplay = { type: "QUOTE_ONLY", amount: null, currency: "USD", billing_period: "ONE_TIME" };

describe("commercialSummary - the four cases", () => {
  it("price with amount and no accessible modes", () => {
    const s = commercialSummary(pub, []);
    expect(s.line).toBe("Price published; ordering not confirmed");
    expect(s.kind).toBe("price_only");
  });
  it("accessible modes and no price", () => {
    expect(commercialSummary(null, ["RAAS", "PURCHASE"]).line).toBe(
      "Offered via RaaS, Purchase; no published price",
    );
  });
  it("accessible modes and a price", () => {
    expect(commercialSummary(pub, ["PURCHASE"]).line).toBe("Offered via Purchase");
  });
  it("neither: unknown, never 'not available'", () => {
    const s = commercialSummary(null, []);
    expect(s.line).toBe("No confirmed availability or price");
    expect(s.line).not.toMatch(/not available/i);
    expect(commercialSummary(undefined, undefined).kind).toBe("none");
  });
  it("price on request is a KNOWN fact, distinct from no published price", () => {
    expect(commercialSummary(quote, []).line).toBe("Price on request; ordering not confirmed");
    expect(commercialSummary(quote, ["RAAS"]).line).toBe("Offered via RaaS; price on request");
    expect(hasPublishedAmount(quote)).toBe(false);
    expect(hasPublishedAmount(pub)).toBe(true);
  });
});

describe("accessibleModes", () => {
  it("drops NOT_AVAILABLE / DISCONTINUED / non-NEW rows and de-duplicates", () => {
    expect(
      accessibleModes([
        { transaction_type: "PURCHASE", availability_status: "NOT_AVAILABLE" },
        { transaction_type: "RAAS", availability_status: "ON_REQUEST" },
        { transaction_type: "RAAS", availability_status: "AVAILABLE" },
        { transaction_type: "RENTAL", availability_status: "AVAILABLE", condition: "USED" },
      ]),
    ).toEqual(["RAAS"]);
  });
});

// Fixture modelled on 4NE1 Mini: Standard EUR 19,999 and Pro EUR 29,999, both
// MANUFACTURER_ESTIMATE, each scoped to its configuration.
const offer = (o: Partial<HeadlineOfferInput>): HeadlineOfferInput => ({
  transaction_type: "PURCHASE",
  price_type: "MANUFACTURER_ESTIMATE",
  price: 19999,
  currency: "EUR",
  billing_period: "ONE_TIME",
  ...o,
});

describe("selectHeadline", () => {
  it("several priced configurations -> lowest, with its configuration and a count", () => {
    const h = selectHeadline([
      offer({ variant: "Pro", price: 29999 }),
      offer({ variant: "Standard", price: 19999 }),
    ]);
    expect(h?.offer.variant).toBe("Standard");
    expect(h?.offer.price).toBe(19999);
    expect(h?.configurationsPriced).toBe(2);
    const pd = priceDisplayFromHeadline(h);
    expect(pd?.variant).toBe("Standard"); // the amount is never separated from its configuration
  });
  it("one configuration only -> no From framing, configuration still carried", () => {
    const h = selectHeadline([offer({ variant: "Standard" })]);
    expect(h?.configurationsPriced).toBe(0);
    expect(priceDisplayFromHeadline(h)?.variant).toBe("Standard");
  });
  it("a robot-level offer outranks configuration-scoped ones (no From)", () => {
    const h = selectHeadline([offer({ variant: "Pro", price: 29999 }), offer({ variant: null, price: 24000 })]);
    expect(h?.offer.price).toBe(24000);
    expect(h?.configurationsPriced).toBe(0);
  });
  it("different currencies are never ranked against each other", () => {
    const h = selectHeadline([
      offer({ variant: "A", price: 100, currency: "EUR" }),
      offer({ variant: "B", price: 90, currency: "USD" }),
    ]);
    expect(h?.configurationsPriced).toBe(0);
  });
  it("different price types never trigger From (not the same kind of figure)", () => {
    const h = selectHeadline([
      offer({ variant: "Standard", price_type: "PUBLIC", price: 19999 }),
      offer({ variant: "Pro", price: 29999 }),
    ]);
    expect(h?.offer.variant).toBe("Standard");
    expect(h?.configurationsPriced).toBe(0);
  });
  it("ignores non-NEW and edition-excluded offers; empty -> null", () => {
    expect(selectHeadline([offer({ condition: "USED" }), offer({ edition_confirmed: false })])).toBeNull();
    expect(selectHeadline([])).toBeNull();
  });
  it("feeds the like-for-like leader logic with the same row", () => {
    const n = headlineOffer([offer({ variant: "Pro", price: 29999 }), offer({ variant: "Standard" })]);
    expect(n?.amount).toBe(19999);
    expect(n?.variant).toBe("Standard");
    expect(n?.configurations_priced).toBe(2);
  });
});

describe("shortBasisTag", () => {
  it("derives a tag only when unambiguous", () => {
    expect(shortBasisTag("Price shown with VAT included (DE).")).toBe("Incl. VAT");
    expect(shortBasisTag("Listed price, net of VAT, ex works")).toBe("Excl. VAT/tax");
    expect(shortBasisTag("Excluding tax and shipping")).toBe("Excl. VAT/tax");
    expect(shortBasisTag("VAT included for EU buyers; excludes tax for exports")).toBeNull();
    expect(shortBasisTag("Manufacturer list price")).toBeNull();
    expect(shortBasisTag(null)).toBeNull();
  });
});
