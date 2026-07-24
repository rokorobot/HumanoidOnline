import { expect, test } from "@playwright/test";

// WS4 exit gate — Advanced Compare / Decision. Asserted against the VERIFIED
// WS2B catalogue (db/import_catalogue.py). Extends, never redesigns, the WS3
// base matrix. Facts: G1 = $13,500 PUBLIC/USD/ONE_TIME, H1 = QUOTE_ONLY (USD),
// Digit = no pricing (UNKNOWN); heights G1 132 cm / H1 180 cm; runtimes
// G1 120 min / 1X NEO 240 min; NEO purchase = $20,000 PUBLIC/USD/ONE_TIME.

test("WS4: base 2–4 compare still renders the grouped matrix (no redesign)", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1,figure-02");
  await expect(page.getByRole("heading", { name: /Comparison matrix/i })).toBeVisible();
  await expect(page.getByText("$13,500").first()).toBeVisible();
  await expect(page.getByText(/Price on request/i).first()).toBeVisible();
  await expect(page.getByText(/No confirmed pricing/i).first()).toBeVisible();
  // Frozen group headers survive.
  await expect(page.getByText(/① Commercial/).first()).toBeVisible();
  await expect(page.getByText(/② Physical/).first()).toBeVisible();
});

test("WS4: Metric/Imperial toggle is presentation-only; canonical value stays visible", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1");
  // Default metric: canonical cm shown.
  await expect(page.getByText("132 cm").first()).toBeVisible();
  await expect(page.getByText("4 ft 4 in")).toHaveCount(0);

  await page.getByRole("button", { name: "IMPERIAL" }).click();
  await expect(page).toHaveURL(/units=imperial/);
  // Imperial restatement appears...
  await expect(page.getByText("4 ft 4 in").first()).toBeVisible();
  // ...and the canonical metric value is STILL traceable on the page.
  await expect(page.getByText("132 cm").first()).toBeVisible();
});

test("WS4: UNKNOWN stays UNKNOWN and QUOTE_ONLY is never collapsed into UNKNOWN", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1,agility-digit");
  await expect(page.getByText("$13,500").first()).toBeVisible(); // G1 PUBLIC
  await expect(page.getByText(/Price on request/i).first()).toBeVisible(); // H1 QUOTE_ONLY
  await expect(page.getByText(/No confirmed pricing/i).first()).toBeVisible(); // Digit UNKNOWN
  // Explicit UNKNOWN token present (runtime known only for G1).
  await expect(page.getByText("UNKNOWN").first()).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("$0");
  expect(body).not.toContain("$90,000");
});

test("WS4: best-in-row marks a numeric leader ONLY — never categorical/leaderless rows", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,1x-neo");
  // runtime_minutes leader = 1X NEO (240 > 120): its cell is best-in-row.
  await expect(page.locator("td.cell.best", { hasText: "240" })).toBeVisible();
  // commercial_status is categorical → never best-in-row.
  await expect(page.locator("td.cell.best", { hasText: "EARLY_ACCESS" })).toHaveCount(0);
  await expect(page.locator("td.cell.best", { hasText: "COMMERCIAL" })).toHaveCount(0);
  // height_cm is numeric but leaderless → never best-in-row (NEO 167.6 cm not marked).
  await expect(page.locator("td.cell.best", { hasText: "167" })).toHaveCount(0);
});

test("WS4: comparable price marks LOWEST COMPARABLE PRICE (like-for-like set)", async ({ page }) => {
  // G1 $13,500 vs NEO $20,000 — both PURCHASE/PUBLIC/USD/ONE_TIME → comparable.
  await page.goto("/compare?ids=unitree-g1,1x-neo");
  await expect(page.getByText(/LOWEST COMPARABLE PRICE/i)).toBeVisible();
  await expect(page.locator("td.cell.best", { hasText: "$13,500" })).toBeVisible();
});

test("WS4: incomparable price → NO winner (G1 PUBLIC / H1 QUOTE_ONLY / Digit UNKNOWN)", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1,agility-digit");
  await expect(page.getByText(/LOWEST COMPARABLE PRICE/i)).toHaveCount(0);
});

