import { expect, test } from "@playwright/test";

// Corporate branding: the footer links "Humanoid.Company" to the canonical
// corporate website, in the same tab, consistently across pages.
//
// The footer carries TWO deliberate brand links, in two different bands:
//   .foot-brand  (upper)  "· A Humanoid.Company project"
//   .foot-legal  (lower)  "HumanoidOnline is a Humanoid.Company brand."
// Both were ratified with the dark-register footer. An earlier version of this
// spec predates the legal band and matched `footer.foot a.foot-brand-link`,
// which now resolves to both anchors and fails Playwright strict mode.
//
// The locators below are band-scoped rather than `.first()`/`.nth()` so the test
// encodes the intended STRUCTURE: each band must carry exactly one brand link.
// A third link, a moved link, or a lost band therefore fails here instead of
// being silently absorbed by an index.

const UPPER = "footer.foot .foot-brand a.foot-brand-link";
const LOWER = "footer.foot .foot-legal a.foot-brand-link";
const CORPORATE_URL = "https://humanoid.company/";

test("footer links Humanoid.Company to the corporate website (same tab)", async ({
  page,
}) => {
  await page.goto("/");

  const upper = page.locator(UPPER);
  const lower = page.locator(LOWER);

  // Exactly one per band — the structural assertion.
  await expect(upper).toHaveCount(1);
  await expect(lower).toHaveCount(1);

  await expect(upper).toHaveText("Humanoid.Company");
  await expect(upper).toHaveAttribute("href", CORPORATE_URL);
  await expect(upper).not.toHaveAttribute("target", "_blank");

  await expect(lower).toHaveText("Humanoid.Company");
  await expect(lower).toHaveAttribute("href", CORPORATE_URL);
  await expect(lower).not.toHaveAttribute("target", "_blank");

  // Both bands point at the same canonical corporate site, and nothing else in
  // the footer claims the brand-link class.
  await expect(page.locator("footer.foot a.foot-brand-link")).toHaveCount(2);
});

test("footer brand link appears consistently on other pages", async ({ page }) => {
  await page.goto("/robots");

  await expect(page.locator(UPPER)).toHaveAttribute("href", CORPORATE_URL);
  await expect(page.locator(LOWER)).toHaveAttribute("href", CORPORATE_URL);
});
