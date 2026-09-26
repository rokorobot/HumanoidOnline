// The /contact form's Netlify Forms contract, shared by the React form
// (components/ContactForm.tsx) and the static detection copy
// (public/__forms.html). Netlify only processes fields it saw in the static
// copy at deploy time, so both must use exactly these names; the test
// __tests__/contact-form.test.tsx fails if they drift apart.
export const CONTACT_FORM_NAME = "contact";
/** Static file the form is detected in and POSTed to (Netlify Next.js runtime v5). */
export const CONTACT_FORM_ENDPOINT = "/__forms.html";
export const CONTACT_HONEYPOT_FIELD = "bot-field";
export const CONTACT_FIELDS = ["name", "email", "category", "message"] as const;

export const CONTACT_CATEGORIES = [
  "General inquiry",
  "Data correction",
  "Manufacturer / provider",
  "Crawler / robots",
  "Crawler opt-out / rate-limit request",
] as const;

export const CONTACT_MAX_NAME = 200;
export const CONTACT_MAX_MESSAGE = 5000;
