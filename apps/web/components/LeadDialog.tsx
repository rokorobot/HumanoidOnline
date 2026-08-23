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
  draftFromIdentity,
  draftNameError,
  draftOrganizationError,
  emptyDraft,
  type Identity,
  type LeadDraft,
  MAX_MESSAGE,
  MAX_NAME,
  MAX_ORG,
  MAX_PHONE,
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
  // Known identity from the Find a Humanoid contact step, when this dialog is
  // opened for a matched requirement — locks the identity fields to a
  // read-only summary (see isIdentityLocked) so the buyer never retypes, and
  // can never diverge from, what they already gave us. Absent/null with a
  // `requirementId` means this browser/session lost track of that identity
  // (see isIdentityUnknown) — the dialog then blocks submission entirely
  // rather than guess. Absent/null with `requirementId === null` (a direct
  // Robot-Detail "Request availability", no requirement context) keeps the
  // full editable form, as before.
  identity?: Identity | null;
}

// Requirement-linked contact identity is canonical once the Find a Humanoid
// CONTACT step (or an earlier lead capture) established it: capture_lead()'s
// identity-integrity guard (app/services/leads/service.py) 409s a
// requirement-linked submission whose contact_email doesn't match the
// lead's existing one — a later action on the SAME requirement must extend
// that identity, never silently replace it. Re-asking editable name/org/
// email fields here would let a buyer type a different email and hit that
// raw backend 409. Whenever both a `requirementId` AND a known `identity`
// are present, the three identity fields become a read-only summary instead
// of inputs — no second source of truth, `draft` (seeded from `identity`)
// still drives the submission. A direct Robot-Detail capture
// (`requirementId === null`) never has an `identity` to lock to and keeps
// the full editable form, unchanged.
function isIdentityLocked(requirementId: string | null, identity: Identity | null | undefined): boolean {
  return requirementId !== null && identity != null;
}

// The residual gap: `requirementId` is set but the sessionStorage bridge came
// up empty (new tab, browser restart, a copied/shared matches URL, private
// mode). Since the Find a Humanoid wizard now creates the commercial lead at
// its CONTACT step (see Wizard.tsx) — BEFORE /matches/[id] is ever reachable —
// every requirementId reaching this dialog already has a lead bound to it.
// Falling back to the editable form here would let a buyer type a *guessed*
// identity that capture_lead() must then judge against the real one, either
// silently extending on a lucky match or surfacing the raw "already bound to
// a different contact email" 409 on a miss — neither is an acceptable UX, and
// there is no non-PII signal anywhere in the current API surface (MatchResponse,
// RequirementRead) that would let the client tell in advance which outcome to
// expect. So this state doesn't collect or submit anything: no editable
// fields, no read-only summary (we don't know the identity to show), just an
// explanation and a way out. Closing this properly — e.g. letting the buyer
// re-verify and re-link — would need a new server data contract; this is the
// smallest safe UX on the existing one.
function isIdentityUnknown(requirementId: string | null, identity: Identity | null | undefined): boolean {
  return requirementId !== null && identity == null;
}

