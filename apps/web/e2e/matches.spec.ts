import { type Page, expect, test } from "@playwright/test";

// WS6 match results, driven end-to-end against the VERIFIED catalogue:
// wizard submit -> SEE MATCHES -> deterministic /matches/[id] -> Compare These /
// Adjust Requirements. Proves the full browser -> FastAPI -> PostgreSQL chain and
// that WS6 owns the results surface (no lead capture).

async function submitWarehouse(page: Page, { country }: { country?: string } = {}) {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK (seeded)
  if (country) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY
    await page.locator("#wz-country").selectOption(country); // COUNTRY
    await page.getByRole("button", { name: /Next/ }).click();
    for (let i = 0; i < 8; i++) {
      await page.getByRole("button", { name: "Skip" }).click(); // ENV..TRANSACTION
    }
  } else {
    for (let i = 0; i < 10; i++) {
      await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
    }
  }
  // CONTACT: buyer identity is now required before REVIEW is reachable.
  await page.locator("#wz-contact-name").fill("Test Buyer");
  await page.locator("#wz-contact-org").fill("Test Org");
  await page.locator("#wz-contact-email").fill("buyer@example.com");
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);
}

test("SEE MATCHES leads to ranked results with the exact six-part breakdown", async ({ page }) => {
  await submitWarehouse(page);
  await expect(page.getByRole("heading", { name: /matched/i })).toBeVisible();

  const card = page.locator(".mr-card").first();
  await expect(card).toBeVisible();
  await expect(card.locator(".mr-score .num")).toBeVisible();
  // exact six-part breakdown.
  await expect(card.locator(".mr-bk")).toHaveCount(6);
  // >= 2 concrete reasons (E6).
  expect(await card.locator(".mr-reasons li").count()).toBeGreaterThanOrEqual(2);
  // Rank 1 is BEST OVERALL.
  await expect(page.locator(".mr-cat").first()).toHaveText(/BEST OVERALL/i);
  // WS7 commercial capture is present as CTAs, but no contact form is in the DOM
  // until the buyer opens the modal (no PII surface on initial render).
  await expect(
    page.getByRole("button", { name: /Request commercial help/i }).first(),
  ).toBeVisible();
  await expect(page.locator("input[type=email]")).toHaveCount(0);
});

test("Request commercial help pre-fills identity captured on the wizard's contact step", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  await page.locator("#wz-contact-name").fill("Jane Buyer");
  await page.locator("#wz-contact-org").fill("Acme Robotics");
  await page.locator("#wz-contact-email").fill("jane@example.com");
  await page.locator("#wz-contact-phone").fill("+1 555 0123");
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);

  await page.getByRole("button", { name: /Request commercial help/i }).first().click();
  // Pre-filled from the requirement's identity — no retyping.
  await expect(page.locator("#lead-name")).toHaveValue("Jane Buyer");
  await expect(page.locator("#lead-org")).toHaveValue("Acme Robotics");
  await expect(page.locator("#lead-email")).toHaveValue("jane@example.com");
  await expect(page.locator("#lead-phone")).toHaveValue("+1 555 0123");
  // Still fully editable before sending the commercial lead.
  await page.locator("#lead-name").fill("Jane B. Buyer");
  await expect(page.locator("#lead-name")).toHaveValue("Jane B. Buyer");
});

test("Compare these links the ranked robots into /compare", async ({ page }) => {
  await submitWarehouse(page);
  const compare = page.getByRole("link", { name: /Compare these/i });
  await expect(compare).toBeVisible();
  await compare.click();
  await expect(page).toHaveURL(/\/compare\?ids=/);
  await expect(page.getByRole("heading", { name: /Comparison matrix/i })).toBeVisible();
});

test("Adjust requirements prefills a new wizard from the stored requirement", async ({ page }) => {
  await submitWarehouse(page, { country: "DE" });
  await page.getByRole("link", { name: /Adjust requirements/i }).first().click();
  await expect(page).toHaveURL(/\/find-a-humanoid\?from=/);
  // TASK prefilled from the stored requirement.
  await expect(page.locator("#wz-usecase")).toHaveValue("warehouse-logistics");
  // COUNTRY prefilled too.
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY
  await expect(page.locator("#wz-country")).toHaveValue("DE");
});
