/**
 * HO-RESEARCH-NA-01 — the North America Regional Research Resource, end to end
 * through the real page, JSON route, metadata, sitemap, hub and preview access
 * route, against a stubbed API that follows the API's own publication rules.
 *
 * North America reuses Europe's gate, rendering and JSON-LD; these tests pin that
 * it is closed by default, isolated from Europe's publication and preview, keeps
 * its DRAFT editorial out of any public page, and keeps HTML, JSON and JSON-LD
 * consistent.
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

import { GET } from "../app/research/humanoid-availability/north-america.json/route";
import NorthAmericaPage, {
  generateMetadata,
} from "../app/research/humanoid-availability/north-america/page";
import ResearchHubPage from "../app/research/page";
import { GET as previewGET, POST as previewPOST } from "../app/research/preview/route";
import sitemap from "../app/sitemap";
import { EDITORIAL, editorialState } from "../lib/research-editorial";
import { buildResearchJsonLd } from "../lib/research-jsonld";
import {
  RESEARCH_REGIONS,
  liveResearchRegions,
  researchPath,
  resolveResearchAccess,
} from "../lib/research";
import { PREVIEW_COOKIE, issuePreviewSession, verifyPreviewSession } from "../lib/research-preview";
import { __setTestCookies } from "../test/stubs/next-headers";

const ORIGIN = "https://na.test.invalid";
const PAGE_URL = `${ORIGIN}/research/humanoid-availability/north-america`;
const TOKEN = "review-token";
const ENV_KEYS = ["RESEARCH_PUBLISHED_REGIONS", "RESEARCH_PREVIEW_TOKEN", "NEXT_PUBLIC_SITE_URL"] as const;
const saved: Record<string, string | undefined> = {};

const NA = { slug: "north-america", code: "NORTH_AMERICA", name: "North America" };
const USD = (amount: number) => ({
  kind: "PUBLISHED" as const,
  price_type: "PUBLIC",
  amount,
  price_min: null,
  price_max: null,
  currency: "USD",
  billing_period: "ONE_TIME",
  price_basis: null,
});

function naProjection(overrides: Partial<ResearchProjection> = {}): ResearchProjection {
  const base = projection();
  return projection({
    region: NA,
    snapshot_date: "2026-10-23",
    latest_evidence_date: "2026-08-17",
    direct_answer:
      "As of 2026-10-23, HumanoidOnline lists 1 published humanoid robot with a confirmed offer in North America. 1 can be purchased: 1 available. 42 other published robots have no confirmed North America offer on file.",
    publication_health: {
      status: "LIMITED_EVIDENCE",
      reasons: ["1 qualifying robot; minimum 5", "1 manufacturer; minimum 3"],
    },
    offers: [
      {
        ...base.offers[0],
        robot_slug: "unitree-g1",
        robot_name: "Unitree G1",
        manufacturer_slug: "unitree",
        manufacturer_name: "Unitree Robotics",
        provider_slug: "robotshop-us",
        region_code: "US",
        evidence_date: "2026-08-17",
        source_urls: ["https://seller.example/g1-us"],
        prices: [USD(17900)],
      },
    ],
    deployments: [
      {
        robot_slug: "agility-digit",
        robot_name: "Digit",
        manufacturer_slug: "agility-robotics",
        manufacturer_name: "Agility Robotics",
        region_code: "US",
        customer_name: "GXO Logistics",
        provider_slug: null,
        transaction_type: "RAAS",
        unit_count: null,
        started_on: "2024-06-27",
        status: "production",
        evidence_date: "2026-07-24",
        confidence: "VERIFIED",
        human_verified: true,
        source_urls: ["https://maker.example/gxo"],
      },
    ],
    no_confirmed_offer: [
      {
        reason: "STALE_OR_NON_CURRENT",
        label: "Regional offer on file was withdrawn (recorded as no longer current)",
        robots: [{ slug: "1x-neo", name: "NEO", manufacturer_slug: "1x-technologies", manufacturer_name: "1X" }],
      },
      {
        reason: "GLOBAL_ONLY",
        label: "Global offer only; no region-specific offer",
        robots: [{ slug: "unitree-r1", name: "R1", manufacturer_slug: "unitree", manufacturer_name: "Unitree Robotics" }],
      },
    ],
    faq: [
      { question: "Can I buy a humanoid robot in North America?", answer: "As of 2026-10-23, 1 published humanoid robot has a confirmed purchase offer on file in North America: Unitree G1." },
    ],
    member_region_codes: ["CA", "MX", "NORTH_AMERICA", "US"],
    ...overrides,
  });
}

// API double: same rules as apps/api/app/routers/research.py, per region.
let apiPublic: string[] = [];
let apiToken: string | null = null;
const fetchMock = vi.fn();

function apiBody(region: string, published: boolean): ResearchProjection {
  const body = region === "north-america" ? naProjection() : projection();
  return {
    ...body,
    published,
    ...(published
      ? {}
      : {
          readiness: {
            gate_passes: false,
            qualifying_robots: 1,
            qualifying_manufacturers: 1,
            min_robots: 5,
            min_manufacturers: 3,
            failures: ["qualifying robots 1 < 5", "qualifying manufacturers 1 < 3"],
            groups_reconcile: true,
          },
        }),
  };
}

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
  delete process.env.RESEARCH_PUBLISHED_REGIONS;
  delete process.env.RESEARCH_PREVIEW_TOKEN;
  apiPublic = [];
  apiToken = null;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const region = String(url).split("/").pop() ?? "";
    const presented = (init?.headers as Record<string, string> | undefined)?.["X-Research-Preview"];
    if (apiToken && presented === apiToken) return Response.json(apiBody(region, false));
    if (apiPublic.includes(region)) return Response.json(apiBody(region, true));
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

const withSession = (region?: string) => {
  const session = region ? issuePreviewSession(TOKEN, region) : undefined;
  __setTestCookies(session ? { [PREVIEW_COOKIE]: session } : {});
  return session;
};
const visitPage = (region?: string) => {
  withSession(region);
  return NorthAmericaPage();
};
const visitMeta = (region?: string) => {
  withSession(region);
  return generateMetadata();
};
const jsonRequest = (region?: string) => {
  const session = region ? issuePreviewSession(TOKEN, region) : undefined;
  return new Request(`${PAGE_URL}.json`, session ? { headers: { cookie: `${PREVIEW_COOKIE}=${session}` } } : undefined);
};
const researchUrls = async () =>
  (await sitemap()).map((e) => e.url).filter((u) => u.includes("/research/"));

describe("registration", () => {
  it("is a built region with its own path", () => {
    expect(RESEARCH_REGIONS).toContain("north-america");
    expect(researchPath("north-america")).toBe("/research/humanoid-availability/north-america");
  });
});

describe("closed (default) and isolated from Europe", () => {
  it("is 404 for page, metadata and JSON, and never calls the API", async () => {
    await expect(visitPage()).rejects.toThrow();
    expect((await visitMeta()).title).toBe("Not found");
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("publishing Europe does not publish North America", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiPublic = ["europe"];
    expect(resolveResearchAccess("north-america", null)).toEqual({ mode: "closed" });
    await expect(visitPage()).rejects.toThrow();
    expect(await researchUrls()).toEqual([`${ORIGIN}/research/humanoid-availability/europe`]);
  });

  it("a Europe preview session grants nothing here", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
    await expect(visitPage("europe")).rejects.toThrow();
    expect((await GET(jsonRequest("europe"))).status).toBe(404);
  });
});

describe("valid North America preview", () => {
  beforeEach(() => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
  });

  it("renders with the banner, readiness and the DRAFT editorial", async () => {
    const { container } = render(await visitPage("north-america"));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')?.textContent).toContain("Gate fails");
    const editorial = container.querySelector('[data-testid="editorial"]')?.textContent ?? "";
    expect(editorial).toContain("DRAFT");
    expect(editorial).toContain("UN M49 North America classification");
    expect(editorial).toContain("Covered List");
    expect(editorial).not.toContain("Reviewed");
    // Every source is cited, not only the first.
    const sources = [...container.querySelectorAll('[data-testid="editorial-source"] a')].map(
      (a) => a.getAttribute("href"),
    );
    expect(sources).toEqual(EDITORIAL["north-america"].sources);
    expect(container.querySelector('[data-testid="editorial-source"]')?.textContent).toContain(
      "FCC — Public Notice DA 26-786 (28 July 2026)",
    );
    // No changing figure is hard-coded into the editorial text.
    expect(EDITORIAL["north-america"].paragraphs.join(" ")).not.toMatch(/\$|USD|\d+ robots?/);
    expect(container.querySelector("h1")?.textContent).toBe(
      "Which humanoid robots are available in North America?",
    );
    // An unpublished preview must not claim to "remain published".
    const warning = container.querySelector('[data-testid="limited-evidence-warning"]')?.textContent ?? "";
    expect(warning).toContain("This resource is not published");
    expect(warning).not.toContain("remains published");
    expect(warning).toContain("1 qualifying robot; minimum 5");
  });

  it("is noindex in metadata and JSON, and absent from the sitemap", async () => {
    expect((await visitMeta("north-america")).robots).toEqual({ index: false, follow: false });
    const res = await GET(jsonRequest("north-america"));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
    expect((await res.json()).readiness.gate_passes).toBe(false);
    expect(await researchUrls()).toEqual([]);
  });

  it("calls the API for the north-america region with the token as a header", async () => {
    await GET(jsonRequest("north-america"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/research\/humanoid-availability\/north-america$/);
    expect(String(url)).not.toContain(TOKEN);
    expect((init.headers as Record<string, string>)["X-Research-Preview"]).toBe(TOKEN);
  });
});

describe("published (after an owner decision)", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe,north-america";
    apiPublic = ["europe", "north-america"];
  });

  it("is indexable with a unique title, canonical URL and the generated description", async () => {
    const meta = await visitMeta();
    expect(meta.title).toBe("Humanoid robot availability in North America");
    expect(meta.description).toBe(naProjection().direct_answer);
    expect(meta.alternates?.canonical).toBe(PAGE_URL);
    expect(meta.robots).toBeUndefined();
  });

  it("never shows the unreviewed editorial publicly", async () => {
    expect(EDITORIAL["north-america"].reviewed_at).toBeNull();
    expect(editorialState("north-america", "2026-10-23", false)).toEqual({ show: false });
    const { container } = render(await visitPage());
    expect(container.querySelector('[data-testid="editorial"]')).toBeNull();
    expect(container.textContent).not.toContain("DRAFT");
  });

  it("HTML, JSON and JSON-LD agree on the same projection", async () => {
    const data = apiBody("north-america", true);
    const { container } = render(await visitPage());
    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld).toEqual(buildResearchJsonLd(data, ORIGIN));
    const dataset = ld["@graph"].find((n: { "@type": string }) => n["@type"] === "Dataset");
    expect(dataset.url).toBe(PAGE_URL);
    expect(dataset.spatialCoverage.name).toBe("North America");
    expect(dataset.distribution.contentUrl).toBe(`${PAGE_URL}.json`);
    expect(container.querySelector('[data-testid="direct-answer"]')?.textContent).toBe(data.direct_answer);
    const json = await (await GET(jsonRequest())).json();
    expect(json).toEqual(data);
    const htmlSlugs = [
      ...container.querySelectorAll('[data-testid^="offers-"][data-testid$="-table"] tbody th a'),
    ].map((a) => (a.getAttribute("href") ?? "").replace("/robots/", ""));
    const ldSlugs = ld["@graph"]
      .find((n: { "@type": string }) => n["@type"] === "ItemList")
      .itemListElement.map((i: { url: string }) => i.url.replace(`${ORIGIN}/robots/`, ""));
    expect(htmlSlugs).toEqual(["unitree-g1"]);
    expect(ldSlugs).toEqual(json.offers.map((o: { robot_slug: string }) => o.robot_slug));
    const faq = ld["@graph"].find((n: { "@type": string }) => n["@type"] === "FAQPage");
    expect(faq.mainEntity.map((q: { name: string }) => q.name)).toEqual(data.faq.map((f) => f.question));
  });

  it("keeps deployments and global-only robots out of the offer tables", async () => {
    const { container } = render(await visitPage());
    const offers = container.querySelector('[data-testid="offers-available-table"]')?.textContent ?? "";
    expect(offers).not.toContain("Digit");
    expect(offers).not.toContain("R1");
    expect(container.querySelector('[data-testid="deployments-table"]')?.textContent).toContain("GXO Logistics");
    expect(container.querySelector('[data-testid="global-only"]')?.textContent).toContain("R1");
    expect(container.querySelector('[data-testid="limited-evidence-warning"]')).toBeTruthy();
  });

  it("links the evidence and the published robot and manufacturer pages", async () => {
    const { container } = render(await visitPage());
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining([
      "/robots/unitree-g1", "/manufacturers/unitree", "https://seller.example/g1-us",
      "/robots/agility-digit", "/robots/1x-neo",
    ]));
  });

  it("is in the sitemap with its real latest-evidence date and listed live on the hub", async () => {
    const entry = (await sitemap()).find((e) => e.url === PAGE_URL);
    expect((entry?.lastModified as Date).toISOString().slice(0, 10)).toBe("2026-08-17");
    expect(await liveResearchRegions()).toEqual(["europe", "north-america"]);
    const { container } = render(await ResearchHubPage());
    const na = container.querySelector('a[href="/research/humanoid-availability/north-america"]');
    expect(na?.textContent).toContain("North America");
  });
});

describe("preview access route", () => {
  const post = (fields: Record<string, string>) =>
    previewPOST(new Request(`${ORIGIN}/research/preview`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(fields),
    }));

  beforeEach(() => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
  });

  it("offers every built region in the form", async () => {
    const html = await (await previewGET(new Request(`${ORIGIN}/research/preview`))).text();
    expect(html).toContain('<option value="europe">Europe</option>');
    expect(html).toContain('<option value="north-america">North America</option>');
  });

  it("issues a session for exactly the chosen region", async () => {
    const res = await post({ token: TOKEN, region: "north-america" });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/research/humanoid-availability/north-america");
    const value = res.headers.get("set-cookie")!.match(new RegExp(`^${PREVIEW_COOKIE}=([^;]*)`))![1];
    expect(verifyPreviewSession(value, TOKEN)).toBe("north-america");
  });

  it("refuses an unbuilt or unknown region without a cookie", async () => {
    for (const region of ["asia", "atlantis", ""]) {
      const res = await post({ token: TOKEN, region });
      expect(res.status).toBe(400);
      expect(res.headers.get("set-cookie")).toBeNull();
    }
  });

  it("a wrong token is refused for North America too", async () => {
    const res = await post({ token: "nope", region: "north-america" });
    expect(res.status).toBe(401);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("the active page links the session's own region", async () => {
    const session = issuePreviewSession(TOKEN, "north-america");
    const html = await (await previewGET(new Request(`${ORIGIN}/research/preview`, {
      headers: { cookie: `${PREVIEW_COOKIE}=${session}` },
    }))).text();
    expect(html).toContain('href="/research/humanoid-availability/north-america"');
    expect(html).toContain("Open the North America resource");
  });
});
