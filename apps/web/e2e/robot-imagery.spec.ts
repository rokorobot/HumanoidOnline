import { expect, test } from "@playwright/test";

// MEDIA-01 verified imagery in the browser (against the verified catalogue).
//
// The contract is not "every published robot has a photo" -- the catalogue
// legitimately grows to include real, identity-verified robots that are not
// yet photographed, and that is an honest state, not a defect. The actual
// contract (RobotCard's and RobotGallery's own comments) is narrower and does
// not change as the catalogue's photo coverage does:
//   - governed display-eligible imagery exists -> render the real image;
//   - none exists -> render the explicit IMAGE_UNAVAILABLE state;
//   - never an invented/placeholder/generated picture in between;
//   - the catalogue card and the detail page agree about which case applies.
// So this suite derives its expectations from the live listing rather than
// hardcoding today's count of imageless robots, which would go stale the next
// time the catalogue's photo coverage changes in either direction.

test("robot detail shows the verified gallery + provenance (real image, no invented art)", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await expect(page.locator(".ro-gallery__img")).toHaveCount(1);
  await expect(page.getByText(/Official ✓|Verified ✓/)).toBeVisible();
  await expect(page.getByText(/Source:/)).toBeVisible();
  await expect(page.getByText("IMAGE UNAVAILABLE")).toHaveCount(0);
});

test("catalogue cards render exactly one governed image state, never both or neither", async ({ page }) => {
  await page.goto("/robots");
  const cards = page.locator(".rcard");
  const cardCount = await cards.count();
  expect(cardCount).toBeGreaterThan(0);

  for (let i = 0; i < cardCount; i++) {
    const card = cards.nth(i);
    const hasImage = await card.locator(".rcard-media__img").count();
    const hasUnavailable = await card.locator(".rcard-media__unavailable").count();
    // Exactly one of the two states -- never a card with both, and never a
    // card with neither (which would mean some third, unaccounted-for state).
    expect(hasImage + hasUnavailable).toBe(1);
  }

  // Every rendered image is a real, non-empty source -- never a blank/invented
  // fallback masquerading as a real photo.
  const srcs = await page.locator(".rcard-media__img").evaluateAll((imgs) =>
    imgs.map((img) => (img as HTMLImageElement).getAttribute("src")),
  );
  for (const src of srcs) {
    expect(src).toBeTruthy();
  }
});

test("listing and detail page agree on image truth for a photographed robot", async ({ page }) => {
  await page.goto("/robots");
  const withImage = page.locator(".rcard").filter({ has: page.locator(".rcard-media__img") }).first();
  await expect(withImage).toHaveCount(1);
  const href = await withImage.locator(".rcard-media").getAttribute("href");
  expect(href).toBeTruthy();

  await page.goto(href!);
  await expect(page.locator(".ro-gallery__img")).toHaveCount(1);
  await expect(page.getByText("IMAGE UNAVAILABLE")).toHaveCount(0);
});

test("listing and detail page agree on image truth for an unphotographed robot", async ({ page }) => {
  await page.goto("/robots");
  const unavailable = page.locator(".rcard").filter({ has: page.locator(".rcard-media__unavailable") }).first();
  const count = await unavailable.count();
  // Skip rather than fail if the catalogue happens to be fully photographed --
  // the absence of this state is not itself a MEDIA-01 violation.
  test.skip(count === 0, "no unphotographed robot currently published");

  const href = await unavailable.locator(".rcard-media").getAttribute("href");
  expect(href).toBeTruthy();

  await page.goto(href!);
  await expect(page.locator(".ro-gallery__img")).toHaveCount(0);
  await expect(page.getByText("IMAGE UNAVAILABLE")).toBeVisible();
});