export function LeadDialog({
  open,
  onClose,
  title,
  context,
  requirementId,
  robotSlugs,
  countries,
  identity,
}: LeadDialogProps) {
  const [draft, setDraft] = useState<LeadDraft>(emptyDraft);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [orgError, setOrgError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const nameRef = useRef<HTMLInputElement>(null);
  const orgRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  // Synchronous re-entrancy guard (see Wizard.tsx): `submitting` updates async,
  // so two clicks in one tick would both read false; the ref blocks the second.
  const submittingRef = useRef(false);

  const nameErrId = useId();
  const orgErrId = useId();
  const emailErrId = useId();
  const titleId = useId();

  const identityLocked = isIdentityLocked(requirementId, identity);
  const identityUnknown = isIdentityUnknown(requirementId, identity);

  // Reset to a clean form whenever the dialog is (re)opened — prefilled from
  // the requirement's identity when we have one (still fully editable).
  useEffect(() => {
    if (open) {
      setDraft(draftFromIdentity(identity));
      setError(null);
      setNameError(null);
      setOrgError(null);
      setEmailError(null);
      setDone(false);
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [open, identity]);

  // Move focus into the dialog on open: the heading in the success state, the
  // first required field — full name — when it's editable, or the heading
  // itself when there is no field to focus (identity locked, or unknown).
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      if (done || identityLocked || identityUnknown) headingRef.current?.focus();
      else nameRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, done, identityLocked, identityUnknown]);

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
    // Defense in depth: this branch renders no <form> (see identityUnknown in
    // the JSX below), so this is structurally unreachable — but never submit
    // a guessed identity against a requirement whose real one we don't know.
    if (identityUnknown) return;
    // Required, in the order they appear in the form: full name, organization,
    // email. Set every field's error state (so all three show at once) but
    // focus only the FIRST invalid one. Skipped entirely when the identity is
    // locked — `draft` was seeded from an already-validated `identity`, and
    // there are no editable name/org/email inputs to focus an error on.
    if (!identityLocked) {
      const nameErr = draftNameError(draft);
      const orgErr = draftOrganizationError(draft);
      const emailErr = draftEmailError(draft);
      setNameError(nameErr);
      setOrgError(orgErr);
      setEmailError(emailErr);
      if (nameErr) {
        nameRef.current?.focus();
        return;
      }
      if (orgErr) {
        orgRef.current?.focus();
        return;
      }
      if (emailErr) {
        emailRef.current?.focus();
        return;
      }
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
    // The backdrop click-to-dismiss is a pointer-only convenience. Keyboard and
    // screen-reader users dismiss via Escape (handled above) or the labelled
    // "Close" button inside the dialog; exposing the whole backdrop as an
    // interactive control would announce a large spurious button to AT, which is
    // worse than the narrow suppression here (WS8.4 / R21 — narrowest documented
    // exception, not a blanket rule-off).
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
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
              will review the relevant commercial paths.
            </p>
            <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
              <button type="button" className="btn btn--signal" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : identityUnknown ? (
          // See isIdentityUnknown's comment: this requirement already has a
          // lead bound to it, but this browser/session doesn't know who
          // submitted it, so there is nothing safe to collect or submit here.
          <div aria-live="polite">
            {context && <p className="note" style={{ marginTop: 0 }}>{context}</p>}
            <p className="prose">
              This request already has a contact saved from when it was
              submitted. To add to it, please continue from the browser tab or
              session you originally used — this one can&apos;t confirm who
              submitted it, so we can&apos;t safely add to it here.
            </p>
            <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
              <button type="button" className="btn btn--ghost" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} noValidate>
            {context && <p className="note" style={{ marginTop: 0 }}>{context}</p>}

            {identityLocked ? (
              // Read-only summary, not editable inputs — see isIdentityLocked's
              // comment. `draft` (seeded from `identity`) is still the single
              // source of truth for what gets submitted; this only displays it.
              <div className="field lead-identity-locked">
                <p className="wz-qhelp" style={{ marginTop: 0 }}>
                  Submitting as <strong>{draft.contact_name}</strong>
                  {draft.organization ? <> · {draft.organization}</> : null}
                  {" · "}
                  {draft.contact_email}
                </p>
                <p className="note">
                  {"// This is the identity from your Find a Humanoid submission and can't be changed here."}
                </p>
              </div>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="lead-name">Full name *</label>
                  <input
                    id="lead-name"
                    ref={nameRef}
                    type="text"
                    required
                    maxLength={MAX_NAME}
                    autoComplete="name"
                    value={draft.contact_name}
                    onChange={(e) => set("contact_name", e.target.value)}
                    aria-invalid={nameError ? true : undefined}
                    aria-describedby={nameError ? nameErrId : undefined}
                  />
                  {nameError && (
                    <span id={nameErrId} className="field-error" role="alert">
                      {nameError}
                    </span>
                  )}
                </div>

                <div className="field">
                  <label htmlFor="lead-org">Company / organization *</label>
                  <input
                    id="lead-org"
                    ref={orgRef}
                    type="text"
                    required
                    maxLength={MAX_ORG}
                    autoComplete="organization"
                    value={draft.organization}
                    onChange={(e) => set("organization", e.target.value)}
                    aria-invalid={orgError ? true : undefined}
                    aria-describedby={orgError ? orgErrId : undefined}
                  />
                  {orgError && (
                    <span id={orgErrId} className="field-error" role="alert">
                      {orgError}
                    </span>
                  )}
                </div>

                <div className="field">
                  <label htmlFor="lead-email">Business email *</label>
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
              </>
            )}

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
              <label htmlFor="lead-phone">Telephone</label>
              <input
                id="lead-phone"
                type="tel"
                maxLength={MAX_PHONE}
                autoComplete="tel"
                value={draft.phone}
                onChange={(e) => set("phone", e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="lead-message">Additional message</label>
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
              {"// No checkout, no payment. This captures a qualified commercial inquiry only."}
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
