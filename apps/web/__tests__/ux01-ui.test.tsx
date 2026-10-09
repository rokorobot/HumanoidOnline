/**
 * UX-01 (Buyer Trust & Mobile Accessibility) - presentation behaviour:
 * price/availability integrity on cards and compare, human labels with the raw
 * enum preserved in data-enum, compact price disclosures, names (not slugs) in the
 * compare tray, the mobile filter disclosure and no developer jargon in public UI.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { ComparePriceCell } from "@/app/compare/CompareView";
import { AvailabilityMatrix } from "@/components/AvailabilityState";
import { CompareBar } from "@/components/CompareBar";
import { FilterPanel } from "@/components/FilterPanel";
import { PriceStateCard } from "@/components/PricingState";
import { RobotCard } from "@/components/RobotCard";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { StatusBadge, StatusBracket } from "@/components/StatusBadge";
import type { PricingOffer, RobotDetail, RobotListItem } from "@/lib/types";

beforeEach(() => push.mockClear());
afterEach(cleanup);

function robot(o: Partial<RobotListItem> = {}): RobotListItem {
  return {
    id: "r1",
    slug: "digit-like",
    name: "Digit",
    manufacturer: { slug: "agility", name: "Agility Robotics" },
    commercial_status: "RAAS_DEPLOYMENT",
    payload_kg: 16,
    height_cm: 175,
    mobility: "BIPEDAL",
    price_display: null,
    available_modes: [],
    deployment_count: 0,
    updated_at: "2026-01-01T00:00:00Z",
    ...o,
  };
}

describe("catalogue card - price and availability integrity", () => {
  it("Digit-like: modes but no price reads 'Offered via ...; no published price'", () => {
    const { container } = render(<RobotCard robot={robot({ available_modes: ["RAAS"] })} />);
    const text = container.textContent ?? "";
    expect(text).toContain("Offered · RaaS");
    expect(text).toContain("Offered via RaaS; no published price");
    expect(text).toContain("No published price");
    // no developer wording survives
    expect(text).not.toMatch(/NO PRICE DATA|no offer rows|UNKNOWN ·/);
    // status label replaces the enum but the enum is preserved
    const status = container.querySelector('[data-enum="RAAS_DEPLOYMENT"]');
    expect(status?.textContent).toBe("Robot-as-a-service");
  });

  it("H2-like: public price + order note + no modes never reads as orderable", () => {
    const { container } = render(
      <RobotCard
        robot={robot({
          name: "H2",
          slug: "unitree-h2",
          commercial_status: "COMMERCIAL",
          price_display: {
            type: "PUBLIC",
            amount: 29900,
            currency: "USD",
            billing_period: "ONE_TIME",
            order_status_note: "Not available to order from this seller at present.",
          },
          available_modes: [],
        })}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("$29,900");
    expect(text).toContain("Not available to order from this seller at present.");
    expect(text).toContain("Price published; ordering not confirmed");
    expect(text).toContain("Availability unknown");
    expect(text).not.toMatch(/Offered ·/);
  });

  it("nothing known: unknown tone, never 'not available'", () => {
    const { container } = render(<RobotCard robot={robot()} />);
    expect(container.textContent).toContain("No confirmed availability or price");
    expect(container.textContent).not.toMatch(/not available/i);
  });

  it("Compare button is a nowrap-able single element in an actions row", () => {
    const { container } = render(<RobotCard robot={robot()} compareHref="/robots?compare=digit-like" />);
    const btn = container.querySelector("button.cmp");
    expect(btn?.textContent).toBe("Compare +");
    expect(btn?.closest(".foot-actions")).toBeTruthy();
  });
});

describe("PriceStateCard - compact disclosure of long price terms", () => {
  const basis =
    "Listed price in EUR including 19% German VAT. Shipping is quoted separately and import duties are the buyer's responsibility; see the seller's terms of sale for details.";
  it("shows amount, a short tag and the full basis only inside <details>", () => {
    const { container } = render(
      <PriceStateCard
        price={{
          type: "PUBLIC",
          amount: 19999,
          currency: "EUR",
          billing_period: "ONE_TIME",
          price_basis: basis.replace("including 19% German VAT", "with VAT included"),
          order_status_note: "Ordering paused.",
          variant: "Standard",
        }}
      />,
    );
    expect(container.querySelector("details.price-terms summary")?.textContent).toBe("Incl. VAT · Price terms");
    const details = container.querySelector("details.price-terms");
    expect(details).toBeTruthy();
    expect(details?.querySelector("summary")?.textContent).toContain("Price terms");
    expect(details?.querySelector("p")?.textContent).toBe(
      basis.replace("including 19% German VAT", "with VAT included"),
    );
    // the long sentence is NOT rendered outside the disclosure
    const outside = Array.from(container.querySelectorAll(".ctx")).map((n) => n.textContent);
    expect(outside.join(" ")).not.toContain("import duties");
    // order status stays visible; configuration stays with the amount
    expect(outside).toContain("Ordering paused.");
    expect(outside).toContain("Configuration: Standard");
  });
  it("ambiguous basis derives no tag but keeps the full text", () => {
    const { container } = render(
      <PriceStateCard
        price={{ type: "PUBLIC", amount: 1, currency: "USD", price_basis: "VAT included; net of VAT for exports" }}
      />,
    );
    expect(container.querySelector("details summary")?.textContent).toBe("Price terms");
    expect(container.querySelector("details p")?.textContent).toContain("net of VAT");
  });
  it("no basis -> no disclosure", () => {
    const { container } = render(<PriceStateCard price={{ type: "PUBLIC", amount: 1, currency: "USD" }} />);
    expect(container.querySelector("details")).toBeNull();
  });
  it("QUOTE_ONLY stays distinct from unknown", () => {
    const quote = render(<PriceStateCard price={{ type: "QUOTE_ONLY", currency: "USD" }} />);
    expect(quote.container.querySelector(".price.quote")?.textContent).toContain("Price on request");
    cleanup();
    const unknown = render(<PriceStateCard price={null} />);
    expect(unknown.container.querySelector(".price.unknown .hatchbox")?.textContent).toBe("No published price");
  });
});

// Fixture modelled on 4NE1 Mini.
const mini = (offers: Partial<PricingOffer>[]): RobotDetail =>
  ({
    slug: "4ne1-mini",
    name: "4NE1 Mini",
    pricing_offers: offers.map((o) => ({
      transaction_type: "PURCHASE",
      price_type: "MANUFACTURER_ESTIMATE",
      currency: "EUR",
      billing_period: "ONE_TIME",
      ...o,
    })),
    availability_offers: [],
  }) as unknown as RobotDetail;

describe("compare price cell", () => {
  it("never shows a configuration-scoped amount without its configuration", () => {
    const { container } = render(
      <ComparePriceCell
        robot={mini([
          { variant: "Pro", price: 29999 },
          { variant: "Standard", price: 19999, order_status_note: "Pre-orders open." },
        ])}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("From €19,999");
    expect(text).not.toContain("29,999");
    expect(text).toContain("Standard configuration");
    expect(text).toContain("2 configurations priced");
    expect(text).toContain("Manufacturer estimate");
    expect(text).toContain("Pre-orders open.");
  });

  it("a single priced configuration: no From, no count, but the configuration is shown", () => {
    const { container } = render(<ComparePriceCell robot={mini([{ variant: "Standard", price: 19999 }])} />);
    const text = container.textContent ?? "";
    expect(text).toContain("€19,999");
    expect(text).not.toContain("From");
    expect(text).not.toContain("configurations priced");
    expect(text).toContain("Standard configuration");
  });

  it("shares the commercial summary line with the card", () => {
    const { container } = render(<ComparePriceCell robot={mini([{ variant: null, price: 100, price_type: "PUBLIC" }])} />);
    expect(container.textContent).toContain("Price published; ordering not confirmed");
  });

  it("no offers -> unknown wording, not zero", () => {
    const { container } = render(<ComparePriceCell robot={mini([])} />);
    expect(container.textContent).toContain("No confirmed pricing");
    expect(container.textContent).toContain("No confirmed availability or price");
  });
});

describe("CompareBar - names, not slugs", () => {
  it("shows display names and de-slugs a selected robot that is not on the page", () => {
    const { container } = render(
      <CompareBar slugs={["4ne1-mini", "agibot-a2-ultra"]} names={{ "4ne1-mini": "4NE1 Mini" }} />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("4NE1 Mini");
    expect(text).toContain("Agibot A2 Ultra");
    expect(text).not.toContain("4ne1-mini");
    expect(text).not.toContain("agibot-a2-ultra");
  });
});

describe("status labels keep the raw enum", () => {
  it("StatusBadge / StatusBracket render labels with data-enum", () => {
    const a = render(<StatusBadge status="LIMITED_COMMERCIAL" />);
    expect(a.container.querySelector("[data-enum]")?.getAttribute("data-enum")).toBe("LIMITED_COMMERCIAL");
    expect(a.container.textContent).toBe("Limited commercial availability");
    cleanup();
    const b = render(<StatusBracket status="UNKNOWN" />);
    expect(b.container.querySelector('[data-enum="UNKNOWN"]')).toBeTruthy();
    expect(b.container.textContent).not.toMatch(/_/);
  });
  it("availability matrix renders human wording with the enum preserved", () => {
    const { container } = render(
      <AvailabilityMatrix
        offers={[{ transaction_type: "RAAS", availability_status: "ON_REQUEST" } as never]}
      />,
    );
    expect(container.textContent).toContain("Availability on request");
    expect(container.querySelector('[data-enum="ON_REQUEST"]')).toBeTruthy();
    cleanup();
    const empty = render(<AvailabilityMatrix offers={[]} />);
    expect(empty.container.textContent).not.toMatch(/availability_offer|NOT_AVAILABLE/);
  });
});

describe("FilterPanel - mobile disclosure", () => {
  it("has a Filters toggle with aria-expanded/aria-controls, result and active counts", () => {
    render(<FilterPanel params={{ commercial_status: ["COMMERCIAL"] }} resultCount={42} activeCount={2} />);
    const toggle = screen.getByRole("button", { name: /filters/i });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toContain("Filters · 2 active");
    expect(toggle.textContent).toContain("42 results");
    const panelId = toggle.getAttribute("aria-controls") as string;
    expect(document.getElementById(panelId)?.tagName).toBe("FORM");
  });

  it("opens, moves focus into the panel, keeps Apply/Reset working, Escape closes and refocuses", async () => {
    render(<FilterPanel params={{}} resultCount={3} />);
    const toggle = screen.getByRole("button", { name: /filters/i });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const panel = document.getElementById(toggle.getAttribute("aria-controls") as string) as HTMLElement;
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(panel.contains(document.activeElement)).toBe(true);
    // the existing controls are all still there, with labels (values stay raw)
    expect(within(panel).getByLabelText("Commercial")).toBeTruthy();
    expect(within(panel).getByRole("button", { name: /apply/i })).toBeTruthy();
    expect(within(panel).getByRole("button", { name: /reset/i })).toBeTruthy();
    const raas = within(panel).getByLabelText("Robot-as-a-service") as HTMLInputElement;
    expect(raas.value).toBe("RAAS_DEPLOYMENT"); // form VALUE stays the raw enum
    fireEvent.keyDown(document, { key: "Escape" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(toggle);
  });

  it("Apply still pushes the URL and closes the panel", () => {
    render(<FilterPanel params={{}} resultCount={3} />);
    const toggle = screen.getByRole("button", { name: /filters/i });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));
    expect(push).toHaveBeenCalled();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("no developer jargon in public components", () => {
  const FORBIDDEN = [
    "WS3 /",
    "INTELLIGENCE UI",
    "Predicate",
    "commercially_accessible =",
    "NULL = UNKNOWN",
    "EVIDENCESTAMP",
    "EvidenceStamp +",
    "PRICE STATES",
    "without redesign",
    "availability_offer row",
    "TRANSACTION_TYPE ×",
    "transaction_type × price_type",
  ];
  it("rendered nav and footer carry none of it", () => {
    const { container } = render(
      <>
        <SiteNav active="robots" />
        <SiteFooter />
      </>,
    );
    for (const f of FORBIDDEN) expect(container.textContent).not.toContain(f);
  });
  it("source of the public pages carries none of it in rendered strings", () => {
    const root = resolve(__dirname, "..");
    for (const rel of ["app/robots/page.tsx", "app/robots/[slug]/page.tsx", "components/AvailabilityState.tsx"]) {
      const src = readFileSync(resolve(root, rel), "utf8");
      // strip comments so a code comment may keep the technical explanation
      const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      for (const f of FORBIDDEN) expect(code, `${rel} contains "${f}"`).not.toContain(f);
    }
  });
});
