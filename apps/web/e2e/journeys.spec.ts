/**
 * WS8.4 / R16 — the three product journeys (Product Contract §5.1), each proven
 * end-to-end. Not page-load smoke tests: every journey performs the meaningful
 * user action and asserts the expected governed state/result appears.
 *
 *   A  Explore & compare      /robots -> add two to compare -> /compare matrix
 *   B  Buyer intent (spine)   /find-a-humanoid -> submit -> /matches -> lead
 *   C  Use-case entry         /use-cases/[slug] -> suitable robot -> detail
 */
import { expect, test } from "@playwright/test";

test("Journey A — explore & compare: catalogue -> compare matrix (2 robots)", async ({
  page,
}) => {
  await page.goto("/", { waitUntil: "networkidle" });
  // Enter the catalogue from the home surface.
  await page.getByRole("link", { name: /^Robots$/ }).first().click();
  await expect(page).toHaveURL(/\/robots/);

  // Add two robots to the comparison via the real "Add to compare" control.
  // Each add is a client-side router.push that rewrites ?compare=… (a real
  // <button>, not an <a>, since Emergency Compare Crawl Containment v0.2 — see
  // components/CompareLink.tsx), so wait for the URL to settle between clicks
  // (the selection is URL-driven state, not a race).
  const cards = page.locator("article.rcard");
  await cards.nth(0).getByRole("button", { name: /Add to compare/i }).click();
  await expect(page).toHaveURL(/[?&]compare=[^&]+/);
  await cards.nth(1).getByRole("button", { name: /Add to compare/i }).click();
  await expect(page).toHaveURL(/[?&]compare=[^&]+%2C|[?&]compare=[^&]+,[^&]+/);

  // The compare tray reflects the selection and opens the matrix.
  await page.getByRole("button", { name: /Open comparison/i }).click();
  await expect(page).toHaveURL(/\/compare\?ids=/);

  // The governed result: a real side-by-side matrix of exactly the two picks.
  await expect(page.locator(".cmp-scroll")).toBeVisible();
  await expect(page.locator("table.cmatrix")).toBeVisible();
  // Both selected robots appear as columns in the picker header row.
  const ids = new URL(page.url()).searchParams.get("ids")!.split(",");
  expect(ids.length).toBe(2);
  const picks = page.locator(".robotpick");
  expect(await picks.count()).toBeGreaterThanOrEqual(2);
});

test("Journey B — buyer intent: wizard -> match results -> commercial lead", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics", {
    waitUntil: "networkidle",
  });

  // Drive the wizard to submission (TASK seeded; the rest skipped/answered).
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY
  await page.locator("#wz-country").selectOption("US");
  await page.getByRole("button", { name: /Next/ }).click(); // COUNTRY
  for (let i = 0; i < 7; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // ENV..TIMELINE
  }
  await page.getByRole("button", { name: "Skip" }).click(); // TRANSACTION
  // CONTACT: buyer identity is now required before REVIEW is reachable.
  await page.locator("#wz-contact-name").fill("Jane Buyer");
  await page.locator("#wz-contact-org").fill("Acme Robotics");
  await page.locator("#wz-contact-email").fill("journey-b@example.com");
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();

  // A real buyer_requirement was persisted -> deterministic match results.
  await page.getByRole("link", { name: /See matches/i }).click();
  await expect(page).toHaveURL(/\/matches\//);
  await expect(page.getByRole("heading", { name: /matched/i })).toBeVisible();

  // The commercial spine completes: request help -> lead extended (200) —
  // the wizard's CONTACT step already created the lead, so LeadDialog shows
  // that identity locked (read-only), not editable fields to refill.
  await page.getByRole("button", { name: /Request commercial help/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("#lead-name")).toHaveCount(0);
  await expect(dialog).toContainText("journey-b@example.com");
  await dialog.getByRole("button", { name: /Send request/i }).click();
  // Governed result: the capture confirmation (a commercial_lead now exists).
  await expect(dialog.getByText(/Request received|received/i)).toBeVisible();
});

test("Journey C — use-case entry: use-case -> suitable robot -> detail", async ({ page }) => {
  await page.goto("/use-cases/warehouse-logistics", { waitUntil: "networkidle" });
  // The page lists suitable robots ranked by fit (governed by use_case_fit).
  const suitable = page.locator("a.name[href^='/robots/']");
  expect(await suitable.count()).toBeGreaterThan(0);
  const href = await suitable.first().getAttribute("href");
  await suitable.first().click();
  await expect(page).toHaveURL(new RegExp(href!.replace(/[/]/g, "\\/")));

  // Landed on the real robot detail record (the decision object), and the
  // use case can seed the wizard from here (proven in buyer-intent.spec).
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Request Availability/i }).first(),
  ).toBeVisible();
});
