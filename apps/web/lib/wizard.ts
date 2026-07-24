// Buyer-intent wizard — pure state model + projection (no React, unit-tested).
//
// The wizard captures 12 steps of buyer intent. Every answer carries an explicit
// state so UNKNOWN and SKIPPED stay distinct (they are different demand signals
// even though both project to a NULL structured column). The versioned raw_input
// preserves that distinction; the structured fields are the projection the
// deterministic matcher (WS6) will read.
//
//   ANSWERED -> structured value + raw {state, value}
//   UNKNOWN  -> structured NULL   + raw {state: "UNKNOWN"}   (a real signal)
//   SKIPPED  -> structured NULL   + raw {state: "SKIPPED"}   (declined)

export type AnswerState = "ANSWERED" | "UNKNOWN" | "SKIPPED";

export const WIZARD_VERSION = 1;

export type StepKey =
  | "task"
  | "industry"
  | "country"
  | "environment"
  | "payload"
  | "hours"
  | "manipulation"
  | "autonomy"
  | "budget"
  | "timeline"
  | "transaction";

export interface Answers {
  task: { state: AnswerState; useCase: string; taskDescription: string };
  industry: { state: AnswerState; value: string };
  country: { state: AnswerState; value: string };
  environment: { state: AnswerState; value: string };
  payload: { state: AnswerState; value: string };
  hours: { state: AnswerState; value: string };
  manipulation: { state: AnswerState; value: boolean | null };
  autonomy: { state: AnswerState; value: string };
  budget: { state: AnswerState; currency: string; min: string; max: string };
  timeline: { state: AnswerState; value: string };
  transaction: { state: AnswerState; value: string };
}

// The 12 steps in frozen order. REVIEW (12) is not an answer, it is the submit
// gate; the first 11 keys map 1:1 to `Answers`.
export const STEP_TITLES: string[] = [
  "Task",
  "Industry",
  "Country",
  "Environment",
  "Payload",
  "Hours",
  "Manipulation",
  "Autonomy",
  "Budget",
  "Timeline",
  "Transaction",
  "Review",
];

export const ANSWER_KEYS: StepKey[] = [
  "task",
  "industry",
  "country",
  "environment",
  "payload",
  "hours",
  "manipulation",
  "autonomy",
  "budget",
  "timeline",
  "transaction",
];

export const AUTONOMY_OPTIONS: { value: string; label: string; hint: string }[] = [
  { value: "TELEOPERATED", label: "Teleoperated", hint: "Human in the loop, remote" },
  { value: "ASSISTED", label: "Assisted", hint: "Teleop with assists" },
  { value: "SUPERVISED_AUTONOMY", label: "Supervised", hint: "Autonomous under supervision" },
  { value: "TASK_AUTONOMOUS", label: "Task-autonomous", hint: "Autonomous for set tasks" },
  { value: "HIGHLY_AUTONOMOUS", label: "Highly autonomous", hint: "Minimal supervision" },
];

// transaction_preference enum values. "Unknown" is a first-class ANSWERED choice
// (distinct from skipping the step).
export const TRANSACTION_OPTIONS: { value: string; label: string; hint: string }[] = [
  { value: "BUY", label: "Buy", hint: "Outright unit purchase" },
  { value: "RENT", label: "Rent", hint: "Short-term paid use" },
  { value: "LEASE", label: "Lease", hint: "Long-term financed" },
  { value: "RAAS", label: "RaaS", hint: "Robots-as-a-service" },
  { value: "FLEXIBLE", label: "Flexible", hint: "Open to any model" },
  { value: "UNKNOWN", label: "Unknown", hint: "No preference yet" },
];

export function initialAnswers(seedUseCase?: string | null): Answers {
  const skipped: AnswerState = "SKIPPED";
  return {
    task: seedUseCase
      ? { state: "ANSWERED", useCase: seedUseCase, taskDescription: "" }
      : { state: skipped, useCase: "", taskDescription: "" },
    industry: { state: skipped, value: "" },
    country: { state: skipped, value: "" },
    environment: { state: skipped, value: "" },
    payload: { state: skipped, value: "" },
    hours: { state: skipped, value: "" },
    manipulation: { state: skipped, value: null },
    autonomy: { state: skipped, value: "" },
    budget: { state: skipped, currency: "", min: "", max: "" },
    timeline: { state: skipped, value: "" },
    transaction: { state: skipped, value: "" },
  };
}

function trimOrUndef(s: string): string | undefined {
  const t = s.trim();
  return t === "" ? undefined : t;
}

function numOrNull(s: string): number | null {
  const t = s.trim();
  return t === "" ? null : Number(t);
}

