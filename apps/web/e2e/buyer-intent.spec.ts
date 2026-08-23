import { expect, Page, test } from "@playwright/test";

// WS5 buyer-intent wizard, driven end-to-end against the VERIFIED catalogue:
// browser -> Next route handler -> FastAPI -> PostgreSQL. Proves a real
// buyer_requirement is captured, that UNKNOWN/SKIP are distinct, and that WS5
// stops at capture confirmation (matching / /matches is WS6).
//
// Product reversal: the wizard now ends with a required CONTACT step (Full
// name / Company / Business email / optional Telephone) between the last
// question and REVIEW — see fillContact below.
//
// v0.2: completing the questionnaire now ALSO captures the commercial lead
// (reusing the existing WS7 /api/commercial-leads pipeline) in the same
// submission — see the tests below for the two-call sequence, the
// commercial-leads-failure/retry contract, and duplicate protection.

async function fillContact(page: Page, overrides: Partial<Record<"name" | "org" | "email" | "phone", string>> = {}) {
  await page.locator("#wz-contact-name").fill(overrides.name ?? "Test Buyer");
  await page.locator("#wz-contact-org").fill(overrides.org ?? "Test Org");
  await page.locator("#wz-contact-email").fill(overrides.email ?? "buyer@example.com");
  if (overrides.phone) await page.locator("#wz-contact-phone").fill(overrides.phone);
  await page.getByRole("button", { name: /Next/ }).click();
}

test("wizard: pre-seeds from ?use_case and shows the distinction on review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  // TASK seeded from the query param against live data.
  await expect(page.locator("#wz-usecase")).toHaveValue("warehouse-logistics");

  // TASK -> Next (ANSWERED)
  await page.getByRole("button", { name: /Next/ }).click();
  // INDUSTRY -> Unknown
  await page.getByRole("button", { name: "Unknown" }).click();
  // COUNTRY -> pick a canonical country from the expanded ISO list, then Next
  await page.locator("#wz-country").selectOption("DE");
  await page.getByRole("button", { name: /Next/ }).click();
  // Skip the rest — ENVIRONMENT..TRANSACTION (8 steps) — to reach CONTACT.
  for (let i = 0; i < 8; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  await fillContact(page);

  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  // Review keeps UNKNOWN and SKIPPED visibly distinct.
  await expect(page.locator(".wz-badge--unknown").first()).toBeVisible();
  await expect(page.locator(".wz-badge--skipped").first()).toBeVisible();
});

test("wizard: submitting captures a requirement and stops at confirmation (no matches)", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");

  // v0.2: completion must call BOTH endpoints exactly once, with the lead
  // payload carrying the same contact identity + this exact requirement,
  // and no invented robot interest (matching hasn't run yet).
  let buyerReqPosts = 0;
  let leadPosts = 0;
  let leadBody: Record<string, unknown> | null = null;
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    if (r.url().includes("/api/buyer-requirements")) buyerReqPosts++;
    if (r.url().includes("/api/commercial-leads")) {
      leadPosts++;
      leadBody = r.postDataJSON() as Record<string, unknown>;
    }
  });

  // TASK -> Next
  await page.getByRole("button", { name: /Next/ }).click();
  // INDUSTRY -> Skip
  await page.getByRole("button", { name: "Skip" }).click();
  // COUNTRY -> DE -> Next
  await page.locator("#wz-country").selectOption("DE");
  await page.getByRole("button", { name: /Next/ }).click();
  // ENVIRONMENT..TIMELINE -> Skip 7 times to reach TRANSACTION
  for (let i = 0; i < 7; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  // TRANSACTION -> choose RENT (a preference, not an offered product) -> Next
  await page.getByRole("radio", { name: /Rent/ }).click();
  await page.getByRole("button", { name: /Next/ }).click();

  // CONTACT -> identity, then REVIEW -> submit
  await fillContact(page, { name: "Jane Buyer", org: "Acme Robotics", email: "jane@example.com" });
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();

  // Capture confirmation — primary action is SEE MATCHES (WS6).
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  await expect(page.getByRole("link", { name: /See matches/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Browse robots/i })).toBeVisible();
  // The confirmation screen itself presents no form — identity was already
  // captured on the CONTACT step, not re-asked here.
  await expect(page.locator("input[type=email]")).toHaveCount(0);

  expect(buyerReqPosts).toBe(1);
  expect(leadPosts).toBe(1);
  expect(leadBody).toMatchObject({
    contact_name: "Jane Buyer",
    organization: "Acme Robotics",
    contact_email: "jane@example.com",
    robot_slugs: [],
  });
  // No phone was filled — genuinely optional, never sent as "".
  expect(leadBody).not.toHaveProperty("contact_phone");
  const body = leadBody as unknown as { requirement_id: string };
  expect(typeof body.requirement_id).toBe("string");
  expect(body.requirement_id.length).toBeGreaterThan(0);
});

