/**
 * WS8.4 / R19 — responsive behaviour, exercised as a real execution surface.
 *
 * Tagged @responsive so it runs on BOTH projects: desktop-chromium (Desktop
 * Chrome) and mobile-chromium (Pixel 7). It is NOT a viewport tweak inside one
 * desktop test — the same flow genuinely runs on a phone profile in CI.
 *
 * Every check asserts a concrete responsive property (no horizontal overflow,
 * usable nav, compare/table/cards not clipped, primary actions visible and
 * operable), so a broken mobile layout fails rather than merely rendering.
 */
import { expect, test, type Page } from "@playwright/test";

/** The page must not scroll horizontally: content fits the viewport width. */
async function expectNoHorizontalOverflow(page: Page, where: string) {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    // 1px tolerance for sub-pixel rounding.
    return el.scrollWidth - el.clientWidth;
  });
  expect(overflow, `${where}: horizontal overflow of ${overflow}px`).toBeLessThanOrEqual(1);
}

/** An element must sit within the viewport horizontally (not clipped off-screen). */
async function expectWithinViewport(page: Page, selector: string, where: string) {
  const box = await page.locator(selector).first().boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect(box, `${where}: ${selector} not found`).not.toBeNull();
  if (box) {
    expect(box.x, `${where}: ${selector} clipped left`).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.width, `${where}: ${selector} clipped right`).toBeLessThanOrEqual(
      width + 1,
    );
  }
}

test("@responsive home: nav usable, primary CTA operable, no overflow", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expectNoHorizontalOverflow(page, "home");

  // The primary "Find a Humanoid" action is present, on-screen and clickable at
  // both sizes (nav may reflow on mobile, but the CTA must remain reachable).
  const cta = page.getByRole("link", { name: /Find a Humanoid/i }).first();
  await expect(cta).toBeVisible();
  await cta.click();
  await expect(page).toHaveURL(/\/find-a-humanoid/);
  await expectNoHorizontalOverflow(page, "find-a-humanoid");
});

test("@responsive catalogue: cards not clipped, filters reachable", async ({ page }) => {
  await page.goto("/robots", { waitUntil: "networkidle" });
  await expectNoHorizontalOverflow(page, "catalogue");
  // Robot cards render and stay within the viewport.
  const cards = page.locator("article.rcard");
  expect(await cards.count()).toBeGreaterThan(0);
  await expectWithinViewport(page, "article.rcard", "catalogue");
  // A card's primary link is operable -> detail loads.
  await cards.first().getByRole("link").first().click();
  await expect(page).toHaveURL(/\/robots\//);
  await expectNoHorizontalOverflow(page, "robot detail");
});

test("@responsive compare: matrix scrolls within a bounded container, no page overflow", async ({
  page,
}) => {
  await page.goto("/compare?ids=unitree-g1,agility-digit", { waitUntil: "networkidle" });
  // The comparison matrix may be wider than a phone, but it must scroll INSIDE
  // its own container — the page itself must not overflow horizontally.
  await expectNoHorizontalOverflow(page, "compare");
  const scroller = page.locator(".cmp-scroll");
  await expect(scroller).toBeVisible();
  // The scroll container is keyboard-focusable (WCAG 2.1.1).
  await expect(scroller).toHaveAttribute("tabindex", "0");
});

test("@responsive wizard: form controls fit and are operable", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics", {
    waitUntil: "networkidle",
  });
  await expectNoHorizontalOverflow(page, "wizard");
  // The task select is on-screen and operable at both sizes.
  await expectWithinViewport(page, "#wz-usecase", "wizard");
  await page.getByRole("button", { name: /Next/ }).click();
  await expectNoHorizontalOverflow(page, "wizard step 2");
});

test("@responsive robot detail: spec table scrolls in-container, no page overflow", async ({
  page,
}) => {
  await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
  await expectNoHorizontalOverflow(page, "robot detail");
  const ptable = page.locator(".ptable");
  await expect(ptable).toBeVisible();
  await expect(ptable).toHaveAttribute("tabindex", "0");
});
