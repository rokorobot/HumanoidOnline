import { expect, test } from "@playwright/test";

// MEDIA-01 verified imagery in the browser (against the verified catalogue).
// Robots with a cleared official image render the verified gallery + provenance;
// robots without an honestly-clearable image render the explicit
// IMAGE_UNAVAILABLE state — never a generated/placeholder fill. The
// display-eligibility gate itself is covered by the backend matrix
// (test_robot_images.py).

test("robot with a cleared official image shows the verified gallery + provenance", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  // a real image element is rendered from the display-eligible record...
  await expect(page.locator(".ro-gallery__img")).toHaveCount(1);
  // ...framed with an Official/Verified badge and an attributed source link.
  await expect(page.getByText(/Official ✓|Verified ✓/)).toBeVisible();
  await expect(page.getByText(/Source:/)).toBeVisible();
  // and NOT the unavailable state
  await expect(page.getByText("IMAGE UNAVAILABLE")).toHaveCount(0);
});

test("robot without a cleared image shows IMAGE_UNAVAILABLE (never an invented image)", async ({ page }) => {
  // figure-02 is retired by Figure; no clean OEM front full-body could be honestly
  // sourced, so it stays IMAGE_UNAVAILABLE rather than a guess.
  await page.goto("/robots/figure-02");
  await expect(page.getByText("IMAGE UNAVAILABLE")).toBeVisible();
  await expect(page.locator(".ro-gallery__img")).toHaveCount(0);
});

test("catalogue cards use the same image truth: real images + honest unavailable tiles", async ({ page }) => {
  await page.goto("/robots");
  // populated robots render a real card image...
  await expect(page.locator(".rcard-media__img").first()).toBeVisible();
  expect(await page.locator(".rcard-media__img").count()).toBeGreaterThanOrEqual(1);
  // ...and robots without a cleared image render the explicit unavailable tile.
  expect(await page.locator(".rcard-media__unavailable").count()).toBeGreaterThanOrEqual(1);
});
