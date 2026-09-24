/**
 * About page — the canonical entity definition of HumanoidOnline.
 *
 * Proves, at the rendered layer:
 *   - the page is server-rendered with its own title and canonical;
 *   - the visible key-facts table carries live coverage counts;
 *   - Organization / WebSite / AboutPage JSON-LD is in the delivered HTML;
 *   - unconfirmed corporate facts render nowhere (no placeholders);
 *   - the page is reachable from the footer, the sitemap and llms.txt.
 */
import { expect, test } from "@playwright/test";

test.describe("About page", () => {
  test("server-renders title, H1, key facts and principle", async ({ page }) => {
    await page.goto("/about", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveTitle("About — HumanoidOnline");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("About HumanoidOnline");

    const facts = page.locator("dl.about-facts");
    await expect(facts).toContainText("Humanoid.Company");
    await expect(facts).toContainText(/\d+ TRACKED · \d+ PUBLISHED/);
    await expect(facts).toContainText(
      "Maturity, obtainability and evidence are different facts. Unknown stays unknown.",
    );

    const canonical = page.locator('link[rel="canonical"]');
    await expect(canonical).toHaveAttribute("href", /\/about$/);
  });

  test("delivered HTML carries AboutPage + Organization JSON-LD without placeholders", async ({
    page,
  }) => {
    const res = await page.request.get("/about");
    expect(res.status()).toBe(200);
    const html = await res.text();

    const match = html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s);
    expect(match, "JSON-LD must be server-rendered").not.toBeNull();
    const graph = JSON.parse(match![1])["@graph"] as Array<Record<string, unknown>>;
    const types = graph.map((n) => n["@type"]);
    expect(types).toEqual(expect.arrayContaining(["AboutPage", "WebSite", "Organization"]));

    const org = graph.find((n) => n["@type"] === "Organization")!;
    expect(org.name).toBe("HumanoidOnline");
    expect((org.parentOrganization as Record<string, unknown>).name).toBe("Humanoid.Company");

    // Unknown stays unknown: no editorial placeholders reach the page.
    expect(html).not.toMatch(/\[URL\]|\[Add |confirm preferred/i);
  });

  test("is linked from the footer, the sitemap and llms.txt", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "domcontentloaded" });
    await expect(page.locator('footer.foot a[href="/about"]')).toHaveCount(1);

    const sitemap = await (await page.request.get("/sitemap.xml")).text();
    expect(sitemap).toContain("/about</loc>");

    const llms = await (await page.request.get("/llms.txt")).text();
    expect(llms).toMatch(/\/about$/m);
  });
});
