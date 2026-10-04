/**
 * /research hub and publication-aware navigation.
 *
 * The contract: with ZERO published Research Resources the hub is a 404, Research
 * is absent from primary nav, dark nav, footer and the sitemap, and nothing leaks
 * the (unpublished) Europe resource. With at least one published AND served, all
 * of those appear together.
 */
import { cleanup, render, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projection } from "./research-fixture";

vi.mock("@/lib/seo", () => ({
  listAllRobots: async () => [],
  listAllManufacturers: async () => [],
  listAllUseCases: async () => [],
  lastMod: () => ({}),
}));

import ResearchHubPage, { generateMetadata } from "../app/research/page";
import EuropeResearchPage from "../app/research/humanoid-availability/europe/page";
import sitemap from "../app/sitemap";
import { DarkNav, SiteFooter, SiteNav } from "../components/SiteNav";
import {
  liveResearchRegions,
  publishedResearchRegions,
  researchNavVisible,
} from "../lib/research";

const ORIGIN = "https://hub.test.invalid";
const EUROPE_URL = "/research/humanoid-availability/europe";
const ENV_KEYS = ["RESEARCH_PUBLISHED_REGIONS", "RESEARCH_PREVIEW_TOKEN", "NEXT_PUBLIC_SITE_URL"] as const;
const saved: Record<string, string | undefined> = {};

