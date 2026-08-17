// AGENT-02.1d — the price filter's currency pairing.
//
// The API takes `price_max` and `price_currency` as a required pair and applies
// no default currency, so the UI must state the denomination its label already
// shows ("Max purchase price (USD)"). The invariant that matters is that the two
// are inseparable: a lone `price_currency` is invalid by contract, so it must be
// impossible to produce — including when the price box is cleared, when a URL is
// hand-edited, and when the form submits without JavaScript.
import { describe, expect, it } from "vitest";

import {
  PRICE_CURRENCY,
  toQueryString,
  toRobotListParams,
} from "@/lib/search-params";

describe("price_max / price_currency pairing", () => {
  it("sends the currency whenever a price ceiling is active", () => {
    const params = toRobotListParams({ price_max: "30000" });
    expect(params.price_max).toBe(30000);
    expect(params.price_currency).toBe("USD");
  });

  it("sends neither member when no price is set", () => {
    const params = toRobotListParams({});
    expect(params.price_max).toBeUndefined();
    expect(params.price_currency).toBeUndefined();
  });

  it("drops BOTH members when the price field is cleared", () => {
    const cleared = toRobotListParams({ price_max: "" });
    expect(cleared.price_max).toBeUndefined();
    expect(cleared.price_currency).toBeUndefined();
  });

  it("never emits a lone currency from a hand-edited URL", () => {
    // `?price_currency=USD` alone is invalid by contract. Deriving the currency
    // from the ceiling makes that request unrepresentable rather than relying on
    // the server to reject it.
    const params = toRobotListParams({ price_currency: "USD" });
    expect(params.price_currency).toBeUndefined();
    expect(params.price_max).toBeUndefined();
  });

  it("ignores a conflicting currency in the URL rather than trusting it", () => {
    const params = toRobotListParams({ price_max: "30000", price_currency: "EUR" });
    expect(params.price_currency).toBe(PRICE_CURRENCY);
  });

  it("derives the currency for a no-JS submission that carried only price_max", () => {
    // The plain GET form has no currency field, so the URL it produces omits it.
    // The pair is still complete by the time the API is called.
    const params = toRobotListParams({ price_max: "50000", q: "atlas" });
    expect(params.price_currency).toBe("USD");
    expect(params.q).toBe("atlas");
  });

  it("treats a non-numeric price as no price at all", () => {
    const params = toRobotListParams({ price_max: "not-a-number" });
    expect(params.price_max).toBeUndefined();
    expect(params.price_currency).toBeUndefined();
  });

  it("leaves every other filter untouched", () => {
    const params = toRobotListParams({
      price_max: "30000",
      region: "DE",
      commercial_status: ["COMMERCIAL", "PILOT"],
      has_sdk: "true",
      sort: "-payload",
    });
    expect(params.region).toBe("DE");
    expect(params.commercial_status).toEqual(["COMMERCIAL", "PILOT"]);
    expect(params.has_sdk).toBe(true);
    expect(params.sort).toBe("-payload");
  });
});

describe("URL state", () => {
  it("round-trips an active price filter with its denomination visible", () => {
    const qs = toQueryString({ price_max: "30000", price_currency: PRICE_CURRENCY });
    expect(qs).toContain("price_max=30000");
    expect(qs).toContain("price_currency=USD");

    const restored = toRobotListParams(
      Object.fromEntries(new URLSearchParams(qs.slice(1))),
    );
    expect(restored.price_max).toBe(30000);
    expect(restored.price_currency).toBe("USD");
  });

  it("drops empty values so a cleared price leaves no trace in the URL", () => {
    expect(toQueryString({ price_max: "", price_currency: "" })).toBe("");
  });
});

describe("single currency declaration", () => {
  it("matches the denomination the control displays", () => {
    // The visible label is "Max purchase price (USD)". If this constant ever
    // changes without that label changing, the UI would be asserting a
    // denomination the user was never shown.
    expect(PRICE_CURRENCY).toBe("USD");
  });
});
