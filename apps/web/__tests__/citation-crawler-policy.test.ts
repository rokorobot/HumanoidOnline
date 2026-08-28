/**
 * AI Citation Layer v0.1 — crawler-eligibility gates (docs/23 §12/§13, CID-07).
 *
 *   CIT-G  search/retrieval crawlers (explicitly OAI-SearchBot) can reach
 *          public robot records and the machine-discovery surfaces
 *   CIT-H  this slice does NOT silently change training-crawler policy
 *
 * §13 is explicit that robots.txt alone is insufficient: the whole public path
 * matters, and the Netlify native rate limits are the one piece of that path
 * this repository actually controls. Those limits are declared in edge-function
 * `config.path` values, so their SCOPE is assertable here as a unit test —
 * runtime behaviour against a deployed origin is a separate concern (E2E).
 */
import { beforeAll, describe, expect, it } from "vitest";

import robots from "@/app/robots";
import { config as compareRateLimit } from "@/netlify/edge-functions/compare-native-rate-limit";
import { config as robotsRateLimit } from "@/netlify/edge-functions/robots-native-rate-limit";

const ORIGIN = "https://crawler.test.invalid";

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});

/** Netlify native `config.path` is an EXACT path match unless it ends in a
 *  wildcard. Mirrors that rule so scope assertions below are meaningful. */
function pathMatches(pattern: string, url: string): boolean {
  if (pattern.endsWith("/*")) return url.startsWith(pattern.slice(0, -1));
  if (pattern.endsWith("*")) return url.startsWith(pattern.slice(0, -1));
  return pattern === url;
}

// ---- CIT-G — retrieval crawlers are permitted ------------------------------

describe("CIT-G — search/retrieval crawlers may retrieve public content", () => {
  it("robots.txt allows all user agents at the root", () => {
    const r = robots();
    const wildcard = (Array.isArray(r.rules) ? r.rules : [r.rules]).find(
      (rule) => rule?.userAgent === "*",
    );
    expect(wildcard).toBeTruthy();
    expect(wildcard?.allow).toBe("/");
  });

  it("OAI-SearchBot is permitted (covered by the wildcard allow, not disallowed)", () => {
    const r = robots();
    const rules = Array.isArray(r.rules) ? r.rules : [r.rules];
    // Either it is explicitly allowed, or it is covered by `*: allow /` and
    // carries no disallow of its own. Both satisfy CIT-G; what must NEVER be
    // true is a Disallow that applies to it.
    for (const rule of rules) {
      const agents = Array.isArray(rule?.userAgent) ? rule.userAgent : [rule?.userAgent];
      const appliesToOai = agents.some(
        (a) => a === "*" || String(a).toLowerCase() === "oai-searchbot",
      );
      if (!appliesToOai) continue;
      const disallow = rule?.disallow;
      const disallowList = Array.isArray(disallow) ? disallow : disallow ? [disallow] : [];
      // A disallow of "" is the robots.txt idiom for "nothing is disallowed".
      expect(disallowList.filter((d) => d !== "")).toEqual([]);
    }
  });

  it("declares the sitemap so crawlers can enumerate the published set", () => {
    const r = robots();
    expect(r.sitemap).toBe(`${ORIGIN}/sitemap.xml`);
  });

  it("emits no blanket Disallow anywhere in the policy", () => {
    const r = robots();
    const rules = Array.isArray(r.rules) ? r.rules : [r.rules];
    for (const rule of rules) {
      const disallow = rule?.disallow;
      const list = Array.isArray(disallow) ? disallow : disallow ? [disallow] : [];
      expect(list).not.toContain("/");
    }
  });
});

// ---- CIT-H — training policy is untouched ----------------------------------

describe("CIT-H — training-crawler policy is not silently changed", () => {
  it("names no training-crawler agent (that split is a separate owner decision)", () => {
    const r = robots();
    const rules = Array.isArray(r.rules) ? r.rules : [r.rules];
    const named = rules
      .flatMap((rule) => (Array.isArray(rule?.userAgent) ? rule.userAgent : [rule?.userAgent]))
      .map((a) => String(a).toLowerCase());
    // docs/23 §12: search/retrieval access and training permission are separate
    // axes. v0.1 must leave the training axis exactly as it was — which, in this
    // repo, means no per-bot rule exists at all.
    for (const trainingAgent of ["gptbot", "claudebot", "google-extended", "ccbot"]) {
      expect(named).not.toContain(trainingAgent);
    }
  });

  it("keeps a single wildcard rule — the pre-existing stance, unmodified", () => {
    const r = robots();
    const rules = Array.isArray(r.rules) ? r.rules : [r.rules];
    expect(rules).toHaveLength(1);
    expect(rules[0]?.userAgent).toBe("*");
  });
});

// ---- CIT-G — edge rate limits must not cover crawlable surfaces ------------

describe("CIT-G — Netlify edge rate limits do not cover citation surfaces", () => {
  const CITATION_SURFACES = [
    "/robots/unitree-g1",
    "/robots/figure-02",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/manufacturers/unitree",
    "/use-cases/research-education",
    "/",
  ];

  it("the /robots list limiter matches ONLY the list route, not robot records", () => {
    // This is the single highest-risk crawler-blocking surface in the repo: a
    // pattern of "/robots/*" instead of "/robots" would silently rate-limit
    // every robot detail page — the exact citation target — at 30/60s/IP.
    expect(robotsRateLimit.path).toBe("/robots");
    for (const url of CITATION_SURFACES) {
      expect(pathMatches(String(robotsRateLimit.path), url)).toBe(false);
    }
    expect(pathMatches(String(robotsRateLimit.path), "/robots")).toBe(true);
  });

  it("the /compare limiter covers only /compare", () => {
    expect(compareRateLimit.path).toBe("/compare");
    for (const url of CITATION_SURFACES) {
      expect(pathMatches(String(compareRateLimit.path), url)).toBe(false);
    }
  });

  it("no rate limit applies to robots.txt, sitemap.xml or llms.txt", () => {
    for (const limiter of [robotsRateLimit, compareRateLimit]) {
      for (const surface of ["/robots.txt", "/sitemap.xml", "/llms.txt"]) {
        expect(pathMatches(String(limiter.path), surface)).toBe(false);
      }
    }
  });
});
