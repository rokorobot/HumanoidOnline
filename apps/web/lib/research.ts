// ADR-027 — Regional Research Resources: types, the publication gate, and the
// governed read. The aggregation lives in the API read model
// (apps/api/app/services/regional_research); this module only gates, fetches and
// labels. It never recomputes a count, status or price.
import { timingSafeEqual } from "node:crypto";

import { API_BASE_URL } from "./server";

export const RESEARCH_REGIONS = ["europe"] as const;
export type ResearchRegion = (typeof RESEARCH_REGIONS)[number];

export const RESEARCH_BASE_PATH = "/research/humanoid-availability";
export const RESEARCH_HUB_PATH = "/research";

export function researchPath(region: ResearchRegion): string {
  return `${RESEARCH_BASE_PATH}/${region}`;
}

// ---- Projection (mirrors the API's build_projection) ----------------------

export interface ResearchPriceState {
  kind: "PUBLISHED" | "PRICE_ON_REQUEST" | "ESTIMATE" | "NOT_PUBLISHED";
  price_type: string | null;
  amount: number | null;
  price_min: number | null;
  price_max: number | null;
  currency: string | null;
  billing_period: string | null;
  price_basis: string | null;
}

export interface ResearchOffer {
  robot_slug: string;
  robot_name: string;
  manufacturer_slug: string;
  manufacturer_name: string;
  provider_slug: string | null;
  provider_type: string | null;
  region_code: string;
  transaction_type: string;
  availability_status: string;
  evidence_date: string;
  confidence: string;
  human_verified: boolean;
  source_urls: string[];
  prices: ResearchPriceState[];
}

export interface ResearchDeployment {
  robot_slug: string;
  robot_name: string;
  manufacturer_slug: string;
  manufacturer_name: string;
  region_code: string;
  customer_name: string | null;
  provider_slug: string | null;
  transaction_type: string | null;
  unit_count: number | null;
  started_on: string | null;
  status: string | null;
  evidence_date: string;
  confidence: string;
  human_verified: boolean;
  source_urls: string[];
}

export interface ResearchGroup {
  reason: string;
  label: string;
  robots: { slug: string; name: string; manufacturer_slug: string; manufacturer_name: string }[];
}

export interface ResearchProjection {
  region: { slug: string; code: string; name: string };
  snapshot_date: string;
  freshness_days: number;
  latest_evidence_date: string | null;
  direct_answer: string;
  key_figures: {
    published_population: number;
    robots_with_confirmed_offer: number;
    manufacturers_with_confirmed_offer: number;
    robots_without_confirmed_offer: number;
    purchase_robots: number;
    purchase_by_best_status: { status: string; robots: number }[];
    robots_by_other_transaction: { transaction_type: string; robots: number }[];
    purchase_robots_with_published_price: number;
    purchase_robots_price_on_request: number;
    purchase_robots_price_not_published: number;
  };
  offers: ResearchOffer[];
  deployments: ResearchDeployment[];
  no_confirmed_offer: ResearchGroup[];
  methodology: Record<string, string>;
  faq: { question: string; answer: string }[];
  member_region_codes: string[];
  published: boolean;
  // Review-only; the API omits it from any public body.
  readiness?: {
    gate_passes: boolean;
    qualifying_robots: number;
    qualifying_manufacturers: number;
    min_robots: number;
    min_manufacturers: number;
    failures: string[];
    groups_reconcile: boolean;
  };
}

// ---- Publication gate ------------------------------------------------------

export type ResearchAccess =
  | { mode: "published" }
  | { mode: "preview"; token: string }
  | { mode: "closed" };

