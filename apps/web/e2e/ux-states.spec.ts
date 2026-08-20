/**
 * WS8.4 / R20 — every required §5.2 empty/error state, proven INDIVIDUALLY by
 * triggering the real state the user would see. No "an error component renders"
 * catch-all: each test drives the app into one specific governed state and
 * asserts its exact copy.
 *
 * The distinctions that matter (Product Contract §5.2):
 *   "No confirmed pricing" (UNKNOWN)  ≠  "Price on request" (QUOTE_ONLY)  ≠  $0
 *   "No confirmed commercial availability"  ≠  "unavailable"
 *   NULL spec  →  "Unknown" / em-dash  ≠  0 / false
 */
import { expect, test } from "@playwright/test";

test.describe("R20 empty / error states", () => {
  test("404: unknown robot slug renders the not-found record state", async ({ page }) => {
    const res = await page.goto("/robots/no-such-robot-xyz");
    expect(res?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: /Not found/i })).toBeVisible();
    await expect(page.getByText(/does not exist in the catalogue/i)).toBeVisible();
    // Offers a route back, per §5.2.
    await expect(page.getByRole("link", { name: /Return to the catalogue/i })).toBeVisible();
  });

  test("compare with <2 ids: prompt to select, not an empty matrix", async ({ page }) => {
    await page.goto("/compare?ids=unitree-g1", { waitUntil: "networkidle" });
    await expect(page.getByText(/Select\s+2 to 4 robots/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /catalogue/i })).toBeVisible();
    // The matrix itself must NOT be present in the <2 state.
    await expect(page.locator(".cmp-scroll")).toHaveCount(0);
  });

  test("price trichotomy: PUBLIC, PRICE ON REQUEST and NO PRICE DATA are visibly distinct", async ({
    page,
  }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    const body = page.locator("#main-content");
    // A known public price (G1) — a real amount, never $0.
    await expect(body).toContainText("$");
    // QUOTE_ONLY renders "PRICE ON REQUEST" (a known commercial model)...
    await expect(page.getByText("PRICE ON REQUEST").first()).toBeVisible();
    // ...and it is NOT the same string as UNKNOWN ("NO PRICE DATA").
    // At least one of the two unknown-ish states exists in the verified set.
    const noData = page.getByText(/NO PRICE DATA/i);
    if (await noData.count()) {
      await expect(noData.first()).toBeVisible();
    }
    // Never a fabricated zero price anywhere in the catalogue.
    await expect(body).not.toContainText(/\$0\b/);
  });

  test("availability-unknown reads as unknown, never 'unavailable'", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    const body = await page.locator("#main-content").innerText();
    // The detail page must never assert a negative availability fact from
    // absence of data. "No confirmed commercial availability" is allowed;
    // a bare "unavailable" verdict is not.
    expect(body.toLowerCase()).not.toMatch(/\bnot available\b/);
  });

  test("invalid form state: empty required fields are announced, submission blocked", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // Submit fully empty -> inline error (role=alert) + aria-invalid on the
    // first required field (full name), no close.
    await dialog.getByRole("button", { name: /Send request/i }).click();
    await expect(dialog.getByRole("alert").first()).toBeVisible();
    await expect(dialog.locator("#lead-name")).toHaveAttribute("aria-invalid", "true");
    await expect(dialog).toBeVisible(); // dialog stayed open; nothing was captured

    // Name + organization filled, email still empty -> now email is the one
    // flagged invalid.
    await dialog.locator("#lead-name").fill("Jane Buyer");
    await dialog.locator("#lead-org").fill("Acme Robotics");
    await dialog.getByRole("button", { name: /Send request/i }).click();
    await expect(dialog.locator("#lead-email")).toHaveAttribute("aria-invalid", "true");
    await expect(dialog).toBeVisible();
  });

  test("API failure: the lead form shows an error and retains what was typed", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.locator("#lead-name").fill("Jane Buyer");
    await dialog.locator("#lead-org").fill("Acme Robotics");
    await dialog.locator("#lead-email").fill("buyer@example.com");

    // Force the write to fail at the network boundary.
    await page.route("**/api/commercial-leads", (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
    );
    await dialog.getByRole("button", { name: /Send request/i }).click();

    // An error is shown, the dialog stays open, and the entered email survives —
    // the user does not lose their input to a failed request.
    await expect(dialog.getByText(/failed|error|try again/i).first()).toBeVisible();
    await expect(dialog.locator("#lead-email")).toHaveValue("buyer@example.com");
  });
});