async function reachContactStep(page: Page) {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  await expect(page.getByRole("heading", { name: /Who should we send matches to/i })).toBeVisible();
}

// Scoped to the wizard's own `role="group" aria-label="Requirement wizard"`
// container (Wizard.tsx), not the whole page: Next.js's built-in App Router
// announcer (`#__next-route-announcer__`) injects a permanent, page-wide
// `role="alert"` element outside this container on every route, which a
// bare `page.locator('[role="alert"]')` would also (wrongly) count.
function wizardAlerts(page: Page) {
  return page.getByRole("group", { name: "Requirement wizard" }).locator('[role="alert"]');
}

test("wizard: CONTACT step shows no validation alerts on initial entry", async ({ page }) => {
  await reachContactStep(page);
  // A — untouched, empty fields: no validation feedback at all, not even for
  // the required ones. role="alert" is reserved for actual feedback, never
  // the default/untouched state; aria-invalid is omitted entirely (not just
  // "false") when there is no error to describe.
  await expect(wizardAlerts(page)).toHaveCount(0);
  await expect(page.locator("#wz-contact-name")).not.toHaveAttribute("aria-invalid");
  await expect(page.locator("#wz-contact-org")).not.toHaveAttribute("aria-invalid");
  await expect(page.locator("#wz-contact-email")).not.toHaveAttribute("aria-invalid");
});

test("wizard: CONTACT step validates only after an attempted Next, then live-clears per field", async ({
  page,
}) => {
  await reachContactStep(page);
  const next = page.getByRole("button", { name: /Next/ });

  // B — attempt Next with everything blank: all three required errors appear,
  // and the wizard stays on CONTACT (never silently advances).
  await next.click();
  await expect(wizardAlerts(page)).toHaveCount(3);
  await expect(page.getByRole("heading", { name: /Who should we send matches to/i })).toBeVisible();
  // Focus moved to the first invalid field (full name).
  await expect(page.locator("#wz-contact-name")).toBeFocused();
  await expect(page.locator("#wz-contact-name")).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("#wz-contact-name")).toHaveAttribute(
    "aria-describedby",
    "wz-contact-name-error",
  );

  // C — fill full name only: its error clears immediately (no second attempt
  // needed); organization/email remain invalid.
  await page.locator("#wz-contact-name").fill("Jane Buyer");
  await expect(wizardAlerts(page)).toHaveCount(2);
  await expect(page.locator("#wz-contact-name")).not.toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("#wz-contact-org-error")).toBeVisible();
  await expect(page.locator("#wz-contact-email-error")).toBeVisible();

  // D — fill valid organization + email: every error clears, Next now
  // succeeds and the wizard reaches REVIEW.
  await page.locator("#wz-contact-org").fill("Acme Robotics");
  await page.locator("#wz-contact-email").fill("jane@example.com");
  await expect(wizardAlerts(page)).toHaveCount(0);
  await next.click();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
});

