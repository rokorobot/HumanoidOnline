/**
 * HO-RESEARCH-ASIA-01 — the Asia Regional Research Resource, end to end through
 * the real page, JSON route, metadata, sitemap, hub, llms.txt and preview access
 * route, against a stubbed API that follows the API's own publication rules.
 *
 * Asia reuses the shared gate, rendering and JSON-LD; these tests pin that it is
 * closed by default (including under production's current flag
 * "europe,north-america"), isolated from the other regions' publication and
 * preview, keeps its DRAFT editorial out of any public page, never names a
 * withdrawn or unpublished robot, and keeps HTML, JSON and JSON-LD consistent.
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

import { GET } from "../app/research/humanoid-availability/asia.json/route";
import AsiaPage, { generateMetadata } from "../app/research/humanoid-availability/asia/page";
import { GET as llmsGET } from "../app/llms.txt/route";
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

const ORIGIN = "https://asia.test.invalid";
const PAGE_URL = `${ORIGIN}/research/humanoid-availability/asia`;
const TOKEN = "review-token";
const ENV_KEYS = ["RESEARCH_PUBLISHED_REGIONS", "RESEARCH_PREVIEW_TOKEN", "NEXT_PUBLIC_SITE_URL"] as const;
const saved: Record<string, string | undefined> = {};

const ASIA = { slug: "asia", code: "ASIA", name: "Asia" };
const price = (amount: number, currency: string, period = "ONE_TIME") => ({
  kind: "PUBLISHED" as const,
  price_type: "PUBLIC",
  amount,
  price_min: null,
  price_max: null,
  currency,
  billing_period: period,
  price_basis: null,
});
const NOT_PUBLISHED = {
  kind: "NOT_PUBLISHED" as const,
  price_type: null,
  amount: null,
  price_min: null,
  price_max: null,
  currency: null,
  billing_period: null,
  price_basis: null,
};

function asiaProjection(overrides: Partial<ResearchProjection> = {}): ResearchProjection {
  const base = projection();
  const offer = base.offers[0];
  return projection({
    region: ASIA,
    snapshot_date: "2026-10-24",
    latest_evidence_date: "2026-10-24",
    direct_answer:
      "As of 2026-10-24, HumanoidOnline lists 2 published humanoid robots with a confirmed offer in Asia. 1 can be purchased: 1 on request. Additionally, 1 of these robots has a confirmed rental offer. 41 other published robots have no confirmed Asia offer on file.",
    publication_health: {
      status: "LIMITED_EVIDENCE",
      reasons: ["2 qualifying robots; minimum 5", "2 manufacturers; minimum 3"],
    },
    offers: [
      {
        ...offer,
        robot_slug: "unitree-g1",
        robot_name: "G1 Basic",
        manufacturer_slug: "unitree",
        manufacturer_name: "Unitree Robotics",
        provider_slug: "unitree-cn",
        provider_type: "OEM",
        region_code: "CN",
        availability_status: "ON_REQUEST",
        evidence_date: "2026-10-24",
        source_urls: ["https://maker.example/cn/g1"],
        prices: [price(85000, "CNY")],
      },
      {
        ...offer,
        robot_slug: "softbank-pepper",
        robot_name: "Pepper",
        manufacturer_slug: "softbank-robotics",
        manufacturer_name: "SoftBank Robotics",
        provider_slug: "tent-pepper-rental",
        provider_type: "RENTAL_PROVIDER",
        region_code: "JP",
        transaction_type: "RENTAL",
        availability_status: "AVAILABLE",
        evidence_date: "2026-10-24",
        source_urls: ["https://rental.example/pepper"],
        prices: [price(43780, "JPY", "MONTHLY")],
      },
    ],
    deployments: [
      {
        robot_slug: "ubtech-walker-s2",
        robot_name: "Walker S2",
        manufacturer_slug: "ubtech-robotics",
        manufacturer_name: "UBTECH Robotics",
        region_code: "CN",
        customer_name: "Hitachi (China) Ltd.",
        provider_slug: null,
        transaction_type: "PILOT",
        unit_count: null,
        started_on: null,
        status: "pilot",
        evidence_date: "2026-10-24",
        confidence: "MEDIUM",
        human_verified: false,
        source_urls: ["https://maker.example/hitachi"],
      },
    ],
    no_confirmed_offer: [
      {
        reason: "GLOBAL_ONLY",
        label: "Global offer only; no region-specific offer",
        robots: [{ slug: "unitree-h1", name: "H1", manufacturer_slug: "unitree", manufacturer_name: "Unitree Robotics" }],
      },
      {
        reason: "OTHER_REGION_ONLY",
        label: "Offers on file for other regions only",
        robots: [{ slug: "agibot-a2-ultra", name: "A2 Ultra", manufacturer_slug: "agibot", manufacturer_name: "AgiBot" }],
      },
    ],
    faq: [
      { question: "Can I buy a humanoid robot in Asia?", answer: "As of 2026-10-24, 1 published humanoid robot has a confirmed purchase offer on file in Asia: G1 Basic." },
    ],
    member_region_codes: ["ASIA", "CN", "JP", "KR", "SG", "TW"],
    ...overrides,
  });
}

// API double: same rules as apps/api/app/routers/research.py, per region.
let apiPublic: string[] = [];
let apiToken: string | null = null;
const fetchMock = vi.fn();

function apiBody(region: string, published: boolean): ResearchProjection {
  const body = region === "asia" ? asiaProjection() : projection();
  return {
    ...body,
    published,
    ...(published
      ? {}
      : {
          readiness: {
            gate_passes: false,
            qualifying_robots: 2,
            qualifying_manufacturers: 2,
            min_robots: 5,
            min_manufacturers: 3,
            failures: ["qualifying robots 2 < 5", "qualifying manufacturers 2 < 3"],
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
  return AsiaPage();
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
const llmsText = async () => (await llmsGET()).text();

describe("registration", () => {
  it("is a built region with its own path", () => {
    expect(RESEARCH_REGIONS).toContain("asia");
    expect(researchPath("asia")).toBe("/research/humanoid-availability/asia");
  });
});

describe("closed (default) and isolated from Europe and North America", () => {
  it("is 404 for page, metadata and JSON, and never calls the API", async () => {
    await expect(visitPage()).rejects.toThrow();
    expect((await visitMeta()).title).toBe("Not found");
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("production's current flag (europe,north-america) does not publish Asia anywhere", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe,north-america";
    apiPublic = ["europe", "north-america", "asia"]; // even if the API would serve it
    expect(resolveResearchAccess("asia", null)).toEqual({ mode: "closed" });
    await expect(visitPage()).rejects.toThrow();
    expect((await GET(jsonRequest())).status).toBe(404);
    expect(await researchUrls()).toEqual([
      `${ORIGIN}/research/humanoid-availability/europe`,
      `${ORIGIN}/research/humanoid-availability/north-america`,
    ]);
    expect(await liveResearchRegions()).toEqual(["europe", "north-america"]);
    const llms = await llmsText();
    expect(llms).not.toContain("/research/humanoid-availability/asia");
    expect(llms).not.toContain("Asia");
    const { container } = render(await ResearchHubPage());
    expect(container.querySelector('a[href="/research/humanoid-availability/asia"]')).toBeNull();
  });

  it("a Europe or North America preview session grants nothing here", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
    for (const other of ["europe", "north-america"]) {
      await expect(visitPage(other)).rejects.toThrow();
      expect((await GET(jsonRequest(other))).status).toBe(404);
    }
  });

  it("an Asia preview session grants nothing on Europe or North America", () => {
    const env = { RESEARCH_PREVIEW_TOKEN: TOKEN };
    const session = issuePreviewSession(TOKEN, "asia");
    expect(resolveResearchAccess("europe", session, env)).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("north-america", session, env)).toEqual({ mode: "closed" });
    expect(resolveResearchAccess("asia", session, env)).toEqual({ mode: "preview", token: TOKEN });
  });
});

describe("valid Asia preview", () => {
  beforeEach(() => {
    process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
    apiToken = TOKEN;
  });

  it("renders with the banner, readiness and the DRAFT editorial", async () => {
    const { container } = render(await visitPage("asia"));
    expect(container.querySelector('[data-testid="preview-banner"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="readiness"]')?.textContent).toContain("Gate fails");
    const editorial = container.querySelector('[data-testid="editorial"]')?.textContent ?? "";
    expect(editorial).toContain("DRAFT");
    expect(editorial).toContain("UN M49 Asia classification");
    expect(editorial).toContain("Cyprus");
    expect(editorial).toContain("Taiwan");
    expect(editorial).not.toContain("Reviewed");
    const sources = [...container.querySelectorAll('[data-testid="editorial-source"] a')].map(
      (a) => a.getAttribute("href"),
    );
    expect(sources).toEqual(EDITORIAL.asia.sources);
    expect(container.querySelector("h1")?.textContent).toBe("Which humanoid robots are available in Asia?");
    const warning = container.querySelector('[data-testid="limited-evidence-warning"]')?.textContent ?? "";
    expect(warning).toContain("This resource is not published");
  });

  it("the editorial hard-codes no price, currency, count or robot name", () => {
    const text = EDITORIAL.asia.paragraphs.join(" ");
    expect(text.replaceAll("M49", "")).not.toMatch(/[$¥€]|USD|CNY|JPY|\d/);
    for (const name of ["Unitree", "G1", "Pepper", "Booster", "UBTECH", "AgiBot", "Walker"]) {
      expect(text).not.toContain(name);
    }
  });

  it("is noindex in metadata and JSON, and absent from the sitemap and llms.txt", async () => {
    expect((await visitMeta("asia")).robots).toEqual({ index: false, follow: false });
    const res = await GET(jsonRequest("asia"));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
    expect((await res.json()).readiness.gate_passes).toBe(false);
    expect(await researchUrls()).toEqual([]);
    expect(await llmsText()).not.toContain("/research/humanoid-availability/asia");
  });

  it("calls the API for the asia region with the token as a header", async () => {
    await GET(jsonRequest("asia"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/research\/humanoid-availability\/asia$/);
    expect(String(url)).not.toContain(TOKEN);
    expect((init.headers as Record<string, string>)["X-Research-Preview"]).toBe(TOKEN);
  });
});

describe("published (after an owner decision)", () => {
  beforeEach(() => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe,north-america,asia";
    apiPublic = ["europe", "north-america", "asia"];
  });

  it("is indexable with a unique title, canonical URL and the generated description", async () => {
    const meta = await visitMeta();
    expect(meta.title).toBe("Humanoid robot availability in Asia");
    expect(meta.description).toBe(asiaProjection().direct_answer);
    expect(meta.alternates?.canonical).toBe(PAGE_URL);
    expect(meta.robots).toBeUndefined();
  });

  it("never shows the unreviewed editorial publicly", async () => {
    expect(EDITORIAL.asia.reviewed_at).toBeNull();
    expect(editorialState("asia", "2026-10-24", false)).toEqual({ show: false });
    const { container } = render(await visitPage());
    expect(container.querySelector('[data-testid="editorial"]')).toBeNull();
    expect(container.textContent).not.toContain("DRAFT");
  });

  it("HTML, JSON and JSON-LD agree on the same projection", async () => {
    const data = apiBody("asia", true);
    const { container } = render(await visitPage());
    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld).toEqual(buildResearchJsonLd(data, ORIGIN));
    const types = ld["@graph"].map((n: { "@type": string }) => n["@type"]);
    expect(types).toEqual(expect.arrayContaining(["Dataset", "ItemList", "FAQPage"]));
    const dataset = ld["@graph"].find((n: { "@type": string }) => n["@type"] === "Dataset");
    expect(dataset.url).toBe(PAGE_URL);
    expect(dataset.spatialCoverage.name).toBe("Asia");
    expect(dataset.distribution.contentUrl).toBe(`${PAGE_URL}.json`);
    expect(container.querySelector('[data-testid="direct-answer"]')?.textContent).toBe(data.direct_answer);
    const json = await (await GET(jsonRequest())).json();
    expect(json).toEqual(data);
    const ldSlugs = ld["@graph"]
      .find((n: { "@type": string }) => n["@type"] === "ItemList")
      .itemListElement.map((i: { url: string }) => i.url.replace(`${ORIGIN}/robots/`, ""));
    expect(ldSlugs).toEqual(json.offers.map((o: { robot_slug: string }) => o.robot_slug));
    const faq = ld["@graph"].find((n: { "@type": string }) => n["@type"] === "FAQPage");
    expect(faq.mainEntity.map((q: { name: string }) => q.name)).toEqual(data.faq.map((f) => f.question));
  });

  it("shows prices in their published currency and period, never converted", async () => {
    const { container } = render(await visitPage());
    const text = container.textContent ?? "";
    expect(text).toContain("85,000 CNY");
    expect(text).toContain("43,780 JPY / month");
    expect(text).not.toMatch(/\bUSD\b/);
  });

  it("an unpublished price stays 'Not published', never 0", async () => {
    const body = asiaProjection();
    body.offers[0] = { ...body.offers[0], prices: [NOT_PUBLISHED] };
    fetchMock.mockImplementation(async () => Response.json({ ...body, published: true }));
    const { container } = render(await visitPage());
    const row =
      [...container.querySelectorAll('[data-testid^="offers-"][data-testid$="-table"] tbody tr')]
        .map((tr) => tr.textContent ?? "")
        .find((t) => t.includes("G1 Basic")) ?? "";
    expect(row).toContain("Not published");
    expect(row).not.toMatch(/\b0 CNY\b/);
  });

  it("keeps deployments, global-only and unpublished robots out of the offer tables", async () => {
    const { container } = render(await visitPage());
    const tables = [...container.querySelectorAll('[data-testid^="offers-"][data-testid$="-table"]')]
      .map((t) => t.textContent ?? "")
      .join(" ");
    expect(tables).not.toContain("Walker S2");
    expect(tables).not.toContain("H1");
    expect(container.textContent).not.toMatch(/agibot-x2|AgiBot X2/);
    expect(container.querySelector('[data-testid="deployments-table"]')?.textContent).toContain("Hitachi (China) Ltd.");
    expect(container.querySelector('[data-testid="global-only"]')?.textContent).toContain("H1");
  });

  it("is in the sitemap and llms.txt, and listed live on the hub", async () => {
    expect(await researchUrls()).toContain(PAGE_URL);
    expect(await liveResearchRegions()).toEqual(["europe", "north-america", "asia"]);
    expect(await llmsText()).toContain(`${PAGE_URL}.json`);
    const { container } = render(await ResearchHubPage());
    expect(container.querySelector('a[href="/research/humanoid-availability/asia"]')?.textContent).toContain("Asia");
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

  it("offers Asia in the form", async () => {
    const html = await (await previewGET(new Request(`${ORIGIN}/research/preview`))).text();
    expect(html).toContain('<option value="asia">Asia</option>');
  });

  it("issues a session for exactly Asia", async () => {
    const res = await post({ token: TOKEN, region: "asia" });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/research/humanoid-availability/asia");
    const value = res.headers.get("set-cookie")!.match(new RegExp(`^${PREVIEW_COOKIE}=([^;]*)`))![1];
    expect(verifyPreviewSession(value, TOKEN)).toBe("asia");
  });

  it("APAC is not a synonym for Asia", async () => {
    for (const region of ["apac", "asia-pacific", "ASIA"]) {
      const res = await post({ token: TOKEN, region });
      expect(res.status).toBe(400);
      expect(res.headers.get("set-cookie")).toBeNull();
    }
  });
});
