/**
 * /insights (DR-I1): content invariants, draft exclusion, and the article page render.
 */
import { cleanup, render } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/seo", () => ({
  listAllRobots: async () => [],
  listAllManufacturers: async () => [],
  listAllProductLines: async () => [],
  listAllUseCases: async () => [],
  lastMod: () => ({}),
}));
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api-client")>()),
  findRobot: async (slug: string) => ({
    slug,
    name: `Robot ${slug}`,
    manufacturer: { name: "Agility Robotics", slug: "agility-robotics" },
    commercial_status: "ANNOUNCED",
    availability_offers: [],
    deployments: [],
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/insights",
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import InsightPage, { generateMetadata, generateStaticParams } from "../app/insights/[slug]/page";
import InsightsIndexPage from "../app/insights/page";
import sitemap from "../app/sitemap";
import { ALL_INSIGHTS, publishedInsights } from "../lib/insights";

const ORIGIN = "https://insights.test.invalid";
const SLUG = "agility-digit-5-europe-2027";
const CATALOGUE = path.resolve(__dirname, "../../../db/catalogue/robots");
let savedOrigin: string | undefined;

beforeEach(() => {
  savedOrigin = process.env.NEXT_PUBLIC_SITE_URL;
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});
afterEach(() => {
  cleanup();
  if (savedOrigin === undefined) delete process.env.NEXT_PUBLIC_SITE_URL;
  else process.env.NEXT_PUBLIC_SITE_URL = savedOrigin;
});

describe("insight content", () => {
  it("has at least one published insight, and drafts are excluded from the published list", () => {
    expect(publishedInsights.length).toBeGreaterThan(0);
    expect(publishedInsights.every((i) => i.status === "published")).toBe(true);
    expect(publishedInsights.length).toBe(ALL_INSIGHTS.filter((i) => i.status === "published").length);
  });

  it("slugs are unique", () => {
    const slugs = ALL_INSIGHTS.map((i) => i.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("descriptions are at most 160 characters", () => {
    for (const i of ALL_INSIGHTS) expect(i.description.length, i.slug).toBeLessThanOrEqual(160);
  });

  it("every published insight has sources with https URLs", () => {
    for (const i of publishedInsights) {
      expect(i.sources.length, i.slug).toBeGreaterThan(0);
      for (const s of i.sources) {
        expect(s.url, i.slug).toMatch(/^https:\/\//);
        expect(s.title && s.publisher && s.date, i.slug).toBeTruthy();
      }
    }
  });

  it("every robotSlugs entry is a published catalogue robot", () => {
    for (const i of ALL_INSIGHTS) {
      for (const slug of i.robotSlugs) {
        const file = path.join(CATALOGUE, `${slug}.json`);
        expect(existsSync(file), `${i.slug} -> ${slug}`).toBe(true);
        expect(JSON.parse(readFileSync(file, "utf8")).is_published, slug).toBe(true);
      }
    }
  });
});

describe("routes", () => {
  it("static params and sitemap list published insights only", async () => {
    expect(generateStaticParams()).toEqual(publishedInsights.map((i) => ({ slug: i.slug })));
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toContain(`${ORIGIN}/insights`);
    expect(urls).toContain(`${ORIGIN}/insights/${SLUG}`);
    for (const i of ALL_INSIGHTS.filter((x) => x.status === "draft")) {
      expect(urls).not.toContain(`${ORIGIN}/insights/${i.slug}`);
    }
  });

  it("an unknown or draft slug is a 404", async () => {
    await expect(InsightPage({ params: Promise.resolve({ slug: "no-such-article" }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("the index lists the article with title, date and description", () => {
    const { container } = render(InsightsIndexPage());
    const i = publishedInsights[0];
    expect(container.textContent).toContain(i.title);
    expect(container.textContent).toContain(i.publishedAt);
    expect(container.textContent).toContain(i.description);
  });
});

describe("article page", () => {
  it("renders title, updated date, live robot blocks, sources and Article JSON-LD", async () => {
    const insight = publishedInsights.find((i) => i.slug === SLUG)!;
    const { container } = render(await InsightPage({ params: Promise.resolve({ slug: SLUG }) }));
    expect(container.querySelector("h1")?.textContent).toBe(insight.title);
    expect(container.textContent).toContain(`Updated ${insight.updatedAt}`);
    expect(container.querySelectorAll('[data-testid="insight-robot"]').length).toBe(insight.robotSlugs.length);
    expect(container.querySelector('a[href="/robots/agility-digit-5"]')).not.toBeNull();
    const sources = container.querySelector('[data-testid="insight-sources"]')!;
    for (const s of insight.sources) {
      expect(sources.querySelector(`a[href="${s.url}"]`)?.textContent).toBe(s.title);
    }
    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld["@type"]).toBe("Article");
    expect(ld.headline).toBe(insight.title);
    expect(ld.datePublished).toBe(insight.publishedAt);
    expect(ld.dateModified).toBe(insight.updatedAt);
    expect(ld.author.name).toBe("HumanoidOnline");
    expect(ld.about.map((a: { url: string }) => a.url)).toContain(`${ORIGIN}/robots/agility-digit-5`);
    expect(ld.citation.map((c: { url: string }) => c.url)).toEqual(insight.sources.map((s) => s.url));
  });

  it("sets canonical and Open Graph metadata", async () => {
    const meta = await generateMetadata({ params: Promise.resolve({ slug: SLUG }) });
    expect(meta.alternates?.canonical).toBe(`${ORIGIN}/insights/${SLUG}`);
    expect(meta.openGraph).toMatchObject({ type: "article", url: `${ORIGIN}/insights/${SLUG}` });
  });
});