function safeEqual(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

/**
 * Who may see a regional resource. Closed by default: a region is public only
 * when RESEARCH_PUBLISHED_REGIONS lists it (the owner's publication decision,
 * ADR-027 §12). Otherwise a reviewer holding RESEARCH_PREVIEW_TOKEN may open it
 * with `?preview=<token>`. Anything else is closed (404, no disclosure).
 */
export function resolveResearchAccess(
  region: string,
  previewParam: string | null | undefined,
  env: Record<string, string | undefined> = process.env,
): ResearchAccess {
  if (!(RESEARCH_REGIONS as readonly string[]).includes(region)) return { mode: "closed" };
  const published = (env.RESEARCH_PUBLISHED_REGIONS ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  if (published.includes(region)) return { mode: "published" };
  const token = (env.RESEARCH_PREVIEW_TOKEN ?? "").trim();
  if (token && previewParam && safeEqual(token, previewParam)) {
    return { mode: "preview", token };
  }
  return { mode: "closed" };
}

// ---- Hub and navigation --------------------------------------------------------

/** Regions the hub presents. Only those with a built resource (RESEARCH_REGIONS)
 *  can ever be live; the others are shown as "in preparation", never as links. */
export const HUB_REGIONS = [
  { slug: "europe", name: "Europe" },
  { slug: "north-america", name: "North America" },
  { slug: "asia", name: "Asia" },
] as const;

/**
 * Regions the owner has switched on for THIS web app (RESEARCH_PUBLISHED_REGIONS)
 * that actually have a built resource. Synchronous and env-only, so navigation
 * can use it everywhere; whether a region really serves is decided by the
 * governed read (`liveResearchRegions`).
 */
export function publishedResearchRegions(
  env: Record<string, string | undefined> = process.env,
): ResearchRegion[] {
  return RESEARCH_REGIONS.filter((r) => resolveResearchAccess(r, null, env).mode === "published");
}

/** Research appears in navigation only once at least one resource is published. */
export function researchNavVisible(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return publishedResearchRegions(env).length > 0;
}

/**
 * Regions that are published AND actually served publicly (the API also requires
 * data readiness, ADR-027 section 12). The hub exists only while this is non-empty.
 */
export async function liveResearchRegions(
  fetchProjection: (region: ResearchRegion) => Promise<ResearchProjection | null> = (r) =>
    fetchResearchProjection(r, { mode: "published" }),
  env: Record<string, string | undefined> = process.env,
): Promise<ResearchRegion[]> {
  const live: ResearchRegion[] = [];
  for (const region of publishedResearchRegions(env)) {
    try {
      if (await fetchProjection(region)) live.push(region);
    } catch {
      // an unreachable API is not a published resource
    }
  }
  return live;
}

// ---- Sitemap -----------------------------------------------------------------

export interface ResearchSitemapEntry {
  url: string;
  lastModified?: Date;
  changeFrequency: "weekly";
  priority: number;
}

/**
 * Sitemap entries for regional resources: ONLY published regions. A closed or
 * preview-only resource never appears (it must not be discoverable), and
 * `lastModified` is the real latest evidence date, never the render time.
 */
export async function researchSitemapEntries(
  origin: string,
  fetchProjection: (region: ResearchRegion) => Promise<ResearchProjection | null>,
  env: Record<string, string | undefined> = process.env,
): Promise<ResearchSitemapEntry[]> {
  const out: ResearchSitemapEntry[] = [];
  for (const region of RESEARCH_REGIONS) {
    if (resolveResearchAccess(region, null, env).mode !== "published") continue;
    let data: ResearchProjection | null = null;
    try {
      data = await fetchProjection(region);
    } catch {
      data = null;
    }
    if (!data) continue; // no data, no entry: never list a page that would 404
    const d = data.latest_evidence_date ? new Date(data.latest_evidence_date) : null;
    out.push({
      url: `${origin}${researchPath(region)}`,
      ...(d && !Number.isNaN(d.getTime()) ? { lastModified: d } : {}),
      changeFrequency: "weekly",
      priority: 0.7,
    });
  }
  return out;
}

// ---- Labels ------------------------------------------------------------------

const STATUS_LABELS: Record<string, string> = {
  AVAILABLE: "Available",
  LIMITED: "Limited",
  PREORDER: "Preorder",
  WAITLIST: "Waitlist",
  ON_REQUEST: "On request",
};
const TRANSACTION_LABELS: Record<string, string> = {
  PURCHASE: "Purchase",
  RENTAL: "Rental",
  LEASE: "Lease",
  RAAS: "RaaS",
};
const PERIOD_LABELS: Record<string, string> = {
  HOURLY: "hour",
  DAILY: "day",
  WEEKLY: "week",
  MONTHLY: "month",
  QUARTERLY: "quarter",
  ANNUAL: "year",
};

export const statusLabel = (s: string): string => STATUS_LABELS[s] ?? s;
export const transactionLabel = (t: string): string => TRANSACTION_LABELS[t] ?? t;

function money(n: number): string {
  return Number.isInteger(n)
    ? n.toLocaleString("en-US")
    : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Price as published; unknown stays unknown (never 0, never "free"). */
export function formatPriceState(p: ResearchPriceState): string {
  const per = p.billing_period && PERIOD_LABELS[p.billing_period] ? ` / ${PERIOD_LABELS[p.billing_period]}` : "";
  const cur = p.currency ? ` ${p.currency}` : "";
  switch (p.kind) {
    case "PUBLISHED":
      if (p.amount !== null) return `${money(p.amount)}${cur}${per}`;
      // A range is shown only with BOTH bounds; there is no path to a made-up 0.
      if (p.price_min !== null && p.price_max !== null) {
        return `${money(p.price_min)}–${money(p.price_max)}${cur}${per}`;
      }
      return "Not published";
    case "PRICE_ON_REQUEST":
      return "Price on request";
    case "ESTIMATE":
      return `Estimate only: ${p.amount !== null ? money(p.amount) : "n/a"}${cur}${per} (not a published price)`;
    default:
      return "Not published";
  }
}

// ---- Governed read ------------------------------------------------------------

/** 404 -> null (closed or unknown); other non-2xx throw. */
export async function fetchResearchProjection(
  region: ResearchRegion,
  access: ResearchAccess,
): Promise<ResearchProjection | null> {
  if (access.mode === "closed") return null;
  const init: RequestInit & { next?: { revalidate: number } } =
    access.mode === "published"
      ? { next: { revalidate: 300 } }
      : { cache: "no-store", headers: { "X-Research-Preview": access.token } };
  const res = await fetch(`${API_BASE_URL}/api/research/humanoid-availability/${region}`, init);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status} for research/${region}`);
  return (await res.json()) as ResearchProjection;
}

/**
 * The gate + the governed read, together. If a region is flagged published but the
 * API declines to serve it publicly (ADR-027 §12: data readiness not met), a
 * reviewer holding the preview token still gets the review-only view; everyone
 * else gets null (404).
 */
export async function loadResearch(
  region: ResearchRegion,
  previewParam: string | null | undefined,
  env: Record<string, string | undefined> = process.env,
): Promise<{ access: ResearchAccess; data: ResearchProjection | null }> {
  let access = resolveResearchAccess(region, previewParam, env);
  let data = await fetchResearchProjection(region, access);
  if (!data && access.mode === "published") {
    const review = resolveResearchAccess(region, previewParam, {
      ...env,
      RESEARCH_PUBLISHED_REGIONS: "",
    });
    if (review.mode === "preview") {
      access = review;
      data = await fetchResearchProjection(region, review);
    }
  }
  return data ? { access, data } : { access: { mode: "closed" }, data: null };
}
