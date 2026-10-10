/**
 * UX-03 - mobile compare: Buyer context (Region vs Offer market), concise price
 * cells with an "Offers & evidence" sheet, availability wording, and the
 * two-column paging used when the compared set is too wide for the screen.
 *
 * Fixtures follow the real API response shape (RobotDetail / CompareResponse).
 * The unpublished Batch 01 records (R1, T2 Education) appear here as fixtures
 * only; the live UI renders whatever the published-only compare API returns.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/compare",
  useSearchParams: () => new URLSearchParams(),
}));

import { buildCompareUrl, CompareView, visiblePair } from "@/app/compare/CompareView";
import {
  contextCounts,
  inScope,
  NO_BUYER_CONTEXT,
  OFFER_MARKETS,
  parseContextCode,
  REGIONS,
  scopedRegions,
  type BuyerContext,
} from "@/lib/buyer-context";
import type {
  AvailabilityOffer,
  CompareResponse,
  Evidence,
  PricingOffer,
  RobotDetail,
} from "@/lib/types";

afterEach(() => cleanup());
beforeEach(() => push.mockReset());

// The scope lists exactly as GET /api/regions/{code}/scope returns them.
const EU_SCOPE = { applicable: ["EU", "GLOBAL"], market: ["DE", "EU", "GLOBAL", "IE"] };
const DE_SCOPE = { applicable: ["DE", "EU", "GLOBAL"], market: ["DE", "EU", "GLOBAL"] };

const ev = (over: Partial<Evidence> = {}): Evidence => ({
  source_type: "MANUFACTURER_SITE",
  confidence: "HIGH",
  observed_at: "2026-09-10T00:00:00Z",
  source_url: "https://example.test/source",
  ...over,
});

const price = (over: Partial<PricingOffer> = {}): PricingOffer => ({
  transaction_type: "PURCHASE",
  price_type: "PUBLIC",
  currency: "EUR",
  billing_period: "ONE_TIME",
  evidence: ev(),
  ...over,
});

const avail = (over: Partial<AvailabilityOffer> = {}): AvailabilityOffer => ({
  transaction_type: "PURCHASE",
  availability_status: "AVAILABLE",
  evidence: ev(),
  ...over,
});

const robot = (
  slug: string,
  name: string,
  pricing_offers: PricingOffer[],
  availability_offers: AvailabilityOffer[],
): RobotDetail =>
  ({
    id: slug,
    slug,
    name,
    manufacturer: { slug: "maker", name: "Maker" },
    commercial_status: "COMMERCIAL",
    pricing_offers,
    availability_offers,
    deployments: [],
  }) as unknown as RobotDetail;

// One robot per price state the matrix must carry.
const published = robot(
  "r1",
  "R1",
  [
    price({
      price: 9930,
      region: "DE",
      provider: "reichelt",
      provider_name: "reichelt elektronik",
      price_basis: "Including 19% German VAT",
      shipping_terms: "Shipping is extra",
    }),
  ],
  [avail({ region: "DE", provider: "reichelt", seller_wording: "Limited stock" })],
);
const twoRegions = robot(
  "t2",
  "T2 Education",
  [price({ price: 32100, region: "DE" }), price({ price: 33178.99, region: "IE" })],
  [],
);
const onRequest = robot(
  "h1",
  "H1",
  [price({ price_type: "QUOTE_ONLY", currency: "USD", region: "GLOBAL" })],
  [avail({ availability_status: "ON_REQUEST", region: "GLOBAL" })],
);
const ranged = robot(
  "rg",
  "Ranger",
  [price({ price_type: "RANGE", price_min: 20000, price_max: 30000, currency: "USD" })],
  [avail({ transaction_type: "RENTAL", region: "US" })],
);
const estimated = robot(
  "es",
  "Estimo",
  [price({ price_type: "ESTIMATED", price: 50000, currency: "USD" })],
  [],
);
const configured = robot(
  "mini",
  "Mini",
  [
    price({ price_type: "MANUFACTURER_ESTIMATE", variant: "Pro", price: 29999 }),
    price({ price_type: "MANUFACTURER_ESTIMATE", variant: "Standard", price: 19999 }),
  ],
  [avail({ availability_status: "WAITLIST", variant: "Standard" })],
);
const raasOnly = robot(
  "digit",
  "Digit",
  [],
  [avail({ transaction_type: "RAAS", availability_status: "ON_REQUEST", region: "US" })],
);
const weeklyRental = robot(
  "a2",
  "A2 Ultra",
  [price({ transaction_type: "RENTAL", billing_period: "WEEKLY", price: 6500, region: "BG" })],
  [avail({ transaction_type: "RENTAL", region: "BG" })],
);

const compare = (...robots: RobotDetail[]): CompareResponse => ({
  robots,
  rows: [
    {
      group: "physical",
      key: "height_cm",
      label: "Height",
      values: Object.fromEntries(robots.map((r, i) => [r.slug, 120 + i * 10])),
    },
  ],
});

const view = (
  robots: RobotDetail[],
  opts: { ref?: string | null; context?: BuyerContext } = {},
) =>
  render(
    <CompareView
      data={compare(...robots)}
      ids={robots.map((r) => r.slug)}
      state={{ ref: opts.ref ?? null, units: "metric", view: "matrix" }}
      context={opts.context}
    />,
  );

const rowOf = (container: HTMLElement, label: string) =>
  Array.from(container.querySelectorAll("table.cmatrix tr")).find(
    (tr) => tr.querySelector("th.rowlab")?.textContent === label,
  ) as HTMLElement;

describe("buyer context - Region and Offer market stay two questions", () => {
  it("accepts only the offered codes, case-insensitively", () => {
    expect(parseContextCode("eu", REGIONS)).toBe("EU");
    expect(parseContextCode("XX", REGIONS)).toBeNull();
    expect(parseContextCode("DE", OFFER_MARKETS)).toBeNull();
    expect(parseContextCode(undefined, REGIONS)).toBeNull();
  });

  it("a member-country offer is in the EU market but does not apply to the EU region", () => {
    expect(inScope("DE", EU_SCOPE.applicable)).toBe(false);
    expect(inScope("DE", EU_SCOPE.market)).toBe(true);
    // An EU-wide or worldwide offer applies to a buyer in Germany.
    expect(inScope("EU", DE_SCOPE.applicable)).toBe(true);
    expect(inScope("GLOBAL", DE_SCOPE.applicable)).toBe(true);
    // No region recorded: in scope everywhere, and never listed as a region.
    expect(inScope(null, EU_SCOPE.applicable)).toBe(true);
    expect(scopedRegions([{ region: null }, { region: "IE" }, { region: "US" }], EU_SCOPE.market)).toEqual(["IE"]);
  });

  it("counts follow the catalogue filters' predicates", () => {
    const robots = [published, twoRegions, raasOnly];
    const ctx: BuyerContext = {
      region: "EU",
      market: "EU",
      applicable: EU_SCOPE.applicable,
      marketCodes: EU_SCOPE.market,
    };
    // Region = EU: the German availability offer does not apply; nothing else is recorded.
    // Market = EU: R1 and T2 have German / Irish entries; Digit's only entry is US.
    expect(contextCounts(robots, ctx)).toEqual({ region: 0, market: 2 });
    expect(
      contextCounts(robots, { ...ctx, region: "DE", applicable: DE_SCOPE.applicable }).region,
    ).toBe(1);
    expect(contextCounts(robots, NO_BUYER_CONTEXT)).toEqual({ region: null, market: null });
  });

  it("round-trips through the URL with the catalogue's parameter names", () => {
    const base = { ref: null, units: "metric" as const, view: "matrix" as const };
    expect(buildCompareUrl(["a", "b"], base)).toBe("/compare?ids=a%2Cb");
    expect(buildCompareUrl(["a", "b"], { ...base, region: "DE", market: "EU" })).toBe(
      "/compare?ids=a%2Cb&region=DE&offered_in=EU",
    );
  });

  it("is collapsed by default and writes a choice to the URL", () => {
    view([published, twoRegions]);
    expect(screen.queryByLabelText(/^Region/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Buyer context/ }));
    fireEvent.change(screen.getByLabelText(/^Region/), { target: { value: "EU" } });
    expect(push).toHaveBeenCalledWith("/compare?ids=r1%2Ct2&region=EU", { scroll: false });
  });

  it("annotates recorded offers and never hides or changes them", () => {
    const { container } = view([published, twoRegions, raasOnly], {
      context: { region: "EU", market: "EU", applicable: EU_SCOPE.applicable, marketCodes: EU_SCOPE.market },
    });
    const cells = rowOf(container, "Purchase").querySelectorAll("td");
    // The recorded fact is still there, with what the context says beside it.
    expect(cells[0].textContent).toContain("Available");
    expect(cells[0].textContent).toContain("Recorded for DE; does not apply to EU");
    expect(cells[0].textContent).toContain("In EU market (DE)");
    const prices = rowOf(container, "Price").querySelectorAll("td");
    expect(prices[0].textContent).toContain("€9,930");
    expect(prices[1].textContent).toContain("In EU market (DE, IE)");
    // Digit has no price entry at all: nothing to annotate, nothing invented.
    expect(prices[2].textContent).not.toContain("market");
    expect(rowOf(container, "RaaS").querySelectorAll("td")[2].textContent).toContain("No EU market entry");
  });
});

describe("availability - missing evidence is not unavailability", () => {
  it("a robot with no availability entry reads 'Availability not recorded'", () => {
    const { container } = view([published, twoRegions]);
    const cells = rowOf(container, "Purchase").querySelectorAll("td");
    expect(cells[0].textContent).toContain("Available");
    expect(cells[1].textContent).toBe("Availability not recorded");
    expect(container.textContent).toContain("not a statement that it is unavailable");
  });

  it("keeps '—' for a robot that has entries, just not in this mode", () => {
    const { container } = view([published, raasOnly]);
    expect(rowOf(container, "Purchase").querySelectorAll("td")[1].textContent).toBe("—");
    expect(rowOf(container, "RaaS").querySelectorAll("td")[0].textContent).toBe("—");
  });

  it("still shows an availability row when no compared robot has any entry", () => {
    const { container } = view([twoRegions, estimated]);
    const cells = rowOf(container, "Availability").querySelectorAll("td");
    expect(Array.from(cells).map((c) => c.textContent)).toEqual([
      "Availability not recorded",
      "Availability not recorded",
    ]);
  });

  it("a status carries the date it was observed, not a live claim", () => {
    const { container } = view([published, onRequest]);
    expect(rowOf(container, "Purchase").querySelectorAll("td")[0].textContent).toContain(
      "observed 10 SEP 2026",
    );
  });
});

describe("price states in the matrix", () => {
  it("renders every state distinctly and never invents a number", () => {
    const { container } = view([published, onRequest, ranged, estimated]);
    const cells = Array.from(rowOf(container, "Price").querySelectorAll("td")).map(
      (c) => c.textContent ?? "",
    );
    expect(cells[0]).toContain("€9,930");
    expect(cells[1]).toContain("Price on request");
    expect(cells[1]).not.toMatch(/\d{2},\d{3}/);
    expect(cells[2]).toContain("$20,000");
    expect(cells[2]).toContain("$30,000");
    expect(cells[3]).toContain("~$50,000");
    expect(cells[3]).toContain("Estimated");
  });

  it("a configuration-scoped price keeps its configuration; no price stays unknown", () => {
    const { container } = view([configured, raasOnly]);
    const cells = Array.from(rowOf(container, "Price").querySelectorAll("td")).map(
      (c) => c.textContent ?? "",
    );
    expect(cells[0]).toContain("From €19,999");
    expect(cells[0]).toContain("Standard configuration");
    expect(cells[0]).toContain("2 configurations priced");
    expect(cells[1]).toContain("No confirmed pricing");
  });

  it("names a leader only among like-for-like offers", () => {
    const like = view([published, twoRegions]);
    expect(like.container.textContent).toContain("LOWEST COMPARABLE PRICE");
    expect(rowOf(like.container, "Price").querySelector("td.best")?.textContent).toContain("€9,930");
    cleanup();
    // Purchase vs weekly rental vs price on request: nothing is comparable.
    const mixed = view([published, weeklyRental, onRequest], { ref: "r1" });
    expect(mixed.container.textContent).not.toContain("LOWEST COMPARABLE PRICE");
    expect(rowOf(mixed.container, "Price").textContent).toContain("NO COMPARABLE OFFER");
  });

  it("one row per transaction mode on record", () => {
    const { container } = view([published, weeklyRental, raasOnly]);
    for (const label of ["Purchase", "Rental", "RaaS"]) expect(rowOf(container, label)).toBeTruthy();
  });
});

describe("offers & evidence sheet", () => {
  it("opens from the price cell with the full record of the same offers", () => {
    view([published, twoRegions]);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Offers and evidence: R1" }));
    const dialog = screen.getByRole("dialog", { hidden: true });
    const text = dialog.textContent ?? "";
    expect(within(dialog).getByRole("heading", { name: "R1", hidden: true })).toBeTruthy();
    for (const fact of [
      "€9,930",
      "Including 19% German VAT",
      "Shipping is extra",
      "reichelt elektronik",
      "Limited stock",
      "As observed 10 SEP 2026. Not a live stock check.",
      "OBSERVED",
    ]) {
      expect(text).toContain(fact);
    }
    expect(within(dialog).getAllByText("View source ↗")[0].getAttribute("href")).toBe(
      "https://example.test/source",
    );
  });

  it("lists every price entry, and says plainly when availability is not recorded", () => {
    view([published, twoRegions]);
    fireEvent.click(screen.getByRole("button", { name: "Offers and evidence: T2 Education" }));
    const text = screen.getByRole("dialog", { hidden: true }).textContent ?? "";
    expect(text).toContain("Price entries · 2");
    expect(text).toContain("€32,100");
    expect(text).toContain("€33,179");
    expect(text).toContain("Availability not recorded");
    expect(text).toContain("missing evidence, not a statement that the robot is unavailable");
  });

  it("closes from its close button", () => {
    view([published, twoRegions]);
    fireEvent.click(screen.getByRole("button", { name: "Offers and evidence: R1" }));
    fireEvent.click(screen.getByRole("button", { name: "Close offers and evidence", hidden: true }));
    expect(screen.queryByRole("dialog", { hidden: true })).toBeNull();
  });
});

describe("two-column paging for a set too wide for the screen", () => {
  it("shows adjacent pairs, or pins the reference robot", () => {
    const four = ["a", "b", "c", "d"];
    expect(visiblePair(["a", "b"], null, 0)).toEqual(["a", "b"]);
    expect(visiblePair(four, null, 0)).toEqual(["a", "b"]);
    expect(visiblePair(four, null, 2)).toEqual(["c", "d"]);
    expect(visiblePair(four, "c", 0)).toEqual(["c", "a"]);
    expect(visiblePair(four, "c", 2)).toEqual(["c", "d"]);
  });

  it("marks the paged-out columns consistently in the header and every row", () => {
    const { container } = view([published, onRequest, ranged, estimated]);
    const root = container.querySelector(".cmp-root") as HTMLElement;
    expect(root.getAttribute("data-n")).toBe("4");
    const offIn = (sel: string) =>
      Array.from(container.querySelectorAll(sel)).map((c) => c.classList.contains("c-off"));
    expect(offIn(".selrow .robotpick")).toEqual([false, false, true, true]);
    for (const tr of Array.from(container.querySelectorAll("table.cmatrix tr"))) {
      const cells = tr.querySelectorAll("td.cell:not([colspan])");
      if (cells.length !== 4) continue;
      expect(Array.from(cells).map((c) => c.classList.contains("c-off"))).toEqual([false, false, true, true]);
    }
    fireEvent.click(screen.getByRole("button", { name: "Show next robot" }));
    expect(offIn(".selrow .robotpick")).toEqual([true, false, false, true]);
  });

  it("two and three robots keep every column", () => {
    for (const set of [[published, onRequest], [published, onRequest, ranged]]) {
      const { container } = view(set);
      expect(container.querySelector(".cmp-root")?.getAttribute("data-n")).toBe(String(set.length));
      expect(container.querySelectorAll(".selrow .robotpick").length).toBe(set.length);
      cleanup();
    }
  });
});
