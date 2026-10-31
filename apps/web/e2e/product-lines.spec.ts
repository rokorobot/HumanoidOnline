/**
 * DR-L1 (b) — product-line pages against the verified catalogue (CI imports every
 * db/catalogue file, including product_lines.json). Untagged: desktop project.
 */
import { expect, test } from "@playwright/test";

test("/lines/unitree-g1 renders the H1, the direct answer first and links to its editions", async ({ page }) => {
  await page.goto("/lines/unitree-g1", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveTitle(/^Unitree G1: .*Specs & Editions/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Unitree G1");
  const answer = page.getByTestId("direct-answer");
  await expect(answer).toContainText("Unitree G1 is sold in 2 published editions:");
  await expect(answer).toContainText("Standing height:");
  const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
  expect(canonical).toMatch(/\/lines\/unitree-g1$/);
  const table = page.getByTestId("edition-table");
  await expect(table.locator("tbody tr")).toHaveCount(2);
  await expect(table.locator('a[href="/robots/unitree-g1"]')).toBeVisible();
  await expect(table.locator('a[href="/robots/unitree-g1-edu-plus-u2"]')).toBeVisible();
  // ProductGroup JSON-LD with one variant per edition and no offers.
  const ld = JSON.parse((await page.locator('script[type="application/ld+json"]').first().textContent()) ?? "{}");
  const group = ld["@graph"].find((n: { "@type": string }) => n["@type"] === "ProductGroup");
  expect(group.hasVariant).toHaveLength(2);
  expect(JSON.stringify(ld)).not.toContain("offers");
});

test("an unknown line is a 404", async ({ page }) => {
  const res = await page.goto("/lines/no-such-line", { waitUntil: "domcontentloaded" });
  expect(res?.status()).toBe(404);
});

test("a member robot links up to its line; sitemap and llms.txt list the line", async ({ page, request }) => {
  await page.goto("/robots/unitree-g1", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("product-line-link")).toBeVisible();
  const sitemap = await (await request.get("/sitemap.xml")).text();
  expect(sitemap).toMatch(/\/lines\/unitree-g1</);
  expect((sitemap.match(/\/lines\//g) ?? []).length).toBe(5);
  const llms = await (await request.get("/llms.txt")).text();
  expect(llms).toContain("## Product lines (published, canonical)");
  expect(llms).toMatch(/\/lines\/booster-k1/);
});
