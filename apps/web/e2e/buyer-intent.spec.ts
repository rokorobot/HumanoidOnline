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

// ---- exit-gate proofs (accessibility / robustness) ----------------------

test("Back/Next preserves the entered draft value", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK -> INDUSTRY
  await page.locator("#wz-industry").fill("logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // INDUSTRY -> COUNTRY
  await page.getByRole("button", { name: /Back/ }).click(); // back to INDUSTRY
  await expect(page.locator("#wz-industry")).toHaveValue("logistics");
});

test("step transition moves focus to the question heading", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // -> INDUSTRY
  await expect(page.locator(".wz-qlabel")).toBeFocused();
});

test("keyboard-only: select a transaction choice and advance to review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 9; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TIMELINE
  }
  // TRANSACTION: operate the choice + Next by keyboard only.
  await page.getByRole("radio", { name: /Rent/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("radio", { name: /Rent/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.getByRole("button", { name: /Next/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
});

test("rapid double-submit fires exactly one request", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/buyer-requirements")) posts++;
  });
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  // Two synchronous clicks in one tick — the ref guard must collapse to one POST.
  await page
    .getByRole("button", { name: /Submit requirements/i })
    .evaluate((b: HTMLButtonElement) => {
      b.click();
      b.click();
    });
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  expect(posts).toBe(1);
});

test("submit error shows a message and keeps the draft on review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  // Force a server error at the submit boundary.
  await page.route("**/api/buyer-requirements", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "server boom" }),
    }),
  );
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  // Visible error, and the draft is intact (still on review, not confirmation).
  await expect(page.locator(".wz-error")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toHaveCount(0);
});
