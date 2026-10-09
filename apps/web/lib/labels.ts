// Buyer-facing labels for database enums (UX-01 / P0-B).
//
// SCOPE: visible human UI only. Machine surfaces (llms.txt, JSON-LD, the Europe
// research JSON, CitationFacts, API payloads, URL/query params and form VALUES)
// keep the raw enum verbatim - never route them through this module. Wherever a
// label replaces an enum in the DOM, the raw value rides along as
// `data-enum="RAW"` so traceability and tests are preserved.
//
// Mappings are total over the frozen enums in db/schema.sql / docs/03; an
// unrecognised token falls back to a readable Title Case form and is never
// dropped, so a new enum value degrades to prose rather than disappearing.

export type EnumKind =
  | "commercial_status"
  | "availability_status"
  | "price_type"
  | "autonomy"
  | "mobility"
  | "transaction"
  | "source_type"
  | "confidence"
  | "capability_category"
  | "provider_type";

const LABELS: Record<EnumKind, Record<string, string>> = {
  commercial_status: {
    UNKNOWN: "Status not verified",
    ANNOUNCED: "Announced",
    DEVELOPMENT: "In development",
    PROTOTYPE: "Prototype",
    PILOT: "Pilot",
    EARLY_ACCESS: "Early access",
    LIMITED_COMMERCIAL: "Limited commercial availability",
    COMMERCIAL: "Commercial",
    RAAS_DEPLOYMENT: "Robot-as-a-service",
    DISCONTINUED: "Discontinued",
  },
  availability_status: {
    NOT_AVAILABLE: "Not available",
    WAITLIST: "Waitlist",
    PREORDER: "Pre-order",
    LIMITED: "Limited availability",
    AVAILABLE: "Available",
    ON_REQUEST: "Availability on request",
    DISCONTINUED: "Discontinued",
  },
  price_type: {
    PUBLIC: "Published price",
    FROM: "From price",
    RANGE: "Price range",
    ESTIMATED: "Estimated price",
    MANUFACTURER_ESTIMATE: "Manufacturer estimate",
    QUOTE_ONLY: "Price on request",
  },
  autonomy: {
    TELEOPERATED: "Teleoperated",
    ASSISTED: "Assisted",
    SUPERVISED_AUTONOMY: "Supervised autonomy",
    TASK_AUTONOMOUS: "Task-autonomous",
    HIGHLY_AUTONOMOUS: "Highly autonomous",
  },
  mobility: {
    BIPEDAL: "Bipedal",
    WHEELED: "Wheeled",
    HYBRID: "Hybrid",
    QUADRUPED: "Quadruped",
    STATIONARY: "Stationary",
    OTHER: "Other",
  },
  // Same wording as format.ts#modeLabel so every surface agrees.
  transaction: {
    PURCHASE: "Purchase",
    RENTAL: "Rental",
    SUBSCRIPTION: "Subscription",
    LEASE: "Lease",
    RAAS: "RaaS",
    PILOT: "Pilot",
    DEVELOPER: "Developer",
    OTHER: "Other",
  },
  source_type: {
    MANUFACTURER_STORE: "Manufacturer store",
    MANUFACTURER_SITE: "Manufacturer website",
    PRESS_RELEASE: "Press release",
    NEWS_ARTICLE: "News article",
    ANALYST_REPORT: "Analyst report",
    FINANCIAL_FILING: "Financial filing",
    DIRECT_QUOTE: "Direct quote",
    CONFERENCE: "Conference",
    INTERVIEW: "Interview",
    OTHER: "Other source",
  },
  // Seller / channel kinds (db/schema.sql provider_type).
  provider_type: {
    OEM: "Manufacturer (OEM)",
    DISTRIBUTOR: "Distributor",
    INTEGRATOR: "Integrator",
    RENTAL_PROVIDER: "Rental provider",
    LEASING_PROVIDER: "Leasing provider",
    RAAS_PROVIDER: "Robot-as-a-service provider",
    SERVICE_PROVIDER: "Service provider",
  },
  // Extended-spec headings (db/schema.sql capability_category).
  capability_category: {
    MANIPULATION: "Manipulation",
    MOBILITY: "Mobility",
    PERCEPTION: "Perception",
    AI_AUTONOMY: "AI and autonomy",
    INTERACTION: "Interaction",
    SOFTWARE: "Software",
    SAFETY: "Safety",
    OTHER: "Other",
  },
  confidence: {
    LOW: "Low",
    MEDIUM: "Medium",
    HIGH: "High",
    VERIFIED: "Verified",
  },
};

/** The known raw values per kind (used by totality tests). */
export const ENUM_VALUES: Record<EnumKind, string[]> = Object.fromEntries(
  (Object.keys(LABELS) as EnumKind[]).map((k) => [k, Object.keys(LABELS[k])]),
) as Record<EnumKind, string[]>;

/** "SOME_TOKEN" -> "Some token". Never returns an empty string for a non-empty input. */
export function humanizeToken(raw: string): string {
  const words = raw.replace(/_+/g, " ").trim().toLowerCase();
  if (!words) return raw;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Buyer-facing label for an enum value; safe fallback for unknown values. */
export function enumLabel(kind: EnumKind, value: string | null | undefined): string {
  if (value == null || value === "") return "";
  return LABELS[kind][value] ?? humanizeToken(value);
}

export const statusLabel = (v: string | null | undefined) => enumLabel("commercial_status", v);
export const availabilityLabel = (v: string | null | undefined) =>
  enumLabel("availability_status", v);
export const priceTypeLabel = (v: string | null | undefined) => enumLabel("price_type", v);
export const autonomyLabel = (v: string | null | undefined) => enumLabel("autonomy", v);
export const mobilityLabel = (v: string | null | undefined) => enumLabel("mobility", v);
export const sourceTypeLabel = (v: string | null | undefined) => enumLabel("source_type", v);
export const confidenceLabel = (v: string | null | undefined) => enumLabel("confidence", v);

/** De-slugged display name for when only a slug is known: "agibot-a2-ultra" -> "Agibot A2 Ultra". */
export function nameFromSlug(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((w) => (/^\d/.test(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}
