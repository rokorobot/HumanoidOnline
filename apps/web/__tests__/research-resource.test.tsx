/**
 * ADR-027 Step 3 — Regional Research Resource: publication gate, sitemap
 * integration, rendering, and HTML / JSON / JSON-LD parity.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ResearchResource } from "../components/ResearchResource";
import {
  type ResearchProjection,
  formatPriceState,
  researchSitemapEntries,
  resolveResearchAccess,
} from "../lib/research";
import { EDITORIAL, editorialSourceLabel, editorialState } from "../lib/research-editorial";
import { buildResearchJsonLd } from "../lib/research-jsonld";
import { projection } from "./research-fixture";

const ORIGIN = "https://research.test.invalid";
const URL = `${ORIGIN}/research/humanoid-availability/europe`;

afterEach(cleanup);

// --- publication gate ---------------------------------------------------------

describe("publication gate", () => {
  it("is closed by default", () => {
    expect(resolveResearchAccess("europe", null, {})).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("europe", "anything", {})).toEqual({ mode: "closed" });
  });

  it("opens only for a region the owner listed as published", () => {
    const env = { RESEARCH_PUBLISHED_REGIONS: "Europe, asia" };
    expect(resolveResearchAccess("europe", null, env)).toEqual({ mode: "published" });
  });

  it("opens a preview only with the exact review token", () => {
    const env = { RESEARCH_PREVIEW_TOKEN: "s3cret" };
    expect(resolveResearchAccess("europe", "s3cret", env)).toEqual({ mode: "preview", token: "s3cret" });
    expect(resolveResearchAccess("europe", "s3cre", env)).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("europe", "", env)).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("europe", null, env)).toEqual({ mode: "closed" });
  });

  it("an unset token never grants preview, even for an empty param", () => {
    expect(resolveResearchAccess("europe", "", { RESEARCH_PREVIEW_TOKEN: "" })).toEqual({ mode: "closed" });
  });

  it("published wins over preview; other regions stay closed", () => {
    const env = { RESEARCH_PUBLISHED_REGIONS: "europe", RESEARCH_PREVIEW_TOKEN: "t" };
    expect(resolveResearchAccess("europe", "t", env)).toEqual({ mode: "published" });
    expect(resolveResearchAccess("north-america", "t", env)).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("asia", null, { RESEARCH_PUBLISHED_REGIONS: "asia" })).toEqual({ mode: "closed" });
  });
});

// --- sitemap ------------------------------------------------------------------

describe("sitemap integration", () => {
  const serve = async () => projection({ published: true });

  it("lists nothing while the region is not published", async () => {
    expect(await researchSitemapEntries(ORIGIN, serve, {})).toEqual([]);
    expect(await researchSitemapEntries(ORIGIN, serve, { RESEARCH_PREVIEW_TOKEN: "t" })).toEqual([]);
  });

  it("lists a published region with the real latest-evidence lastModified", async () => {
    const out = await researchSitemapEntries(ORIGIN, serve, { RESEARCH_PUBLISHED_REGIONS: "europe" });
    expect(out).toHaveLength(1);
    expect(out[0].url).toBe(URL);
    expect(out[0].lastModified?.toISOString().slice(0, 10)).toBe("2026-09-26");
  });

  it("omits lastModified rather than inventing one, and skips an entry with no data", async () => {
    const env = { RESEARCH_PUBLISHED_REGIONS: "europe" };
    const none = await researchSitemapEntries(ORIGIN, async () => projection({ latest_evidence_date: null }), env);
    expect(none[0]).not.toHaveProperty("lastModified");
    expect(await researchSitemapEntries(ORIGIN, async () => null, env)).toEqual([]);
    expect(await researchSitemapEntries(ORIGIN, async () => { throw new Error("api down"); }, env)).toEqual([]);
  });
});

// --- rendering ------------------------------------------------------------------

function renderPage(data: ResearchProjection, preview = false) {
  return render(<ResearchResource data={data} preview={preview} canonicalUrl={URL} />);
}

describe("rendering", () => {
  it("renders the direct answer verbatim as the first section", () => {
    renderPage(projection());
    expect(screen.getByTestId("direct-answer").textContent).toBe(projection().direct_answer);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Which humanoid robots are available in Europe?",
    );
  });

  it("renders one offers row per projected offer with links to published robot and manufacturer pages", () => {
    renderPage(projection());
    const rows = [
      ...within(screen.getByTestId("offers-available-table")).getAllByRole("row").slice(1),
      ...within(screen.getByTestId("offers-gated-table")).getAllByRole("row").slice(1),
    ];
    expect(rows).toHaveLength(3);
    const table = screen.getByTestId("offers-available-table");
    expect(within(table).getByRole("link", { name: "Bot A" }).getAttribute("href")).toBe("/robots/bot-a");
    expect(within(table).getByRole("link", { name: "Maker A" }).getAttribute("href")).toBe("/manufacturers/maker-a");
  });

  it("keeps AVAILABLE apart from waitlist, preorder and quote-only offers", () => {
    renderPage(projection());
    const available = within(screen.getByTestId("offers-available-table"));
    const gated = within(screen.getByTestId("offers-gated-table"));
    expect(available.getByText("Bot A")).toBeTruthy();
    expect(available.getByText("Bot C")).toBeTruthy(); // rental, AVAILABLE
    expect(available.queryByText("Bot B")).toBeNull(); // ON_REQUEST
    expect(gated.getByText("Bot B")).toBeTruthy();
    expect(gated.queryByText("Bot A")).toBeNull();
    expect(screen.getByTestId("offers-available-table").textContent).not.toContain("On request");
    expect(screen.getByTestId("offers-gated-table").textContent).not.toContain("Available");
  });

  it("puts waitlist/preorder in the gated table and limited with the available one", () => {
    const base = projection();
    const mk = (slug: string, status: string) => ({
      ...base.offers[0],
      robot_slug: slug,
      robot_name: slug,
      availability_status: status,
    });
    renderPage(projection({ offers: [mk("lim", "LIMITED"), mk("pre", "PREORDER"), mk("wl", "WAITLIST")] }));
    expect(within(screen.getByTestId("offers-available-table")).getByText("lim")).toBeTruthy();
    const gated = within(screen.getByTestId("offers-gated-table"));
    expect(gated.getByText("pre")).toBeTruthy();
    expect(gated.getByText("wl")).toBeTruthy();
  });

  it("labels the geography column Region (EU is a valid value, not a country)", () => {
    renderPage(projection());
    const headers = within(screen.getByTestId("offers-available-table"))
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toContain("Region");
    expect(headers).not.toContain("Country");
  });

  it("gives global-only robots their own section, apart from no-confirmed-offer", () => {
    const { container } = renderPage(projection());
    const global = screen.getByTestId("global-only");
    expect(global.textContent).toContain("Global availability, region unconfirmed");
    expect(within(global).getByText("Bot G (Maker G)")).toBeTruthy();
    expect(container.querySelector('[data-group="GLOBAL_ONLY"]')).toBeNull();
    expect(container.querySelector('[data-group="NO_OFFERS"]')?.textContent).toContain("Bot Z");
    expect(container.querySelector('[data-group="NO_OFFERS"]')?.textContent).not.toContain("Bot G");
  });

  it("states factually that no deployment is on file, and never invents one", () => {
    renderPage(projection());
    expect(screen.getByTestId("deployments-empty").textContent).toBe(
      "No evidenced deployment in Europe is on file for a published humanoid robot.",
    );
    expect(screen.queryByTestId("deployments-table")).toBeNull();
    expect(screen.getByTestId("deployments").textContent).toContain("does not show that the robot can be purchased");
  });

  it("renders evidenced deployments apart from offers, with undisclosed fields explicit", () => {
    renderPage(
      projection({
        deployments: [
          {
            robot_slug: "bot-d",
            robot_name: "Bot D",
            manufacturer_slug: "maker-d",
            manufacturer_name: "Maker D",
            region_code: "DE",
            customer_name: null,
            provider_slug: null,
            transaction_type: "RAAS",
            unit_count: null,
            started_on: "2024-06-01",
            status: "production",
            evidence_date: "2024-06-27",
            confidence: "MEDIUM",
            human_verified: false,
            source_urls: ["https://news.example/d"],
          },
        ],
      }),
    );
    const t = within(screen.getByTestId("deployments-table"));
    expect(t.getByText("Undisclosed")).toBeTruthy();
    expect(t.getByText("Not stated")).toBeTruthy(); // units
    expect(t.getByText("2024-06-01")).toBeTruthy();
    expect(screen.queryByTestId("deployments-empty")).toBeNull();
    expect(within(screen.getByTestId("offers-available-table")).queryByText("Bot D")).toBeNull();
    expect(within(screen.getByTestId("offers-gated-table")).queryByText("Bot D")).toBeNull();
  });

  it("keeps unknowns unknown and estimates distinct from published prices", () => {
    renderPage(projection());
    const table = document.body;
    expect(within(table).getByText("Not published")).toBeTruthy();
    expect(table.textContent).toContain("9,930 EUR");
    expect(table.textContent).toContain("6,500 EUR / week");
    expect(table.textContent).toContain("Estimate only: 19,999 EUR (not a published price)");
    expect(table.textContent).not.toMatch(/\b0 EUR\b/);
  });

  it("shows confidence as recorded and never implies verification", () => {
    renderPage(projection());
    const table = document.body;
    expect(table.textContent).toContain("MEDIUM · no human verification recorded");
    expect(table.textContent).toContain("HIGH");
  });

  it("never describes a missing offer as 'not available'", () => {
    const { container } = renderPage(projection());
    expect(container.textContent!.toLowerCase()).not.toContain("not_available");
    expect(container.textContent!.toLowerCase()).not.toMatch(/\bnot available\b/);
    expect(container.textContent).toContain("does not mean they are unavailable");
    expect(container.querySelector('[data-testid="global-only"]')).toBeTruthy();
  });

  it("handles a region with no confirmed offers without claiming availability", () => {
    renderPage(projection({ offers: [], latest_evidence_date: null }));
    expect(screen.queryByTestId("offers-available-table")).toBeNull();
    expect(screen.queryByTestId("offers-gated-table")).toBeNull();
    expect(screen.getByTestId("offers-available-empty")).toBeTruthy();
    expect(screen.getByTestId("offers-gated-empty")).toBeTruthy();
  });

  it("marks a preview and shows readiness only in preview", () => {
    const ready = projection({
      readiness: { gate_passes: true, qualifying_robots: 7, qualifying_manufacturers: 3, min_robots: 5, min_manufacturers: 3, failures: [], groups_reconcile: true },
    });
    renderPage(ready, true);
    expect(screen.getByTestId("preview-banner")).toBeTruthy();
    expect(screen.getByTestId("readiness").textContent).toContain("Gate passes");
    cleanup();
    renderPage(ready, false);
    expect(screen.queryByTestId("preview-banner")).toBeNull();
    expect(screen.queryByTestId("readiness")).toBeNull();
  });
});

// --- editorial fragment ----------------------------------------------------------

describe("editorial fragment", () => {
  it("is owner-reviewed: shown without a DRAFT label, in public and in preview", () => {
    expect(EDITORIAL.europe.reviewed_at).toBe("2026-10-04");
    expect(EDITORIAL.europe.reviewed_by).toBeTruthy();
    for (const preview of [false, true]) {
      expect(editorialState("europe", "2026-10-04", preview)).toMatchObject({
        show: true,
        draft: false,
        outdated: false,
      });
      renderPage(projection(), preview);
      const section = screen.getByTestId("editorial").textContent ?? "";
      expect(section).not.toContain("DRAFT");
      expect(section).not.toContain("outdated");
      expect(section).toContain("Reviewed 2026-10-04.");
      for (const paragraph of EDITORIAL.europe.paragraphs) {
        expect(section).toContain(paragraph);
      }
      cleanup();
    }
  });

  it("cites an official UN M49 source for the Europe classification statement", () => {
    expect(EDITORIAL.europe.sources).toEqual(["https://unstats.un.org/unsd/methodology/m49/overview/"]);
    expect(EDITORIAL.europe.paragraphs[0]).toContain("UN M49 Europe classification");
  });

  it("renders the UN M49 citation as a visible link inside the editorial section", () => {
    renderPage(projection(), false);
    const source = within(screen.getByTestId("editorial")).getByTestId("editorial-source");
    expect(source.textContent).toBe(
      "Source: UN Statistics Division \u2014 M49 Standard Country or Area Codes",
    );
    const link = within(source).getByRole("link");
    expect(link.getAttribute("href")).toBe(EDITORIAL.europe.sources[0]);
    expect(link.getAttribute("href")).toBe("https://unstats.un.org/unsd/methodology/m49/overview/");
  });

  it("renders no source block when the fragment has no sources", () => {
    const original = EDITORIAL.europe.sources;
    EDITORIAL.europe.sources = [];
    try {
      renderPage(projection(), false);
      expect(screen.getByTestId("editorial")).toBeTruthy(); // the paragraphs still render
      expect(screen.queryByTestId("editorial-source")).toBeNull();
      expect(screen.getByTestId("editorial").textContent).not.toContain("Source:");
    } finally {
      EDITORIAL.europe.sources = original;
    }
  });

  it("labels an unlisted source host by its hostname rather than showing a bare URL", () => {
    expect(editorialSourceLabel("https://example.org/page")).toBe("example.org");
    expect(editorialSourceLabel("https://unstats.un.org/x")).toContain("M49");
  });

  it("still treats an unreviewed fragment as DRAFT: hidden publicly, marked in preview", () => {
    const original = EDITORIAL.europe.reviewed_at;
    EDITORIAL.europe.reviewed_at = null;
    try {
      expect(editorialState("europe", "2026-10-04", false)).toEqual({ show: false });
      expect(editorialState("europe", "2026-10-04", true)).toMatchObject({ show: true, draft: true });
      renderPage(projection(), true);
      expect(screen.getByTestId("editorial").textContent).toContain("DRAFT");
      cleanup();
      renderPage(projection(), false);
      expect(screen.queryByTestId("editorial")).toBeNull();
    } finally {
      EDITORIAL.europe.reviewed_at = original;
    }
  });

  it("contains no price, status, count or robot-specific commercial claim", () => {
    // "M49" is the UN classification name, the only digits allowed.
    const text = EDITORIAL.europe.paragraphs.join(" ").replace("M49", "");
    expect(text).not.toMatch(/[€$£]|\d/);
    expect(text).not.toMatch(/\b(unitree|booster|agibot|neura|price|priced|cost)\b/i);
  });

  it("keeps the 180-day review rule: not outdated through day 180, outdated from day 181", () => {
    // Reviewed 2026-10-04: day 180 is 2027-04-02, day 181 is 2027-04-03.
    expect(editorialState("europe", "2027-04-02", false)).toMatchObject({ outdated: false });
    expect(editorialState("europe", "2027-04-03", false)).toMatchObject({ show: true, outdated: true });
    renderPage(projection({ snapshot_date: "2027-04-03" }), false);
    expect(screen.getByTestId("editorial").textContent).toContain("may be outdated");
  });
});

// --- JSON-LD and cross-surface parity ------------------------------------------------

describe("JSON-LD and parity", () => {
  const data = projection();
  const graph = (buildResearchJsonLd(data, ORIGIN)["@graph"] as Record<string, unknown>[]);
  const byType = (t: string) => graph.find((n) => n["@type"] === t) as Record<string, any>;

  it("describes the dataset from the declared snapshot, not a clock", () => {
    const ds = byType("Dataset");
    expect(ds.dateModified).toBe(data.snapshot_date);
    expect(ds.temporalCoverage).toBe(data.snapshot_date);
    expect(ds.spatialCoverage.name).toBe("Europe");
    expect(ds.url).toBe(URL);
    expect(ds.distribution.contentUrl).toBe(`${URL}.json`);
    expect(ds.description).toBe(data.direct_answer);
    expect(ds).not.toHaveProperty("license");
  });

  it("lists exactly the robots in the offers table, once each, in order", () => {
    const list = byType("ItemList");
    const names = list.itemListElement.map((i: any) => i.name);
    const slugs = [...new Set(data.offers.map((o) => o.robot_slug))];
    expect(list.numberOfItems).toBe(slugs.length);
    expect(list.itemListElement.map((i: any) => i.url)).toEqual(slugs.map((s) => `${ORIGIN}/robots/${s}`));

    const { container } = renderPage(data);
    const htmlSlugs = [...container.querySelectorAll('[data-testid^="offers-"][data-testid$="-table"] tbody th a')].map((a) =>
      (a.getAttribute("href") ?? "").replace("/robots/", ""),
    );
    // The page splits offers into the section 8 tables; membership must still match exactly.
    expect([...htmlSlugs].sort()).toEqual(data.offers.map((o) => o.robot_slug).sort());
    expect(names).toEqual(slugs.map((s) => data.offers.find((o) => o.robot_slug === s)!.robot_name));
  });

  it("the FAQ in JSON-LD is exactly the visible FAQ", () => {
    const faq = byType("FAQPage");
    const ld = faq.mainEntity.map((q: any) => [q.name, q.acceptedAnswer.text]);
    expect(ld).toEqual(data.faq.map((f) => [f.question, f.answer]));
    const { container } = renderPage(data);
    for (const [q, a] of ld) {
      expect(container.textContent).toContain(q);
      expect(container.textContent).toContain(a);
    }
  });

  it("emits only projected (published, qualifying) robots, never the excluded ones", () => {
    const ld = JSON.stringify(graph);
    expect(ld).not.toContain("bot-g");
    expect(ld).not.toContain("bot-z");
  });

  it("a range is shown only with both bounds; a missing bound is Not published, never 0", () => {
    const base = projection().offers[0].prices[0];
    const range = { ...base, amount: null, price_min: 8000, price_max: 9000 };
    expect(formatPriceState(range)).toBe("8,000\u20139,000 EUR");
    expect(formatPriceState({ ...range, price_max: null })).toBe("Not published");
    expect(formatPriceState({ ...range, price_min: null })).toBe("Not published");
    expect(formatPriceState({ ...range, price_min: null, price_max: null })).toBe("Not published");
  });

  it("price formatting never turns UNKNOWN into a number", () => {
    const unknown = projection().offers[1].prices[0];
    expect(formatPriceState(unknown)).toBe("Not published");
    expect(formatPriceState({ ...unknown, kind: "PRICE_ON_REQUEST" })).toBe("Price on request");
  });
});
