/**
 * DR-UI2 (ecosystem blend): offer-board pairing safety, request-from-row prefill,
 * catalogue mode tabs / board view URLs, the ecosystem rail's landmark role, and
 * the explicit UNKNOWN states the boards must keep.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { CatalogueBoard } from "@/components/CatalogueBoard";
import { EcosystemRail } from "@/components/EcosystemRail";
import { HomeOfferBoard } from "@/components/HomeOfferBoard";
import { OfferBoard } from "@/components/OfferBoard";
import { activeModeTab, catalogueView, modeTabHref, viewHref, withoutMode } from "@/lib/catalogue-view";
import { buildOfferRows, leadTransactionFor } from "@/lib/offer-board";
import type { AvailabilityOffer, PricingOffer, RobotListItem } from "@/lib/types";

afterEach(cleanup);

const ev = (confidence = "MEDIUM", verified_at: string | null = null) => ({
  source_type: "OTHER",
  confidence,
  observed_at: "2026-10-04T00:00:00Z",
  verified_at,
  source_url: "https://example.com/src",
});

function avail(o: Partial<AvailabilityOffer> = {}): AvailabilityOffer {
  return {
    transaction_type: "RENTAL",
    availability_status: "AVAILABLE",
    region: "BG",
    provider: "robotoplus",
    provider_name: "Robotoplus",
    condition: "NEW",
    evidence: ev(),
    ...o,
  };
}

function price(o: Partial<PricingOffer> = {}): PricingOffer {
  return {
    transaction_type: "RENTAL",
    price_type: "PUBLIC",
    price: 6500,
    currency: "EUR",
    billing_period: "WEEKLY",
    region: "BG",
    provider: "robotoplus",
    provider_name: "Robotoplus",
    price_basis: "Net of VAT and shipping",
    condition: "NEW",
    evidence: ev(),
    ...o,
  };
}

describe("buildOfferRows — pairing safety", () => {
  it("joins a price and an availability only on an identical offer identity", () => {
    const rows = buildOfferRows([price()], [avail()]);
    expect(rows).toHaveLength(1);
    expect(rows[0].availability).toHaveLength(1);
    expect(rows[0].prices).toHaveLength(1);
  });

  it("never puts one seller's price under another seller's availability", () => {
    const rows = buildOfferRows([price({ provider: "other-seller", provider_name: "Other" })], [avail()]);
    expect(rows).toHaveLength(2);
    const byProvider = Object.fromEntries(rows.map((r) => [r.provider, r]));
    expect(byProvider.robotoplus.prices).toEqual([]);
    expect(byProvider["other-seller"].availability).toEqual([]);
  });

  it("does not widen a price across regions, configurations or condition", () => {
    const rows = buildOfferRows(
      [
        price({ region: "RO" }),
        price({ variant: "Pro", variant_slug: "pro" }),
        price({ condition: "USED" }),
        price({ provider: null, provider_name: null }),
      ],
      [avail()],
    );
    expect(rows).toHaveLength(5);
    const base = rows.find((r) => r.region === "BG" && !r.variant && r.condition === "NEW" && r.provider === "robotoplus");
    expect(base?.prices).toEqual([]);
  });

  it("orders obtainable statuses first, then rows with no availability record", () => {
    const rows = buildOfferRows(
      [price({ transaction_type: "PURCHASE", region: "DE", provider: "reichelt" })],
      [avail({ availability_status: "ON_REQUEST", region: "RO" }), avail()],
    );
    expect(rows.map((r) => [r.region, r.availability[0]?.availability_status ?? null])).toEqual([
      ["BG", "AVAILABLE"],
      ["RO", "ON_REQUEST"],
      ["DE", null],
    ]);
  });

  it("is deterministic: the same input gives the same output", () => {
    const p = [price(), price({ region: "RO" })];
    const a = [avail({ region: "RO" }), avail()];
    expect(buildOfferRows(p, a)).toEqual(buildOfferRows([...p].reverse(), [...a].reverse()));
  });

  it("maps modes onto the lead form's vocabulary and never guesses one", () => {
    expect(leadTransactionFor("RENTAL")).toBe("RENT");
    expect(leadTransactionFor("PURCHASE")).toBe("BUY");
    expect(leadTransactionFor("SUBSCRIPTION")).toBe("");
  });
});

describe("OfferBoard", () => {
  const props = { robotSlug: "a2", robotName: "A2 Ultra", names: {}, countries: [] };

  it("renders price, status and evidence together, and unknown sides explicitly", () => {
    const { container } = render(
      <OfferBoard
        {...props}
        pricing={[price(), price({ transaction_type: "PURCHASE", region: "DE", provider: "reichelt", provider_name: "reichelt" })]}
        availability={[avail(), avail({ transaction_type: "PURCHASE", availability_status: "ON_REQUEST", region: "RO" })]}
      />,
    );
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(3);
    const first = within(rows[0] as HTMLElement);
    expect(first.getByText("€6,500")).toBeTruthy();
    expect(first.getByText("Available")).toBeTruthy();
    expect(first.getByText("Net of VAT and shipping")).toBeTruthy();
    expect(first.getAllByText("View source ↗")).toHaveLength(2);
    // Availability without a price: the explicit unknown price state, never $0.
    expect(within(rows[1] as HTMLElement).getByText("No confirmed pricing")).toBeTruthy();
    // Price without availability: unknown, not "unavailable".
    expect(within(rows[2] as HTMLElement).getByText("No availability on record")).toBeTruthy();
    expect(container.textContent).not.toMatch(/\$0|unavailable/i);
    // The scroll container keeps the keyboard-focusable named region.
    const scroll = container.querySelector(".ptable");
    expect(scroll?.getAttribute("tabindex")).toBe("0");
  });

  it("with no offers at all, shows explicit unknown cells", () => {
    const { container } = render(<OfferBoard {...props} pricing={[]} availability={[]} />);
    expect(screen.getByText("No confirmed pricing")).toBeTruthy();
    expect(container.querySelector(".offer-board .val.unknown")).toBeTruthy();
  });

  it("only shows Verified when verified_at is present", () => {
    render(
      <OfferBoard {...props} pricing={[]} availability={[avail({ evidence: ev("VERIFIED", null) })]} />,
    );
    expect(screen.queryByText("Verified")).toBeNull();
  });

  it("Request opens the lead dialog with the offer stub and an editable prefill", () => {
    render(<OfferBoard {...props} pricing={[price()]} availability={[avail()]} />);
    fireEvent.click(screen.getByRole("button", { name: /Request this offer/ }));
    const dialog = screen.getByRole("dialog");
    const stub = within(dialog).getByRole("complementary", { name: "Selected offer" });
    expect(within(stub).getByText("Rental · BG")).toBeTruthy();
    expect(within(stub).getByText("Robotoplus")).toBeTruthy();
    expect((within(dialog).getByLabelText("Preferred transaction") as HTMLSelectElement).value).toBe("RENT");
    const message = within(dialog).getByLabelText("Additional message") as HTMLTextAreaElement;
    expect(message.value).toContain("Seller: Robotoplus");
    // The buyer's own country is never prefilled from the offer region.
    expect((within(dialog).getByLabelText("Country") as HTMLSelectElement).value).toBe("");
  });
});

describe("catalogue view helpers", () => {
  it("builds tab and view links without compare or offset", () => {
    const sp = { q: "warehouse", compare: "a,b", offset: "20", view: "board", transaction_type: "PURCHASE" };
    expect(modeTabHref(sp, "RENTAL")).toBe("/robots?q=warehouse&view=board&transaction_type=RENTAL");
    expect(modeTabHref(sp, null)).toBe("/robots?q=warehouse&view=board");
    expect(viewHref(sp, "cards")).toBe("/robots?q=warehouse&transaction_type=PURCHASE");
    expect(viewHref({}, "board")).toBe("/robots?view=board");
  });

  it("marks All, a single mode, or nothing for a mixed filter", () => {
    expect(activeModeTab({})).toBeNull();
    expect(activeModeTab({ transaction_type: "RENTAL" })).toBe("RENTAL");
    expect(activeModeTab({ transaction_type: ["RENTAL", "LEASE"] })).toBeUndefined();
    expect(withoutMode({ transaction_type: "RENTAL", q: "x" })).toEqual({ q: "x" });
    expect(catalogueView({ view: "board" })).toBe("board");
    expect(catalogueView({ view: "x" })).toBe("cards");
  });
});

function item(o: Partial<RobotListItem> = {}): RobotListItem {
  return {
    id: "1",
    slug: "a2",
    name: "A2 Ultra",
    manufacturer: { slug: "agibot", name: "AgiBot" },
    commercial_status: "COMMERCIAL",
    payload_kg: null,
    height_cm: 169,
    mobility: "BIPEDAL",
    price_display: null,
    available_modes: [],
    deployment_count: 0,
    updated_at: "2026-10-01T00:00:00Z",
    ...o,
  };
}

describe("boards keep UNKNOWN explicit", () => {
  it("catalogue board: unknown payload, unknown availability, no published price", () => {
    const { container } = render(
      <CatalogueBoard robots={[item()]} compareHref={() => "/robots?compare=a2"} compareSlugs={[]} />,
    );
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.getByText("Availability unknown")).toBeTruthy();
    expect(screen.getByText("No published price")).toBeTruthy();
    // Crawl containment: the compare action is a button, never an <a href>.
    expect(container.querySelector('a[href*="compare="]')).toBeNull();
  });

  it("home board: headline price keeps its seller and region", () => {
    render(
      <HomeOfferBoard
        robots={[
          item({
            available_modes: ["RENTAL"],
            price_display: { type: "PUBLIC", amount: 6500, currency: "EUR", billing_period: "WEEKLY", provider: "robotoplus", provider_name: "Robotoplus", region: "BG" },
          }),
        ]}
        tabs={[{ mode: "RENTAL", label: "Rental", count: 3 }]}
      />,
    );
    expect(screen.getByText("€6,500")).toBeTruthy();
    expect(screen.getByText("Robotoplus · BG")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Rental 3/ }).getAttribute("href")).toBe(
      "/robots?transaction_type=RENTAL&view=board",
    );
  });
});

describe("ecosystem rail", () => {
  it("is a banner, not a navigation landmark, and links only live platforms", () => {
    const { container } = render(<EcosystemRail />);
    expect(container.querySelector("nav")).toBeNull();
    expect(screen.getByRole("banner", { name: "Humanoid.Company platforms" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /RentHumanoid/ }).getAttribute("href")).toBe("https://renthumanoid.com/");
    expect(screen.queryByRole("link", { name: /HumanoidMart|HumanoidLease/ })).toBeNull();
    expect(screen.getAllByText("· In development")).toHaveLength(2);
  });
});
