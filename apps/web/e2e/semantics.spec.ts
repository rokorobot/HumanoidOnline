/**
 * WS8.4 / R17 — semantic structure, pinned directly.
 *
 * The frozen gate names "semantic headings/forms/dialogs" as its own obligation.
 * axe helps here, but its rule set can change; these assertions pin the concrete
 * structural facts so R17 stays durable regardless: one H1 per route, a main
 * landmark, a single named primary nav, programmatic form labels, and the
 * dialog's role/modality/accessible-title + validation invalid↔alert wiring.
 *
 * Untagged -> desktop-chromium only (structure is viewport-independent; the
 * mobile surface is exercised by the @a11y axe suite and @responsive checks).
 */
import { expect, test, type Page } from "@playwright/test";

async function createRequirement(page: Page): Promise<string> {
  const res = await page.request.post("/api/buyer-requirements", {
    data: {
      country: "US",
      preferred_transaction: "UNKNOWN",
      raw_input: {
        wizard_version: 1,
        answers: { country: { state: "ANSWERED", value: "US" } },
      },
    },
  });
  expect(res.status()).toBe(201);
  return (await res.json()).id as string;
}

// Every §5.1 public route with a stable URL. /matches/[id] needs a created
// requirement, so it is asserted separately below.
//
// `nav` = whether the route composes the shared primary navigation. It is true
// everywhere EXCEPT /robots/[slug], which deliberately renders its frozen dark
// "identity header" (idhead) instead of the light SiteNav and carries no nav
// landmark. This is an INTENTIONAL UI-D1 variance, not a WCAG issue: SC 3.2.3
// governs the relative ORDER of navigation mechanisms WHEN they are repeated — it
// does not require the same navigation on every page. The flag is false here so
// the test still PROVES the absence (locking the variance so it cannot drift
// accidentally), and the dedicated test below proves the nav that IS repeated
// appears, identically named, on every browse surface.
const ROUTES: { path: string; name: string; nav: boolean }[] = [
  { path: "/", name: "home", nav: true },
  { path: "/robots", name: "catalogue", nav: true },
  { path: "/robots/unitree-g1", name: "robot detail", nav: false },
  { path: "/compare?ids=unitree-g1,agility-digit", name: "compare", nav: true },
  { path: "/manufacturers", name: "manufacturers index", nav: true },
  { path: "/manufacturers/unitree", name: "manufacturer detail", nav: true },
  { path: "/use-cases", name: "use-cases index", nav: true },
  { path: "/use-cases/warehouse-logistics", name: "use-case detail", nav: true },
  { path: "/find-a-humanoid", name: "wizard", nav: true },
];

/** Structural invariants every rendered route must satisfy. */
async function expectPageStructure(page: Page, where: string, hasNav: boolean) {
  // Exactly one H1 — a single document title for the route.
  await expect(
    page.getByRole("heading", { level: 1 }),
    `${where}: expected exactly one H1`,
  ).toHaveCount(1);
  // A main landmark exists (the skip-link target).
  await expect(page.getByRole("main"), `${where}: missing main landmark`).toBeVisible();
  // The navigation landmark — where the route composes it — is named "Primary"
  // and unique. An unnamed or misnamed nav landmark is a defect; two would be a
  // duplicate-landmark defect. Where the route carries no nav (robot detail),
  // assert its documented absence exactly, so nothing is quietly assumed.
  await expect(
    page.getByRole("navigation", { name: "Primary" }),
    `${where}: expected ${hasNav ? "one" : "no"} nav named "Primary"`,
  ).toHaveCount(hasNav ? 1 : 0);
  await expect(
    page.getByRole("navigation"),
    `${where}: unexpected extra navigation landmark`,
  ).toHaveCount(hasNav ? 1 : 0);
}

