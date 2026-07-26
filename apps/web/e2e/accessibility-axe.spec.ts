/**
 * WS8.4 / R17 — automated WCAG 2.2 AA checks (axe-core) across EVERY public
 * route (Product Contract §5.1) AND the interactive states where defects hide
 * (dialog open, a wizard step, a validation/error state).
 *
 * §5.1 public surface, each covered below:
 *   /  ·  /robots  ·  /robots/[slug]  ·  /compare  ·  /manufacturers  ·
 *   /manufacturers/[slug]  ·  /use-cases  ·  /use-cases/[slug]  ·
 *   /find-a-humanoid  ·  /matches/[id]  ·  404
 *
 * Honest about what this proves: axe detects a subset of WCAG failures — rule
 * violations, not total conformance. It is an oracle for *detectable* defects.
 * That is precisely why R18 (screen-reader) stays a separate, Attested gate and
 * is NOT satisfied by a green run here. The keyboard-only journeys, focus
 * behaviour and semantic-structure obligations of R17 are proven in the
 * companion specs keyboard.spec.ts and semantics.spec.ts; mobile target size in
 * responsive.spec.ts. axe alone is NOT R17.
 *
 * Tagged @a11y so it runs on BOTH the desktop and mobile (Pixel 7) projects.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const WCAG_22_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoViolations(page: import("@playwright/test").Page, context: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_22_AA).analyze();
  const summary = violations.map(
    (v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.help}`,
  );
  expect(violations, `${context}\n${summary.join("\n")}`).toEqual([]);
}

async function createRequirement(page: import("@playwright/test").Page): Promise<string> {
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

test.describe("@a11y automated WCAG 2.2 AA", () => {
  test("landing / home", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expectNoViolations(page, "home");
  });

  test("catalogue", async ({ page }) => {
    await page.goto("/robots", { waitUntil: "networkidle" });
    await expectNoViolations(page, "catalogue");
  });

  test("robot detail", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await expectNoViolations(page, "robot detail");
  });

  test("compare", async ({ page }) => {
    await page.goto("/compare?ids=unitree-g1,agility-digit", { waitUntil: "networkidle" });
    await expectNoViolations(page, "compare");
  });

  test("buyer-intent wizard (initial + an advanced step)", async ({ page }) => {
    await page.goto("/find-a-humanoid?use_case=warehouse-logistics", {
      waitUntil: "networkidle",
    });
    await expectNoViolations(page, "wizard step 1");
    // Interactive state: advance a step so a different panel is rendered.
    await page.getByRole("button", { name: /Next/ }).click();
    await expectNoViolations(page, "wizard step 2");
  });

  test("match results", async ({ page }) => {
    const id = await createRequirement(page);
    await page.goto(`/matches/${id}`, { waitUntil: "networkidle" });
    await expectNoViolations(page, "matches");
  });

  test("lead dialog — open state and a validation-error state", async ({ page }) => {
    await page.goto("/robots/unitree-g1", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Request Availability/i }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expectNoViolations(page, "lead dialog open");

    // Interactive state where a11y defects hide: submit empty -> inline error
    // with role="alert" + aria-invalid. Axe must still find no violations.
    await dialog.getByRole("button", { name: /Send request/i }).click();
    await expect(dialog.getByRole("alert")).toBeVisible();
    await expectNoViolations(page, "lead dialog validation error");
  });

  test("manufacturers and use-cases indexes", async ({ page }) => {
    await page.goto("/manufacturers", { waitUntil: "networkidle" });
    await expectNoViolations(page, "manufacturers");
    await page.goto("/use-cases", { waitUntil: "networkidle" });
    await expectNoViolations(page, "use-cases");
  });

  test("manufacturer detail", async ({ page }) => {
    await page.goto("/manufacturers/unitree", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoViolations(page, "manufacturer detail");
  });

  test("use-case detail", async ({ page }) => {
    await page.goto("/use-cases/warehouse-logistics", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoViolations(page, "use-case detail");
  });

  test("404 not-found", async ({ page }) => {
    // Unknown slug -> notFound() -> the 404 record, served with HTTP 404.
    const res = await page.goto("/robots/no-such-robot-zzz", { waitUntil: "networkidle" });
    expect(res?.status()).toBe(404);
    await expect(page.getByRole("heading", { level: 1, name: /Not found/i })).toBeVisible();
    await expectNoViolations(page, "404 not-found");
  });
});
