// DATA-D1 operator review surface — route-level coverage.
//
// The unit tests prove the component renders correctly from mocked data. This
// proves the real route, against the real API, does not blur the boundary: the
// page shows unverified candidates, the catalogue shows verified robots, and
// nothing crosses.
import { expect, test } from "@playwright/test";

// Tagged @discovery and run by its OWN CI job, for the same reason the
// zero-match suite is: this surface is fail-closed. The API mounts
// /api/discovery-review only when APP_ENV is relaxed, the page notFound()s
// otherwise, and the candidates it renders exist only after MANUAL_BOOTSTRAP has
// run. The verified-catalogue job has none of that by design, so these specs
// cannot pass there — and making them pass there would mean relaxing the
// environment the catalogue suite deliberately tests in.
test.describe("discovery review @discovery", () => {
  test("renders the review surface with its unverified warning", async ({ page }) => {
    await page.goto("/discovery-review");

    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      /discovery review/i,
    );
    const warning = page.getByTestId("unverified-warning");
    await expect(warning).toBeVisible();
    await expect(warning).toContainText(/not verified catalogue entries/i);
    await expect(warning).toContainText(
      /cannot be used for comparison or commercial decisions/i,
    );
    await expect(warning).toContainText(
      /Specifications, prices, commercial availability, maturity and imagery/i,
    );
  });

  test("offers no commercial or comparison action on a candidate", async ({ page }) => {
    await page.goto("/discovery-review");

    // The controls that would imply a verified, purchasable option.
    for (const name of [/compare/i, /request availability/i, /rent/i, /buy/i, /lease/i]) {
      await expect(page.getByRole("button", { name })).toHaveCount(0);
    }
    await expect(page.locator("form")).toHaveCount(0);
  });

  test("links back to the verified catalogue, and is reachable from it", async ({
    page,
  }) => {
    await page.goto("/discovery-review");
    const back = page.getByRole("link", { name: /VERIFIED ROBOT CATALOGUE/i });
    await expect(back).toBeVisible();
    await back.click();
    await expect(page).toHaveURL(/\/robots$/);

    // And the operator link on the catalogue leads back — the only entry point,
    // deliberately not in the primary navigation.
    const forward = page.getByRole("link", { name: /DISCOVERY REVIEW/i });
    await expect(forward).toBeVisible();
    await forward.click();
    await expect(page).toHaveURL(/\/discovery-review$/);
  });

  test("the review surface is absent from the primary navigation", async ({ page }) => {
    // Blurring the canonical/noncanonical boundary is the risk; the catalogue's
    // own nav must not advertise an unverified queue as a peer destination.
    await page.goto("/robots");
    const nav = page.getByRole("navigation");
    if (await nav.count()) {
      await expect(nav.first().getByRole("link", { name: /discovery/i })).toHaveCount(0);
    }
  });

  // Asserted through the RENDERED PAGES, not through `request`: Playwright's
  // request fixture resolves against the web origin, where the catalogue API does
  // not live. An earlier version of these two tests called `/api/robots` there,
  // got a 404, and then asserted "the 404 body does not contain NOT_TRACED" —
  // which passes for the wrong reason and proves nothing.
  test("the two populations are rendered by separate surfaces", async ({ page }) => {
    await page.goto("/discovery-review");
    const candidateRows = page.getByTestId("candidate-row");
    await expect(candidateRows.first()).toBeVisible();
    const reviewCount = await candidateRows.count();
    expect(reviewCount).toBeGreaterThan(0);

    await page.goto("/robots");
    // The catalogue renders robot cards, never candidate rows, and never the
    // review warning.
    await expect(page.getByTestId("candidate-row")).toHaveCount(0);
    await expect(page.getByTestId("unverified-warning")).toHaveCount(0);
  });

  test("the catalogue page carries no discovery-queue vocabulary", async ({ page }) => {
    await page.goto("/robots");
    const body = await page.locator("body").innerText();
    // These words belong to the queue. Seeing one on the catalogue would mean a
    // candidate had reached a canonical surface.
    for (const term of ["NOT_TRACED", "UNRESOLVED", "DISCOVERED"]) {
      expect(body).not.toContain(term);
    }
  });
});
