import { type Locator, type Page, expect, test } from "@playwright/test";

// WS7 commercial-lead capture, driven end-to-end against the VERIFIED catalogue.
// Four capture surfaces (matched card, whole shortlist, zero-match "tell us
// anyway", Robot-Detail "Request Availability") + form behaviour: required-field
// validation (name/organization/email), keyboard submit, focus handling, Escape,
// API-failure retains the form, double-submit guard, and no contact data in the
// URL.

async function matchedRequirement(page: Page) {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK (seeded)
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  // CONTACT: buyer identity is now required before REVIEW is reachable.
  await page.locator("#wz-contact-name").fill("Test Buyer");
  await page.locator("#wz-contact-org").fill("Test Org");
  await page.locator("#wz-contact-email").fill("buyer@example.com");
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);
  await expect(page.getByRole("heading", { name: /matched/i })).toBeVisible();
}

// Fills the three required contact fields (full name, organization, email) —
// every successful-submission test needs all three since the API now rejects
// a lead missing any of them.
async function fillRequiredContact(dialog: Locator, email: string) {
  await dialog.locator("#lead-name").fill("Jane Buyer");
  await dialog.locator("#lead-org").fill("Acme Robotics");
  await dialog.locator("#lead-email").fill(email);
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
  await fillRequiredContact(dialog, "jane@example.com");
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
  await fillRequiredContact(dialog, "shortlist@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
});

// ---- capture path 4: Robot Detail "Request Availability" ------------------

test("robot detail: Request Availability -> form -> success", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await fillRequiredContact(dialog, "dev@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
});

// ---- form behaviour -------------------------------------------------------

test("required-field validation blocks submit: name, then organization, then email", async ({
  page,
}) => {
  await page.goto("/robots/unitree-g1");
  const trigger = page.getByRole("button", { name: /Request Availability/i }).first();
  await trigger.click();
  const dialog = page.getByRole("dialog");
  // focus enters the form on the FIRST required field: full name
  await expect(dialog.locator("#lead-name")).toBeFocused();

  // all three blank -> blocked on name first
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.getByRole("alert").first()).toBeVisible();
  await expect(dialog.locator("#lead-name")).toBeFocused();
  await expect(page.getByRole("heading", { name: /Request received/i })).toHaveCount(0);

  // name filled, organization still blank -> blocked on organization next
  await dialog.locator("#lead-name").fill("Jane Buyer");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.locator("#lead-org")).toBeFocused();
  await expect(page.getByRole("heading", { name: /Request received/i })).toHaveCount(0);

  // name + organization filled, invalid email -> blocked on email, no success
  await dialog.locator("#lead-org").fill("Acme Robotics");
  await dialog.locator("#lead-email").fill("not-an-email");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.locator("#lead-email")).toBeFocused();
  await expect(page.getByRole("heading", { name: /Request received/i })).toHaveCount(0);
});

test("keyboard: Enter submits the form", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await fillRequiredContact(dialog, "keyboard@example.com");
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
  await fillRequiredContact(dialog, "retry@example.com");
  await page.route("**/api/commercial-leads", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog).toBeVisible(); // not closed
  await expect(dialog.locator("#lead-email")).toHaveValue("retry@example.com"); // retained
  await expect(dialog.locator("#lead-name")).toHaveValue("Jane Buyer"); // retained
});

test("double-submit guard fires exactly one POST", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await fillRequiredContact(dialog, "once@example.com");

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

test("telephone is optional: submission succeeds without it and persists when supplied", async ({
  page,
}) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await fillRequiredContact(dialog, "phone-optional@example.com");
  // telephone deliberately left blank
  let body: Record<string, unknown> | undefined;
  await page.route("**/api/commercial-leads", async (route) => {
    body = route.request().postDataJSON();
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "x", lead_status: "NEW" }),
    });
  });
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
  expect(body).not.toHaveProperty("contact_phone");
});

test("telephone is included in the POST body when supplied", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  await page.getByRole("button", { name: /Request Availability/i }).first().click();
  const dialog = page.getByRole("dialog");
  await fillRequiredContact(dialog, "phone-supplied@example.com");
  await dialog.locator("#lead-phone").fill("+1 555 123 4567");
  let body: Record<string, unknown> | undefined;
  await page.route("**/api/commercial-leads", async (route) => {
    body = route.request().postDataJSON();
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "x", lead_status: "NEW" }),
    });
  });
  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
  expect(body?.contact_phone).toBe("+1 555 123 4567");
});
