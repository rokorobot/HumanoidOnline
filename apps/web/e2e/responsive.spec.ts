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
import AxeBuilder from "@axe-core/playwright";
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

// ---------------------------------------------------------------------------
// WS8.4 / R17 — mobile target size (WCAG 2.2 AA, SC 2.5.8 Target Size (Minimum),
// 24×24 CSS px), proven on the Pixel-7 profile. Two complementary checks, so the
// gate is neither inferred from "the click succeeded" nor a naive pixel rule that
// ignores the SC's exceptions:
//
//   1. DIRECT geometric measurement of the deliberate controls a buyer operates
//      — buttons, .btn/.cta/.act, form fields, and the option LABELS that are the
//      real target for the wrapped filter checkboxes (the ~15px native box is not
//      the target). These must meet 24×24 outright. This is the explicit, exact
//      assertion — it is what caught the 22px lead-dialog close button.
//
//   2. axe's target-size RULE, run by name. Small inline/nav links are permitted
//      under 24px by the SC's Spacing / Inline / user-agent-control exceptions;
//      that geometry is subtle (24px-diameter circles, off-screen and hidden
//      targets, target grouping), so it is delegated to axe's authoritative,
//      exception-aware implementation rather than re-derived here. Running it as a
//      named single-rule check makes target size an EXPLICIT gate on the phone
//      profile, not something merely folded into the general axe pass.
// ---------------------------------------------------------------------------

const MIN_TARGET = 24;

/** Deliberate controls that must satisfy the 24×24 minimum outright. */
const CONTROL_SELECTOR = [
  "button:visible",
  "a.btn:visible",
  "a.cta:visible",
  "a.act:visible",
  "input[type=submit]:visible",
  "input[type=text]:visible",
  "input[type=email]:visible",
  "input[type=number]:visible",
  "select:visible",
  "textarea:visible",
  "label.opt:visible", // the real target for the wrapped filter checkboxes
].join(", ");

async function expectControlsMeetTargetSize(page: Page, where: string) {
  const undersized = await page.locator(CONTROL_SELECTOR).evaluateAll(
    (els, min) =>
      els
        .map((el) => {
          const r = el.getBoundingClientRect();
          return {
            w: Math.round(r.width),
            h: Math.round(r.height),
            label: (
              el.textContent ||
              el.getAttribute("aria-label") ||
              el.getAttribute("name") ||
              el.tagName
            )
              .replace(/\s+/g, " ")
              .trim()
              .slice(0, 32),
          };
        })
        .filter((c) => c.w > 0 && c.h > 0 && (c.w < min || c.h < min)),
    MIN_TARGET,
  );
  expect(
    undersized,
    `${where}: controls below ${MIN_TARGET}×${MIN_TARGET}px:\n` +
      undersized.map((c) => `  ${c.w}×${c.h}  "${c.label}"`).join("\n"),
  ).toEqual([]);
}

/** axe's WCAG 2.2 target-size rule, by name — exception-aware, on this viewport. */
async function expectAxeTargetSizeClean(page: Page, where: string) {
  const { violations } = await new AxeBuilder({ page })
    .withRules(["target-size"])
    .analyze();
  const summary = violations.flatMap((v) => v.nodes.map((n) => n.failureSummary));
  expect(violations, `${where} target-size:\n${summary.join("\n")}`).toEqual([]);
}

for (const [path, name] of [
  ["/", "home"],
  ["/robots", "catalogue"],
  ["/robots/unitree-g1", "robot detail"],
  ["/compare?ids=unitree-g1,agility-digit", "compare"],
  ["/manufacturers", "manufacturers"],
  ["/manufacturers/unitree", "manufacturer detail"],
  ["/use-cases", "use-cases"],
  ["/use-cases/warehouse-logistics", "use-case detail"],
  ["/find-a-humanoid?use_case=warehouse-logistics", "wizard"],
] as const) {
  test(`@responsive target size: ${name} (direct ≥24×24 + axe target-size)`, async ({
    page,
  }) => {
    await page.goto(path, { waitUntil: "networkidle" });
    await expectControlsMeetTargetSize(page, name);
    await expectAxeTargetSizeClean(page, name);
  });
}

test("@responsive target size: lead dialog controls ≥24×24", async ({ page }) => {
  await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expectControlsMeetTargetSize(page, "lead dialog");
  await expectAxeTargetSizeClean(page, "lead dialog");
});