test("WS4: reference robot shows factual numeric deltas; UNKNOWN stays UNKNOWN", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1&ref=unitree-g1");
  // H1 height 180 − G1 132 = +48 cm (factual delta, canonical units).
  await expect(page.getByText("+48 cm").first()).toBeVisible();
  // The reference column is labelled REFERENCE, not scored.
  await expect(page.getByText("REFERENCE").first()).toBeVisible();
  // Runtime is UNKNOWN for H1 → delta stays UNKNOWN (never fabricated).
  await expect(page.getByText(/Δ UNKNOWN/).first()).toBeVisible();
  // No qualitative verdict language.
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/Superior|Recommended|% better/i);
});

test("WS4: evidence view is inspectable; UNKNOWN facts read NO CONFIRMED FACT", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1&view=evidence");
  await expect(page.getByText(/Pricing — headline offer/i)).toBeVisible();
  // G1's price fact carries store provenance.
  await expect(page.getByText(/MANUFACTURER_STORE/i).first()).toBeVisible();
  // Neither robot has deployments → explicit NO CONFIRMED FACT.
  await expect(page.getByText(/NO CONFIRMED FACT/i).first()).toBeVisible();
  // Confidence is the raw enum ladder, never a computed/synthetic number.
  await expect(page.getByText(/No synthetic evidence score/i)).toBeVisible();
});

test("WS4: URL view state round-trips through reload and back", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1");
  await page.getByRole("button", { name: "IMPERIAL" }).click();
  await expect(page).toHaveURL(/units=imperial/);
  await expect(page.getByText("4 ft 4 in").first()).toBeVisible();

  // Survives a hard reload (server reads the canonical URL).
  await page.reload();
  await expect(page).toHaveURL(/units=imperial/);
  await expect(page.getByText("4 ft 4 in").first()).toBeVisible();

  // Survives back navigation (returns to metric).
  await page.goBack();
  await expect(page).not.toHaveURL(/units=imperial/);
  await expect(page.getByText("4 ft 4 in")).toHaveCount(0);
});

test("WS4: a device-local saved view reconstructs the canonical URL", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1");
  await page.getByRole("button", { name: "IMPERIAL" }).click();
  await expect(page).toHaveURL(/units=imperial/);

  await page.getByRole("button", { name: "SAVE VIEW" }).click();
  await page.getByPlaceholder("Name this view").fill("imperial view");
  await page.getByRole("button", { name: "SAVE", exact: true }).click();

  // Navigate to a plain (metric) compare — the imperial restatement is gone.
  await page.goto("/compare?ids=unitree-g1,unitree-h1");
  await expect(page.getByText("4 ft 4 in")).toHaveCount(0);

  // Selecting the saved view reconstructs the canonical URL.
  await page.getByRole("button", { name: /SAVED VIEWS/ }).click();
  await page.getByRole("button", { name: "imperial view", exact: true }).click();
  await expect(page).toHaveURL(/units=imperial/);
  await expect(page.getByText("4 ft 4 in").first()).toBeVisible();
});

test("WS4: an invalid/stale local save fails safely (ignored, never crashes)", async ({ page }) => {
  await page.goto("/compare?ids=unitree-g1,unitree-h1");
  // Corrupt JSON + malformed / wrong-version entries — all must be skipped.
  await page.evaluate(() => {
    window.localStorage.setItem("ho.compare.savedViews.v1", "}{not-json");
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: /Comparison matrix/i })).toBeVisible();
  await page.getByRole("button", { name: /SAVED VIEWS/ }).click();
  await expect(page.getByText(/NO SAVED VIEWS ON THIS DEVICE/i)).toBeVisible();

  // A well-formed-but-stale array of invalid entries is likewise ignored.
  await page.evaluate(() => {
    window.localStorage.setItem(
      "ho.compare.savedViews.v1",
      JSON.stringify([{ name: "x" }, { name: "y", created_at: "2020", version: 999, url: "/compare?ids=a" }, "garbage"]),
    );
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: /Comparison matrix/i })).toBeVisible();
  await page.getByRole("button", { name: /SAVED VIEWS/ }).click();
  await expect(page.getByText(/NO SAVED VIEWS ON THIS DEVICE/i)).toBeVisible();
});
