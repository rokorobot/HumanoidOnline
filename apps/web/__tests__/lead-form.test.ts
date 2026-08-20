import { describe, expect, it } from "vitest";

import {
  buildSubmission,
  draftEmailError,
  draftFromIdentity,
  draftNameError,
  draftOrganizationError,
  emailError,
  emptyDraft,
  type Identity,
  isValidEmail,
  type LeadDraft,
  nameError,
  organizationError,
} from "../lib/lead-form";

function draft(overrides: Partial<LeadDraft> = {}): LeadDraft {
  return { ...emptyDraft(), ...overrides };
}

// A draft satisfying all three required fields, for tests that aren't
// specifically exercising the required-field errors themselves.
function validDraft(overrides: Partial<LeadDraft> = {}): LeadDraft {
  return draft({
    contact_name: "Jane Buyer",
    organization: "Acme",
    contact_email: "jane@example.com",
    ...overrides,
  });
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

describe("draftNameError", () => {
  it("requires a full name", () => {
    expect(draftNameError(draft({ contact_name: "   " }))).toMatch(/required/i);
  });
  it("passes a non-blank name", () => {
    expect(draftNameError(draft({ contact_name: "Jane Buyer" }))).toBeNull();
  });
});

describe("draftOrganizationError", () => {
  it("requires a company / organization", () => {
    expect(draftOrganizationError(draft({ organization: "   " }))).toMatch(/required/i);
  });
  it("passes a non-blank organization", () => {
    expect(draftOrganizationError(draft({ organization: "Acme" }))).toBeNull();
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

// Plain-string validators — shared with the Find a Humanoid wizard's contact
// step (lib/wizard.ts / Wizard.tsx), which has no LeadDraft to build against.
describe("nameError / organizationError / emailError (plain-string primitives)", () => {
  it("nameError mirrors draftNameError", () => {
    expect(nameError("   ")).toMatch(/required/i);
    expect(nameError("Jane Buyer")).toBeNull();
  });
  it("organizationError mirrors draftOrganizationError", () => {
    expect(organizationError("   ")).toMatch(/required/i);
    expect(organizationError("Acme")).toBeNull();
  });
  it("emailError mirrors draftEmailError", () => {
    expect(emailError("   ")).toMatch(/required/i);
    expect(emailError("nope")).toMatch(/valid/i);
    expect(emailError("jane@example.com")).toBeNull();
  });
});

describe("draftFromIdentity", () => {
  const identity: Identity = {
    contact_name: "Jane Buyer",
    organization: "Acme",
    contact_email: "jane@example.com",
    contact_phone: "+1 555 0123",
  };

  it("maps a known identity into a fully-editable draft (contact_phone -> phone)", () => {
    const d = draftFromIdentity(identity);
    expect(d.contact_name).toBe("Jane Buyer");
    expect(d.organization).toBe("Acme");
    expect(d.contact_email).toBe("jane@example.com");
    expect(d.phone).toBe("+1 555 0123");
    // everything else stays at the empty-draft default.
    expect(d.country).toBe("");
    expect(d.preferred_transaction).toBe("");
    expect(d.message).toBe("");
  });

  it("null/undefined identity is identical to emptyDraft (unchanged behavior)", () => {
    expect(draftFromIdentity(null)).toEqual(emptyDraft());
    expect(draftFromIdentity(undefined)).toEqual(emptyDraft());
  });
});

describe("buildSubmission", () => {
  it("always sends contact_name/organization/contact_email (now required); omits blank optionals", () => {
    const body = buildSubmission(
      validDraft({ contact_email: " jane@example.com ", contact_name: " Jane Buyer ", organization: " Acme " }),
      { requirementId: "req-1", robotSlugs: ["digit"] },
    );
    expect(body).toEqual({
      requirement_id: "req-1",
      contact_email: "jane@example.com",
      contact_name: "Jane Buyer",
      organization: "Acme",
      robot_slugs: ["digit"],
    });
    // no server-owned keys ever
    expect(body).not.toHaveProperty("lead_status");
    expect(body).not.toHaveProperty("match_score");
  });

  it("includes trimmed optionals (including phone) when provided", () => {
    const body = buildSubmission(
      validDraft({
        contact_email: "jane@example.com",
        contact_name: "  Jane Buyer ",
        organization: " Acme ",
        phone: " +1 (555) 123-4567 ",
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
      contact_phone: "+1 (555) 123-4567",
      country: "DE",
      preferred_transaction: "RAAS",
      message: "20 units in 2027",
      robot_slugs: ["digit", "apollo"],
    });
  });

  it("omits contact_phone when telephone is left blank", () => {
    const body = buildSubmission(validDraft({ phone: "   " }), {
      requirementId: "r",
      robotSlugs: [],
    });
    expect(body).not.toHaveProperty("contact_phone");
  });

  it("passes requirement_id null and empty robot_slugs through (zero-match)", () => {
    const body = buildSubmission(validDraft(), {
      requirementId: "req-9",
      robotSlugs: [],
    });
    expect(body.requirement_id).toBe("req-9");
    expect(body.robot_slugs).toEqual([]);
  });

  it("omits an empty preferred_transaction (inherit) rather than sending \"\"", () => {
    const body = buildSubmission(
      validDraft({ preferred_transaction: "" }),
      { requirementId: "r", robotSlugs: [] },
    );
    expect(body).not.toHaveProperty("preferred_transaction");
  });
});
