import { describe, expect, it } from "vitest";

import { buildLineAnswer, lowestPricesByCurrency } from "../lib/line-answer";
import { edition, offer } from "./line-fixture";

describe("buildLineAnswer", () => {
  it("states the edition count and names", () => {
    const a = buildLineAnswer("Unitree G1", [edition("a", "G1 Basic"), edition("b", "G1 EDU")]);
    expect(a.paragraphs[0]).toBe("Unitree G1 is sold in 2 published editions: G1 Basic, G1 EDU.");
  });

  it("single edition uses the singular and one height without 'all editions'", () => {
    const a = buildLineAnswer("Solo", [edition("a", "Solo One", { height: 120 })]);
    expect(a.paragraphs[0]).toBe("Solo is sold in 1 published edition: Solo One.");
    expect(a.text).toContain("Standing height: 120 cm.");
    expect(a.text).not.toContain("all editions");
  });

  it("lowest published price per currency, labelled, never converted", () => {
    const g1 = edition("g1", "G1 Basic", {
      pricing_offers: [
        offer({ price_type: "PUBLIC", price: 17900, currency: "USD", provider_name: "RobotShop" }),
        offer({ price_type: "PUBLIC", price: 13500, currency: "USD" }),
        offer({ price_type: "PUBLIC", price: 85000, currency: "CNY", provider_name: "Unitree CN" }),
      ],
    });
    const edu = edition("edu", "G1 EDU Plus U2", {
      pricing_offers: [offer({ price_type: "PUBLIC", price: 917990, currency: "CZK", provider_name: "Alza" })],
    });
    const a = buildLineAnswer("Unitree G1", [g1, edu]);
    expect(a.text).toContain(
      "Lowest published price in CNY: CN¥85,000 (G1 Basic, Published price, seller: Unitree CN, observed 2026-10-18).",
    );
    expect(a.text).toContain(
      "Lowest published price in USD: $13,500 (G1 Basic, Published price, seller: Unitree Store, observed 2026-10-18).",
    );
    expect(a.text).toContain("Lowest published price in CZK:");
    expect(a.text).toContain("Alza");
    expect(a.text).toContain("Prices in different currencies are not converted or compared.");
    expect(a.text).not.toContain("17,900");
  });

  it("does not compare across currencies: a numerically smaller foreign amount never wins", () => {
    const r = edition("x", "X", {
      pricing_offers: [
        offer({ price_type: "PUBLIC", price: 100, currency: "CNY" }),
        offer({ price_type: "PUBLIC", price: 5000, currency: "USD" }),
      ],
    });
    const rows = lowestPricesByCurrency([r]);
    expect(rows.map((p) => p.currency)).toEqual(["CNY", "USD"]);
  });

  it("quote-only editions say 'price on request'; unpriced ones say 'no published price'", () => {
    const priced = edition("a", "Basic", { pricing_offers: [offer({ price_type: "PUBLIC", price: 5900 })] });
    const quote = edition("b", "EDU", { pricing_offers: [offer({ price_type: "QUOTE_ONLY", price: null })] });
    const none = edition("c", "Pro");
    const a = buildLineAnswer("L", [priced, quote, none]);
    expect(a.text).toContain("EDU: price on request.");
    expect(a.text).toContain("Pro: no published price.");
    expect(a.text).not.toMatch(/Basic: (price on request|no published price)/);
  });

  it("estimates, rentals and used offers are never 'published prices'", () => {
    const r = edition("a", "A", {
      pricing_offers: [
        offer({ price_type: "ESTIMATED", price: 1000 }),
        offer({ price_type: "MANUFACTURER_ESTIMATE", price: 1100 }),
        offer({ price_type: "PUBLIC", price: 50, billing_period: "MONTHLY" }),
        offer({ price_type: "PUBLIC", price: 900, condition: "USED" }),
      ],
    });
    expect(lowestPricesByCurrency([r])).toEqual([]);
    expect(buildLineAnswer("L", [r]).text).toContain("No edition has a published price.");
  });

  it("a range counts by its lower bound and keeps its range label", () => {
    const r = edition("a", "A", {
      pricing_offers: [offer({ price_type: "RANGE", price: null, price_min: 8000, price_max: 9000 })],
    });
    const [p] = lowestPricesByCurrency([r]);
    expect(p.amountLabel).toBe("$8,000 – $9,000");
    expect(p.priceTypeLabel).toBe("Price range");
  });

  it("missing seller / date are stated as not recorded, never invented", () => {
    const r = edition("a", "A", {
      pricing_offers: [
        offer({ price_type: "PUBLIC", price: 10, provider: null, provider_name: null, evidence: null }),
      ],
    });
    expect(buildLineAnswer("L", [r]).text).toContain("seller: not recorded, observed date not recorded");
  });

  it("height: same everywhere -> once, 'all editions'", () => {
    const a = buildLineAnswer("L", [edition("a", "A", { height: 132 }), edition("b", "B", { height: 132 })]);
    expect(a.text).toContain("Standing height: 132 cm (all editions).");
  });

  it("height: mixed values are stated per edition", () => {
    const a = buildLineAnswer("L", [edition("a", "A", { height: 120 }), edition("b", "B", { height: 130 })]);
    expect(a.text).toContain("Standing height: A 120 cm; B 130 cm.");
  });

  it("height: an unknown edition is 'not published' and never borrows from a sibling", () => {
    const a = buildLineAnswer("L", [edition("a", "A", { height: 132 }), edition("b", "B")]);
    expect(a.text).toContain("Standing height: A 132 cm; B not published.");
    expect(a.text).not.toContain("all editions");
  });

  it("height: unknown everywhere", () => {
    const a = buildLineAnswer("L", [edition("a", "A"), edition("b", "B")]);
    expect(a.text).toContain("Standing height: not published for any edition.");
  });

  it("no published editions", () => {
    expect(buildLineAnswer("L", []).text).toBe("L has no published editions.");
  });
});
