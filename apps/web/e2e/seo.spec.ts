/**
 * WS8.5 / R22 + R23 — SEO / machine surface, proven at the rendered layer.
 *
 * R22: every route has a specific title; no page inherits the generic root
 *      title. Covered here for a static route, a dynamic entity route, and both
 *      404 cases (unknown slug + unmatched path).
 * R23: the sitemap and llms.txt enumerate the ENTIRE published canonical set of
 *      every public entity type — robots, manufacturers AND use cases.
 *
 * Untagged (desktop project): titles/machine output are viewport-independent.
 */
import { expect, test } from "@playwright/test";

const ROOT_TITLE =
  "HumanoidOnline — Commercial intelligence for the humanoid market";

test.describe("R22 — per-page metadata (no generic-root inheritance)", () => {
  test("static route carries its own title", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveTitle("Robot Catalogue — HumanoidOnline");
  });

  test("dynamic entity route carries an entity-specific title, not the root", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "domcontentloaded" });
    const title = await page.title();
    expect(title, "must not inherit the generic root title").not.toBe(ROOT_TITLE);
    expect(title).toMatch(/ — HumanoidOnline$/);
    // The title leads with the entity name (the robot's H1).
    const h1 = (await page.getByRole("heading", { level: 1 }).textContent())?.trim();
    expect(h1 && title.startsWith(h1)).toBeTruthy();
  });

  test("dynamic use-case route carries its own title", async ({ page }) => {
    await page.goto("/use-cases/warehouse-logistics", { waitUntil: "domcontentloaded" });
    const title = await page.title();
    expect(title).not.toBe(ROOT_TITLE);
    expect(title).toMatch(/ — HumanoidOnline$/);
  });

  test("both 404 cases carry a specific 'Not found' title", async ({ page }) => {
    const unknownSlug = await page.goto("/robots/no-such-robot-zzz", {
      waitUntil: "domcontentloaded",
    });
    expect(unknownSlug?.status()).toBe(404);
    await expect(page).toHaveTitle("Not found — HumanoidOnline");

    const unmatched = await page.goto("/totally/unknown/path", {
      waitUntil: "domcontentloaded",
    });
    expect(unmatched?.status()).toBe(404);
    await expect(page).toHaveTitle("Not found — HumanoidOnline");
  });
});

test.describe("R23 — machine surface covers the entire published canonical set", () => {
  test("sitemap.xml enumerates robots, manufacturers AND use cases", async ({ page }) => {
    const res = await page.request.get("/sitemap.xml");
    expect(res.status()).toBe(200);
    const xml = await res.text();
    // All three public entity types present (use cases are the override addition).
    expect(xml).toContain("/robots/unitree-g1");
    expect(xml).toContain("/manufacturers/unitree");
    expect(xml).toContain("/use-cases/warehouse-logistics");
    // Every verified robot appears (WS2B catalogue = 7).
    const robotUrls = (xml.match(/\/robots\/[a-z0-9-]+</g) || []).length;
    expect(robotUrls).toBeGreaterThanOrEqual(7);
  });

  test("llms.txt lists robots, manufacturers and use cases", async ({ page }) => {
    const res = await page.request.get("/llms.txt");
    expect(res.status()).toBe(200);
    const txt = await res.text();
    expect(txt).toContain("## Robots");
    expect(txt).toContain("## Manufacturers");
    expect(txt).toContain("## Use cases");
    expect(txt).toContain("/manufacturers/unitree");
    expect(txt).toContain("/use-cases/warehouse-logistics");
  });
});
