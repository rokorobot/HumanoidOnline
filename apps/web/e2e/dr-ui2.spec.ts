import { expect, test } from "@playwright/test";

// DR-UI2 (ecosystem blend) journeys, read-only: the home fact headline and board,
// the robot-detail offer board with request-from-row, and the catalogue board view.

test("home: live obtainable count leads the H1, the fixed claim stays in it", async ({ page }) => {
  await page.goto("/");
  const h1 = page.getByRole("heading", { level: 1 });
  await expect(h1).toContainText(/\d+ humanoids?\s+obtainable now/i);
  await expect(h1).toContainText("Find the right humanoid.");
  await expect(h1).not.toContainText(/^0+ humanoids/);
  await expect(page.locator(".home-board tbody tr").first()).toBeVisible();
  await expect(page.getByRole("banner", { name: "Humanoid.Company platforms" })).toBeVisible();
});

test("robot detail: offer board pairs price with status and opens a prefilled request", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  const board = page.locator(".offer-board");
  await expect(board).toBeVisible();
  await expect(board.locator("tbody tr").first()).toBeVisible();
  await board.getByRole("button", { name: /Request this offer/ }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("complementary", { name: "Selected offer" })).toBeVisible();
  await expect(dialog.getByLabel("Preferred transaction")).toHaveValue("BUY");
  await expect(dialog.getByLabel("Country")).toHaveValue("");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("catalogue: mode tab filters and the board view keeps unknown explicit", async ({ page }) => {
  await page.goto("/robots?view=board");
  await expect(page.locator(".cat-board")).toBeVisible();
  await expect(page.locator(".cat-board").getByText("UNKNOWN").first()).toBeVisible();
  await page.locator(".mode-tabs").getByRole("link", { name: /Rental/ }).click();
  await expect(page).toHaveURL(/transaction_type=RENTAL/);
  await expect(page).toHaveURL(/view=board/);
  await expect(page.locator(".mode-tab.is-on")).toContainText("Rental");
});
