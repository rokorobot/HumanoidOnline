/**
 * DR-I1 — /insights journey against the verified catalogue (Digit 5 is published there).
 * Untagged: runs in the web-integration suite.
 */
import { expect, test } from "@playwright/test";

test("/insights → Digit 5 Europe article → link to /robots/agility-digit-5", async ({ page }) => {
  await page.goto("/insights", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Insights");
  await page.getByRole("link", { name: /Agility Digit 5 plans to enter Europe in 2027/ }).click();
  await expect(page).toHaveURL(/\/insights\/agility-digit-5-europe-2027$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Digit 5 plans to enter Europe");
  await expect(page.getByTestId("insight-sources").getByRole("link")).toHaveCount(3);
  await page.getByTestId("insight-article").getByRole("link", { name: "Agility Digit 5", exact: true }).first().click();
  await expect(page).toHaveURL(/\/robots\/agility-digit-5$/);
});
