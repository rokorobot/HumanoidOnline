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

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
