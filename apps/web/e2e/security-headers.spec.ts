/**
 * WS8.1 / R4 — the web tier's security-header posture, asserted on real
 * responses rather than trusted from `next.config.mjs`.
 *
 * A config block that looks right but never reaches the wire is exactly the
 * class of defect WS8 exists to catch, so this checks the delivered headers on
 * a static route, a dynamic route and a machine surface.
 */
import { expect, test } from "@playwright/test";

const EXPECTED: Record<string, string> = {
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "no-referrer",
};

const PATHS = ["/", "/robots", "/robots/unitree-g1", "/sitemap.xml"];

for (const path of PATHS) {
  test(`security headers are present on ${path}`, async ({ request }) => {
    const res = await request.get(path);
    expect(res.ok()).toBeTruthy();
    const headers = res.headers();
    for (const [name, value] of Object.entries(EXPECTED)) {
      expect(headers[name], `${name} on ${path}`).toBe(value);
    }
    expect(headers["permissions-policy"]).toContain("camera=()");
  });
}

test("no wildcard cross-origin header is advertised", async ({ request }) => {
  // R4 / WS8-L9: the posture is strict same-origin, and it must be observably
  // so — not merely undocumented.
  const res = await request.get("/", { headers: { Origin: "https://evil.example" } });
  const acao = res.headers()["access-control-allow-origin"];
  expect(acao === undefined || acao !== "*").toBeTruthy();
});
