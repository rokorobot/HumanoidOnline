/**
 * /contact — Netlify Forms contact form (crawler contact mechanism, docs/16 §13).
 *
 * Netlify detects forms only in static HTML at deploy time, so the live React
 * form must match public/__forms.html exactly (name, fields, honeypot, options)
 * and POST there. These tests hold that contract, plus accessibility, the
 * validation, success and failure states, and "no mailto anywhere".
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ContactPage from "@/app/contact/page";
import { ContactForm } from "@/components/ContactForm";
import {
  CONTACT_CATEGORIES,
  CONTACT_FIELDS,
  CONTACT_FORM_ENDPOINT,
  CONTACT_FORM_NAME,
  CONTACT_HONEYPOT_FIELD,
} from "@/lib/contact-form";

const STATIC_FORMS = readFileSync(resolve(process.cwd(), "public/__forms.html"), "utf8");

function staticForm(): HTMLFormElement {
  const doc = new DOMParser().parseFromString(STATIC_FORMS, "text/html");
  const form = doc.querySelector<HTMLFormElement>(`form[name="${CONTACT_FORM_NAME}"]`);
  if (!form) throw new Error("contact form missing from public/__forms.html");
  return form;
}

function fill(values: Partial<Record<"name" | "email" | "category" | "message", string>>) {
  if (values.name !== undefined)
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: values.name } });
  if (values.email !== undefined)
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: values.email } });
  if (values.category !== undefined)
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: values.category } });
  if (values.message !== undefined)
    fireEvent.change(screen.getByLabelText(/^Message/), { target: { value: values.message } });
}

const VALID = {
  name: "Site Owner",
  email: "owner@example.com",
  category: "Crawler opt-out / rate-limit request",
  message: "Please exclude example.com.",
};

describe("/contact", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders with accessible, required fields", () => {
    render(<ContactPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Contact HumanoidOnline" })).toBeTruthy();
    for (const label of ["Name", "Email", "Reason"]) {
      const field = screen.getByLabelText(label);
      expect(field.hasAttribute("required")).toBe(true);
    }
    expect(screen.getByLabelText(/^Message/).hasAttribute("required")).toBe(true);
    expect(screen.getByLabelText("Email").getAttribute("type")).toBe("email");
    expect(screen.getByRole("button", { name: "Send message" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "crawler policy" }).getAttribute("href")).toBe(
      "/crawler-policy",
    );
  });

  it("offers the crawler categories", () => {
    render(<ContactForm />);
    const options = Array.from(
      (screen.getByLabelText("Reason") as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toEqual(["", ...CONTACT_CATEGORIES]);
    expect(options).toContain("Crawler / robots");
    expect(options).toContain("Crawler opt-out / rate-limit request");
  });

  it("carries the Netlify Forms metadata and a hidden honeypot", () => {
    const { container } = render(<ContactForm />);
    const form = container.querySelector("form")!;
    expect(form.getAttribute("name")).toBe(CONTACT_FORM_NAME);
    expect(form.getAttribute("data-netlify")).toBe("true");
    expect(form.getAttribute("data-netlify-honeypot")).toBe(CONTACT_HONEYPOT_FIELD);
    expect(form.getAttribute("action")).toBe(CONTACT_FORM_ENDPOINT);
    const hidden = form.querySelector<HTMLInputElement>('input[name="form-name"]')!;
    expect(hidden.type).toBe("hidden");
    expect(hidden.value).toBe(CONTACT_FORM_NAME);
    const trap = form.querySelector(`input[name="${CONTACT_HONEYPOT_FIELD}"]`)!;
    expect(trap.closest("[aria-hidden='true']")).not.toBeNull();
    expect(trap.getAttribute("tabindex")).toBe("-1");
  });

  it("matches the static detection copy Netlify parses at deploy time", () => {
    const form = staticForm();
    expect(form.getAttribute("data-netlify")).toBe("true");
    expect(form.getAttribute("data-netlify-honeypot")).toBe(CONTACT_HONEYPOT_FIELD);
    const names = Array.from(form.querySelectorAll("[name]")).map((el) => el.getAttribute("name"));
    expect(new Set(names)).toEqual(
      new Set(["form-name", CONTACT_HONEYPOT_FIELD, ...CONTACT_FIELDS]),
    );
    const options = Array.from(form.querySelectorAll("select[name=category] option")).map(
      (o) => o.getAttribute("value"),
    );
    expect(options).toEqual([...CONTACT_CATEGORIES]);

    const { container } = render(<ContactForm />);
    const live = Array.from(container.querySelectorAll("form [name]")).map((el) =>
      el.getAttribute("name"),
    );
    expect(new Set(live)).toEqual(new Set(names));
  });

  it("validates before sending and never posts an invalid form", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactForm />);
    fill({ email: "not-an-email" });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Enter your name.")).toBeTruthy();
    expect(screen.getByText(/Enter a valid email address/)).toBeTruthy();
    expect(screen.getByText("Choose a reason for contacting us.")).toBeTruthy();
    expect(screen.getByText("Enter a message.")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText("Name"));
    const describedBy = screen.getByLabelText("Email").getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy.split(" ").at(-1)!)?.textContent).toMatch(
      /valid email/,
    );
  });

  it("posts URL-encoded to the Netlify endpoint and shows a success state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactForm />);
    fill(VALID);
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Message sent" })).toBeTruthy();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(CONTACT_FORM_ENDPOINT);
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    const body = new URLSearchParams(init.body);
    expect(body.get("form-name")).toBe(CONTACT_FORM_NAME);
    expect(body.get("category")).toBe(VALID.category);
    expect(body.get("email")).toBe(VALID.email);
    expect(body.get(CONTACT_HONEYPOT_FIELD)).toBe("");
  });

  it("shows a clear failure state and keeps the message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    render(<ContactForm />);
    fill(VALID);
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("could not be sent");
    expect((screen.getByLabelText(/^Message/) as HTMLTextAreaElement).value).toBe(VALID.message);
    expect(screen.getByRole("button", { name: "Send message" })).toBeTruthy();
  });

  it("publishes no email address", () => {
    const { container } = render(<ContactPage />);
    expect(container.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
    expect(container.textContent).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
    expect(STATIC_FORMS).not.toMatch(/mailto:|@humanoid|@gmail/);
  });
});
