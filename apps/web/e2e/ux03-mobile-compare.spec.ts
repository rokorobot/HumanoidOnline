/**
 * UX-03 — mobile compare, against the real catalogue through the real API.
 *
 * Tagged @responsive / @a11y so it runs on BOTH projects (Desktop Chrome and the
 * Pixel 7 profile). Each test sets its own viewport: the property under test is
 * the layout at 320 / 390 / 430 px for 2, 3 and 4 PUBLISHED robots.
 *
 * What is pinned:
 *   - no horizontal page overflow, also with a wide fallback font (the CI runner
 *     has none of the design fonts, so metrics there are wider than on a dev box);
 *   - the pinned robot header and the matrix columns are the SAME columns;
 *   - a set too wide for the screen is paged two columns at a time, never squeezed;
 *   - the "Offers & evidence" sheet is a real modal: focus in, Escape out, focus back;
 *   - Buyer context annotates recorded offers and never hides or changes one;
 *   - the desktop table is unchanged.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const SETS: Record<number, string> = {
  2: "unitree-g1,agility-digit",
  3: "unitree-g1,unitree-h1,agility-digit",
  4: "unitree-g1,unitree-h1,agility-digit,agibot-a2-ultra",
};
const WIDTHS = [320, 390, 430];

async function pageOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const el = document.documentElement;
    return el.scrollWidth - el.clientWidth;
  });
}

/** Left edge and width of every DISPLAYED element matching `selector`. */
async function columns(page: Page, selector: string): Promise<{ x: number; w: number }[]> {
  return page.evaluate((sel) => {
    return Array.from(document.querySelectorAll<HTMLElement>(sel))
      .filter((el) => el.getClientRects().length > 0)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left), w: Math.round(r.width) };
      });
  }, selector);
}

/** The displayed cells of the matrix's Price row. */
async function priceCells(page: Page): Promise<{ x: number; w: number }[]> {
  return page.evaluate(() => {
    const row = Array.from(document.querySelectorAll("table.cmatrix tr")).find(
      (tr) => tr.querySelector("th.rowlab")?.textContent === "Price",
    );
    return Array.from(row?.querySelectorAll<HTMLElement>("td.cell") ?? [])
      .filter((el) => el.getClientRects().length > 0)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left), w: Math.round(r.width) };
      });
  });
}

for (const n of [2, 3, 4]) {
  for (const width of WIDTHS) {
    test(`@responsive compare ${n} robots at ${width}px: aligned pinned columns, no overflow`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(`/compare?ids=${SETS[n]}`, { waitUntil: "networkidle" });
      await expect(page.locator("table.cmatrix")).toBeVisible();

      expect(await pageOverflow(page), "page overflow").toBeLessThanOrEqual(1);
      // Wide fallback metrics, as on a machine without the design fonts.
      await page.addStyleTag({ content: "*{font-family:serif !important}" });
      expect(await pageOverflow(page), "page overflow with a wide fallback font").toBeLessThanOrEqual(1);

      // Four robots on a phone (or three on a very small one) page two at a time.
      const paged = n === 4 || (n === 3 && width < 360);
      const expected = paged ? 2 : n;
      const head = await columns(page, ".selrow .robotpick");
      const cells = await priceCells(page);
      expect(head.length, "robot header columns").toBe(expected);
      expect(cells.length, "matrix columns").toBe(expected);
      for (let i = 0; i < expected; i++) {
        expect(Math.abs(head[i].x - cells[i].x), `column ${i} left edge`).toBeLessThanOrEqual(1);
        expect(Math.abs(head[i].w - cells[i].w), `column ${i} width`).toBeLessThanOrEqual(1);
        // A column is never squeezed into unreadability.
        expect(cells[i].w, `column ${i} width`).toBeGreaterThanOrEqual(84);
      }
      if (paged) await expect(page.locator(".cmp-pager")).toBeVisible();
      else await expect(page.locator(".cmp-pager")).toBeHidden();

      // The robot header stays pinned while the rows scroll under it.
      await page.locator("table.cmatrix tr").last().scrollIntoViewIfNeeded();
      const pinned = await page.locator(".selrow-wrap").boundingBox();
      expect(Math.abs(pinned?.y ?? 99), "pinned header offset").toBeLessThanOrEqual(1);
    });
  }
}

