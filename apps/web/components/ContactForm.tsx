"use client";

// Contact form — submitted through Netlify Forms, with no backend of our own.
//
// Netlify's Next.js runtime detects forms from STATIC HTML at deploy time, so
// the form is declared in public/__forms.html and this component POSTs to that
// file (URL-encoded, with `form-name`). A client-rendered form alone would never
// be detected. The honeypot field is Netlify's standard spam trap: people never
// see it, and a submission that fills it in is discarded.
import { type FormEvent, useId, useRef, useState } from "react";

import {
  CONTACT_CATEGORIES,
  CONTACT_FORM_ENDPOINT,
  CONTACT_FORM_NAME,
  CONTACT_HONEYPOT_FIELD,
  CONTACT_MAX_MESSAGE,
  CONTACT_MAX_NAME,
} from "@/lib/contact-form";

type Status = "idle" | "sending" | "sent" | "failed";
type Errors = Partial<Record<"name" | "email" | "category" | "message", string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(data: FormData): Errors {
  const errors: Errors = {};
  const name = String(data.get("name") ?? "").trim();
  const email = String(data.get("email") ?? "").trim();
  const category = String(data.get("category") ?? "");
  const message = String(data.get("message") ?? "").trim();
  if (!name) errors.name = "Enter your name.";
  if (!email) errors.email = "Enter your email address.";
  else if (!EMAIL.test(email)) errors.email = "Enter a valid email address, like name@example.com.";
  if (!(CONTACT_CATEGORIES as readonly string[]).includes(category)) {
    errors.category = "Choose a reason for contacting us.";
  }
  if (!message) errors.message = "Enter a message.";
  return errors;
}

export function ContactForm() {
  const uid = useId();
  const ids = {
    name: `${uid}-name`,
    email: `${uid}-email`,
    category: `${uid}-category`,
    message: `${uid}-message`,
  };
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Errors>({});
  const formRef = useRef<HTMLFormElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const found = validate(data);
    setErrors(found);
    const first = (Object.keys(found) as (keyof Errors)[])[0];
    if (first) {
      form.ownerDocument.getElementById(ids[first])?.focus();
      return;
    }
    setStatus("sending");
    try {
      const body = new URLSearchParams();
      data.forEach((value, key) => body.append(key, String(value)));
      const response = await fetch(CONTACT_FORM_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setStatus("sent");
      formRef.current?.reset();
    } catch {
      setStatus("failed");
    }
    requestAnimationFrame(() => statusRef.current?.focus());
  }

  if (status === "sent") {
    return (
      <div ref={statusRef} tabIndex={-1} role="status" className="contact-status contact-status--ok">
        <h2>Message sent</h2>
        <p className="prose">
          Thank you. Your message has reached the HumanoidOnline team. If you asked a question,
          we will reply to the email address you gave.
        </p>
        <button type="button" className="btn btn--ghost" onClick={() => setStatus("idle")}>
          Send another message
        </button>
      </div>
    );
  }

  const describe = (field: keyof Errors, hint?: string) =>
    [hint, errors[field] ? `${ids[field]}-error` : undefined].filter(Boolean).join(" ") ||
    undefined;

  return (
    <form
      ref={formRef}
      name={CONTACT_FORM_NAME}
      method="POST"
      action={CONTACT_FORM_ENDPOINT}
      data-netlify="true"
      data-netlify-honeypot={CONTACT_HONEYPOT_FIELD}
      noValidate
      onSubmit={onSubmit}
      className="contact-form"
      aria-describedby={`${uid}-required`}
    >
      <input type="hidden" name="form-name" value={CONTACT_FORM_NAME} />
      <p className="contact-honeypot" aria-hidden="true">
        <label>
          Leave this field empty
          <input name={CONTACT_HONEYPOT_FIELD} tabIndex={-1} autoComplete="off" />
        </label>
      </p>
      <p id={`${uid}-required`} className="note">
        All fields are required.
      </p>

      {status === "failed" && (
        <div
          ref={statusRef}
          tabIndex={-1}
          role="alert"
          className="contact-status contact-status--error"
        >
          <p>
            Your message could not be sent. Please try again in a few minutes. If you want to
            exclude or slow down our crawler, the robots.txt rules on the crawler policy page
            work without contacting us.
          </p>
        </div>
      )}

      <div className="field">
        <label htmlFor={ids.name}>Name</label>
        <input
          id={ids.name}
          name="name"
          type="text"
          required
          maxLength={CONTACT_MAX_NAME}
          autoComplete="name"
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={describe("name")}
        />
        {errors.name && (
          <span id={`${ids.name}-error`} className="field-error">
            {errors.name}
          </span>
        )}
      </div>

      <div className="field">
        <label htmlFor={ids.email}>Email</label>
        <input
          id={ids.email}
          name="email"
          type="email"
          required
          autoComplete="email"
          inputMode="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={describe("email")}
        />
        {errors.email && (
          <span id={`${ids.email}-error`} className="field-error">
            {errors.email}
          </span>
        )}
      </div>

      <div className="field">
        <label htmlFor={ids.category}>Reason</label>
        <select
          id={ids.category}
          name="category"
          required
          defaultValue=""
          aria-invalid={errors.category ? true : undefined}
          aria-describedby={describe("category")}
        >
          <option value="" disabled>
            Choose a reason
          </option>
          {CONTACT_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
        {errors.category && (
          <span id={`${ids.category}-error`} className="field-error">
            {errors.category}
          </span>
        )}
      </div>

      <div className="field">
        <label htmlFor={ids.message}>Message</label>
        <textarea
          id={ids.message}
          name="message"
          required
          rows={7}
          maxLength={CONTACT_MAX_MESSAGE}
          aria-invalid={errors.message ? true : undefined}
          aria-describedby={describe("message", `${uid}-message-hint`)}
        />
        <span id={`${uid}-message-hint`} className="note">
          For a crawler request, include your site&apos;s domain.
        </span>
        {errors.message && (
          <span id={`${ids.message}-error`} className="field-error">
            {errors.message}
          </span>
        )}
      </div>

      <div className="actions">
        <button type="submit" className="btn btn--signal" disabled={status === "sending"}>
          {status === "sending" ? "Sending…" : "Send message"}
        </button>
      </div>
    </form>
  );
}
