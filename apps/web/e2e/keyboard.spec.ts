/**
 * WS8.4 / R17 — keyboard-only journeys + focus behaviour.
 *
 * The axe suite proves *detectable* rule violations; it CANNOT prove that the
 * meaningful journeys are operable without a pointer, nor that focus is managed
 * correctly. These two obligations of the frozen R17 gate are proven here by
 * driving the UI with the keyboard alone — Tab / Shift+Tab / Enter / Escape —
 * and asserting focus lands where a keyboard/AT user needs it.
 *
 * Untagged, so it runs on the desktop-chromium project only: keyboard traversal
 * is the desktop/assistive-tech surface (the Pixel-7 project has no Tab order to
 * exercise). Target size — the mobile obligation — lives in responsive.spec.ts.
 */
import { expect, test, type Page } from "@playwright/test";

/** Snapshot of the current focus for readable assertions and predicates. */
async function focused(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return null;
    return {
      tag: el.tagName,
      id: el.id || null,
      text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60),
      aria: el.getAttribute("aria-label"),
      insideDialog: !!el.closest('[role="dialog"]'),
    };
  });
}

/**
 * Press Tab (or Shift+Tab) up to `max` times until `match` accepts the focused
 * element. Returns true if reached — a keyboard user could get there. Bounded so
 * a broken tab order fails instead of hanging.
 */
async function tabUntil(
  page: Page,
  match: (f: NonNullable<Awaited<ReturnType<typeof focused>>>) => boolean,
  { max = 40, shift = false } = {},
): Promise<boolean> {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press(shift ? "Shift+Tab" : "Tab");
    const f = await focused(page);
    if (f && match(f)) return true;
  }
  return false;
}

test.describe("@keyboard keyboard-only journeys", () => {
  test("skip link is the first tab stop and moves focus into the main landmark", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    // First Tab from a fresh document lands on the skip link.
    await page.keyboard.press("Tab");
    await expect(page.locator("a.skip-link")).toBeFocused();
    // Activating it MOVES focus to <main id="main-content"> (not just scrolls).
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("primary navigation is reachable and operable with the keyboard alone", async ({
    page,
  }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    // Reach the "Compare" primary-nav link purely by tabbing, then activate it
    // with Enter — a real keyboard-only navigation, no pointer involved.
    const reached = await tabUntil(
      page,
      (f) => f.tag === "A" && /^Compare$/i.test(f.text),
    );
    expect(reached, "Compare nav link never received keyboard focus").toBe(true);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/compare/);
  });

  test("buyer can open the commercial lead dialog and submit via the keyboard", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    // Tab to the "Request Availability" CTA and open it with Enter.
    const reached = await tabUntil(page, (f) => /Request Availability/i.test(f.text));
    expect(reached, "Request Availability never received keyboard focus").toBe(true);
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // Focus entered the dialog on the email field.
    await expect(page.locator("#lead-email")).toBeFocused();

    // Fill and submit entirely from the keyboard (Enter submits the form).
    await page.keyboard.type("keyboard-journey@example.com");
    await page.keyboard.press("Enter");
    // Governed result: the capture confirmation (a commercial_lead now exists).
    await expect(dialog.getByText(/Request received|received/i)).toBeVisible();
  });
});

test.describe("focus behaviour", () => {
  test("lead dialog traps focus while open (Tab and Shift+Tab stay inside)", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.locator("#lead-email")).toBeFocused();

    // Tab many times: focus must never escape the dialog (WCAG 2.4.3 / 2.1.2).
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("Tab");
      const f = await focused(page);
      expect(f?.insideDialog, `Tab #${i + 1} escaped the dialog`).toBe(true);
    }
    // And in reverse.
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("Shift+Tab");
      const f = await focused(page);
      expect(f?.insideDialog, `Shift+Tab #${i + 1} escaped the dialog`).toBe(true);
    }
  });

  test("Escape closes the dialog and returns focus to the opener", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    const opener = page.getByRole("button", { name: /Request Availability/i }).first();
    await opener.click();
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    // Focus is restored to the trigger, not lost to <body>.
    await expect(opener).toBeFocused();
  });

  test("a submitted invalid field takes focus so the error is discoverable", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    // Submit empty: the email field is invalid, gets aria-invalid + an alert, and
    // receives focus so a keyboard user is taken straight to the problem.
    await dialog.getByRole("button", { name: /Send request/i }).click();
    const email = page.locator("#lead-email");
    await expect(email).toBeFocused();
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await expect(dialog.getByRole("alert")).toBeVisible();
  });
});