test("@responsive compare paging: four robots, two at a time; the reference stays pinned", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/compare?ids=${SETS[4]}`, { waitUntil: "networkidle" });
  const names = () =>
    page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>(".selrow .robotpick"))
        .filter((el) => el.getClientRects().length > 0)
        .map((el) => el.querySelector(".name")?.textContent ?? ""),
    );
  const first = await names();
  expect(first).toHaveLength(2);
  await page.getByRole("button", { name: "Show next robot" }).click();
  const second = await names();
  expect(second).toHaveLength(2);
  expect(second[0]).toBe(first[1]);

  // Setting a reference pins it: every page shows the reference plus one other.
  await page.locator(".selrow .robotpick:not(.c-off) .cmp-ref-btn").first().click();
  await expect(page).toHaveURL(/ref=/);
  // (Columns keep their catalogue order, so the reference is not always the left one.)
  const ref = (await names())[0];
  for (let i = 0; i < 3; i++) {
    await page.getByRole("button", { name: "Show next robot" }).click();
    const shown = await names();
    expect(shown).toHaveLength(2);
    expect(shown).toContain(ref);
  }
});

test("@responsive @a11y compare sheet: full offer record in a modal; Escape closes, focus returns", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/compare?ids=${SETS[4]}`, { waitUntil: "networkidle" });
  // A2 Ultra is on the second page of the paged set.
  await page.getByRole("button", { name: "Show next robot" }).click();
  await page.getByRole("button", { name: "Show next robot" }).click();
  const trigger = page.getByRole("button", { name: /^Offers and evidence: .*A2 Ultra/ });
  await trigger.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Price entries");
  await expect(dialog).toContainText("Availability entries");
  // Terms the concise cell leaves out are all here, from the same offer rows.
  await expect(dialog).toContainText("Price basis");
  await expect(dialog).toContainText("OBSERVED");
  await expect(dialog.getByRole("link", { name: /View source/ }).first()).toBeVisible();

  // The entries scroll inside the sheet, not the page.
  const body = dialog.locator(".cmp-sheet-body");
  const scrolled = await body.evaluate((el) => {
    el.scrollTop = 400;
    return { top: el.scrollTop, scrollable: el.scrollHeight > el.clientHeight };
  });
  expect(scrolled.scrollable).toBe(true);
  expect(scrolled.top).toBeGreaterThan(0);
  expect(await pageOverflow(page)).toBeLessThanOrEqual(1);

  // Focus starts inside the dialog and can never reach the page behind it: a
  // modal dialog makes the rest of the document inert, so Tab moves through the
  // dialog's own controls (and the browser's), never the matrix underneath.
  const inDialog = () => page.evaluate(() => !!document.activeElement?.closest("dialog.cmp-sheet"));
  const onPageBehind = () =>
    page.evaluate(() => {
      const a = document.activeElement;
      return !!a && a !== document.body && !a.closest("dialog.cmp-sheet");
    });
  expect(await inDialog()).toBe(true);
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(await onPageBehind(), `focus after ${i + 1} tabs`).toBe(false);
  }

  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`)).toEqual([]);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("@responsive compare buyer context: Region and Offer market annotate, never hide", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/compare?ids=agibot-a2-ultra,unitree-g1", { waitUntil: "networkidle" });
  const rental = page.locator("table.cmatrix tr:has(th.rowlab:text-is('Rental')) td.cell").first();
  const before = (await rental.innerText()).split("\n")[0];

  // Collapsed by default; the controls exist only once opened.
  await expect(page.locator("#cmp-region")).toHaveCount(0);
  await page.getByRole("button", { name: /Buyer context/ }).click();
  await page.locator("#cmp-region").selectOption("EU");
  await expect(page).toHaveURL(/region=EU/);
  await page.locator("#cmp-market").selectOption("EU");
  await expect(page).toHaveURL(/region=EU&offered_in=EU/);

  // A2 Ultra's rental offers are recorded for Bulgaria and Romania: member
  // countries, so they are IN the EU market but do NOT apply to the EU as a region.
  await expect(rental).toContainText(before);
  await expect(rental).toContainText(/Recorded for .*BG.*; does not apply to EU/);
  await expect(rental).toContainText(/In EU market \(.*BG.*\)/);
  expect(await pageOverflow(page)).toBeLessThanOrEqual(1);

  // The context is part of the canonical URL, so share/save carry it.
  await page.reload({ waitUntil: "networkidle" });
  await expect(rental).toContainText(/does not apply to EU/);
  await expect(page.getByRole("button", { name: /Buyer context/ })).toContainText(
    "Region: EU · Offer market: EU",
  );
});

test("@responsive compare: a configuration-specific manufacturer estimate keeps its configuration on a phone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/compare?ids=4ne1-mini,unitree-g1", { waitUntil: "networkidle" });
  // 4NE1 Mini: NEURA's own estimates, EUR 19,999 (Standard) and EUR 29,999 (Pro).
  const cell = page.locator("table.cmatrix tr", { has: page.locator("th.rowlab", { hasText: /^Price$/ }) })
    .locator("td.cell")
    .first();
  // The concise cell never shows the amount without what it is and whose it is.
  await expect(cell).toContainText("From €19,999");
  await expect(cell).toContainText("Manufacturer estimate");
  await expect(cell).toContainText("Standard configuration");
  await expect(cell).toContainText("2 configurations priced");
  await expect(cell).not.toContainText("29,999");
  // An estimate is not a like-for-like published price: no leader is named.
  await expect(page.getByText(/LOWEST COMPARABLE PRICE/i)).toHaveCount(0);
  expect(await pageOverflow(page)).toBeLessThanOrEqual(1);

  // The sheet holds BOTH configurations' entries, each with its own configuration.
  await cell.getByRole("button", { name: /^Offers and evidence/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Price entries · 2");
  await expect(dialog).toContainText("€19,999");
  await expect(dialog).toContainText("€29,999");
  await expect(dialog.locator("article.cmp-entry", { hasText: "€29,999" })).toContainText("Pro");
  await expect(dialog.locator("article.cmp-entry", { hasText: "€19,999" })).toContainText("Standard");
  await expect(dialog).toContainText("Manufacturer estimate");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("@responsive @a11y compare at 390px: four robots, axe clean", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/compare?ids=${SETS[4]}`, { waitUntil: "networkidle" });
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`)).toEqual([]);
});

test("@responsive compare on desktop keeps the table layout", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/compare?ids=${SETS[4]}`, { waitUntil: "networkidle" });
  // Row label sits to the LEFT of its cells, on the same line: a table row.
  const label = await page.locator("table.cmatrix th.rowlab", { hasText: /^Price$/ }).boundingBox();
  const cells = await priceCells(page);
  expect(cells).toHaveLength(4);
  expect(label && label.x + label.width).toBeLessThanOrEqual(cells[0].x + 1);
  // Mobile-only affordances are absent; all four robots are shown.
  await expect(page.locator(".cmp-detail").first()).toBeHidden();
  await expect(page.locator(".cmp-pager")).toBeHidden();
  expect(await columns(page, ".selrow .robotpick")).toHaveLength(4);
});