test("wizard: CONTACT step telephone never produces a required-field error", async ({ page }) => {
  await reachContactStep(page);
  await page.locator("#wz-contact-name").fill("Jane Buyer");
  await page.locator("#wz-contact-org").fill("Acme Robotics");
  await page.locator("#wz-contact-email").fill("jane@example.com");
  // E — telephone deliberately left blank throughout, including after an
  // attempted Next: no alert of any kind, and Next still succeeds.
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(wizardAlerts(page)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
});

// ---- exit-gate proofs (accessibility / robustness) ----------------------

test("Back/Next preserves the entered draft value", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK -> INDUSTRY
  await page.locator("#wz-industry").fill("logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // INDUSTRY -> COUNTRY
  await page.getByRole("button", { name: /Back/ }).click(); // back to INDUSTRY
  await expect(page.locator("#wz-industry")).toHaveValue("logistics");
});

test("step transition moves focus to the question heading", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // -> INDUSTRY
  await expect(page.locator(".wz-qlabel")).toBeFocused();
});

test("keyboard-only: select a transaction choice and advance to review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 9; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TIMELINE
  }
  // TRANSACTION: operate the choice + Next by keyboard only.
  await page.getByRole("radio", { name: /Rent/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("radio", { name: /Rent/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.getByRole("button", { name: /Next/ }).focus();
  await page.keyboard.press("Enter");
  // TRANSACTION -> CONTACT: identity is required before REVIEW is reachable.
  await fillContact(page);
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
});

test("rapid double-submit fires exactly one request to each endpoint (no duplicate lead)", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  let buyerReqPosts = 0;
  let leadPosts = 0;
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    if (r.url().includes("/api/buyer-requirements")) buyerReqPosts++;
    if (r.url().includes("/api/commercial-leads")) leadPosts++;
  });
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click(); // INDUSTRY..TRANSACTION
  }
  await fillContact(page);
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  // Two synchronous clicks in one tick — the ref guard must collapse to one
  // full submission (both calls), never two leads for one completion.
  await page
    .getByRole("button", { name: /Submit requirements/i })
    .evaluate((b: HTMLButtonElement) => {
      b.click();
      b.click();
    });
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  expect(buyerReqPosts).toBe(1);
  expect(leadPosts).toBe(1);
});

test("commercial-lead failure after a successful requirement capture shows a retryable error, not REQUIREMENT CAPTURED, and retry does not resubmit the questionnaire", async ({
  page,
}) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  let buyerReqPosts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/buyer-requirements")) buyerReqPosts++;
  });
  // The requirement capture itself is real (unmocked); only the lead call
  // fails, so this proves the "persist wins, notify-adjacent capture can
  // fail independently" contract holds at the wizard boundary too.
  await page.route("**/api/commercial-leads", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "lead capture boom" }),
    }),
  );

  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  await fillContact(page, { name: "Jane Buyer", org: "Acme Robotics", email: "jane@example.com" });
  await page.getByRole("button", { name: /Submit requirements/i }).click();

  // Must NOT show REQUIREMENT CAPTURED — the lead was never confirmed saved
  // — and the review draft (including everything just typed) must still be
  // there so the buyer never has to re-enter anything to retry.
  await expect(page.locator(".wz-error")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  expect(buyerReqPosts).toBe(1);

  // Retry, now letting the lead call through for real. Must NOT re-submit
  // the questionnaire (still exactly one buyer-requirements POST ever) —
  // only the lead capture is retried, using the requirement_id already
  // obtained on the first attempt.
  await page.unroute("**/api/commercial-leads");
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toBeVisible();
  expect(buyerReqPosts).toBe(1);
});

test("submit error shows a message and keeps the draft on review", async ({ page }) => {
  await page.goto("/find-a-humanoid?use_case=warehouse-logistics");
  // Force a server error at the submit boundary.
  await page.route("**/api/buyer-requirements", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "server boom" }),
    }),
  );
  await page.getByRole("button", { name: /Next/ }).click(); // TASK
  for (let i = 0; i < 10; i++) {
    await page.getByRole("button", { name: "Skip" }).click();
  }
  await fillContact(page);
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: /Submit requirements/i }).click();
  // Visible error, and the draft is intact (still on review, not confirmation).
  await expect(page.locator(".wz-error")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Requirement captured" })).toHaveCount(0);
});