test.describe("semantic structure — every public route", () => {
  for (const r of ROUTES) {
    test(`${r.name}: one H1, a main landmark, ${r.nav ? "a named primary nav" : "no nav (documented)"}`, async ({
      page,
    }) => {
      await page.goto(r.path, { waitUntil: "networkidle" });
      await expectPageStructure(page, r.name, r.nav);
    });
  }

  test("match results: one H1, a main landmark, a named primary nav", async ({ page }) => {
    const id = await createRequirement(page);
    await page.goto(`/matches/${id}`, { waitUntil: "networkidle" });
    await expectPageStructure(page, "matches", true);
  });

  test("404: one H1, a main landmark, a named primary nav", async ({ page }) => {
    const res = await page.goto("/robots/no-such-robot-zzz", { waitUntil: "networkidle" });
    expect(res?.status()).toBe(404);
    await expectPageStructure(page, "404", true);
  });

  test("the repeated primary nav is present and identically named on every browse surface", async ({
    page,
  }) => {
    // WCAG 3.2.3 (Consistent Navigation) applies to nav mechanisms that ARE
    // repeated: where the primary nav appears it is present and identically named
    // "Primary". Robot detail intentionally does not repeat it (frozen idhead
    // composition; see the ROUTES table) — which SC 3.2.3 permits.
    for (const path of [
      "/",
      "/robots",
      "/compare?ids=unitree-g1,agility-digit",
      "/manufacturers",
      "/manufacturers/unitree",
      "/use-cases",
      "/use-cases/warehouse-logistics",
      "/find-a-humanoid",
    ]) {
      await page.goto(path, { waitUntil: "networkidle" });
      await expect(
        page.getByRole("navigation", { name: "Primary" }),
        `${path}: primary nav missing/misnamed`,
      ).toHaveCount(1);
    }
  });
});

test.describe("semantic forms", () => {
  test("wizard: visible form controls have programmatic labels", async ({ page }) => {
    await page.goto("/find-a-humanoid?use_case=warehouse-logistics", {
      waitUntil: "networkidle",
    });
    // Every visible field on the step is associated with a <label for> (or an
    // explicit aria-label). Proven structurally, not by axe's ruleset.
    const unlabeled = await page
      .locator("form input:visible, form select:visible, form textarea:visible")
      .evaluateAll((els) =>
        els
          .filter((el) => {
            const id = el.getAttribute("id");
            const hasLabelFor = id
              ? !!document.querySelector(`label[for="${CSS.escape(id)}"]`)
              : false;
            const hasAria =
              !!el.getAttribute("aria-label") || !!el.getAttribute("aria-labelledby");
            const wrapped = !!el.closest("label");
            return !(hasLabelFor || hasAria || wrapped);
          })
          .map((el) => el.getAttribute("id") || el.getAttribute("name") || el.outerHTML.slice(0, 60)),
      );
    expect(unlabeled, `unlabeled wizard controls: ${unlabeled.join(", ")}`).toEqual([]);
  });

  test("lead dialog: each field has an associated label", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    for (const id of ["lead-email", "lead-name", "lead-org", "lead-country", "lead-transaction", "lead-message"]) {
      await expect(
        page.locator(`label[for="${id}"]`),
        `no <label for="${id}">`,
      ).toHaveCount(1);
    }
  });
});

test.describe("semantic dialog", () => {
  test("dialog exposes role=dialog + aria-modal + an accessible title", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    // The accessible name resolves via aria-labelledby -> the heading text; a
    // role="dialog" queried BY that name proves title + role together.
    const dialog = page.getByRole("dialog", { name: /Request availability/i });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  test("validation error is programmatically tied to its field (aria-invalid + alert)", async ({
    page,
  }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /Send request/i }).click();

    const email = page.locator("#lead-email");
    await expect(email).toHaveAttribute("aria-invalid", "true");
    // aria-describedby points at the error, and that node is the role=alert.
    const describedby = await email.getAttribute("aria-describedby");
    expect(describedby, "email has no aria-describedby when invalid").toBeTruthy();
    const errNode = page.locator(`#${describedby}`);
    await expect(errNode).toHaveAttribute("role", "alert");
    await expect(errNode).toBeVisible();
  });
});
