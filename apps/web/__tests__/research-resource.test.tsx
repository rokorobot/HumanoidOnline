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
import { EDITORIAL, editorialState } from "../lib/research-editorial";
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

  it("renders one offers row per projected offer with links to published robot pages", () => {
    renderPage(projection());
    const table = screen.getByTestId("offers-table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(table).getByRole("link", { name: "Bot A" }).getAttribute("href")).toBe("/robots/bot-a");
  });

  it("keeps unknowns unknown and estimates distinct from published prices", () => {
    renderPage(projection());
    const table = screen.getByTestId("offers-table");
    expect(within(table).getByText("Not published")).toBeTruthy();
    expect(table.textContent).toContain("9,930 EUR");
    expect(table.textContent).toContain("6,500 EUR / week");
    expect(table.textContent).toContain("Estimate only: 19,999 EUR (not a published price)");
    expect(table.textContent).not.toMatch(/\b0 EUR\b/);
  });

  it("shows confidence as recorded and never implies verification", () => {
    renderPage(projection());
    const table = screen.getByTestId("offers-table");
    expect(table.textContent).toContain("MEDIUM · no human verification recorded");
    expect(table.textContent).toContain("HIGH");
  });

  it("never describes a missing offer as 'not available'", () => {
    const { container } = renderPage(projection());
    expect(container.textContent!.toLowerCase()).not.toContain("not_available");
    expect(container.textContent!.toLowerCase()).not.toMatch(/\bnot available\b/);
    expect(container.textContent).toContain("does not mean they are unavailable");
    expect(container.querySelector('[data-group="GLOBAL_ONLY"]')).toBeTruthy();
  });

  it("handles a region with no confirmed offers without claiming availability", () => {
    renderPage(projection({ offers: [], latest_evidence_date: null }));
    expect(screen.queryByTestId("offers-table")).toBeNull();
    expect(screen.getByText(/No confirmed Europe offer is on file/)).toBeTruthy();
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
  it("is unreviewed (DRAFT) today: hidden publicly, marked DRAFT in preview", () => {
    expect(EDITORIAL.europe.reviewed_at).toBeNull();
    expect(editorialState("europe", "2026-10-04", false)).toEqual({ show: false });
    const preview = editorialState("europe", "2026-10-04", true);
    expect(preview).toMatchObject({ show: true, draft: true });
    renderPage(projection(), true);
    expect(screen.getByTestId("editorial").textContent).toContain("DRAFT");
    cleanup();
    renderPage(projection(), false);
    expect(screen.queryByTestId("editorial")).toBeNull();
  });

  it("contains no price, status, count or robot-specific commercial claim", () => {
    // "M49" is the UN classification name, the only digits allowed.
    const text = EDITORIAL.europe.paragraphs.join(" ").replace("M49", "");
    expect(text).not.toMatch(/[€$£]|\d/);
    expect(text).not.toMatch(/\b(unitree|booster|agibot|neura|price|priced|cost)\b/i);
  });

  it("flags a reviewed fragment older than 180 days as possibly outdated", () => {
    EDITORIAL.europe.reviewed_at = "2026-01-01";
    try {
      expect(editorialState("europe", "2026-10-04", false)).toMatchObject({ show: true, draft: false, outdated: true });
      expect(editorialState("europe", "2026-02-01", false)).toMatchObject({ outdated: false });
    } finally {
      EDITORIAL.europe.reviewed_at = null;
    }
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
    const htmlSlugs = [...container.querySelectorAll('[data-testid="offers-table"] tbody th a')].map((a) =>
      (a.getAttribute("href") ?? "").replace("/robots/", ""),
    );
    expect(htmlSlugs).toEqual(data.offers.map((o) => o.robot_slug));
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

  it("price formatting never turns UNKNOWN into a number", () => {
    const unknown = projection().offers[1].prices[0];
    expect(formatPriceState(unknown)).toBe("Not published");
    expect(formatPriceState({ ...unknown, kind: "PRICE_ON_REQUEST" })).toBe("Price on request");
  });
});
