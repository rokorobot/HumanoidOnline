"use client";

// The 12-step Buyer-Intent wizard (WS5). Client-side draft only — NOTHING is
// written until the buyer submits at REVIEW, which POSTs exactly one
// buyer_requirement. UNKNOWN and SKIP are separate, explicit actions on every
// step (on TRANSACTION, "Unknown" is a first-class choice). On success it shows
// an interim capture confirmation — matching (SEE MATCHES / /matches) is WS6.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { SectionIndex } from "@/components/SectionIndex";
import { SystemLabel } from "@/components/SystemLabel";
import type { RegionListItem, UseCaseListItem } from "@/lib/types";
import {
  ANSWER_KEYS,
  AUTONOMY_OPTIONS,
  type AnswerState,
  type Answers,
  buildSubmission,
  hasSignal,
  initialAnswers,
  STEP_TITLES,
  type StepKey,
  stepIsComplete,
  TRANSACTION_OPTIONS,
} from "@/lib/wizard";

const REVIEW_INDEX = 11; // steps 0..10 are questions; 11 is REVIEW

interface WizardProps {
  useCases: UseCaseListItem[];
  countries: RegionListItem[];
  seedUseCase: string | null;
}

const QUESTION: Record<StepKey, { label: string; help: string }> = {
  task: {
    label: "What do you need the robot to do?",
    help: "Pick the closest application. Add a specific task if you can.",
  },
  industry: { label: "What industry is this for?", help: "Free text — e.g. logistics, manufacturing." },
  country: { label: "Where will it be deployed?", help: "The country of deployment." },
  environment: { label: "What is the operating environment?", help: "e.g. indoor warehouse, outdoor, cleanroom." },
  payload: { label: "Minimum payload required?", help: "In kilograms. Leave to Unknown if not sure." },
  hours: { label: "Operating hours per day?", help: "Expected daily duty cycle, in hours." },
  manipulation: { label: "Is manipulation required?", help: "Does the task need the robot to grasp / handle objects?" },
  autonomy: { label: "What autonomy level do you need?", help: "How much human supervision is acceptable." },
  budget: { label: "What is your budget?", help: "State a currency and a min and/or max. No budget? Skip or Unknown." },
  timeline: { label: "When do you need it deployed?", help: "Target deployment date." },
  transaction: {
    label: "How would you prefer to obtain it?",
    help: "Captured as demand intelligence before transaction products exist. Unknown is a valid, first-class answer.",
  },
};

