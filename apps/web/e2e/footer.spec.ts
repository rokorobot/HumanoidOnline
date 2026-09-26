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

test("footer lower band: identity/copyright left, secondary nav right", async ({ page }) => {
  await page.goto("/");
  const band = page.locator("footer.foot .foot-legal");
  const id = band.locator(".foot-id");
  const nav = page.getByRole("contentinfo").getByRole("navigation", { name: "Footer" });

  await expect(id).toContainText("© 2026 Humanoid Company. All rights reserved.");
  // The footer nav lives in the same band as the copyright, not above it.
  await expect(band.locator("nav.foot-nav")).toHaveCount(1);
  const labels = (await nav.getByRole("link").allTextContents()).map((t) => t.trim());
  expect(labels).toEqual(["Robots", "Compare", "Manufacturers", "Use Cases", "About", "Contact"]);
  // Plain links — the orange CTA stays in the top navigation only.
  await expect(nav.locator("a.cta")).toHaveCount(0);

  // Desktop: identity block on the left, navigation on the right.
  const vw = page.viewportSize()?.width ?? 0;
  if (vw >= 900) {
    const idBox = (await id.boundingBox())!;
    const navBox = (await nav.boundingBox())!;
    expect(navBox.x).toBeGreaterThan(idBox.x + idBox.width);
  }
});
