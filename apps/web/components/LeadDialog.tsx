"use client";

// WS7 reusable commercial-lead form, rendered as a modal dialog. Used by every
// capture surface (matched card, whole shortlist, zero-match, Robot-Detail
// direct). NOTHING is written until submit; on success the server has created or
// extended exactly one commercial_lead. The copy is deliberately honest — we do
// NOT claim a provider was contacted / a quote requested / an introduction made.
//
// Accessibility: focus enters the form on open, Escape closes, focus returns to
// the trigger (the parent refocuses via onClose), errors are associated with
// their field, and Enter submits. A rapid double-submit fires exactly one POST.
import { useEffect, useId, useRef, useState } from "react";

import type { RegionListItem } from "@/lib/types";
import {
  buildSubmission,
  draftEmailError,
  emptyDraft,
  type LeadDraft,
  MAX_MESSAGE,
  MAX_NAME,
  MAX_ORG,
  TRANSACTION_OPTIONS,
} from "@/lib/lead-form";

export interface LeadDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  // A short line describing what the buyer is requesting help with (e.g. the
  // robot names). Purely informational.
  context?: string;
  requirementId: string | null;
  robotSlugs: string[];
  countries: RegionListItem[];
}

export function LeadDialog({
  open,
  onClose,
  title,
  context,
  requirementId,
  robotSlugs,
  countries,
}: LeadDialogProps) {
  const [draft, setDraft] = useState<LeadDraft>(emptyDraft);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const emailRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  // Synchronous re-entrancy guard (see Wizard.tsx): `submitting` updates async,
  // so two clicks in one tick would both read false; the ref blocks the second.
  const submittingRef = useRef(false);

  const emailErrId = useId();
  const titleId = useId();

  // Reset to a clean form whenever the dialog is (re)opened.
  useEffect(() => {
    if (open) {
      setDraft(emptyDraft());
      setError(null);
      setEmailError(null);
      setDone(false);
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [open]);

  // Move focus into the dialog on open (the email field, or the heading in the
  // success state).
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      if (done) headingRef.current?.focus();
      else emailRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, done]);

  // Escape to close + a simple focus trap that keeps Tab inside the dialog.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const focusable = root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  if (!open) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const emailErr = draftEmailError(draft);
    setEmailError(emailErr);
    if (emailErr) {
      emailRef.current?.focus();
      return;
    }
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/commercial-leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSubmission(draft, { requirementId, robotSlugs })),
      });
      // 201 (created) and 200 (existing requirement lead extended) both succeed.
      if (res.status === 201 || res.status === 200) {
        setDone(true);
        return;
      }
      let detail = "Request failed. Please try again.";
      try {
        const j = await res.json();
        if (typeof j?.detail === "string") detail = j.detail;
      } catch {
        /* non-JSON error body */
      }
      setError(detail); // keep the modal open and the entered data intact
    } catch {
      setError("Network error. Please try again.");
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  function set<K extends keyof LeadDraft>(k: K, v: string) {
    setDraft((prev) => ({ ...prev, [k]: v }));
  }

  return (
    <div
      className="lead-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="lead-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
      >
        <div className="lead-modal__head">
          <h2 id={titleId} ref={headingRef} tabIndex={-1} className="wz-confirm-title">
            {done ? "Request received" : title}
          </h2>
          <button
            type="button"
            className="lead-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {done ? (
          <div aria-live="polite">
            <p className="prose">
              We&apos;ve saved your requirement and robot interest. HumanoidOnline
              will review the relevant commercial paths and follow up by email.
            </p>
            <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
              <button type="button" className="btn btn--signal" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} noValidate>
            {context && <p className="note" style={{ marginTop: 0 }}>{context}</p>}

            <div className="field">
              <label htmlFor="lead-email">Email *</label>
              <input
                id="lead-email"
                ref={emailRef}
                type="email"
                required
                autoComplete="email"
                value={draft.contact_email}
                onChange={(e) => set("contact_email", e.target.value)}
                aria-invalid={emailError ? true : undefined}
                aria-describedby={emailError ? emailErrId : undefined}
              />
              {emailError && (
                <span id={emailErrId} className="field-error" role="alert">
                  {emailError}
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="lead-name">Name</label>
              <input
                id="lead-name"
                type="text"
                maxLength={MAX_NAME}
                autoComplete="name"
                value={draft.contact_name}
                onChange={(e) => set("contact_name", e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="lead-org">Organization</label>
              <input
                id="lead-org"
                type="text"
                maxLength={MAX_ORG}
                autoComplete="organization"
                value={draft.organization}
                onChange={(e) => set("organization", e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="lead-country">Country</label>
              <select
                id="lead-country"
                value={draft.country}
                onChange={(e) => set("country", e.target.value)}
              >
                <option value="">Not specified</option>
                {countries.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="lead-transaction">Preferred transaction</label>
              <select
                id="lead-transaction"
                value={draft.preferred_transaction}
                onChange={(e) => set("preferred_transaction", e.target.value)}
              >
                {TRANSACTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="lead-message">Message</label>
              <textarea
                id="lead-message"
                rows={4}
                maxLength={MAX_MESSAGE}
                value={draft.message}
                onChange={(e) => set("message", e.target.value)}
              />
            </div>

            {error && (
              <p className="field-error" role="alert" style={{ marginBottom: "var(--ho-sp-3)" }}>
                {error}
              </p>
            )}

            <div className="actions">
              <button
                type="submit"
                className="btn btn--signal"
                disabled={submitting}
              >
                {submitting ? "Sending…" : "Send request"}
              </button>
              <button type="button" className="btn btn--ghost" onClick={onClose}>
                Cancel
              </button>
            </div>
            <p className="note">
              // No checkout, no payment. This captures a qualified commercial
              inquiry only.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
