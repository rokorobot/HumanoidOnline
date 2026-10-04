/**
 * ADR-027 §13 — the page journey, end to end through the real page, JSON route,
 * metadata and sitemap code, against a stubbed API that follows the API's own
 * publication rules.
 *
 *   closed -> 404                                  (no fetch is even made)
 *   valid preview SESSION -> 200, noindex, no-store, not in the sitemap
 *   published + ready -> 200, indexable, in the sitemap, JSON == HTML == JSON-LD
 *   published but readiness failing -> not public, not in the sitemap
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResearchProjection } from "../lib/research";
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
import { SiteNav } from "../components/SiteNav";
import { PREVIEW_COOKIE, issuePreviewSession } from "../lib/research-preview";
import { __setTestCookies } from "../test/stubs/next-headers";
import { EDITORIAL } from "../lib/research-editorial";
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
let apiHealth: ResearchProjection["publication_health"] = { status: "CURRENT", reasons: [] };
let apiToken: string | null = null;
const fetchMock = vi.fn();

function apiBody(published: boolean) {
  return projection({
    published,
    publication_health: apiHealth,
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
  apiHealth = { status: "CURRENT", reasons: [] };
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
  __setTestCookies({});
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

// A browser holding a preview session signed with `token` (or no session at all).
// The session is a signed assertion; the secret itself is never in the cookie.
const sessionFor = (token?: string) => (token ? issuePreviewSession(token, "europe") : undefined);
const visitPage = (token?: string) => {
  const session = sessionFor(token);
  __setTestCookies(session ? { [PREVIEW_COOKIE]: session } : {});
  return EuropeResearchPage();
};
const visitMeta = (token?: string) => {
  const session = sessionFor(token);
  __setTestCookies(session ? { [PREVIEW_COOKIE]: session } : {});
  return generateMetadata();
};
const jsonRequest = (token?: string) => {
  const session = sessionFor(token);
  return new Request(`${PAGE_URL}.json`, session ? { headers: { cookie: `${PREVIEW_COOKIE}=${session}` } } : undefined);
};
const researchUrls = async () =>
  (await sitemap()).map((e) => e.url).filter((u) => u.includes("/research/"));

describe("closed (default)", () => {
  it("page, metadata and JSON are 404 and the API is never called", async () => {
    // Editorial approval is one publication prerequisite; it must not publish.
    expect(EDITORIAL.europe.reviewed_at).not.toBeNull();
    await expect(visitPage()).rejects.toThrow();
    expect((await visitMeta()).title).toBe("Not found");
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(await researchUrls()).toEqual([]);
  });

  it("a session signed with the wrong key, or with no token configured, stays closed", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    await expect(visitPage("nope")).rejects.toThrow();
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

  it("renders 200 with a preview banner, readiness and the reviewed editorial section", async () => {
    const { container } = render(await visitPage(TOKEN));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')).toBeTruthy();
    const editorial = container.querySelector('[data-testid="editorial"]')?.textContent ?? "";
    expect(editorial).toContain("Reviewed 2026-10-04.");
    expect(editorial).not.toContain("DRAFT");
  });

  it("is noindex in metadata, and the JSON is noindex and no-store", async () => {
    const meta = await visitMeta(TOKEN);
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
    const { container } = render(await visitPage());
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeNull();
    expect(container.querySelector('[data-testid="readiness"]')).toBeNull();
    const editorial = container.querySelector('[data-testid="editorial"]')?.textContent ?? "";
    expect(editorial).toContain("Reviewed 2026-10-04."); // approved text is part of the public page
    expect(editorial).not.toContain("DRAFT");
    expect(editorial).not.toContain("outdated");
    const meta = await visitMeta();
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
    const { container } = render(await visitPage());
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

describe("published but degraded: limited evidence stays public (ADR-027 section 12)", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = true;
    apiHealth = { status: "LIMITED_EVIDENCE", reasons: ["4 qualifying robots; minimum 5"] };
  });

  it("renders publicly, indexable, with a visible factual warning and its reasons", async () => {
    const { container } = render(await visitPage());
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeNull();
    const warning = container.querySelector('[data-testid="limited-evidence-warning"]');
    expect(warning?.textContent).toContain("Limited current evidence.");
    expect(warning?.textContent).toContain("This resource remains published");
    expect(warning?.textContent).toContain("Stale offers are excluded from current availability figures.");
    expect(warning?.textContent).toContain("4 qualifying robots; minimum 5");
    expect((await visitMeta()).robots).toBeUndefined();
  });

  it("the JSON carries the machine-readable health and is public-cacheable", async () => {
    const res = await GET(jsonRequest());
    expect(res.status).toBe(200);
    expect(res.headers.get("x-robots-tag")).toBeNull();
    expect((await res.json()).publication_health).toEqual(apiHealth);
  });

  it("keeps the sitemap entries, the hub and the navigation", async () => {
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toContain(PAGE_URL);
    expect(urls).toContain(`${ORIGIN}/research`);
    const { container } = render(<SiteNav />);
    expect(container.querySelector('a[href="/research"]')).toBeTruthy();
  });

  it("the JSON-LD still describes only the projected (current) offers", async () => {
    const { container } = render(await visitPage());
    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld).toEqual(buildResearchJsonLd(apiBody(true), ORIGIN));
  });
});

describe("published but structurally invalid: the API fails closed", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = false; // the API answers 404 (e.g. groups do not reconcile)
  });

  it("is not public: 404 page, 404 JSON, absent from the sitemap and the hub", async () => {
    await expect(visitPage()).rejects.toThrow();
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(await researchUrls()).toEqual([]);
  });

  it("a reviewer with the token still sees the review-only report", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
    const { container } = render(await visitPage(TOKEN));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')?.textContent).toContain("Gate fails");
    expect((await visitMeta(TOKEN)).robots).toEqual({ index: false, follow: false });
    expect(await researchUrls()).toEqual([]);
  });
});

describe("preview session security", () => {
  const ENV_TOKEN = TOKEN;

  beforeEach(() => {
    process.env.RESEARCH_PREVIEW_TOKEN = ENV_TOKEN;
    apiToken = ENV_TOKEN;
  });

  it("a valid session cookie opens the HTML and the JSON preview, noindex and no-store", async () => {
    const { container } = render(await visitPage(ENV_TOKEN));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect((await visitMeta(ENV_TOKEN)).robots).toEqual({ index: false, follow: false });
    const res = await GET(jsonRequest(ENV_TOKEN));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
  });

  it("the correct secret in the URL (?preview=) no longer grants anything", async () => {
    // The page no longer reads query parameters at all, and the JSON route ignores them.
    const res = await GET(new Request(`${PAGE_URL}.json?preview=${ENV_TOKEN}`));
    expect(res.status).toBe(404);
    __setTestCookies({});
    await expect(EuropeResearchPage()).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a tampered cookie grants nothing", async () => {
    const good = issuePreviewSession(ENV_TOKEN, "europe");
    const [v, payload, sig] = good.split(".");
    const forgedPayload = Buffer.from(
      JSON.stringify({ v: 1, r: "europe", exp: Math.floor(Date.now() / 1000) + 3000 }),
    ).toString("base64url");
    for (const bad of [`${v}.${forgedPayload}.${sig}`, `${v}.${payload}.${sig}x`, `${v}.${payload}`, "garbage", ""]) {
      const res = await GET(new Request(`${PAGE_URL}.json`, { headers: { cookie: `${PREVIEW_COOKIE}=${bad}` } }));
      expect(res.status, bad).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an expired cookie grants nothing", async () => {
    const expired = issuePreviewSession(ENV_TOKEN, "europe", Date.now() - 2 * 3600 * 1000);
    const res = await GET(new Request(`${PAGE_URL}.json`, { headers: { cookie: `${PREVIEW_COOKIE}=${expired}` } }));
    expect(res.status).toBe(404);
    __setTestCookies({ [PREVIEW_COOKIE]: expired });
    await expect(EuropeResearchPage()).rejects.toThrow();
  });

  it("rotating RESEARCH_PREVIEW_TOKEN invalidates every existing session", async () => {
    const session = issuePreviewSession(ENV_TOKEN, "europe");
    const withSession = () =>
      new Request(`${PAGE_URL}.json`, { headers: { cookie: `${PREVIEW_COOKIE}=${session}` } });
    expect((await GET(withSession())).status).toBe(200);
    process.env.RESEARCH_PREVIEW_TOKEN = "rotated-token";
    apiToken = "rotated-token";
    expect((await GET(withSession())).status).toBe(404);
  });

  it("the API credential travels only as a server-side header; the cookie never carries it", async () => {
    const session = issuePreviewSession(ENV_TOKEN, "europe");
    expect(session).not.toContain(ENV_TOKEN);
    expect(Buffer.from(session.split(".")[1], "base64url").toString()).not.toContain(ENV_TOKEN);
    await GET(jsonRequest(ENV_TOKEN));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain(ENV_TOKEN);
    expect((init.headers as Record<string, string>)["X-Research-Preview"]).toBe(ENV_TOKEN);
    // Nothing a browser receives contains the secret: not the page markup, not the JSON.
    const { container } = render(await visitPage(ENV_TOKEN));
    expect(container.innerHTML).not.toContain(ENV_TOKEN);
    expect(await (await GET(jsonRequest(ENV_TOKEN))).text()).not.toContain(ENV_TOKEN);
  });

  it("clearing the cookie closes access again", async () => {
    expect((await GET(jsonRequest(ENV_TOKEN))).status).toBe(200);
    expect((await GET(jsonRequest())).status).toBe(404);
    __setTestCookies({});
    await expect(EuropeResearchPage()).rejects.toThrow();
  });

  it("a session never exposes the preview: absent from the sitemap, hub and llms nav", async () => {
    expect(await researchUrls()).toEqual([]);
    const { container } = render(<SiteNav />);
    expect(container.querySelector('a[href="/research"]')).toBeNull();
  });

  it("when Europe is published the cookie is irrelevant: the public path wins", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = true;
    for (const token of [undefined, ENV_TOKEN, "wrong"]) {
      const { container } = render(await visitPage(token));
      expect(container.querySelector('[data-testid="preview-banner"]'), String(token)).toBeNull();
      expect((await visitMeta(token)).robots).toBeUndefined();
      cleanup();
    }
    const res = await GET(jsonRequest(ENV_TOKEN));
    expect(res.headers.get("cache-control")).toContain("max-age=300");
    expect(res.headers.get("x-robots-tag")).toBeNull();
  });

  it("the preview banner offers End preview as a POST, with no secret", async () => {
    const { container } = render(await visitPage(ENV_TOKEN));
    const form = container.querySelector('[data-testid="preview-banner"] form') as HTMLFormElement;
    expect(form.getAttribute("method")).toBe("post");
    expect(form.getAttribute("action")).toBe("/research/preview");
    expect((form.querySelector('input[name="action"]') as HTMLInputElement).value).toBe("end");
    expect(form.outerHTML).not.toContain(ENV_TOKEN);
  });
});
