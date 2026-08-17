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
  // baseline: home 47.0 catalogue 43.9 detail 68.1 compare 24.0 wizard 35.1 matches 42.8
  // (`catalogue` = /robots, now scale-aware and asserted in its own test below)
  docKB: number;
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

// `/robots` is deliberately NOT in this table — see the scale-aware test below.
const STATIC: Budget[] = [
  { path: "/", docKB: 62, jsRawKB: 404 },
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

/**
 * `/robots` is the one route whose document size is a function of catalogue
 * SIZE, not of page complexity: it renders every published robot card in a
 * single document (`limit: 100`, no pagination controls). A flat byte cap
 * therefore measures how many robots the product owner has published, which is
 * not a performance property. The original 58 kB cap was calibrated against 7
 * published robots and was exhausted at 10 — ordinary editorial work would keep
 * breaking it, and raising the number would only postpone that.
 *
 * So the budget scales with the number of rendered cards. Measured on the
 * built route against the verified catalogue: ~20.1 kB fixed page cost plus
 * ~3.68 kB per card (fitted across 4, 5 and 13 rendered robots). The allowance
 * below adds modest regression headroom to both terms.
 *
 * What this still catches — the reason the gate exists:
 *   - fixed page overhead growing (chrome, filter panel, head, footer, scripts),
 *   - per-card payload growing (a heavier card, a new embedded field),
 *   - JS asset count/weight regressions, which stay flat-budgeted below.
 * What it deliberately tolerates:
 *   - publishing more robots.
 *
 * The card count is read from the RENDERED page, never assumed, so the gate
 * stays correct as the catalogue changes.
 */
const ROBOTS_FIXED_KB = 22; // measured 20.1
const ROBOTS_PER_CARD_KB = 4.0; // measured 3.68
const ROBOTS_JS_RAW_KB = 411; // unchanged from the flat budget

test("@perf built-route budget: /robots (scales with rendered cards)", async ({
  page,
}) => {
  const m = await measure(page, "/robots");
  // One <article class="rcard"> per rendered published robot.
  const cards = await page.locator("article.rcard").count();
  expect(cards, "/robots rendered no robot cards").toBeGreaterThan(0);

  const allowedKB = ROBOTS_FIXED_KB + ROBOTS_PER_CARD_KB * cards;
  expect(
    m.docKB,
    `/robots document ${m.docKB.toFixed(1)}kB for ${cards} rendered card(s) ` +
      `— allowance ${allowedKB.toFixed(1)}kB ` +
      `(${ROBOTS_FIXED_KB}kB fixed + ${ROBOTS_PER_CARD_KB}kB/card)`,
  ).toBeLessThanOrEqual(allowedKB);

  expect(m.jsCount, "/robots JS asset count").toBeLessThanOrEqual(JS_COUNT_MAX);
  expect(
    m.jsRawKB,
    `/robots JS total ${m.jsRawKB.toFixed(1)}kB`,
  ).toBeLessThanOrEqual(ROBOTS_JS_RAW_KB);
});

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
