// AGENT-02.1e — canonical URL state for the price filter.
//
// `search-params.ts` declares the URL to be the single source of truth for
// catalogue state. That only holds if the address bar and the API request agree,
// so an active ceiling must carry its denomination explicitly in the URL, and a
// denomination must never appear without a ceiling.
//
// The interesting case is a URL naming a currency this USD-only UI cannot
// honour. Three things it must NOT do: quietly query USD instead (the address
// bar would then be lying), quietly drop the ceiling (silently widening the
// result set), or render results under a "(USD)" label that came from another
// currency. It refuses instead.
import { describe, expect, it } from "vitest";

import {
  PRICE_CURRENCY,
  canonicalizePriceParams,
  toQueryString,
  toRobotListParams,
  type RawSearchParams,
} from "@/lib/search-params";

function redirectTarget(sp: RawSearchParams): string {
  const result = canonicalizePriceParams(sp);
  expect(result.action).toBe("redirect");
  if (result.action !== "redirect") throw new Error("unreachable");
  return toQueryString(result.params);
}

describe("A. ceiling without a denomination", () => {
  it("redirects to add the explicit currency", () => {
    const qs = redirectTarget({ price_max: "30000" });
    expect(qs).toContain("price_max=30000");
    expect(qs).toContain("price_currency=USD");
  });

  it("is the no-JS form's path, and preserves every other filter", () => {
    // The plain GET form has no currency field, so this is exactly what it emits.
    const qs = redirectTarget({
      price_max: "30000",
      region: "DE",
      commercial_status: ["COMMERCIAL", "PILOT"],
      sort: "-payload",
      q: "atlas",
    });
    const params = new URLSearchParams(qs.slice(1));
    expect(params.get("price_currency")).toBe("USD");
    expect(params.get("region")).toBe("DE");
    expect(params.getAll("commercial_status")).toEqual(["COMMERCIAL", "PILOT"]);
    expect(params.get("sort")).toBe("-payload");
    expect(params.get("q")).toBe("atlas");
  });

  it("treats an empty currency value as absent", () => {
    expect(redirectTarget({ price_max: "30000", price_currency: "" })).toContain(
      "price_currency=USD",
    );
  });
});

describe("B. denomination without a ceiling", () => {
  it("redirects to drop the orphan currency", () => {
    const qs = redirectTarget({ price_currency: "USD" });
    expect(qs).not.toContain("price_currency");
  });

  it("drops it when the ceiling is non-numeric junk", () => {
    const qs = redirectTarget({ price_max: "not-a-number", price_currency: "USD" });
    expect(qs).not.toContain("price_currency");
  });

  it("keeps the rest of the query intact while dropping it", () => {
    const qs = redirectTarget({ price_currency: "USD", region: "US", sort: "price" });
    const params = new URLSearchParams(qs.slice(1));
    expect(params.has("price_currency")).toBe(false);
    expect(params.get("region")).toBe("US");
    expect(params.get("sort")).toBe("price");
  });
});

describe("C. canonical URL is stable", () => {
  it("leaves an explicit USD pair untouched", () => {
    expect(
      canonicalizePriceParams({ price_max: "30000", price_currency: "USD" }),
    ).toEqual({ action: "ok" });
  });

  it("leaves a URL with no price params untouched", () => {
    expect(canonicalizePriceParams({})).toEqual({ action: "ok" });
    expect(canonicalizePriceParams({ region: "DE", sort: "name" })).toEqual({
      action: "ok",
    });
  });

  it("leaves junk price_max alone when there is no currency to orphan", () => {
    expect(canonicalizePriceParams({ price_max: "abc" })).toEqual({ action: "ok" });
  });

  it("normalises a non-canonical spelling of the same currency once", () => {
    expect(redirectTarget({ price_max: "30000", price_currency: "usd" })).toContain(
      "price_currency=USD",
    );
  });

  it("never redirects in a loop: every redirect target is itself canonical", () => {
    const starts: RawSearchParams[] = [
      { price_max: "30000" },
      { price_currency: "USD" },
      { price_max: "30000", price_currency: "usd" },
      { price_max: "abc", price_currency: "USD" },
      { price_max: "30000", price_currency: "" },
    ];
    for (const start of starts) {
      const first = canonicalizePriceParams(start);
      expect(first.action).toBe("redirect");
      if (first.action !== "redirect") continue;
      expect(canonicalizePriceParams(first.params)).toEqual({ action: "ok" });
    }
  });
});

describe("D. a currency this UI cannot represent", () => {
  it("is rejected, never reinterpreted as USD", () => {
    const result = canonicalizePriceParams({
      price_max: "30000",
      price_currency: "EUR",
    });
    expect(result).toEqual({ action: "reject", currency: "EUR" });
  });

  it("is rejected rather than silently dropping the ceiling", () => {
    // Dropping it would return the UNFILTERED catalogue for a query that asked
    // for a ceiling — a silent widening, the exact failure the price contract
    // exists to prevent.
    const result = canonicalizePriceParams({
      price_max: "30000",
      price_currency: "GBP",
    });
    expect(result.action).toBe("reject");
  });

  it("rejects regardless of spelling", () => {
    for (const currency of ["eur", "Eur", " EUR ", "JPY"]) {
      expect(
        canonicalizePriceParams({ price_max: "1", price_currency: currency }).action,
      ).toBe("reject");
    }
  });
});

describe("URL and API request can never disagree about currency", () => {
  const urls: RawSearchParams[] = [
    {},
    { price_max: "30000", price_currency: "USD" },
    { price_max: "250000", price_currency: "USD", region: "DE" },
    { region: "US", sort: "price" },
    { price_max: "abc" },
  ];

  it("holds for every URL the route is willing to render", () => {
    for (const sp of urls) {
      const canonical = canonicalizePriceParams(sp);
      expect(canonical.action).toBe("ok"); // these render as-is
      const api = toRobotListParams(sp);
      const urlCurrency = sp.price_currency as string | undefined;

      if (api.price_max != null) {
        // Whatever the API is asked, the URL says the same thing.
        expect(api.price_currency).toBe(urlCurrency);
      } else {
        // No ceiling -> no denomination reaches the API, whatever the URL holds.
        expect(api.price_currency).toBeUndefined();
      }
    }
  });

  it("holds after a canonicalizing redirect", () => {
    const result = canonicalizePriceParams({ price_max: "30000" });
    expect(result.action).toBe("redirect");
    if (result.action !== "redirect") return;

    const api = toRobotListParams(result.params);
    expect(api.price_currency).toBe(result.params.price_currency);
    expect(api.price_currency).toBe(PRICE_CURRENCY);
  });

  it("never sends a denomination the URL does not contain", () => {
    const api = toRobotListParams({ price_currency: "USD" });
    expect(api.price_max).toBeUndefined();
    expect(api.price_currency).toBeUndefined();
  });
});
