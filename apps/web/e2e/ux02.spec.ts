/**
 * UX-02 - catalogue discovery & comparison, against the real stack (verified catalogue).
 * Tagged @responsive so the same journeys run on the desktop AND the phone project.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function expectNoHorizontalOverflow(page: Page, where: string) {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return el.scrollWidth - el.clientWidth;
  });
  expect(overflow, `${where}: horizontal overflow of ${overflow}px`).toBeLessThanOrEqual(1);
}

const cards = (page: Page) => page.locator("article.rcard");
const search = (page: Page) => page.getByRole("search").getByRole("searchbox", { name: "Search robots" });

// ---- UX-02A ---------------------------------------------------------------------------------
test.describe("@responsive UX-02A catalogue search", () => {
  test("a buyer sentence becomes visible, removable chips; URL restores it on reload, back and forward", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    const box = search(page);
    await expect(box).toBeVisible();
    expect((await box.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await box.fill("unitree research under $20000 purchase");
    await box.press("Enter");
    await expect(page).toHaveURL(/\/robots\?q=unitree\+research\+under\+%2420000\+purchase$/);
    // The URL carries ONLY the raw text; the server interpreted it.
    const chips = page.locator(".interp .chip-label");
    await expect(chips).toHaveText([
      "Manufacturer: Unitree Robotics",
      "Use case: Research & Education",
      "Maximum purchase price: $20,000",
      "Obtainable by: Purchase",
    ]);
    await expect(page.getByText(/recorded purchase prices in that currency only/)).toBeVisible();
    await expectNoHorizontalOverflow(page, "search chips");
    const count = await cards(page).count();

    // reload restores everything
    await page.reload({ waitUntil: "networkidle" });
    await expect(chips).toHaveCount(4);
    expect(await cards(page).count()).toBe(count);
    await expect(box).toHaveValue("unitree research under $20000 purchase");

    // removing a chip edits the query text and navigates (button, not a link)
    await page.getByRole("button", { name: "Remove: Maximum purchase price: $20,000" }).click();
    await expect(page).toHaveURL(/q=unitree\+research\+purchase$/);
    await expect(chips).toHaveCount(3);

    // back / forward restore the previous interpretation
    await page.goBack();
    await expect(chips).toHaveCount(4);
    await page.goForward();
    await expect(chips).toHaveCount(3);
  });

  test("a number without a currency is not applied and offers explicit choices", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    const total = await cards(page).count();
    await page.goto("/robots?q=" + encodeURIComponent("warehouse under 20000"), { waitUntil: "networkidle" });
    await expect(page.getByText("Maximum purchase price 20,000 — choose a currency")).toBeVisible();
    await expect(page.getByText(/no currency was given and none is assumed/)).toBeVisible();
    // the use case IS applied, the price is NOT (so results are the use-case set, not price-filtered)
    const ucOnly = await cards(page).count();
    expect(ucOnly).toBeGreaterThan(0);
    expect(ucOnly).toBeLessThan(total);
    await page.getByRole("button", { name: "EUR", exact: true }).click();
    await expect(page).toHaveURL(/q=warehouse\+under\+20000\+EUR/);
    await expect(page.locator(".interp .chip-label").filter({ hasText: "Maximum purchase price: €20,000" })).toBeVisible();
  });

  test("price ceilings never match unknown, quote-only or rental-only robots", async ({ page, request }) => {
    await page.goto("/robots?q=" + encodeURIComponent("under 30000 usd"), { waitUntil: "networkidle" });
    const names = await cards(page).locator(".lockup .name").allInnerTexts();
    expect(names.length).toBeGreaterThan(0);
    expect(names).not.toContain("Digit"); // no recorded price at all (unknown, never 0)
    expect(names).not.toContain("H1"); // QUOTE_ONLY: a known fact with no number
    // Rental rates: robots whose only EUR price is a RENTAL rate never satisfy a EUR purchase ceiling.
    const list = (await (await request.get(`${API}/api/robots?limit=100`)).json()).items as { slug: string }[];
    const rentalOnly: string[] = [];
    for (const r of list) {
      const d = await (await request.get(`${API}/api/robots/${r.slug}`)).json();
      const eur = (d.pricing_offers as { currency: string; transaction_type: string; condition?: string }[]).filter(
        (o) => o.currency === "EUR" && (o.condition ?? "NEW") === "NEW",
      );
      if (eur.some((o) => o.transaction_type === "RENTAL") && !eur.some((o) => o.transaction_type === "PURCHASE")) {
        rentalOnly.push(r.slug);
      }
    }
    const under = (await (await request.get(`${API}/api/robots?limit=100&price_max=100000000&price_currency=EUR`)).json()).items as { slug: string }[];
    for (const slug of rentalOnly) expect(under.map((x) => x.slug)).not.toContain(slug);
  });

  test("no-result state names the query, the interpretation, what was not understood, and offers a clear action", async ({ page }) => {
    await page.goto("/robots?q=" + encodeURIComponent("unitree waterproof"), { waitUntil: "networkidle" });
    const empty = page.getByTestId("no-results");
    await expect(empty).toBeVisible();
    await expect(empty).toContainText("You searched for “unitree waterproof”");
    await expect(empty).toContainText("Manufacturer: Unitree Robotics");
    await expect(empty).toContainText("Not understood: “waterproof”");
    await expect(empty).toContainText("could not be fully interpreted");
    await expect(empty).toContainText("not that no such robot exists");
    await expectNoHorizontalOverflow(page, "no-result");
    await empty.getByRole("link", { name: "Clear search and filters" }).click();
    await expect(page).toHaveURL(/\/robots$/);
    await expect(search(page)).toHaveValue("");
    expect(await cards(page).count()).toBeGreaterThan(10);
  });

  test("conflicting constraints are reported and not silently resolved", async ({ page }) => {
    await page.goto("/robots?q=" + encodeURIComponent("unitree figure"), { waitUntil: "networkidle" });
    await expect(page.getByText(/Two manufacturers in one query/)).toBeVisible();
    await page.goto("/robots?q=" + encodeURIComponent("unitree") + "&manufacturer=agility-robotics", { waitUntil: "networkidle" });
    await expect(page.getByText(/already set to something else/)).toBeVisible();
  });

  test("the price filter carries an explicit currency (EUR) and the URL stays the source of truth", async ({ page }) => {
    await page.goto("/robots?price_max=20000&price_currency=EUR", { waitUntil: "networkidle" });
    expect(page.url()).toContain("price_currency=EUR");
    // an unsupported currency is refused, never reinterpreted
    const res = await page.goto("/robots?price_max=20000&price_currency=JPY");
    expect(res?.status()).toBe(404);
  });

  test("homepage search still posts q to /robots", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const form = page.getByRole("search");
    await form.getByRole("textbox", { name: "Search robots" }).fill("digit");
    await form.getByRole("button", { name: "Search" }).click();
    await expect(page).toHaveURL(/\/robots\?q=digit$/);
    await expect(cards(page)).toHaveCount(1);
  });
});

// ---- UX-02D ---------------------------------------------------------------------------------
test.describe("@responsive UX-02D region / offer market help", () => {
  test("help opens and closes by keyboard; both filters count as two active filters", async ({ page }) => {
    await page.goto("/robots?region=DE&offered_in=EU", { waitUntil: "networkidle" });
    const toggle = page.getByRole("button", { name: /^Filters/ });
    if (await toggle.isVisible()) {
      await expect(toggle).toContainText("2 active");
      await toggle.click();
    }
    const help = page.getByRole("button", { name: "Region help" });
    await help.focus();
    await expect(help).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Enter");
    await expect(help).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText(/not proof that the robot can be bought there/)).toBeVisible();
    await expect(page.getByText(/Missing regional information is unknown, not unavailable/)).toBeVisible();
    await page.keyboard.press("Space");
    await expect(help).toHaveAttribute("aria-expanded", "false");
    const market = page.getByRole("button", { name: "Offer market help" });
    await market.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/not that the robot can be ordered, shipped or cleared through customs there/)).toBeVisible();
    await expectNoHorizontalOverflow(page, "filter help");
  });

  test("filter help passes axe", async ({ page }) => {
    await page.goto("/robots?q=unitree", { waitUntil: "networkidle" });
    const toggle = page.getByRole("button", { name: /^Filters/ });
    if (await toggle.isVisible()) await toggle.click();
    await page.getByRole("button", { name: "Region help" }).click();
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});

// ---- UX-02C ---------------------------------------------------------------------------------
test.describe("@responsive UX-02C comparison continuity through robot detail", () => {
  const SEL = "unitree-g1,agility-digit";

  test("catalogue -> detail -> compare -> detail -> catalogue, then back/forward and reload", async ({ page }) => {
    await page.goto(`/robots?compare=${SEL}`, { waitUntil: "networkidle" });
    // server HTML hrefs stay plain (no selection-carrying anchors)
    const href = await cards(page).first().locator("a.name").getAttribute("href");
    expect(href).toMatch(/^\/robots\/[a-z0-9-]+$/);

    // catalogue -> detail carries the selection
    await page.locator('article.rcard:has(a.name[href="/robots/unitree-g1"]) a.name').click();
    await expect(page).toHaveURL(/\/robots\/unitree-g1\?compare=unitree-g1(,|%2C)agility-digit$/);
    const tray = page.getByRole("region", { name: "Compare selection" });
    await expect(tray).toContainText("Compare selection: 2 / 4");
    await expect(tray).toContainText("Agility Digit");
    expect(await tray.innerText()).not.toContain("agility-digit");
    await expectNoHorizontalOverflow(page, "detail with tray");

    // reload keeps the selection
    await page.reload({ waitUntil: "networkidle" });
    await expect(tray).toContainText("2 / 4");

    // detail -> compare (tray), then compare -> detail carries it back
    await tray.getByRole("button", { name: /Open comparison/ }).click();
    await expect(page).toHaveURL(/\/compare\?ids=unitree-g1,agility-digit$/);
    await page.locator(".robotpick a.name", { hasText: "Digit" }).click();
    await expect(page).toHaveURL(/\/robots\/agility-digit\?compare=/);
    await expect(page.getByRole("region", { name: "Compare selection" })).toContainText("2 / 4");

    // browser Back restores Compare, then the previous detail
    await page.goBack();
    await expect(page).toHaveURL(/\/compare\?ids=unitree-g1,agility-digit$/);
    await page.goForward();
    await expect(page).toHaveURL(/\/robots\/agility-digit\?compare=/);

    // detail -> catalogue (breadcrumb) keeps the tray
    await page.getByRole("link", { name: "Robot Catalogue" }).click();
    await expect(page).toHaveURL(/\/robots\?compare=unitree-g1(,|%2C)agility-digit$/);
    await expect(page.getByText(/Compare selection: 2 \/ 4/)).toBeVisible();
  });

  test("Compare + on detail toggles THIS robot in the carried selection (URL only)", async ({ page }) => {
    await page.goto("/robots/unitree-g1?compare=agility-digit", { waitUntil: "networkidle" });
    const tray = page.getByRole("region", { name: "Compare selection" });
    await expect(tray).toContainText("1 / 4");
    await expect(tray).toContainText("Select at least 2 to compare");
    await page.getByRole("link", { name: /Compare \+/ }).click();
    await expect(page).toHaveURL(/\/robots\/unitree-g1\?compare=agility-digit(,|%2C)unitree-g1$/);
    await expect(tray).toContainText("2 / 4");
    await page.getByRole("link", { name: /In compare/ }).click();
    await expect(tray).toContainText("1 / 4");
    // no storage is used as a source of truth
    const stored = await page.evaluate(() => localStorage.length + sessionStorage.length);
    expect(stored).toBe(0);
  });

  test("a shared detail link works in a fresh context; /compare with no selection stays an empty state", async ({ page, browser }) => {
    const ctx = await browser.newContext();
    const fresh = await ctx.newPage();
    await fresh.goto(new URL(`/robots/unitree-g1?compare=${SEL}`, page.url() === "about:blank" ? "http://127.0.0.1:3000" : page.url()).toString(), { waitUntil: "networkidle" });
    await expect(fresh.getByRole("region", { name: "Compare selection" })).toContainText("2 / 4");
    await fresh.goto(new URL("/compare", fresh.url()).toString(), { waitUntil: "networkidle" });
    await expect(fresh.locator(".cmp-scroll")).toHaveCount(0);
    await ctx.close();
  });

  test("a plain detail visit (no selection) shows no tray and Compare + works as before", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await expect(page.getByRole("region", { name: "Compare selection" })).toHaveCount(0);
    await page.getByRole("link", { name: /Compare \+/ }).click();
    await expect(page).toHaveURL(/\/compare\?ids=unitree-g1$/);
  });
});

// ---- UX-02E ---------------------------------------------------------------------------------
test.describe("UX-02E no developer tokens in visible text", () => {
  const PAGES = [
    "/",
    "/robots",
    "/robots?q=unitree",
    "/robots/unitree-g1",
    "/robots/4ne1-mini",
    "/robots/agility-digit",
    "/robots/figure-02",
    "/compare?ids=unitree-g1,agility-digit",
    "/compare?ids=unitree-g1,unitree-h1&view=evidence",
    "/manufacturers",
    "/manufacturers/agility-robotics",
    "/manufacturers/unitree",
    "/use-cases",
    "/use-cases/warehouse-logistics",
  ];
  for (const path of PAGES) {
    test(`${path}`, async ({ page }) => {
      await page.goto(path, { waitUntil: "networkidle" });
      const text = await page.evaluate(() => document.body.innerText);
      const upper = [...text.matchAll(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g)].map((m) => m[0]);
      expect(upper, `SCREAMING_SNAKE tokens on ${path}`).toEqual([]);
      for (const bad of ["FIT_SCORE", "availability_offer", "pricing_offer", "commercially_accessible", "WS3 /", "Predicate"]) {
        expect(text, `${bad} on ${path}`).not.toContain(bad);
      }
    });
  }

  test("detail 'Record summary' shows labels with the raw enum in data-enum", async ({ page }) => {
    await page.goto("/robots/agility-digit", { waitUntil: "networkidle" });
    const dd = page.locator("dl.citation-facts dd[data-enum]");
    await expect(dd.first()).toBeVisible();
    const pairs = await dd.evaluateAll((els) => els.map((e) => [e.getAttribute("data-enum"), e.textContent]));
    const status = pairs.find(([raw]) => raw === "RAAS_DEPLOYMENT");
    expect(status?.[1]).toBe("Robot-as-a-service");
  });

  test("provider names from the API: a reseller shows its real name on a card and in a detail row", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    await expect(page.locator('article.rcard [data-provider="alza-cz"]').first()).toContainText("Alza.cz");
    await expect(page.locator('article.rcard [data-provider="reichelt"]').first()).toContainText("reichelt elektronik");
    await page.goto("/robots/unitree-h2", { waitUntil: "networkidle" });
    await expect(page.locator('[data-provider="reichelt"]').first()).toHaveText("reichelt elektronik");
    // no page shows a bare provider slug (visible text is the name, even though CSS upper-cases it)
    for (const path of ["/robots", "/robots/unitree-h2", "/robots/unitree-g1", "/compare?ids=unitree-g1,unitree-h2"]) {
      await page.goto(path, { waitUntil: "networkidle" });
      const text = (await page.evaluate(() => document.body.innerText)).toLowerCase();
      for (const slug of ["alza-cz", "robotshop-eu", "robotshop-us", "quadruped-de", "unitree-store", "seller ref"]) {
        expect(text, `${slug} on ${path}`).not.toContain(slug);
      }
    }
  });

  test("provider names: the maker's own store is named, a reseller is a labelled identifier", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    const named = page.locator('[data-provider="unitree-store"]').first();
    await expect(named).toHaveText("Unitree Online Store");
    // A reseller now carries the provider record's own name from the API.
    await expect(page.locator('[data-provider="robotshop-us"]').first()).toHaveText("RobotShop US");
  });
});

// ---- width matrix: search field + chips, no-result, filter help, detail tray ------------------
for (const width of [320, 375, 390, 768, 1280]) {
  test(`@responsive UX-02 no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const sentence = encodeURIComponent("unitree research under $20000 purchase");
    for (const [label, path] of [
      ["search + chips", `/robots?q=${sentence}`],
      ["currency chip", `/robots?q=${encodeURIComponent("warehouse under 20000")}`],
      ["no-result", `/robots?q=${encodeURIComponent("unitree waterproof")}`],
      ["conflict chips", `/robots?q=${encodeURIComponent("unitree figure")}`],
      ["detail tray", "/robots/unitree-g1?compare=agility-digit,unitree-h1"],
    ] as const) {
      await page.goto(path, { waitUntil: "networkidle" });
      await expectNoHorizontalOverflow(page, `${label} @${width}`);
    }
    // filter help, opened
    await page.goto("/robots?region=DE&offered_in=EU", { waitUntil: "networkidle" });
    const toggle = page.getByRole("button", { name: /^Filters/ });
    if (await toggle.isVisible()) await toggle.click();
    await page.getByRole("button", { name: "Region help" }).click();
    await page.getByRole("button", { name: "Offer market help" }).click();
    await expectNoHorizontalOverflow(page, `filter help @${width}`);
    // the search field and its button stay inside the viewport and are at least 44px tall
    await page.goto("/robots", { waitUntil: "networkidle" });
    const field = await search(page).boundingBox();
    expect(field && field.x + field.width).toBeLessThanOrEqual(width + 1);
    const btn = await page.getByRole("search").getByRole("button", { name: "Search" }).boundingBox();
    expect(btn && btn.height).toBeGreaterThanOrEqual(44);
  });
}

test.describe("@a11y UX-02 interpretation UI passes axe", () => {
  for (const [label, path] of [
    ["chips", "/robots?q=" + encodeURIComponent("unitree research under $20000 purchase")],
    ["needs currency", "/robots?q=" + encodeURIComponent("warehouse under 20000")],
    ["no-result", "/robots?q=" + encodeURIComponent("unitree waterproof")],
    ["detail tray", "/robots/unitree-g1?compare=agility-digit,unitree-h1"],
  ] as const) {
    test(label, async ({ page }) => {
      await page.goto(path, { waitUntil: "networkidle" });
      const { violations } = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
    });
  }
});