// API double: serves the published projection only when `apiServes` is true.
let apiServes = false;
const fetchMock = vi.fn();

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
  delete process.env.RESEARCH_PUBLISHED_REGIONS;
  delete process.env.RESEARCH_PREVIEW_TOKEN;
  apiServes = false;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () =>
    apiServes ? Response.json(projection({ published: true })) : new Response("Not found", { status: 404 }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

const publish = (value: string) => {
  process.env.RESEARCH_PUBLISHED_REGIONS = value;
};
const hrefs = (el: HTMLElement) =>
  [...el.querySelectorAll("a")].map((a) => a.getAttribute("href"));

// --- helpers --------------------------------------------------------------------

describe("publication helpers", () => {
  it("count only built, env-published regions", () => {
    expect(publishedResearchRegions({})).toEqual([]);
    expect(publishedResearchRegions({ RESEARCH_PUBLISHED_REGIONS: " Europe " })).toEqual(["europe"]);
    // asia / north-america have no built resource, so listing them publishes nothing
    expect(publishedResearchRegions({ RESEARCH_PUBLISHED_REGIONS: "asia,north-america" })).toEqual([]);
    expect(researchNavVisible({ RESEARCH_PUBLISHED_REGIONS: "asia" })).toBe(false);
    expect(researchNavVisible({ RESEARCH_PUBLISHED_REGIONS: "europe" })).toBe(true);
  });

  it("a region is live only when it is published AND actually served", async () => {
    const env = { RESEARCH_PUBLISHED_REGIONS: "europe" };
    expect(await liveResearchRegions(async () => projection(), env)).toEqual(["europe"]);
    expect(await liveResearchRegions(async () => null, env)).toEqual([]);
    expect(await liveResearchRegions(async () => { throw new Error("api down"); }, env)).toEqual([]);
    expect(await liveResearchRegions(async () => projection(), {})).toEqual([]);
  });
});

// --- navigation -------------------------------------------------------------------

describe("navigation", () => {
  it("is unchanged while zero resources are published", () => {
    const { container } = render(
      <>
        <SiteNav />
        <DarkNav />
        <SiteFooter />
      </>,
    );
    expect(hrefs(container)).not.toContain("/research");
    expect(container.textContent).not.toContain("Research");
  });

  it("an env flag for a region with no built resource changes nothing", () => {
    publish("asia");
    const { container } = render(<SiteNav />);
    expect(hrefs(container)).not.toContain("/research");
  });

  it("shows Research in primary nav, dark nav and footer, just before About", () => {
    publish("europe");
    for (const [name, node] of [
      ["primary", <SiteNav key="a" />],
      ["dark", <DarkNav key="b" />],
      ["footer", <SiteFooter key="c" />],
    ] as const) {
      const { container } = render(node);
      const links = hrefs(container).filter((h) => h?.startsWith("/") && h !== "/");
      const at = links.indexOf("/research");
      expect(at, name).toBeGreaterThan(-1);
      expect(links[at + 1], name).toBe("/about");
      expect(links[at - 1], name).toBe("/use-cases");
      cleanup();
    }
  });

  it("marks Research as the current section on its own pages", () => {
    publish("europe");
    const { container } = render(<SiteNav active="research" />);
    expect(within(container).getByRole("link", { name: "Research" }).getAttribute("aria-current")).toBe("page");
  });
});

// --- hub ---------------------------------------------------------------------------

describe("hub with zero published resources", () => {
  it("is a 404: no page, noindex metadata, no API call, not in the sitemap", async () => {
    await expect(ResearchHubPage()).rejects.toThrow();
    expect(await generateMetadata()).toMatchObject({ title: "Not found", robots: { index: false } });
    expect(fetchMock).not.toHaveBeenCalled();
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls.filter((u) => u.includes("/research"))).toEqual([]);
  });

  it("is omitted when a region is flagged but the API does not serve it (or is unavailable)", async () => {
    publish("europe");
    apiServes = false;
    await expect(ResearchHubPage()).rejects.toThrow();
    expect((await sitemap()).map((e) => e.url).filter((u) => u.includes("/research"))).toEqual([]);
  });

  it("is omitted when the API is unreachable", async () => {
    publish("europe");
    fetchMock.mockImplementation(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    await expect(ResearchHubPage()).rejects.toThrow();
    expect((await sitemap()).map((e) => e.url).filter((u) => u.includes("/research"))).toEqual([]);
  });
});

describe("hub with a published, served resource", () => {
  beforeEach(() => {
    publish("europe");
    apiServes = true;
  });

  it("renders the hub with canonical metadata", async () => {
    const meta = await generateMetadata();
    expect(meta.title).toBe("Research");
    expect(meta.alternates?.canonical).toBe(`${ORIGIN}/research`);
    expect(meta.robots).toBeUndefined();
    const { getByRole } = render(await ResearchHubPage());
    expect(getByRole("heading", { level: 1 }).textContent).toBe("Research");
  });

  it("links only the live region; the others are in preparation and not links", async () => {
    const { container } = render(await ResearchHubPage());
    const live = container.querySelectorAll('[data-region-state="live"]');
    const preparing = container.querySelectorAll('[data-region-state="preparing"]');
    expect(live).toHaveLength(1);
    expect(live[0].querySelector("a")?.getAttribute("href")).toBe(EUROPE_URL);
    expect(preparing).toHaveLength(2);
    for (const p of preparing) {
      expect(p.querySelector("a")).toBeNull();
      expect(p.textContent).toContain("IN PREPARATION");
    }
    expect(container.textContent).toContain("North America");
    expect(container.textContent).toContain("Asia");
  });

  it("states no catalogue figure and uses no news or article language", async () => {
    const { container } = render(await ResearchHubPage());
    const hub = container.querySelector('[data-testid="research-hub"]') as HTMLElement;
    // Reader-facing copy only: the 01/02/03 tile indices are ordinals, not figures.
    const text = [...hub.querySelectorAll("h1, p, .name, .research-principle-body")]
      .map((e) => e.textContent)
      .join(" ");
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/[€$£]/);
    expect(text).not.toMatch(/\b(news|blog|articles?|posts?|headlines?)\b/i);
  });

  it("explains the five Research Resource guarantees", async () => {
    const { container } = render(await ResearchHubPage());
    const text = container.textContent ?? "";
    for (const phrase of [
      "Snapshot-dated",
      "Evidence-linked",
      "Deterministic",
      "Unknown stays unknown",
      "Availability is not deployment",
    ]) {
      expect(text).toContain(phrase);
    }
  });

  it("joins the sitemap together with the first resource, and nothing else changes", async () => {
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toContain(`${ORIGIN}/research`);
    expect(urls).toContain(`${ORIGIN}${EUROPE_URL}`);
    expect(urls.filter((u) => u.includes("/research"))).toHaveLength(2);
  });
});

// --- page structure ---------------------------------------------------------------------

describe("landmarks", () => {
  it("the Europe resource page does not nest a second <main> inside the layout's", async () => {
    publish("europe");
    apiServes = true;
    const { container } = render(await EuropeResearchPage());
    expect(container.querySelector("main")).toBeNull();
  });

  it("the hub does not render its own <main> either", async () => {
    publish("europe");
    apiServes = true;
    const { container } = render(await ResearchHubPage());
    expect(container.querySelector("main")).toBeNull();
  });
});
