import { expect, test } from "@playwright/test";

// Integration truths asserted against the VERIFIED WS2B catalogue (loaded via
// db/import_catalogue.py). These would FAIL against seed data or hardcoded
// mock values — that is the point of this gate.

test("home renders live market-snapshot counts (not illustrative)", async ({ page }) => {
  await page.goto("/");
  // Hero claim is fixed and exact.
  await expect(page.getByRole("heading", { name: /Find the right/i })).toBeVisible();
  // 7 verified robots are tracked; the seed set (20) must never appear.
  await expect(page.getByText("Humanoids tracked")).toBeVisible();
  const snapshot = page.locator(".snap", { hasText: "Humanoids tracked" });
  await expect(snapshot.locator(".num")).toHaveText("7");
  await expect(page.locator("body")).not.toContainText("20 PLATFORMS TRACKED");
});

test("catalogue: G1 shows $13,500 PUBLIC, never the illustrative $16,000", async ({ page }) => {
  await page.goto("/robots");
  await expect(page.getByText("$13,500")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("$16,000");
});

test("robot detail unitree-g1: $13,500 PUBLIC", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await expect(page.getByText("$13,500").first()).toBeVisible();
  // PUBLIC price_type surfaced verbatim in the pricing table context.
  await expect(page.locator("body")).toContainText("PUBLIC");
  await expect(page.locator("body")).not.toContainText("$16,000");
});

test("unitree-h1: PRICE ON REQUEST / QUOTE_ONLY, and never $90,000", async ({ page }) => {
  await page.goto("/robots/unitree-h1");
  await expect(page.getByText(/Price on request/i).first()).toBeVisible();
  await expect(page.locator("body")).toContainText("QUOTE_ONLY");
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("$90,000");
  expect(body).not.toContain("90,000");
});

test("figure-02 is DISCONTINUED", async ({ page }) => {
  await page.goto("/robots/figure-02");
  await expect(page.getByText("DISCONTINUED").first()).toBeVisible();
});

test("unknown-price robot (agility-digit) shows explicit unknown, never $0/0/unavailable", async ({
  page,
}) => {
  await page.goto("/robots/agility-digit");
  await expect(page.getByText("No confirmed pricing").first()).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("$0");
  expect(body.toLowerCase()).not.toContain("unavailable");
  // The price cell must not read a bare "0".
  await expect(page.locator(".prow .val.unknown").first()).toBeVisible();
});

test("QUOTE_ONLY and UNKNOWN render as visibly different states on the catalogue", async ({
  page,
}) => {
  await page.goto("/robots");
  // Distinct labels...
  await expect(page.getByText("PRICE ON REQUEST").first()).toBeVisible();
  await expect(page.getByText("NO PRICE DATA").first()).toBeVisible();
  // ...backed by distinct state classes (caution vs unknown/grey).
  await expect(page.locator(".price.quote").first()).toBeVisible();
  await expect(page.locator(".price.unknown").first()).toBeVisible();
});

test("filters are URL-addressable: DISCONTINUED filter isolates figure-02", async ({
  page,
}) => {
  await page.goto("/robots?commercial_status=DISCONTINUED");
  await expect(page.getByText("Figure 02").first()).toBeVisible();
  // G1 (COMMERCIAL) must be filtered out.
  await expect(page.locator(".grid")).not.toContainText("$13,500");
});

test("compare renders a matrix with QUOTE_ONLY, PUBLIC and UNKNOWN kept distinct", async ({
  page,
}) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1,figure-02");
  await expect(page.getByRole("heading", { name: /Comparison matrix/i })).toBeVisible();
  await expect(page.getByText("$13,500").first()).toBeVisible();
  await expect(page.getByText(/Price on request/i).first()).toBeVisible();
  await expect(page.getByText("No confirmed pricing").first()).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("$16,000");
  expect(body).not.toContain("$90,000");
});

test("robot detail 404s for an unknown slug", async ({ page }) => {
  const res = await page.goto("/robots/does-not-exist");
  expect(res?.status()).toBe(404);
  await expect(page.getByText(/NO SUCH RECORD/i)).toBeVisible();
});
