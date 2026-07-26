/**
 * WS8.2 / R7 + R8 — canonical-origin correctness, tested adversarially.
 *
 * Gap B4: `lib/site.ts` defaulted to `https://humanoidonline.com`, so any
 * staging or preview deploy silently published production canonical URLs into
 * JSON-LD, the sitemap, robots.txt and llms.txt. Search engines and LLM crawlers
 * would then attribute preview content to the production origin.
 *
 * Two things are proven here:
 *
 * 1. The environment classifier fails safe. Unset, empty or misspelled `APP_ENV`
 *    must never resolve to a relaxed environment that re-enables a default.
 * 2. All four machine surfaces derive from the *same* resolver, so a staging
 *    origin reaches every one of them and the production hostname reaches none.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const PRODUCTION_HOST = "humanoidonline.com";
const STAGING_ORIGIN = "https://staging.humanoid.invalid";

const ORIGINAL_ENV = { ...process.env };

function setEnv(env: Record<string, string | undefined>) {
  for (const key of ["APP_ENV", "NEXT_PUBLIC_SITE_URL"]) delete process.env[key];
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
  vi.resetModules();
  vi.restoreAllMocks();
});

async function loadSite() {
  return import("@/lib/site");
}

// ---------------------------------------------------------------- classifier

describe("environment classifier (fails safe in both directions)", () => {
  it("treats unset / empty APP_ENV as production, never development", async () => {
    const { resolveAppEnv } = await loadSite();
    expect(resolveAppEnv(undefined)).toBe("production");
    expect(resolveAppEnv("")).toBe("production");
    expect(resolveAppEnv("   ")).toBe("production");
  });

  it("throws on a misspelled environment rather than guessing", async () => {
    const { resolveAppEnv, ConfigurationError } = await loadSite();
    for (const typo of ["developmnt", "dev", "prod", "local", "stage"]) {
      expect(() => resolveAppEnv(typo)).toThrow(ConfigurationError);
    }
  });

  it("normalises case for recognised values", async () => {
    const { resolveAppEnv } = await loadSite();
    expect(resolveAppEnv("PRODUCTION")).toBe("production");
    expect(resolveAppEnv(" Development ")).toBe("development");
  });
});

// ---------------------------------------------------------- origin resolution

describe("siteUrl()", () => {
  it("refuses to invent an origin in production (B4)", async () => {
    setEnv({});
    const { siteUrl, ConfigurationError } = await loadSite();
    expect(() => siteUrl()).toThrow(ConfigurationError);
    try {
      siteUrl();
    } catch (error) {
      // Actionable, and explicit about *why* there is no fallback.
      expect((error as Error).message).toContain("NEXT_PUBLIC_SITE_URL is required");
      expect((error as Error).message).not.toContain(PRODUCTION_HOST);
    }
  });

  it("refuses in staging too", async () => {
    setEnv({ APP_ENV: "staging" });
    const { siteUrl, ConfigurationError } = await loadSite();
    expect(() => siteUrl()).toThrow(ConfigurationError);
  });

  it("allows a convenience origin only in development and test", async () => {
    for (const env of ["development", "test"]) {
      vi.resetModules();
      setEnv({ APP_ENV: env });
      const { siteUrl } = await loadSite();
      expect(siteUrl()).toBe("http://localhost:3000");
    }
  });

  it("uses the explicit origin and strips trailing slashes", async () => {
    setEnv({ APP_ENV: "production", NEXT_PUBLIC_SITE_URL: `${STAGING_ORIGIN}/` });
    const { siteUrl } = await loadSite();
    expect(siteUrl()).toBe(STAGING_ORIGIN);
  });

  it("rejects a malformed or non-http origin", async () => {
    for (const bad of ["not-a-url", "ftp://example.com", "example.com"]) {
      vi.resetModules();
      setEnv({ APP_ENV: "production", NEXT_PUBLIC_SITE_URL: bad });
      const { siteUrl, ConfigurationError } = await loadSite();
      expect(() => siteUrl(), bad).toThrow(ConfigurationError);
    }
  });
});

// ------------------------------------------- all four surfaces, one resolver

describe("every machine surface derives from the one resolver", () => {
  const robot = {
    slug: "unitree-g1",
    name: "Unitree G1",
    manufacturer: { slug: "unitree", name: "Unitree" },
    summary: "A humanoid.",
    description: null,
    announced_year: 2024,
    commercial_status: "COMMERCIAL",
    images: [],
    specs: {},
    updated_at: "2026-01-01T00:00:00Z",
  };

  beforeEach(() => {
    setEnv({ APP_ENV: "staging", NEXT_PUBLIC_SITE_URL: STAGING_ORIGIN });
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: [robot], total: 1 })),
      listManufacturers: vi.fn(async () => ({
        items: [{ slug: "unitree", name: "Unitree", updated_at: "2026-01-01T00:00:00Z" }],
        total: 1,
      })),
    }));
  });

  it("sitemap.xml uses the staging origin and never production", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = await sitemap();
    expect(entries.length).toBeGreaterThan(0);
    for (const entry of entries) {
      expect(entry.url.startsWith(STAGING_ORIGIN)).toBe(true);
      expect(entry.url).not.toContain(PRODUCTION_HOST);
    }
  });

  it("robots.txt uses the staging origin and never production", async () => {
    const { default: robots } = await import("@/app/robots");
    const result = robots();
    expect(result.sitemap).toBe(`${STAGING_ORIGIN}/sitemap.xml`);
    expect(result.host).toBe(STAGING_ORIGIN);
    expect(JSON.stringify(result)).not.toContain(PRODUCTION_HOST);
  });

  it("llms.txt uses the staging origin and never production", async () => {
    const { GET } = await import("@/app/llms.txt/route");
    const body = await (await GET()).text();
    expect(body).toContain(`${STAGING_ORIGIN}/robots/unitree-g1`);
    expect(body).not.toContain(PRODUCTION_HOST);
  });

  it("JSON-LD uses the staging origin and never production", async () => {
    const { buildRobotJsonLd } = await import("@/lib/jsonld");
    const graph = JSON.stringify(buildRobotJsonLd(robot as never));
    expect(graph).toContain(`${STAGING_ORIGIN}/robots/unitree-g1`);
    expect(graph).not.toContain(PRODUCTION_HOST);
  });
});

// --------------------------------------------------- config parity with build

describe("next.config.mjs mirrors the same contract", () => {
  it("keeps the build-time guard in step with the runtime resolver", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const config = readFileSync(resolve(process.cwd(), "next.config.mjs"), "utf-8");
    // The build guard cannot import the TS module, so it restates the rule.
    // If these drift, a bad config could build cleanly and fail in production.
    expect(config).toContain("NEXT_PUBLIC_SITE_URL is required to build");
    expect(config).toContain('["development", "test"]');
    expect(config).not.toContain(PRODUCTION_HOST);
  });
});
