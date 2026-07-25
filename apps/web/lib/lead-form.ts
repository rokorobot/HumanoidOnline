// Pure state + validation for the WS7 commercial-lead form (mirrors lib/wizard.ts
// in spirit: no React, unit-tested separately from the component). Every commercial
// capture surface — matched card, whole shortlist, zero-match, Robot-Detail direct
// — builds its POST body through `buildSubmission`, so the client sends exactly the
// buyer-owned fields and nothing server-owned.

export interface LeadDraft {
  contact_email: string;
  contact_name: string;
  organization: string;
  country: string; // canonical COUNTRY region code, or "" (not specified)
  preferred_transaction: string; // "" (inherit) | RENT | BUY | LEASE | RAAS | FLEXIBLE
  message: string;
}

// Field caps mirror the API contract (§4) so the UI never lets a buyer type past
// what the server will accept.
export const MAX_NAME = 200;
export const MAX_ORG = 300;
export const MAX_MESSAGE = 4000;

// "" is the default: "no preference / same as requirement". The server treats an
// absent preference as inherit (requirement-linked) or UNKNOWN (direct capture),
// so we never send a fabricated value.
export const TRANSACTION_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "No preference" },
  { value: "BUY", label: "Buy" },
  { value: "RENT", label: "Rent" },
  { value: "LEASE", label: "Lease" },
  { value: "RAAS", label: "Robots-as-a-Service" },
  { value: "FLEXIBLE", label: "Flexible" },
];

// Same shape check as the backend (app/schemas/commercial_lead.py): one @, no
// surrounding whitespace, a dotted domain. Shape only — never proof of delivery.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function emptyDraft(): LeadDraft {
  return {
    contact_email: "",
    contact_name: "",
    organization: "",
    country: "",
    preferred_transaction: "",
    message: "",
  };
}

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

/** Client-side gate: only the email is required (identity is light-touch). */
export function draftEmailError(draft: LeadDraft): string | null {
  const email = draft.contact_email.trim();
  if (!email) return "Email is required.";
  if (!isValidEmail(email)) return "Enter a valid email address.";
  return null;
}

export interface LeadSubmission {
  requirement_id: string | null;
  contact_email: string;
  contact_name?: string;
  organization?: string;
  country?: string;
  robot_slugs: string[];
  preferred_transaction?: string;
  message?: string;
}

function clean(v: string): string | undefined {
  const t = v.trim();
  return t.length > 0 ? t : undefined;
}

/**
 * Build the POST body. `requirementId` is the /matches/[id] id (or null for a
 * direct Robot-Detail capture); `robotSlugs` is the selection for this surface
 * (one for a card, all for a shortlist, [] for zero-match). Blank optionals are
 * omitted rather than sent as "". No server-owned fields are ever included.
 */
export function buildSubmission(
  draft: LeadDraft,
  opts: { requirementId: string | null; robotSlugs: string[] },
): LeadSubmission {
  const body: LeadSubmission = {
    requirement_id: opts.requirementId,
    contact_email: draft.contact_email.trim(),
    robot_slugs: opts.robotSlugs,
  };
  const name = clean(draft.contact_name);
  if (name) body.contact_name = name;
  const org = clean(draft.organization);
  if (org) body.organization = org;
  const country = clean(draft.country);
  if (country) body.country = country;
  const pref = clean(draft.preferred_transaction);
  if (pref) body.preferred_transaction = pref;
  const message = clean(draft.message);
  if (message) body.message = message;
  return body;
}
