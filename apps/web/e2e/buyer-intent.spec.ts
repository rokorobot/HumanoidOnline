import { expect, test } from "@playwright/test";

// WS5 buyer-intent wizard, driven end-to-end against the VERIFIED catalogue:
// browser -> Next route handler -> FastAPI -> PostgreSQL. Proves a real
// buyer_requirement is captured, that UNKNOWN/SKIP are distinct, and that WS5
// stops at capture confirmation (matching / /matches is WS6).

test("wizard: pre-seeds from ?use_case and shows the distinction on review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  // TASK seeded from the query param against live data.
  await expect(page.locator("#wz-usecase")).toHaveValue("warehouse-logistics");

  // TASK -> Next (ANSWERED)
  await page.getByRole("button", { name: /Next/ }).click();
  // INDUSTRY -> Unknown
  await page.getByRole("button", { name: "Unknown" }).click();
  // COUNTRY -> pick a canonical country from the expanded ISO list, then Next
  await page.locator("#wz-country").selectOption("DE");
  await page.getByRole("button", { name: /Next/ }).click();
  // Skip the rest — ENVIRONMENT..TRANSACTION (8 steps) — to reach REVIEW.
  for (let i = 0; i < 8; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }

  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  // Review keeps UNKNOWN and SKIPPED visibly distinct.
  await expect(page.locator(".wz-badge--unknown").first()).toBeVisible();
  await expect(page.locator(".wz-badge--skipped").first()).toBeVisible();
});

test("wizard: submitting captures a requirement and stops at confirmation (no matches)", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");

  // TASK -> Next
  await page.getByRole("button", { name: /Next/ }).click();
  // INDUSTRY -> Skip
  await page.getByRole("button", { name: "Skip" }).click();
  // COUNTRY -> DE -> Next
  await page.locator("#wz-country").selectOption("DE");
  await page.getByRole("button", { name: /Next/ }).click();
  // ENVIRONMENT..TIMELINE -> Skip 7 times to reach TRANSACTION
  for (let i = 0; i < 7; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  // TRANSACTION -> choose RENT (a preference, not an offered product) -> Next
  await page.getByRole("radio", { name: /Rent/ }).click();
  await page.getByRole("button", { name: /Next/ }).click();

  // REVIEW -> submit
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();

  // Interim capture confirmation — WS5 persists + confirms only.
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  await expect(page.getByText("Matching has not been generated yet.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Browse robots/i })).toBeVisible();
  // No matches are generated and no /matches route is offered in WS5.
  await expect(page.locator('a[href^="/matches"]')).toHaveCount(0);
});
