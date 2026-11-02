/**
 * Spec rows show the value or the UNKNOWN state only (owner decision 2026-11-02).
 * Spec caveats stay in the catalogue and the API but are not rendered under the rows.
 * Ameca carries a weight caveat ("specification table states 'Weight 137.7 lbs | 62 kg'").
 */
import { expect, test } from "@playwright/test";

test("robot spec rows render no caveat text", async ({ page }) => {
  await page.goto("/robots/engineered-arts-ameca", { waitUntil: "domcontentloaded" });
  const specs = page.locator(".srow", { hasText: "Weight" }).first();
  await expect(specs).toContainText("62");
  await expect(page.getByText(/specification table states/i)).toHaveCount(0);
});
