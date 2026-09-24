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
  test("follows the site's visual register: dark hero, numbered sections, live band", async ({
    page,
  }) => {
    await page.goto("/about", { waitUntil: "domcontentloaded" });
    // Same control-room hero as home, carrying the H1 and the key-facts readout.
    const hero = page.locator(".hero-shell.ho-dark");
    await expect(hero.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(hero.locator("dl.about-facts")).toBeVisible();
    // Numbered section indices 00–07, in order.
    const indices = await page.locator(".ho-section-index").allTextContents();
    expect(indices.map((t) => t.slice(0, 2))).toEqual(["00", "01", "02", "03", "04", "05", "06", "07"]);
    // Live coverage band reuses the home snapshot grammar.
    await expect(page.locator("section.snapshot.ho-dark .snap")).toHaveCount(4);
  });

  test("server-renders title, H1, key facts and principle", async ({ page }) => {
    await page.goto("/about", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveTitle("About — HumanoidOnline");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("About HumanoidOnline");

    const facts = page.locator("dl.about-facts");
    await expect(facts).toContainText("Humanoid.Company");
    await expect(facts).toContainText(/\d+ TRACKED · \d+ PUBLISHED/);
    await expect(page.getByText(
      "Maturity, obtainability and evidence are different facts. Unknown stays unknown.",
    )).toBeVisible();

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

  test("confirmed founder, founding date and HQ agree between visible facts and JSON-LD", async ({
    page,
  }) => {
    await page.goto("/about", { waitUntil: "domcontentloaded" });

    const row = (label: string) =>
      page.locator("dl.about-facts .cf-row").filter({ has: page.locator("dt", { hasText: label }) }).locator("dd");
    await expect(row("Founder")).toHaveText("Robert Konecny");
    await expect(row("Founded")).toHaveText("August 2026");
    await expect(row("Headquarters")).toHaveText("Prague, Czech Republic");
    // Contact email is not confirmed: no row, no mailto link anywhere.
    await expect(page.locator("dl.about-facts dt", { hasText: "Contact" })).toHaveCount(0);
    await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);

    const raw = await page.locator('script[type="application/ld+json"]').textContent();
    const graph = JSON.parse(raw!)["@graph"] as Array<Record<string, unknown>>;
    const org = graph.find((n) => n["@type"] === "Organization")!;
    const person = graph.find((n) => n["@type"] === "Person")!;

    expect(person.name).toBe("Robert Konecny");
    expect(org.founder).toEqual({ "@id": person["@id"] });
    expect(org.foundingDate).toBe("2026-08");
    expect((org.location as Record<string, unknown>).name).toBe("Prague, Czech Republic");
    expect(org).not.toHaveProperty("email");
    expect(raw).not.toContain("contact@humanoidonline.com");
  });

  test("About sits in the shared primary nav, between Use Cases and the CTA", async ({
    page,
  }) => {
    // Light data register (SiteNav) on a catalogue page.
    await page.goto("/robots", { waitUntil: "domcontentloaded" });
    const nav = page.getByRole("navigation", { name: "Primary" });
    const labels = (await nav.getByRole("link").allTextContents()).map((t) => t.trim());
    expect(labels).toEqual([
      "Robots",
      "Compare",
      "Manufacturers",
      "Use Cases",
      "About",
      "Find a Humanoid",
    ]);
    const about = nav.getByRole("link", { name: "About", exact: true });
    await expect(about).toHaveAttribute("href", "/about");
    // About is a normal link; Find a Humanoid stays the one CTA.
    await expect(about).not.toHaveClass(/cta/);
    await expect(nav.locator("a.cta")).toHaveCount(1);
    await expect(nav.locator("a.cta")).toContainText("Find a Humanoid");
    await about.click();
    await expect(page).toHaveURL(/\/about$/);

    // Dark register (DarkNav) on the About hero marks About as current.
    const darkAbout = page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "About", exact: true });
    await expect(darkAbout).toHaveAttribute("aria-current", "page");
  });

  test("is linked from the footer, the sitemap and llms.txt", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "domcontentloaded" });
    // Footer: a normal link inside the footer navigation, not a stray line.
    await expect(page.locator('footer.foot a[href="/about"]')).toHaveCount(1);
    await expect(
      page
        .getByRole("contentinfo")
        .getByRole("navigation", { name: "Footer" })
        .getByRole("link", { name: "About", exact: true }),
    ).toHaveAttribute("href", "/about");

    const sitemap = await (await page.request.get("/sitemap.xml")).text();
    expect(sitemap).toContain("/about</loc>");

    const llms = await (await page.request.get("/llms.txt")).text();
    expect(llms).toMatch(/\/about$/m);
  });
});
