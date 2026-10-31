/**
 * DR-L1 (b) — product-line page: title, JSON-LD parity, rendering, sitemap, llms.txt.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ProductLinePage } from "../components/ProductLinePage";
import { buildProductLineJsonLd } from "../lib/jsonld";
import { buildLineAnswer } from "../lib/line-answer";
import { lineTitle } from "../lib/robot-meta";
import { edition, line, offer } from "./line-fixture";

const ORIGIN = "https://lines.test.invalid";

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});
afterEach(cleanup);

const basic = edition("unitree-g1", "G1 Basic", {
  height: 132,
  pricing_offers: [offer({ price_type: "PUBLIC", price: 13500 })],
  availability_offers: [
    { transaction_type: "PURCHASE", availability_status: "AVAILABLE", condition: "NEW" },
  ],
});
const edu = edition("unitree-g1-edu-plus-u2", "G1 EDU Plus U2", {
  height: 132,
  commercial_status: "LIMITED_COMMERCIAL",
  pricing_offers: [offer({ price_type: "QUOTE_ONLY", price: null })],
});
const L = line([basic, edu]);

describe("lineTitle", () => {
  it("names price only when some edition has a published price", () => {
    expect(lineTitle(L)).toBe("Unitree G1: Price, Specs & Editions");
    expect(lineTitle(line([edu]))).toBe("Unitree G1: Specs & Editions");
    expect(lineTitle(line([]))).toBe("Unitree G1: Specs & Editions");
  });
});

describe("ProductGroup JSON-LD", () => {
  const graph = () => buildProductLineJsonLd(L)["@graph"] as Array<Record<string, unknown>>;
  const group = () => graph().find((n) => n["@type"] === "ProductGroup")!;

  it("is a ProductGroup with canonical url, name and brand", () => {
    expect(group().url).toBe(`${ORIGIN}/lines/unitree-g1`);
    expect(group().name).toBe("Unitree G1");
    expect(group().brand).toEqual({ "@type": "Brand", name: "Unitree Robotics" });
  });

  it("hasVariant is exactly the published editions, by url and name (parity with the page)", () => {
    const variants = group().hasVariant as Array<{ url: string; name: string }>;
    expect(variants.map((v) => v.url)).toEqual(L.robots.map((r) => `${ORIGIN}/robots/${r.slug}`));
    expect(variants.map((v) => v.name)).toEqual(L.robots.map((r) => r.name));
    render(<ProductLinePage line={L} />);
    const rows = within(screen.getByTestId("edition-table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(variants.length);
  });

  it("asserts no offers, prices, availability or specs on the group", () => {
    const text = JSON.stringify(graph());
    for (const forbidden of ["offers", "price", "availability", "height", "additionalProperty"]) {
      expect(text.toLowerCase()).not.toContain(forbidden);
    }
  });
});

describe("ProductLinePage", () => {
  it("renders the H1, then the direct answer before the edition table", () => {
    render(<ProductLinePage line={L} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Unitree G1");
    const answer = screen.getByTestId("direct-answer");
    expect(answer.textContent).toBe(buildLineAnswer("Unitree G1", L.robots).paragraphs.join(""));
    const table = screen.getByTestId("edition-table");
    expect(answer.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("links each edition to its robot page and shows UNKNOWN cells as not published", () => {
    render(<ProductLinePage line={line([basic, edition("x", "X")])} />);
    const link = screen.getByRole("link", { name: "G1 Basic" });
    expect(link.getAttribute("href")).toBe("/robots/unitree-g1");
    const row = document.querySelector('tr[data-edition="x"]')!;
    expect(row.textContent).toContain("Not published");
    expect(row.textContent).not.toContain("0 cm");
  });

  it("shows the price state per edition with the shared labels", () => {
    render(<ProductLinePage line={L} />);
    const rows = document.querySelectorAll("tr[data-edition]");
    expect(rows[0].textContent).toContain("$13,500");
    expect(rows[1].textContent).toContain("Price on request");
  });

  it("cites the manufacturer page that groups the editions", () => {
    render(<ProductLinePage line={L} />);
    expect(screen.getByRole("link", { name: "https://www.unitree.com/g1/" })).toBeTruthy();
  });
});

describe("sitemap and llms.txt", () => {
  beforeEach(() => {
    vi.resetModules();
    const robots = [
      { slug: "unitree-g1", name: "G1 Basic", manufacturer: { slug: "unitree", name: "Unitree" }, updated_at: "2026-10-01T00:00:00Z" },
      { slug: "unitree-g1-edu-plus-u2", name: "EDU", manufacturer: { slug: "unitree", name: "Unitree" }, updated_at: "2026-10-20T00:00:00Z" },
    ];
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: robots, total: 2 })),
      listManufacturers: vi.fn(async () => ({ items: [], total: 0 })),
      listUseCases: vi.fn(async () => ({ items: [], total: 0 })),
      listProductLines: vi.fn(async () => [
        {
          slug: "unitree-g1", name: "Unitree G1", manufacturer: { slug: "unitree", name: "Unitree Robotics" },
          source_url: "https://www.unitree.com/g1/", observed_at: "2026-10-31",
          robot_slugs: ["unitree-g1", "unitree-g1-edu-plus-u2"],
        },
        {
          slug: "no-dates", name: "No Dates", manufacturer: { slug: "unitree", name: "Unitree Robotics" },
          source_url: "https://example.invalid/", observed_at: "2026-10-31", robot_slugs: ["unknown-member"],
        },
      ]),
    }));
  });

  it("sitemap lists each line with lastmod = newest member updated_at, omitted when unknown", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = await sitemap();
    const g1 = entries.find((e) => e.url === `${ORIGIN}/lines/unitree-g1`)!;
    expect(g1.lastModified).toEqual(new Date("2026-10-20T00:00:00Z"));
    const nd = entries.find((e) => e.url === `${ORIGIN}/lines/no-dates`)!;
    expect(nd).toBeTruthy();
    expect(nd.lastModified).toBeUndefined();
  });

  it("llms.txt has a Product lines section with canonical links", async () => {
    const { GET } = await import("@/app/llms.txt/route");
    const text = await (await GET()).text();
    expect(text).toContain("## Product lines (published, canonical)");
    expect(text).toContain(`- Unitree G1 (Unitree Robotics): ${ORIGIN}/lines/unitree-g1`);
  });
});
