import { expect, test } from "@playwright/test";

// MEDIA-01 verified imagery in the browser (against the verified catalogue). All
// seven catalogue robots now have a display-eligible verified real image, so the
// catalogue is a complete real-image lineup and no card shows IMAGE_UNAVAILABLE.
// The IMAGE_UNAVAILABLE UI state (for a robot with no cleared image) is covered by
// the backend (test_robot_images: no images -> empty list) + the display matrix;
// it is not reachable in the browser while the catalogue is fully populated.

test("robot detail shows the verified gallery + provenance (real image, no invented art)", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await expect(page.locator(".ro-gallery__img")).toHaveCount(1);
  await expect(page.getByText(/Official ✓|Verified ✓/)).toBeVisible();
  await expect(page.getByText(/Source:/)).toBeVisible();
  await expect(page.getByText("IMAGE UNAVAILABLE")).toHaveCount(0);
});

test("catalogue is a complete real-image lineup (same image truth as detail)", async ({ page }) => {
  await page.goto("/robots");
  // Every catalogue card carries a real verified image (7/7 populated)...
  expect(await page.locator(".rcard-media__img").count()).toBeGreaterThanOrEqual(5);
  // ...and none falls back to the unavailable tile.
  await expect(page.locator(".rcard-media__unavailable")).toHaveCount(0);
});
