import { expect, test } from "@playwright/test";

// MEDIA-01 verified imagery in the browser. Against the verified catalogue no
// robot_image rows are populated yet (a robot only gets a real image once its
// identity + rights are honestly cleared), so Robot Detail must render the
// explicit IMAGE_UNAVAILABLE state — never a generated/placeholder fill. The
// with-image gallery path + the display-eligibility gate are covered by the
// backend matrix (test_robot_images.py).

test("robot detail shows IMAGE_UNAVAILABLE when no verified image is cleared", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await expect(page.getByText("IMAGE UNAVAILABLE")).toBeVisible();
  // and never an invented image in the identity gallery
  await expect(page.locator(".ro-gallery__img")).toHaveCount(0);
});
