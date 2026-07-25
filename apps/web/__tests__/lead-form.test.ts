import { describe, expect, it } from "vitest";

import {
  buildSubmission,
  draftEmailError,
  emptyDraft,
  isValidEmail,
  type LeadDraft,
} from "../lib/lead-form";

function draft(overrides: Partial<LeadDraft> = {}): LeadDraft {
  return { ...emptyDraft(), ...overrides };
}

describe("isValidEmail", () => {
  it("accepts a well-formed address and trims", () => {
    expect(isValidEmail("  jane@example.com ")).toBe(true);
  });
  it("rejects malformed addresses", () => {
    for (const bad of ["", "jane", "jane@", "@example.com", "jane@example", "a b@c.com"]) {
      expect(isValidEmail(bad)).toBe(false);
    }
  });
});

describe("draftEmailError", () => {
  it("requires an email", () => {
    expect(draftEmailError(draft({ contact_email: "   " }))).toMatch(/required/i);
  });
  it("rejects an invalid email", () => {
    expect(draftEmailError(draft({ contact_email: "nope" }))).toMatch(/valid/i);
  });
  it("passes a valid email", () => {
    expect(draftEmailError(draft({ contact_email: "jane@example.com" }))).toBeNull();
  });
});

describe("buildSubmission", () => {
  it("sends only the buyer-owned fields; omits blank optionals", () => {
    const body = buildSubmission(draft({ contact_email: " jane@example.com " }), {
      requirementId: "req-1",
      robotSlugs: ["digit"],
    });
    expect(body).toEqual({
      requirement_id: "req-1",
      contact_email: "jane@example.com",
      robot_slugs: ["digit"],
    });
    // no server-owned keys ever
    expect(body).not.toHaveProperty("lead_status");
    expect(body).not.toHaveProperty("match_score");
  });

  it("includes trimmed optionals when provided", () => {
    const body = buildSubmission(
      draft({
        contact_email: "jane@example.com",
        contact_name: "  Jane Buyer ",
        organization: " Acme ",
        country: "DE",
        preferred_transaction: "RAAS",
        message: "  20 units in 2027 ",
      }),
      { requirementId: null, robotSlugs: ["digit", "apollo"] },
    );
    expect(body).toEqual({
      requirement_id: null,
      contact_email: "jane@example.com",
      contact_name: "Jane Buyer",
      organization: "Acme",
      country: "DE",
      preferred_transaction: "RAAS",
      message: "20 units in 2027",
      robot_slugs: ["digit", "apollo"],
    });
  });

  it("passes requirement_id null and empty robot_slugs through (zero-match)", () => {
    const body = buildSubmission(draft({ contact_email: "jane@example.com" }), {
      requirementId: "req-9",
      robotSlugs: [],
    });
    expect(body.requirement_id).toBe("req-9");
    expect(body.robot_slugs).toEqual([]);
  });

  it("omits an empty preferred_transaction (inherit) rather than sending \"\"", () => {
    const body = buildSubmission(
      draft({ contact_email: "jane@example.com", preferred_transaction: "" }),
      { requirementId: "r", robotSlugs: [] },
    );
    expect(body).not.toHaveProperty("preferred_transaction");
  });
});
