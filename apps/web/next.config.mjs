/**
 * WS8.1 / R4 — the web tier's half of the explicit security posture.
 *
 * WS8-L9: absence of middleware is not itself a defect, but an *unstated,
 * untested* posture is. The API sets the equivalent headers in
 * `app/security/headers.py`; this states the same intent for the browser-facing
 * surface, and `e2e/security-headers.spec.ts` asserts it against a real
 * response rather than trusting the config.
 *
 * Deliberately NOT included: a Content-Security-Policy. A meaningful CSP for
 * this app needs per-request nonces for Next's inline bootstrap and the
 * JSON-LD script tag (AGENT-01), which is a design decision rather than
 * hardening. R4 does not require it, and framing is already denied below.
 *
 * @type {import('next').NextConfig}
 */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  // No feature of this site needs these APIs; deny them rather than inherit
  // whatever the browser defaults to.
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

/**
 * WS8.2 / R7 — fail the BUILD, not the first request.
 *
 * `lib/site.ts` resolves the canonical origin lazily so importing it is safe.
 * That alone would defer a misconfiguration to production traffic, so the same
 * contract is evaluated here: a strict-environment build without an explicit
 * `NEXT_PUBLIC_SITE_URL` stops with an actionable error instead of shipping.
 *
 * Duplicated deliberately and minimally — `next.config.mjs` cannot import the
 * TypeScript module, so this mirrors the rule and `__tests__/site-origin.test.ts`
 * pins the two together.
 */
function assertCanonicalOriginConfigured() {
  const RELAXED = ["development", "test"];
  const ALLOWED = ["development", "test", "staging", "production"];

  const rawEnv = (process.env.APP_ENV ?? "").trim();
  const env = rawEnv === "" ? "production" : rawEnv.toLowerCase();
  if (!ALLOWED.includes(env)) {
    throw new Error(
      `[WS8.2/R7] APP_ENV="${rawEnv}" is not a recognised environment. ` +
        `Use one of: ${ALLOWED.join(", ")}.`,
    );
  }

  const origin = (process.env.NEXT_PUBLIC_SITE_URL ?? "").trim();
  if (origin) {
    let parsed;
    try {
      parsed = new URL(origin);
    } catch {
      throw new Error(
        `[WS8.2/R7] NEXT_PUBLIC_SITE_URL="${origin}" is not a valid absolute URL.`,
      );
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error(
        `[WS8.2/R7] NEXT_PUBLIC_SITE_URL="${origin}" must use http or https.`,
      );
    }
    // Must match lib/site.ts: an origin carries no path, query or fragment.
    // A build guard that accepts what the runtime rejects is worse than none.
    if (
      (parsed.pathname !== "" && parsed.pathname !== "/") ||
      parsed.search ||
      parsed.hash
    ) {
      throw new Error(
        `[WS8.2/R7] NEXT_PUBLIC_SITE_URL="${origin}" must be a bare origin ` +
          `(scheme + host + port). Use "${parsed.origin}".`,
      );
    }
    return;
  }

  if (RELAXED.includes(env)) return;

  throw new Error(
    `[WS8.2/R7] NEXT_PUBLIC_SITE_URL is required to build for APP_ENV="${env}". ` +
      "Refusing to fall back to a hard-coded production hostname — a staging or " +
      "preview build must never publish production canonical URLs.",
  );
}

assertCanonicalOriginConfigured();

/**
 * SEO-03 — CDN caching of public HTML (owner decision 2026-11-02).
 *
 * Every page is force-dynamic, so Next sends `Cache-Control: private, no-store`
 * and each first request paid a 2.5–3.3 s render. Netlify's CDN may now keep a
 * public page for 5 minutes and serve the old copy while it refreshes in the
 * background. Browsers still get Next's own Cache-Control; only the CDN caches.
 * A deploy purges the CDN, so only catalogue (database) changes wait out the TTL.
 *
 * `Netlify-Vary: query` is REQUIRED: Netlify's Next runtime otherwise keys the
 * cache on `_rsc` alone, so `/robots?status=x` would be served the cached
 * `/robots`. The runtime keeps its own RSC/router header variations on top.
 *
 * Deliberately NOT cached: /matches (one buyer's results), /research/* (a preview
 * cookie changes the response), /discovery-review (operator surface), /api/*,
 * and /find-a-humanoid?from=… (prefilled from a saved buyer requirement).
 */
export const CDN_CACHED_PAGES = [
  "/",
  "/robots",
  "/robots/:slug",
  "/compare",
  "/lines/:slug",
  "/manufacturers",
  "/manufacturers/:slug",
  "/use-cases",
  "/use-cases/:slug",
  "/about",
  "/contact",
  "/crawler-policy",
];

export const CDN_CACHE_HEADERS = [
  {
    key: "Netlify-CDN-Cache-Control",
    value: "public, durable, s-maxage=300, stale-while-revalidate=86400",
  },
  { key: "Netlify-Vary", value: "query" },
];

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      ...CDN_CACHED_PAGES.map((source) => ({ source, headers: CDN_CACHE_HEADERS })),
      {
        source: "/find-a-humanoid",
        missing: [{ type: "query", key: "from" }],
        headers: CDN_CACHE_HEADERS,
      },
    ];
  },
};

export default nextConfig;
