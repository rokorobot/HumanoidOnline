import { describe, expect, it } from "vitest";

import {
  type Answers,
  answersFromRawInput,
  buildRawInput,
  buildSubmission,
  type ContactDraft,
  emptyContactDraft,
  hasSignal,
  initialAnswers,
  stepIsComplete,
} from "../lib/wizard";

// A fully-SKIPPED baseline; individual tests flip one step.
function base(): Answers {
  return initialAnswers(null);
}

describe("initialAnswers", () => {
  it("seeds TASK as ANSWERED when a use case is provided", () => {
    const a = initialAnswers("warehouse-logistics");
    expect(a.task.state).toBe("ANSWERED");
    expect(a.task.useCase).toBe("warehouse-logistics");
  });
  it("is all-SKIPPED with no seed", () => {
    const a = base();
    expect(Object.values(a).every((v) => v.state === "SKIPPED")).toBe(true);
  });
});

describe("hasSignal (mirrors the server rule)", () => {
  it("all SKIPPED → no signal", () => {
    expect(hasSignal(base())).toBe(false);
  });
  it("one ANSWERED → signal", () => {
    const a = base();
    a.industry = { state: "ANSWERED", value: "logistics" };
    expect(hasSignal(a)).toBe(true);
  });
  it("a lone UNKNOWN is a signal (distinct from skipping)", () => {
    const a = base();
    a.payload = { state: "UNKNOWN", value: "" };
    expect(hasSignal(a)).toBe(true);
  });
});

describe("buildSubmission — projection + data laws", () => {
  it("UNKNOWN and SKIPPED both omit the structured field but stay distinct in raw_input", () => {
    const a = base();
    a.payload = { state: "UNKNOWN", value: "" };
    a.environment = { state: "SKIPPED", value: "" };
    const sub = buildSubmission(a);
    expect(sub.payload_min_kg).toBeUndefined();
    expect(sub.environment).toBeUndefined();
    const ans = (sub.raw_input as { answers: Record<string, { state: string }> }).answers;
    expect(ans.payload.state).toBe("UNKNOWN");
    expect(ans.environment.state).toBe("SKIPPED");
  });

  it("manipulation FALSE survives as a real answer", () => {
    const a = base();
    a.manipulation = { state: "ANSWERED", value: false };
    expect(buildSubmission(a).manipulation_required).toBe(false);
  });

  it("no budget → no budget object (never a fabricated currency)", () => {
    const a = base();
    a.budget = { state: "SKIPPED", currency: "", min: "", max: "" };
    expect(buildSubmission(a).budget).toBeUndefined();
  });

  it("answered budget carries currency + amounts", () => {
    const a = base();
    a.budget = { state: "ANSWERED", currency: "EUR", min: "", max: "250000" };
    expect(buildSubmission(a).budget).toEqual({ currency: "EUR", min: null, max: 250000 });
  });

  it("explicit Unknown transaction → preferred_transaction UNKNOWN + ANSWERED raw", () => {
    const a = base();
    a.transaction = { state: "ANSWERED", value: "UNKNOWN" };
    const sub = buildSubmission(a);
    expect(sub.preferred_transaction).toBe("UNKNOWN");
    const ans = (sub.raw_input as { answers: Record<string, { state: string; value: string }> })
      .answers;
    expect(ans.transaction.state).toBe("ANSWERED");
    expect(ans.transaction.value).toBe("UNKNOWN");
    expect(hasSignal(a)).toBe(true);
  });

  it("skipped transaction defaults to UNKNOWN preference (SKIPPED raw)", () => {
    const a = base();
    const sub = buildSubmission(a);
    expect(sub.preferred_transaction).toBe("UNKNOWN");
    const ans = (sub.raw_input as { answers: Record<string, { state: string }> }).answers;
    expect(ans.transaction.state).toBe("SKIPPED");
  });

  it("D1-shaped: DE + logistics projects country code and use_case", () => {
    const a = initialAnswers("warehouse-logistics");
    a.country = { state: "ANSWERED", value: "DE" };
    a.industry = { state: "ANSWERED", value: "logistics" };
    const sub = buildSubmission(a);
    expect(sub.use_case).toBe("warehouse-logistics");
    expect(sub.country).toBe("DE");
    expect(sub.industry).toBe("logistics");
  });
});

