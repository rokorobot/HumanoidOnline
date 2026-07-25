import { expect, test } from "@playwright/test";

// Corporate branding: the footer links "Humanoid.Company" to the canonical
// corporate website, in the same tab, consistently across pages.

test("footer links Humanoid.Company to the corporate website (same tab)", async ({ page }) => {
  await page.goto("/");
  const link = page.locator("footer.foot a.foot-brand-link");
  await expect(link).toHaveText("Humanoid.Company");
  await expect(link).toHaveAttribute("href", "https://humanoid.company/");
  await expect(link).not.toHaveAttribute("target", "_blank");
});

test("footer brand link appears consistently on other pages", async ({ page }) => {
  await page.goto("/robots");
  await expect(page.locator("footer.foot a.foot-brand-link")).toHaveAttribute(
    "href",
    "https://humanoid.company/",
  );
});
