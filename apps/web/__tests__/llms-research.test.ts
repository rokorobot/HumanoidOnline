/**
 * /llms.txt — Research links and wording (ADR-027).
 *
 * Machine discovery enumerates only PUBLIC resources: the Research section exists
 * only while a region is actually published and served, and the description makes
 * no claim that every published fact is human-verified.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projection } from "./research-fixture";

const SUPPRESSED = "UNPUBLISHED-SENTINEL-4b7e";

// The governed reads return published entities only; the sentinel is something a
// surface could only ever emit by inventing it.
vi.mock("@/lib/seo", () => ({
  listAllRobots: async () => [
    { slug: "published-bot", name: "Published Bot", manufacturer: { slug: "acme", name: "Acme Robotics" } },
  ],
  listAllManufacturers: async () => [{ slug: "acme", name: "Acme Robotics" }],
  listAllUseCases: async () => [{ slug: "warehouse", name: "Warehouse" }],
  lastMod: () => ({}),
}));

import { GET } from "../app/llms.txt/route";

const ORIGIN = "https://llms.test.invalid";
const HUB = `${ORIGIN}/research`;
const EUROPE = `${ORIGIN}/research/humanoid-availability/europe`;
const ENV_KEYS = ["RESEARCH_PUBLISHED_REGIONS", "RESEARCH_PREVIEW_TOKEN", "NEXT_PUBLIC_SITE_URL"] as const;
const saved: Record<string, string | undefined> = {};

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
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

const body = async () => (await GET()).text();

describe("Research section", () => {
  it("is absent when zero regions are published: no /research URL, no region teasers", async () => {
    const text = await body();
    expect(text).not.toContain("/research");
    expect(text).not.toContain("## Research resources");
    for (const word of ["Europe", "North America", "Asia", "coming soon", "in preparation"]) {
      expect(text).not.toContain(word);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists the hub, Europe page, methodology anchor and JSON when Europe is published and served", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiServes = true;
    const text = await body();
    expect(text).toContain("## Research resources");
    expect(text).toContain(`- Research hub: ${HUB}`);
    expect(text).toContain(`- Humanoid availability in Europe: ${EUROPE}`);
    expect(text).toContain(`- Europe methodology: ${EUROPE}#method`);
    expect(text).toContain(`- Europe JSON: ${EUROPE}.json`);
  });

  it("enumerates only public resources: no other region is named or teased", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe,asia,north-america";
    apiServes = true;
    const text = await body();
    expect(text).not.toContain("North America");
    expect(text).not.toContain("Asia");
    expect(text).not.toMatch(/coming soon|in preparation|planned/i);
    expect(text.match(/\/research\/humanoid-availability\//g)).toHaveLength(3); // page, #method, .json
  });

  it("is a compact, ordered section between the entry points and the entity lists", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiServes = true;
    const text = await body();
    const at = (s: string) => text.indexOf(s);
    expect(at("## Canonical entry points")).toBeLessThan(at("## Research resources"));
    expect(at("## Research resources")).toBeLessThan(at("## Robots (published, canonical)"));
    const section = text.slice(at("## Research resources"), at("## Robots (published, canonical)"));
    expect(section.trim().split("\n")).toHaveLength(5); // heading + hub + 3 Europe lines
  });

  it("is absent when the region is flagged but the API does not serve it", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiServes = false; // not served: e.g. structurally closed (404)
    const text = await body();
    expect(text).not.toContain("/research");
    expect(text).not.toContain("## Research resources");
  });

  it("is absent when the API is unreachable", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    fetchMock.mockImplementation(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    const text = await body();
    expect(text).not.toContain("/research");
  });

  it("a preview token alone never exposes the resource to machine discovery", async () => {
    process.env.RESEARCH_PREVIEW_TOKEN = "review-token";
    apiServes = true;
    const text = await body();
    expect(text).not.toContain("/research");
    expect(text).not.toContain("review-token");
  });

  it("lists URLs only: no robot names, figures or answers from the resource leak in", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiServes = true;
    const text = await body();
    for (const leaked of ["Bot A", "Bot B", "Bot G", "Maker A", "As of 2026-10-04"]) {
      expect(text).not.toContain(leaked);
    }
  });
});

describe("canonical-only surface", () => {
  it("lists published entities and never an unpublished or candidate one", async () => {
    process.env.RESEARCH_PUBLISHED_REGIONS = "europe";
    apiServes = true;
    const text = await body();
    expect(text).toContain(`${ORIGIN}/robots/published-bot`);
    expect(text).toContain(`${ORIGIN}/manufacturers/acme`);
    expect(text).toContain(`${ORIGIN}/use-cases/warehouse`);
    expect(text).not.toContain(SUPPRESSED);
    expect(text).not.toContain("NOT_VERIFIED");
    expect(text).not.toContain("discovery_candidate");
  });

  it("keeps the UNKNOWN / maturity / availability / evidence semantics", async () => {
    const text = await body();
    expect(text).toContain("## Semantics (read before citing)");
    expect(text).toContain("UNKNOWN is not 0");
    expect(text).toContain("Commercial maturity (commercial_status) is distinct from obtainability (availability)");
    expect(text).toContain("Evidence status (confidence / verified_at) is distinct from commercial status");
    expect(text).toContain("Provenance is exposed where canonical evidence exists; it is never fabricated.");
  });
});

describe("wording does not overclaim", () => {
  it("describes the surface as evidence-aware and says what is retained", async () => {
    const text = await body();
    expect(text).toContain("Evidence-aware humanoid-robot market intelligence.");
    expect(text).toContain("exposes only");
    expect(text).toContain("published canonical entities");
    expect(text).toContain("Commercial facts retain their recorded evidence,");
    expect(text).toContain("confidence and verification state; missing values remain unknown.");
  });

  it("never claims published data is verified, and says publication is not verification", async () => {
    const text = await body();
    expect(text).not.toMatch(/Verified humanoid-robot market intelligence/i);
    expect(text).not.toMatch(/only published, verified data/i);
    expect(text).not.toMatch(/every catalogue fact is canonical and evidence-backed/i);
    expect(text).not.toMatch(/\b(all|every)\b[^\n.]*\bverified\b/i);
    expect(text).toContain("Publication is not verification: a published fact is not necessarily human-verified.");
  });
});