// The `raw_input` payload: full versioned answers, states preserved verbatim.
export function buildRawInput(a: Answers): Record<string, unknown> {
  const ans: Record<string, unknown> = {};

  ans.task =
    a.task.state === "ANSWERED"
      ? {
          state: "ANSWERED",
          use_case: a.task.useCase || null,
          task_description: a.task.taskDescription.trim() || null,
        }
      : { state: a.task.state };

  const simple = (v: { state: AnswerState; value: string }) =>
    v.state === "ANSWERED" ? { state: "ANSWERED", value: v.value.trim() || null } : { state: v.state };

  ans.industry = simple(a.industry);
  ans.country = a.country.state === "ANSWERED"
    ? { state: "ANSWERED", value: a.country.value || null }
    : { state: a.country.state };
  ans.environment = simple(a.environment);
  ans.payload = simple(a.payload);
  ans.hours = simple(a.hours);
  ans.manipulation =
    a.manipulation.state === "ANSWERED"
      ? { state: "ANSWERED", value: a.manipulation.value }
      : { state: a.manipulation.state };
  ans.autonomy = a.autonomy.state === "ANSWERED"
    ? { state: "ANSWERED", value: a.autonomy.value || null }
    : { state: a.autonomy.state };
  ans.budget =
    a.budget.state === "ANSWERED"
      ? {
          state: "ANSWERED",
          currency: a.budget.currency || null,
          min: numOrNull(a.budget.min),
          max: numOrNull(a.budget.max),
        }
      : { state: a.budget.state };
  ans.timeline = simple(a.timeline);
  ans.transaction = a.transaction.state === "ANSWERED"
    ? { state: "ANSWERED", value: a.transaction.value || null }
    : { state: a.transaction.state };

  return { wizard_version: WIZARD_VERSION, answers: ans };
}

export interface SubmissionBudget {
  currency?: string;
  min: number | null;
  max: number | null;
}

export interface Submission {
  use_case?: string;
  task_description?: string;
  industry?: string;
  country?: string;
  environment?: string;
  payload_min_kg?: number;
  operating_hours_day?: number;
  manipulation_required?: boolean;
  autonomy_required?: string;
  budget?: SubmissionBudget;
  required_by?: string;
  preferred_transaction: string;
  raw_input: Record<string, unknown>;
}

// Structured projection sent to POST /api/buyer-requirements. ANSWERED -> value;
// UNKNOWN/SKIPPED -> field omitted (server stores NULL). JSON.stringify drops the
// undefined keys, so `extra: forbid` on the API model stays happy.
export function buildSubmission(a: Answers): Submission {
  const s: Submission = {
    preferred_transaction:
      a.transaction.state === "ANSWERED" && a.transaction.value
        ? a.transaction.value
        : "UNKNOWN",
    raw_input: buildRawInput(a),
  };

  if (a.task.state === "ANSWERED") {
    if (a.task.useCase) s.use_case = a.task.useCase;
    const td = trimOrUndef(a.task.taskDescription);
    if (td) s.task_description = td;
  }
  if (a.industry.state === "ANSWERED") s.industry = trimOrUndef(a.industry.value);
  if (a.country.state === "ANSWERED" && a.country.value) s.country = a.country.value;
  if (a.environment.state === "ANSWERED") s.environment = trimOrUndef(a.environment.value);
  if (a.payload.state === "ANSWERED" && a.payload.value.trim() !== "")
    s.payload_min_kg = Number(a.payload.value);
  if (a.hours.state === "ANSWERED" && a.hours.value.trim() !== "")
    s.operating_hours_day = Number(a.hours.value);
  if (a.manipulation.state === "ANSWERED" && a.manipulation.value !== null)
    s.manipulation_required = a.manipulation.value;
  if (a.autonomy.state === "ANSWERED" && a.autonomy.value)
    s.autonomy_required = a.autonomy.value;
  if (a.budget.state === "ANSWERED") {
    s.budget = {
      currency: trimOrUndef(a.budget.currency),
      min: numOrNull(a.budget.min),
      max: numOrNull(a.budget.max),
    };
  }
  if (a.timeline.state === "ANSWERED" && a.timeline.value)
    s.required_by = a.timeline.value;

  return s;
}

// At least one requirement signal: any ANSWERED or UNKNOWN answer. All-SKIPPED
// (or untouched) is not a submittable requirement. Mirrors the server rule so the
// UI blocks before the round-trip.
export function hasSignal(a: Answers): boolean {
  return ANSWER_KEYS.some((k) => {
    const st = a[k].state;
    return st === "ANSWERED" || st === "UNKNOWN";
  });
}

// True when an ANSWERED step actually carries the value(s) it needs — used to
// enable "Next". Steps with no value must go through Unknown or Skip instead.
export function stepIsComplete(a: Answers, key: StepKey): boolean {
  switch (key) {
    case "task":
      return a.task.useCase.trim() !== "";
    case "industry":
      return a.industry.value.trim() !== "";
    case "country":
      return a.country.value.trim() !== "";
    case "environment":
      return a.environment.value.trim() !== "";
    case "payload":
      return a.payload.value.trim() !== "" && Number(a.payload.value) >= 0;
    case "hours":
      return a.hours.value.trim() !== "" && Number(a.hours.value) >= 0;
    case "manipulation":
      return a.manipulation.value !== null;
    case "autonomy":
      return a.autonomy.value.trim() !== "";
    case "budget": {
      const hasAmount = a.budget.min.trim() !== "" || a.budget.max.trim() !== "";
      const min = numOrNull(a.budget.min);
      const max = numOrNull(a.budget.max);
      const order = min === null || max === null || max >= min;
      return hasAmount && a.budget.currency.trim() !== "" && order;
    }
    case "timeline":
      return a.timeline.value.trim() !== "";
    case "transaction":
      return a.transaction.value.trim() !== "";
    default:
      return false;
  }
}