export function Wizard({ useCases, countries, seedUseCase }: WizardProps) {
  const [answers, setAnswers] = useState<Answers>(() => initialAnswers(seedUseCase));
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captured, setCaptured] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // Synchronous re-entrancy guard: `submitting` state updates async, so two
  // clicks in the same tick would both read it as false. The ref blocks the
  // second call immediately, so a rapid double-submit fires exactly one POST.
  const submittingRef = useRef(false);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step, captured]);

  const useCaseName = (slug: string) =>
    useCases.find((u) => u.slug === slug)?.name ?? slug;
  const countryName = (code: string) =>
    countries.find((c) => c.code === code)?.name ?? code;
  const industryOptions = Array.from(
    new Set(useCases.map((u) => u.category).filter(Boolean) as string[]),
  );

  function patch<K extends StepKey>(k: K, p: Partial<Answers[K]>) {
    setAnswers((prev) => ({ ...prev, [k]: { ...prev[k], ...p } }));
  }
  function commit(k: StepKey, state: AnswerState) {
    setAnswers((prev) => ({ ...prev, [k]: { ...prev[k], state } }));
    setStep((s) => Math.min(s + 1, REVIEW_INDEX));
  }
  const back = () => setStep((s) => Math.max(s - 1, 0));

  async function submit() {
    if (submittingRef.current || !hasSignal(answers)) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/buyer-requirements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSubmission(answers)),
      });
      if (res.status === 201) {
        setCaptured(true);
        return;
      }
      let detail = "Submission failed. Please try again.";
      try {
        const j = await res.json();
        if (typeof j?.detail === "string") detail = j.detail;
      } catch {
        /* non-JSON error body */
      }
      setError(detail);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  function reset() {
    setAnswers(initialAnswers(null));
    setStep(0);
    setCaptured(false);
    setError(null);
  }

  // ---- interim capture confirmation (matching is WS6) --------------------
  if (captured) {
    return (
      <section className="wz-confirm" aria-live="polite">
        <SectionIndex>REQUIREMENT CAPTURED</SectionIndex>
        <h2 ref={headingRef} tabIndex={-1} className="wz-confirm-title">
          Requirement captured
        </h2>
        <p className="prose">Matching has not been generated yet.</p>
        <p className="note">
          {/* WS6 replaces this with real, explainable matches. */}
          // Your requirement is saved. We will generate ranked matches in a later step.
        </p>
        <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
          <Link className="btn btn--signal" href="/robots">
            Browse robots →
          </Link>
          <button className="btn" type="button" onClick={reset}>
            Start another requirement
          </button>
        </div>
      </section>
    );
  }

  const key = step < REVIEW_INDEX ? ANSWER_KEYS[step] : null;
  const pct = Math.round(((step + 1) / STEP_TITLES.length) * 100);

  return (
    <div className="wz" role="group" aria-label="Requirement wizard">
      <aside className="wz-steps" aria-label="Steps">
        <div className="wz-steps-head">
          <SystemLabel>Requirements</SystemLabel>
        </div>
        {STEP_TITLES.map((title, i) => {
          const cls =
            i === step ? "wz-step current" : i < step ? "wz-step done" : "wz-step";
          return (
            <div key={title} className={cls} aria-current={i === step ? "step" : undefined}>
              <span className="n">{String(i + 1).padStart(2, "0")}</span>
              {title}
            </div>
          );
        })}
      </aside>

      <section className="wz-panel">
        <div className="wz-progress">
          <span className="lab">
            Step {step + 1} / {STEP_TITLES.length}
          </span>
          <div className="wz-pbar" aria-hidden="true">
            {STEP_TITLES.map((t, i) => (
              <i
                key={t}
                className={
                  i <= step ? (i === REVIEW_INDEX ? "on last" : "on") : undefined
                }
              />
            ))}
          </div>
          <span className="lab">{pct}%</span>
        </div>

        {key ? (
          <>
            <h2 ref={headingRef} tabIndex={-1} className="wz-qlabel">
              {QUESTION[key].label}
            </h2>
            <p className="wz-qhelp">{QUESTION[key].help}</p>

            {renderQuestion()}

            <div className="wz-navrow">
              <button
                className="btn btn--ghost"
                type="button"
                onClick={back}
                disabled={step === 0}
              >
                ← Back
              </button>
              <div className="wz-navrow-right">
                {key !== "transaction" && (
                  <button
                    className="btn btn--ghost"
                    type="button"
                    onClick={() => commit(key, "UNKNOWN")}
                  >
                    Unknown
                  </button>
                )}
                <button
                  className="btn btn--ghost"
                  type="button"
                  onClick={() => commit(key, "SKIPPED")}
                >
                  Skip
                </button>
                <button
                  className="btn btn--signal"
                  type="button"
                  onClick={() => commit(key, "ANSWERED")}
                  disabled={!stepIsComplete(answers, key)}
                >
                  Next →
                </button>
              </div>
            </div>
          </>
        ) : (
          renderReview()
        )}
      </section>
    </div>
  );

  function renderQuestion() {
    switch (key) {
      case "task":
        return (
          <>
            <div className="field">
              <label htmlFor="wz-usecase">Use case</label>
              <select
                id="wz-usecase"
                value={answers.task.useCase}
                onChange={(e) => patch("task", { useCase: e.target.value })}
              >
                <option value="">Select a use case…</option>
                {useCases.map((u) => (
                  <option key={u.slug} value={u.slug}>
                    {u.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="wz-task">Specific task (optional)</label>
              <textarea
                id="wz-task"
                rows={2}
                value={answers.task.taskDescription}
                placeholder="e.g. Move totes from conveyor to pallets"
                onChange={(e) => patch("task", { taskDescription: e.target.value })}
              />
            </div>
          </>
        );
      case "industry":
        return (
          <div className="field">
            <label htmlFor="wz-industry">Industry</label>
            <input
              id="wz-industry"
              type="text"
              list="wz-industry-opts"
              value={answers.industry.value}
              placeholder="e.g. logistics"
              onChange={(e) => patch("industry", { value: e.target.value })}
            />
            <datalist id="wz-industry-opts">
              {industryOptions.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
        );
      case "country":
        return (
          <div className="field">
            <label htmlFor="wz-country">Country of deployment</label>
            <select
              id="wz-country"
              value={answers.country.value}
              onChange={(e) => patch("country", { value: e.target.value })}
            >
              <option value="">Select a country…</option>
              {countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        );
      case "environment":
        return (
          <div className="field">
            <label htmlFor="wz-env">Environment</label>
            <input
              id="wz-env"
              type="text"
              value={answers.environment.value}
              placeholder="e.g. indoor warehouse"
              onChange={(e) => patch("environment", { value: e.target.value })}
            />
          </div>
        );
      case "payload":
        return (
          <div className="field">
            <label htmlFor="wz-payload">Minimum payload (kg)</label>
            <input
              id="wz-payload"
              type="number"
              min={0}
              step={0.1}
              value={answers.payload.value}
              placeholder="e.g. 10"
              onChange={(e) => patch("payload", { value: e.target.value })}
            />
          </div>
        );
      case "hours":
        return (
          <div className="field">
            <label htmlFor="wz-hours">Operating hours / day</label>
            <input
              id="wz-hours"
              type="number"
              min={0}
              max={24}
              step={0.5}
              value={answers.hours.value}
              placeholder="e.g. 16"
              onChange={(e) => patch("hours", { value: e.target.value })}
            />
          </div>
        );
      case "manipulation":
        return (
          <div className="wz-choices" role="radiogroup" aria-label="Manipulation required">
            <ManipChoice
              label="Required"
              hint="Must grasp / handle objects"
              selected={answers.manipulation.value === true}
              onClick={() => patch("manipulation", { value: true })}
            />
            <ManipChoice
              label="Not required"
              hint="No object handling needed"
              selected={answers.manipulation.value === false}
              onClick={() => patch("manipulation", { value: false })}
            />
          </div>
        );
      case "autonomy":
        return (
          <div className="field">
            <label htmlFor="wz-autonomy">Autonomy level</label>
            <select
              id="wz-autonomy"
              value={answers.autonomy.value}
              onChange={(e) => patch("autonomy", { value: e.target.value })}
            >
              <option value="">Select an autonomy level…</option>
              {AUTONOMY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label} — {o.hint}
                </option>
              ))}
            </select>
          </div>
        );
      case "budget":
        return (
          <div className="wz-budget">
            <div className="field">
              <label htmlFor="wz-cur">Currency</label>
              <input
                id="wz-cur"
                type="text"
                maxLength={3}
                style={{ textTransform: "uppercase" }}
                value={answers.budget.currency}
                placeholder="USD"
                onChange={(e) =>
                  patch("budget", { currency: e.target.value.toUpperCase() })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="wz-bmin">Min</label>
              <input
                id="wz-bmin"
                type="number"
                min={0}
                value={answers.budget.min}
                placeholder="—"
                onChange={(e) => patch("budget", { min: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="wz-bmax">Max</label>
              <input
                id="wz-bmax"
                type="number"
                min={0}
                value={answers.budget.max}
                placeholder="e.g. 250000"
                onChange={(e) => patch("budget", { max: e.target.value })}
              />
            </div>
          </div>
        );
      case "timeline":
        return (
          <div className="field">
            <label htmlFor="wz-date">Required by</label>
            <input
              id="wz-date"
              type="date"
              value={answers.timeline.value}
              onChange={(e) => patch("timeline", { value: e.target.value })}
            />
          </div>
        );
      case "transaction":
        return (
          <div className="wz-choices" role="radiogroup" aria-label="Transaction preference">
            {TRANSACTION_OPTIONS.map((o) => {
              const sel = answers.transaction.value === o.value;
              return (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={sel}
                  className={sel ? "wz-choice sel" : "wz-choice"}
                  onClick={() => patch("transaction", { value: o.value })}
                >
                  <span className="big">{o.label}</span>
                  <span className="d">{o.hint}</span>
                </button>
              );
            })}
          </div>
        );
      default:
        return null;
    }
  }

  function summarize(k: StepKey): { state: AnswerState; text: string } {
    const a = answers[k];
    if (a.state !== "ANSWERED") return { state: a.state, text: "" };
    switch (k) {
      case "task": {
        const t = answers.task;
        return {
          state: "ANSWERED",
          text: t.taskDescription.trim()
            ? `${useCaseName(t.useCase)} — ${t.taskDescription.trim()}`
            : useCaseName(t.useCase),
        };
      }
      case "country":
        return { state: "ANSWERED", text: countryName(answers.country.value) };
      case "manipulation":
        return {
          state: "ANSWERED",
          text: answers.manipulation.value ? "Required" : "Not required",
        };
      case "autonomy":
        return {
          state: "ANSWERED",
          text:
            AUTONOMY_OPTIONS.find((o) => o.value === answers.autonomy.value)?.label ??
            answers.autonomy.value,
        };
      case "budget": {
        const b = answers.budget;
        return {
          state: "ANSWERED",
          text: `${b.currency} ${b.min.trim() || "—"}–${b.max.trim() || "—"}`,
        };
      }
      case "transaction":
        return {
          state: "ANSWERED",
          text:
            TRANSACTION_OPTIONS.find((o) => o.value === answers.transaction.value)
              ?.label ?? answers.transaction.value,
        };
      case "payload":
        return { state: "ANSWERED", text: `${answers.payload.value} kg` };
      case "hours":
        return { state: "ANSWERED", text: `${answers.hours.value} h/day` };
      default:
        return { state: "ANSWERED", text: (a as { value: string }).value };
    }
  }

  function renderReview() {
    const signal = hasSignal(answers);
    return (
      <div className="wz-review">
        <h2 ref={headingRef} tabIndex={-1} className="wz-qlabel">
          Review &amp; submit
        </h2>
        <p className="wz-qhelp">
          Unknown and Skipped are recorded as distinct signals. Submitting saves
          your requirement — nothing is written until you do.
        </p>

        <dl className="wz-review-list">
          {ANSWER_KEYS.map((k, i) => {
            const { state, text } = summarize(k);
            return (
              <div key={k} className="wz-review-row">
                <dt>
                  <span className="n">{String(i + 1).padStart(2, "0")}</span>{" "}
                  {STEP_TITLES[i]}
                </dt>
                <dd>
                  {state === "ANSWERED" ? (
                    <span className="wz-answered">{text}</span>
                  ) : (
                    <span className={`wz-badge wz-badge--${state.toLowerCase()}`}>
                      {state === "UNKNOWN" ? "Unknown" : "Skipped"}
                    </span>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>

        {!signal && (
          <p className="wz-error" role="alert">
            Answer at least one step (or mark it Unknown) before submitting.
          </p>
        )}
        {error && (
          <p className="wz-error" role="alert">
            {error}
          </p>
        )}

        <div className="wz-navrow">
          <button className="btn btn--ghost" type="button" onClick={back}>
            ← Back
          </button>
          <button
            className="btn btn--signal"
            type="button"
            onClick={submit}
            disabled={submitting || !signal}
          >
            {submitting ? "Submitting…" : "Submit requirements"}
          </button>
        </div>
      </div>
    );
  }
}

// A manipulation choice. Clicking only sets the value; "Next" commits ANSWERED,
// so the buyer can still choose Unknown/Skip afterwards (UNKNOWN != a FALSE answer).
function ManipChoice({
  label,
  hint,
  selected,
  onClick,
}: {
  label: string;
  hint: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={selected ? "wz-choice sel" : "wz-choice"}
      onClick={onClick}
    >
      <span className="big">{label}</span>
      <span className="d">{hint}</span>
    </button>
  );
}
