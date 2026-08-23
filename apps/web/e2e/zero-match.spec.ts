import { expect, test } from "@playwright/test";

// Isolated zero-match browser acceptance (WS7 §20). Tagged @zeromatch so it runs
// ONLY in its own CI job (`web-zero-match`) against an ephemeral, controlled DB
// with NO published robots — never against the shared verified-catalogue suite,
// which cannot produce a genuine zero-match (Ameca has UNKNOWN on every hard
// filter, so >= 1 match always survives). The main `npm run e2e` excludes this
// tag (`--grep-invert @zeromatch`); `npm run e2e:zero` runs only it.
//
// With zero published candidates the deterministic matcher returns []
// ("No published platforms are available to match yet."), rendering the true
// zero-match surface. We then exercise the "Tell us anyway" capture end-to-end
// (browser -> proxy -> FastAPI -> Postgres: requirement_id + robot_slugs=[]).

test("@zeromatch zero-match: 'tell us anyway' extends the existing lead using the canonical identity", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK (seeded use case)
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  // CONTACT: buyer identity is now required before REVIEW is reachable — and
  // is canonical for this requirement from here on (the wizard's own submit
  // already creates the commercial lead with this identity; see Wizard.tsx).
  await page.locator("#wz-contact-name").fill("Test Buyer");
  await page.locator("#wz-contact-org").fill("Test Org");
  await page.locator("#wz-contact-email").fill("buyer@example.com");
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);

  // genuine zero-match surface
  await expect(page.getByRole("heading", { name: /No humanoid matched/i })).toBeVisible();

  let leadStatus: number | undefined;
  page.on("response", (r) => {
    if (r.request().method() === "POST" && r.url().includes("/api/commercial-leads")) {
      leadStatus = r.status();
    }
  });

  await page.getByRole("button", { name: /Tell us anyway/i }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // Identity is already known — a read-only summary, not editable inputs.
  // Cannot submit a different email here, so the backend's identity-conflict
  // 409 can never be hit through this UI.
  await expect(dialog.locator("#lead-email")).toHaveCount(0);
  await expect(dialog).toContainText("buyer@example.com");

  await dialog.getByRole("button", { name: /Send request/i }).click();
  await expect(page.getByRole("heading", { name: /Request received/i })).toBeVisible();
  // no contact data in the URL
  expect(page.url()).not.toContain("@");

  // Extends the lead the wizard already created for this zero-match
  // requirement — 200 (UPDATED), never a fresh 201.
  expect(leadStatus).toBe(200);
});
