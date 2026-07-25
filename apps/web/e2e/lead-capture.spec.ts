import { type Page, expect, test } from "@playwright/test";

// WS7 commercial-lead capture, driven end-to-end against the VERIFIED catalogue.
// Four capture surfaces (matched card, whole shortlist, zero-match "tell us
// anyway", Robot-Detail "Request Availability") + form behaviour: email
// validation, keyboard submit, focus handling, Escape, API-failure retains the
// form, double-submit guard, and no contact data in the URL.

async function matchedRequirement(page: Page) {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK (seeded)
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);
  await expect(page.getByRole("heading", { name: /matched/i })).toBeVisible();
}

// NOTE on the zero-match browser path (WS7 §20): the VERIFIED catalogue cannot
// render a genuine zero-match. Hard exclusions never fire on UNKNOWN attributes
// (data law), and `engineered-arts-ameca` has UNKNOWN payload / manipulation /
// autonomy and is not DISCONTINUED, so it survives every possible requirement —
// there is always >= 1 match. Forcing zero would mean fabricating or mutating
// the verified catalogue, which the data laws forbid. The zero-match capture
// path (requirement_id + robot_slugs=[] -> lead with zero robot rows, snapshot
// preserved) is therefore proven end-to-end at the API layer by backend test
// L4 (test_l4_zero_match_capture) — the exact POST body this proxy sends.

// ---- capture path 1: matched per-card -------------------------------------

test("matched per-card: card CTA -> form -> success", async ({ page }) => {
  await matchedRequirement(page);
  await page.getByRole("button", { name: /Request commercial help/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.locator("#lead-email").fill("jane@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
  // no contact data ever leaks into the URL
  expect(page.url()).not.toContain("@");
  expect(page.url()).not.toContain("jane");
});

// ---- capture path 2: whole shortlist --------------------------------------

test("shortlist: 'request help with these matches' -> form -> success", async ({ page }) => {
  await matchedRequirement(page);
  await page.getByRole("button", { name: /Request help with these matches/i }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.locator("#lead-email").fill("shortlist@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
});

// ---- capture path 4: Robot Detail "Request Availability" ------------------

test("robot detail: Request Availability -> form -> success", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.locator("#lead-email").fill("dev@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
});

// ---- form behaviour -------------------------------------------------------

test("email validation blocks submit and shows a field error", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  const trigger = page.getByRole("button", { name: /Request Availability/i }).first();
  await trigger.click();
  const dialog = page.getByRole("dialog");
  // focus enters the form on the email field
  await expect(dialog.locator("#lead-email")).toBeFocused();
  // invalid email -> error, no success
  await dialog.locator("#lead-email").fill("not-an-email");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Request received/i })).toHaveCount(0);
});

test("keyboard: Enter submits the form", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("#lead-email").fill("keyboard@example.com");
  await dialog.locator("#lead-email").press("Enter");
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
});

test("Escape closes the dialog and returns focus to the trigger", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  const trigger = page.getByRole("button", { name: /Request Availability/i }).first();
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("API failure keeps the modal open with entered data intact", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("#lead-email").fill("retry@example.com");
  await page.route("**/api/commercial-leads", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog).toBeVisible(); // not closed
  await expect(dialog.locator("#lead-email")).toHaveValue("retry@example.com"); // retained
});

test("double-submit guard fires exactly one POST", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("#lead-email").fill("once@example.com");

  let posts = 0;
  await page.route("**/api/commercial-leads", async (route) => {
    posts += 1;
    await new Promise((r) => setTimeout(r, 300)); // hold the request open
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "x", lead_status: "NEW" }),
    });
  });

  // Locate by type=submit — the label flips to "Sending…" once in flight.
  const submit = dialog.locator('button[type="submit"]');
  await submit.click();
  // while the first POST is held open the button is disabled, so a second click
  // is a no-op — exactly one POST is fired.
  await expect(submit).toBeDisabled();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
  expect(posts).toBe(1);
});
