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

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
