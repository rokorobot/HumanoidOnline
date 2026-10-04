/**
 * ADR-027 §13 — the page journey, end to end through the real page, JSON route,
 * metadata and sitemap code, against a stubbed API that follows the API's own
 * publication rules.
 *
 *   closed -> 404                                  (no fetch is even made)
 *   valid preview -> 200, noindex, no-store, not in the sitemap
 *   published + ready -> 200, indexable, in the sitemap, JSON == HTML == JSON-LD
 *   published but readiness failing -> not public, not in the sitemap
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projection } from "./research-fixture";

vi.mock("@/lib/seo", () => ({
  listAllRobots: async () => [],
  listAllManufacturers: async () => [],
  listAllUseCases: async () => [],
  lastMod: () => ({}),
}));

import { GET } from "../app/research/humanoid-availability/europe.json/route";
import EuropeResearchPage, { generateMetadata } from "../app/research/humanoid-availability/europe/page";
import sitemap from "../app/sitemap";
import { buildResearchJsonLd } from "../lib/research-jsonld";

const ORIGIN = "https://journey.test.invalid";
const PAGE_URL = `${ORIGIN}/research/humanoid-availability/europe`;
const TOKEN = "review-token";

const ENV_KEYS = [
  "RESEARCH_PUBLISHED_REGIONS",
  "RESEARCH_PREVIEW_TOKEN",
  "NEXT_PUBLIC_SITE_URL",
] as const;
const saved: Record<string, string | undefined> = {};

// The API double: same rules as apps/api/app/routers/research.py. `apiPublic` is
// "flagged AND readiness passes"; a valid X-Research-Preview always gets the
// review-only body.
let apiPublic = false;
let apiToken: string | null = null;
const fetchMock = vi.fn();

function apiBody(published: boolean) {
  return projection({
    published,
    ...(published
      ? {}
      : {
          readiness: {
            gate_passes: apiPublic,
            qualifying_robots: 7,
            qualifying_manufacturers: 3,
            min_robots: 5,
            min_manufacturers: 3,
            failures: apiPublic ? [] : ["qualifying robots 3 < 5"],
            groups_reconcile: true,
          },
        }),
  });
}

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
  delete process.env.RESEARCH_PUBLISHED_REGIONS;
  delete process.env.RESEARCH_PREVIEW_TOKEN;
  apiPublic = false;
  apiToken = null;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
    const presented = (init?.headers as Record<string, string> | undefined)?.["X-Research-Preview"];
    if (apiToken && presented === apiToken) return Response.json(apiBody(false));
    if (apiPublic) return Response.json(apiBody(true));
    return new Response("Not found", { status: 404 });
  });
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

const sp = (preview?: string) => ({ searchParams: Promise.resolve(preview ? { preview } : {}) });
const jsonRequest = (preview?: string) =>
  new Request(`${PAGE_URL}.json${preview ? `?preview=${preview}` : ""}`);
const researchUrls = async () =>
  (await sitemap()).map((e) => e.url).filter((u) => u.includes("/research/"));

describe("closed (default)", () => {
  it("page, metadata and JSON are 404 and the API is never called", async () => {
    await expect(EuropeResearchPage(sp())).rejects.toThrow();
    expect((await generateMetadata(sp())).title).toBe("Not found");
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(await researchUrls()).toEqual([]);
  });

  it("a wrong or unconfigured preview token stays closed", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    await expect(EuropeResearchPage(sp("nope"))).rejects.toThrow();
    expect((await GET(jsonRequest("nope"))).status).toBe(404);
    delete process.env.RESEARCH_PREVIEW_TOKEN;
    expect((await GET(jsonRequest(TOKEN))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("valid preview", () => {
  beforeEach(() => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
  });

  it("renders 200 with a preview banner, readiness and a DRAFT editorial section", async () => {
    const { container } = render(await EuropeResearchPage(sp(TOKEN)));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="editorial"]')?.textContent).toContain("DRAFT");
  });

  it("is noindex in metadata, and the JSON is noindex and no-store", async () => {
    const meta = await generateMetadata(sp(TOKEN));
    expect(meta.robots).toEqual({ index: false, follow: false });
    const res = await GET(jsonRequest(TOKEN));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
    expect((await res.json()).published).toBe(false);
  });

  it("sends the token to the API as a header, never in the API URL", async () => {
    await GET(jsonRequest(TOKEN));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain(TOKEN);
    expect((init.headers as Record<string, string>)["X-Research-Preview"]).toBe(TOKEN);
  });

  it("is never in the sitemap", async () => {
    expect(await researchUrls()).toEqual([]);
  });
});

describe("published and ready", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = true;
  });

  it("renders 200 as an indexable page with canonical metadata and no preview chrome", async () => {
    const { container } = render(await EuropeResearchPage(sp()));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeNull();
    expect(container.querySelector('[data-testid="readiness"]')).toBeNull();
    expect(container.querySelector('[data-testid="editorial"]')).toBeNull(); // unreviewed draft stays hidden
    const meta = await generateMetadata(sp());
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe(PAGE_URL);
  });

  it("JSON is public-cacheable, indexable, and equals the API projection", async () => {
    const res = await GET(jsonRequest());
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toContain("max-age=300");
    expect(res.headers.get("x-robots-tag")).toBeNull();
    expect(await res.json()).toEqual(apiBody(true));
  });

  it("HTML, JSON and JSON-LD agree on the same projection", async () => {
    const data = apiBody(true);
    const { container } = render(await EuropeResearchPage(sp()));
    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld).toEqual(buildResearchJsonLd(data, ORIGIN));
    expect(container.querySelector('[data-testid="direct-answer"]')?.textContent).toBe(data.direct_answer);
    const htmlSlugs = [
      ...container.querySelectorAll('[data-testid^="offers-"][data-testid$="-table"] tbody th a'),
    ].map((a) => (a.getAttribute("href") ?? "").replace("/robots/", ""));
    const jsonSlugs = (await (await GET(jsonRequest())).json()).offers.map((o: { robot_slug: string }) => o.robot_slug);
    const ldSlugs = ld["@graph"]
      .find((n: { "@type": string }) => n["@type"] === "ItemList")
      .itemListElement.map((i: { url: string }) => i.url.replace(`${ORIGIN}/robots/`, ""));
    expect([...htmlSlugs].sort()).toEqual([...jsonSlugs].sort());
    expect([...new Set(jsonSlugs)]).toEqual(ldSlugs);
  });

  it("is listed in the sitemap with the real latest-evidence lastModified", async () => {
    const entries = (await sitemap()).filter((e) => e.url === PAGE_URL);
    expect(entries).toHaveLength(1);
    expect((entries[0].lastModified as Date).toISOString().slice(0, 10)).toBe("2026-09-26");
  });
});

describe("published flag but readiness failing (ADR-027 section 12)", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = false; // the API declines to serve it publicly
  });

  it("is not public: 404 page, 404 JSON, absent from the sitemap", async () => {
    await expect(EuropeResearchPage(sp())).rejects.toThrow();
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(await researchUrls()).toEqual([]);
  });

  it("a reviewer with the token still sees the review-only view and why it fails", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
    const { container } = render(await EuropeResearchPage(sp(TOKEN)));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')?.textContent).toContain("Gate fails");
    expect((await generateMetadata(sp(TOKEN))).robots).toEqual({ index: false, follow: false });
    expect(await researchUrls()).toEqual([]);
  });
});