describe("buildSubmission — contact identity (Find a Humanoid contact step)", () => {
  function contact(overrides: Partial<ContactDraft> = {}): ContactDraft {
    return { ...emptyContactDraft(), contact_name: "Jane Buyer", organization: "Acme",
      contact_email: "jane@example.com", ...overrides };
  }

  it("omitting the second argument sends empty identity (default = emptyContactDraft)", () => {
    const sub = buildSubmission(base());
    expect(sub.contact_name).toBe("");
    expect(sub.organization).toBe("");
    expect(sub.contact_email).toBe("");
    expect(sub).not.toHaveProperty("contact_phone");
  });

  it("a supplied contact draft is trimmed onto the submission", () => {
    const sub = buildSubmission(base(), contact({
      contact_name: "  Jane Buyer  ", organization: " Acme ", contact_email: " jane@example.com ",
    }));
    expect(sub.contact_name).toBe("Jane Buyer");
    expect(sub.organization).toBe("Acme");
    expect(sub.contact_email).toBe("jane@example.com");
  });

  it("blank telephone is omitted; a provided one is trimmed and sent", () => {
    expect(buildSubmission(base(), contact({ contact_phone: "  " }))).not.toHaveProperty(
      "contact_phone",
    );
    expect(buildSubmission(base(), contact({ contact_phone: " +44 20 7946 0958 " }))
      .contact_phone).toBe("+44 20 7946 0958");
  });
});

describe("buildRawInput", () => {
  it("is versioned and carries every answer key", () => {
    const raw = buildRawInput(base()) as {
      wizard_version: number;
      answers: Record<string, unknown>;
    };
    expect(raw.wizard_version).toBe(1);
    expect(Object.keys(raw.answers)).toHaveLength(11);
  });
});

describe("answersFromRawInput (Adjust Requirements prefill)", () => {
  it("round-trips states and values through buildRawInput", () => {
    const a = initialAnswers("warehouse-logistics");
    a.country = { state: "ANSWERED", value: "DE" };
    a.payload = { state: "UNKNOWN", value: "" };
    a.environment = { state: "SKIPPED", value: "" };
    a.manipulation = { state: "ANSWERED", value: false };
    a.budget = { state: "ANSWERED", currency: "EUR", min: "", max: "250000" };
    a.transaction = { state: "ANSWERED", value: "RENT" };

    const back = answersFromRawInput(buildRawInput(a));
    expect(back.task.state).toBe("ANSWERED");
    expect(back.task.useCase).toBe("warehouse-logistics");
    expect(back.country).toEqual({ state: "ANSWERED", value: "DE" });
    expect(back.payload.state).toBe("UNKNOWN");
    expect(back.environment.state).toBe("SKIPPED");
    expect(back.manipulation).toEqual({ state: "ANSWERED", value: false });
    expect(back.budget).toEqual({ state: "ANSWERED", currency: "EUR", min: "", max: "250000" });
    expect(back.transaction).toEqual({ state: "ANSWERED", value: "RENT" });
  });

  it("is robust to missing/garbage raw_input", () => {
    expect(answersFromRawInput(null).task.state).toBe("SKIPPED");
    expect(answersFromRawInput({}).country.state).toBe("SKIPPED");
    expect(answersFromRawInput({ answers: 5 }).budget.state).toBe("SKIPPED");
  });
});

describe("stepIsComplete (enables Next)", () => {
  it("budget needs currency + an amount + min<=max", () => {
    const a = base();
    a.budget = { state: "SKIPPED", currency: "", min: "", max: "100" };
    expect(stepIsComplete(a, "budget")).toBe(false); // no currency
    a.budget.currency = "USD";
    expect(stepIsComplete(a, "budget")).toBe(true);
    a.budget.min = "500"; // min > max
    expect(stepIsComplete(a, "budget")).toBe(false);
  });
  it("manipulation is complete once a boolean is chosen (incl false)", () => {
    const a = base();
    expect(stepIsComplete(a, "manipulation")).toBe(false);
    a.manipulation.value = false;
    expect(stepIsComplete(a, "manipulation")).toBe(true);
  });
});
