/**
 * WS8.6 / R24 (Part B) — deterministic built-route budget.
 *
 * Complements the manifest-level bundle budget (scripts/perf-budget.mjs) by
 * exercising the ACTUAL built routes served against the fixed WS2B catalogue and
 * asserting reproducible, non-timing quantities:
 *   - the server-rendered document (HTML) byte size,
 *   - the number of route JS assets requested,
 *   - their total (decompressed) byte size.
 *
 * No CPU-time / LCP / timing thresholds — those are noisy in CI and belong to the
 * post-release field SLO (§11.1), not this release gate. Against a fixed
 * catalogue these byte/count measurements are deterministic.
 *
 * Budgets were measured from the baseline at `main @ 2b9cd53` with headroom
 * (~30% on the document, ~15% on JS weight; asset count baseline 6 → cap 8).
 */
import { expect, test, type Page } from "@playwright/test";

interface Budget {
  path: string;
  docKB: number; // baseline: home 47.0 catalogue 43.9 detail 68.1 compare 24.0 wizard 35.1 matches 42.8
  jsRawKB: number; // baseline ~351-375 kB
}
const JS_COUNT_MAX = 8; // baseline 6 on every route

async function measure(page: Page, path: string) {
  let jsCount = 0;
  const jsBodies: Promise<Buffer>[] = [];
  const onResp = (resp: { url(): string; body(): Promise<Buffer> }) => {
    if (/\/_next\/static\/.*\.js(\?|$)/.test(resp.url())) {
      jsCount++;
      jsBodies.push(resp.body().catch(() => Buffer.alloc(0)));
    }
  };
  page.on("response", onResp);
  const resp = await page.goto(path, { waitUntil: "networkidle" });
  page.off("response", onResp);
  const docKB = (await resp!.body()).length / 1024;
  const jsRawKB =
    (await Promise.all(jsBodies)).reduce((a, b) => a + b.length, 0) / 1024;
  return { docKB, jsCount, jsRawKB };
}

const STATIC: Budget[] = [
  { path: "/", docKB: 62, jsRawKB: 404 },
  { path: "/robots", docKB: 58, jsRawKB: 411 },
  { path: "/robots/unitree-g1", docKB: 89, jsRawKB: 412 },
  { path: "/compare?ids=unitree-g1,agility-digit", docKB: 32, jsRawKB: 431 },
  { path: "/find-a-humanoid", docKB: 46, jsRawKB: 424 },
];

for (const b of STATIC) {
  test(`@perf built-route budget: ${b.path}`, async ({ page }) => {
    const m = await measure(page, b.path);
    expect(m.docKB, `${b.path} document ${m.docKB.toFixed(1)}kB`).toBeLessThanOrEqual(b.docKB);
    expect(m.jsCount, `${b.path} JS asset count`).toBeLessThanOrEqual(JS_COUNT_MAX);
    expect(m.jsRawKB, `${b.path} JS total ${m.jsRawKB.toFixed(1)}kB`).toBeLessThanOrEqual(b.jsRawKB);
  });
}

test("@perf built-route budget: /matches/[id]", async ({ page, request }) => {
  const created = await request.post("/api/buyer-requirements", {
    data: {
      country: "US",
      preferred_transaction: "UNKNOWN",
      raw_input: {
        wizard_version: 1,
        answers: { country: { state: "ANSWERED", value: "US" } },
      },
    },
  });
  const id = (await created.json()).id as string;
  const m = await measure(page, `/matches/${id}`);
  expect(m.docKB, `matches document ${m.docKB.toFixed(1)}kB`).toBeLessThanOrEqual(56);
  expect(m.jsCount, "matches JS asset count").toBeLessThanOrEqual(JS_COUNT_MAX);
  expect(m.jsRawKB, `matches JS total ${m.jsRawKB.toFixed(1)}kB`).toBeLessThanOrEqual(417);
});
