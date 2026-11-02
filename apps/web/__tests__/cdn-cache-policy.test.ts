// SEO-03 — which pages Netlify's CDN may cache (owner decision 2026-11-02).
import { beforeAll, describe, expect, it } from "vitest";

type Rule = {
  source: string;
  missing?: Array<{ type: string; key: string }>;
  headers: Array<{ key: string; value: string }>;
};

let rules: Rule[] = [];

beforeAll(async () => {
  process.env.APP_ENV = "test"; // the config's build guard runs on import
  // @ts-expect-error -- plain .mjs config without type declarations
  const mod = await import("../next.config.mjs");
  rules = await mod.default.headers();
});

const cdnRules = () =>
  rules.filter((r) => r.headers.some((h) => h.key === "Netlify-CDN-Cache-Control"));

describe("CDN cache policy", () => {
  it("caches the public pages for 5 minutes, serving stale while refreshing", () => {
    const sources = cdnRules().map((r) => r.source);
    for (const p of ["/", "/robots", "/robots/:slug", "/compare", "/manufacturers/:slug", "/use-cases/:slug", "/lines/:slug", "/about"]) {
      expect(sources).toContain(p);
    }
    for (const r of cdnRules()) {
      const v = r.headers.find((h) => h.key === "Netlify-CDN-Cache-Control")!.value;
      expect(v).toMatch(/s-maxage=300/);
      expect(v).toMatch(/stale-while-revalidate=/);
    }
  });

  it("varies every cached page on the full query string", () => {
    // Without this Netlify's Next runtime keys on `_rsc` only, and every filtered
    // /robots URL would be served the cached unfiltered page.
    for (const r of cdnRules()) {
      expect(r.headers).toContainEqual({ key: "Netlify-Vary", value: "query" });
    }
  });

  it("never caches per-buyer, preview, operator or API responses", () => {
    const sources = cdnRules().map((r) => r.source);
    for (const s of sources) {
      expect(s).not.toMatch(/^\/(matches|research|discovery-review|api)\b/);
      expect(s).not.toContain(":path*");
    }
  });

  it("caches /find-a-humanoid only when it is not prefilled from a saved requirement", () => {
    const wizard = cdnRules().filter((r) => r.source === "/find-a-humanoid");
    expect(wizard).toHaveLength(1);
    expect(wizard[0].missing).toEqual([{ type: "query", key: "from" }]);
  });

  it("keeps the security headers on every route", () => {
    const all = rules.find((r) => r.source === "/:path*")!;
    expect(all.headers.map((h) => h.key)).toContain("X-Frame-Options");
  });
});
