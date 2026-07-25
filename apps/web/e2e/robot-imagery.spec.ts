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
  await page.goto("/robots/apptronik-apollo");
  await expect(page.getByText("IMAGE UNAVAILABLE")).toBeVisible();
  await expect(page.locator(".ro-gallery__img")).toHaveCount(0);
});
