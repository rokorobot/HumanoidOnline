// Typed, server-side fetch layer over the FastAPI knowledge API.
//
// Two read policies, chosen per call site:
//   - Catalogue-static reads (robots/manufacturers/use-cases/regions/market
//     snapshot) pass `revalidate` and use Next's Data Cache (`next: { revalidate }`),
//     so repeated page views, prefetches, sitemap/llms.txt generation and
//     crawler requests within the TTL window are served from cache instead of
//     re-querying the API/Neon on every hit (Neon Transfer Optimization Phase 1).
//   - Everything user-specific, write-adjacent or already covered by its own
//     cache (compare, matches, buyer-requirement reads, discovery review) omits
//     `revalidate` and keeps the original `cache: "no-store"` behaviour exactly.
//
// A 404 from a detail endpoint triggers Next's notFound(); other non-2xx
// responses throw so the error boundary / build surfaces the failure.
import { notFound } from "next/navigation";

import { correlationHeader } from "./request-id";
import { API_BASE_URL } from "./server";
import type {
  CompareResponse,
  DiscoveryCandidateReview,
  ManufacturerDetail,
  ManufacturerListItem,
  MarketSnapshot,
  MatchResponse,
  Page,
  RegionListItem,
  RequirementRead,
  RobotDetail,
  RobotListItem,
  UseCaseDetail,
  UseCaseListItem,
} from "./types";

export type QueryValue = string | number | boolean | string[] | undefined | null;

// Governed catalogue reads change by editorial review, not by the second (same
// doctrine as the existing compare cache), so a short TTL is a safe default that
// still converges automatically — no manual invalidation exists or is needed.
const CATALOGUE_REVALIDATE_S = 300;

function buildQuery(params: Record<string, QueryValue>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v !== undefined && v !== null && v !== "") sp.append(key, String(v));
      }
    } else {
      sp.append(key, String(value));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

// Builds the fetch init for one governed read. `revalidate` omitted keeps the
// original always-fresh behaviour byte-for-byte. `revalidate` set switches to
// Next's Data Cache — and deliberately OMITS the `X-Request-ID` correlation
// header for that call: Next's fetch cache key is derived from the full
// request including headers (confirmed against the installed Next 15 source,
// `generateCacheKey` in `incremental-cache/index.js`), and `correlationHeader()`
// mints a fresh random UUID per request when no upstream proxy id is present —
// sending it would make every cache key unique and silently defeat revalidation.
// Non-cacheable calls are unaffected and keep full request correlation.
async function readInit(revalidate?: number): Promise<RequestInit> {
  if (revalidate !== undefined) {
    return { next: { revalidate } };
  }
  return { cache: "no-store", headers: await correlationHeader() };
}

async function getJSON<T>(
  path: string,
  {
    notFoundOn404 = false,
    revalidate,
  }: { notFoundOn404?: boolean; revalidate?: number } = {},
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, await readInit(revalidate));
  if (res.status === 404 && notFoundOn404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`API ${res.status} for ${path}`);
  }
  return (await res.json()) as T;
}

// Non-throwing sibling of getJSON: a 404 yields null instead of Next's
// notFound(), so the caller decides how to handle a missing entity. This lets a
// page's generateMetadata return a specific "Not found" title while the page
// itself renders notFound() — both sharing ONE governed read (wrap in React
// cache()), never an alternate data path (AGENT-01 projection-only).
async function getJSONOrNull<T>(
  path: string,
  { revalidate }: { revalidate?: number } = {},
): Promise<T | null> {
  const res = await fetch(`${API_BASE_URL}${path}`, await readInit(revalidate));
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`API ${res.status} for ${path}`);
  }
  return (await res.json()) as T;
}

// ---- Robots ----------------------------------------------------------------

export interface RobotListParams {
  q?: string;
  manufacturer?: string;
  commercial_status?: string[];
  transaction_type?: string[];
  availability_status?: string[];
  region?: string;
  use_case?: string;
  payload_min?: number;
  height_min?: number;
  height_max?: number;
  price_max?: number;
  // Required by the API whenever price_max is set, and rejected without it.
  // Derived in toRobotListParams — never set independently.
  price_currency?: string;
  mobility?: string;
  autonomy_min?: string;
  has_sdk?: boolean;
  ros_support?: boolean;
  developer_edition?: boolean;
  has_manipulation?: boolean;
  sort?: string;
  limit?: number;
  offset?: number;
}

export function listRobots(
  params: RobotListParams = {},
): Promise<Page<RobotListItem>> {
  return getJSON<Page<RobotListItem>>(
    `/api/robots${buildQuery(params as Record<string, QueryValue>)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

// Non-throwing detail read (404 -> null). Detail pages wrap this in React
// cache() so the page render and generateMetadata share a single governed fetch.
export function findRobot(slug: string): Promise<RobotDetail | null> {
  return getJSONOrNull<RobotDetail>(`/api/robots/${encodeURIComponent(slug)}`, {
    revalidate: CATALOGUE_REVALIDATE_S,
  });
}

// compare returns 422 for <2 or >4 valid slugs — surfaced to the caller as null
// so the compare page can render an explanatory empty state instead of crashing.
//
// COMPARE BACKEND CDN KEY CANONICALIZATION (2026-08-24): the wire request uses
// a SORTED, de-duplicated id list so every permutation of the same robot set
// (ids=a,b,c,d / d,a,c,b / b,d,a,c) hits the identical `/api/robots/compare`
// URL and therefore the same Vercel CDN cache entry (routers/robots.py sets a
// public Cache-Control on this route) instead of each permutation being a
// fresh, ~5s origin compute. The backend already reorders its own response to
// match whatever `ids` order it receives, so sending the sorted order would
// leak into the caller-visible result — `reorderToRequested` below undoes
// that locally, in memory, so the public /compare URL and rendered order stay
// exactly what the caller asked for. Dedup collapses to first occurrence,
// matching the backend's own `dict.fromkeys` (routers/robots.py) exactly, so
// duplicate-id behaviour is unchanged.
export async function compareRobots(
  ids: string[],
): Promise<CompareResponse | null> {
  const requestedIds = [...new Set(ids.map((s) => s.trim()).filter(Boolean))];
  const canonicalIds = [...requestedIds].sort();
  const res = await fetch(
    `${API_BASE_URL}/api/robots/compare${buildQuery({ ids: canonicalIds.join(",") })}`,
    { cache: "no-store", headers: await correlationHeader() },
  );
  if (res.status === 422 || res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status} for /api/robots/compare`);
  const data = (await res.json()) as CompareResponse;
  return reorderToRequested(data, requestedIds);
}

// Reshapes a canonical-order compare response back to the caller's originally
// requested order. Never fabricates: a requested slug the response doesn't
// contain (not found, or dropped by the backend) is simply absent from the
// result too, same as if the backend had received the request in that order.
function reorderToRequested(
  data: CompareResponse,
  requestedIds: string[],
): CompareResponse {
  const bySlug = new Map(data.robots.map((r) => [r.slug, r]));
  const order = requestedIds.filter((slug) => bySlug.has(slug));
  return {
    robots: order.map((slug) => bySlug.get(slug)!),
    rows: data.rows.map((row) => ({
      ...row,
      values: Object.fromEntries(order.map((slug) => [slug, row.values[slug]])),
    })),
  };
}

// ---- DATA-D1 operator review (NONCANONICAL, dev/test only) -----------------
// The API mounts this route only in relaxed environments, so a strict deployment
// returns 404 and the review page renders its unavailable state rather than
// crashing. Kept beside the catalogue reads but never mixed with them: nothing
// here may be rendered as a verified robot.
export function listDiscoveryCandidates(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<DiscoveryCandidateReview>> {
  return getJSON<Page<DiscoveryCandidateReview>>(
    `/api/discovery-review${buildQuery(params as Record<string, QueryValue>)}`,
  );
}

// ---- Manufacturers ---------------------------------------------------------

export function listManufacturers(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<ManufacturerListItem>> {
  return getJSON<Page<ManufacturerListItem>>(
    `/api/manufacturers${buildQuery(params as Record<string, QueryValue>)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

export function findManufacturer(
  slug: string,
): Promise<ManufacturerDetail | null> {
  return getJSONOrNull<ManufacturerDetail>(
    `/api/manufacturers/${encodeURIComponent(slug)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

// ---- Use cases -------------------------------------------------------------

export function listUseCases(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<UseCaseListItem>> {
  return getJSON<Page<UseCaseListItem>>(
    `/api/use-cases${buildQuery(params as Record<string, QueryValue>)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

export function findUseCase(slug: string): Promise<UseCaseDetail | null> {
  return getJSONOrNull<UseCaseDetail>(
    `/api/use-cases/${encodeURIComponent(slug)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

// ---- Regions ---------------------------------------------------------------

// Canonical region reference (drives the buyer-intent Country step). `type` can
// filter to COUNTRY. Returned `code` is what POST /api/buyer-requirements resolves.
export function listRegions(
  params: { type?: string } = {},
): Promise<RegionListItem[]> {
  return getJSON<RegionListItem[]>(
    `/api/regions${buildQuery(params as Record<string, QueryValue>)}`,
    { revalidate: CATALOGUE_REVALIDATE_S },
  );
}

// ---- Buyer intent & matching (WS6) -----------------------------------------

// Triggers deterministic matching on the first call (server persists the result);
// later calls return the stored result. 404 -> notFound() for an unknown id.
export function getMatches(id: string): Promise<MatchResponse> {
  return getJSON<MatchResponse>(
    `/api/buyer-requirements/${encodeURIComponent(id)}/matches`,
    { notFoundOn404: true },
  );
}

// Anonymous requirement read for the Adjust-Requirements prefill.
export function getRequirement(id: string): Promise<RequirementRead> {
  return getJSON<RequirementRead>(
    `/api/buyer-requirements/${encodeURIComponent(id)}`,
    { notFoundOn404: true },
  );
}

// ---- Market snapshot -------------------------------------------------------

export function getMarketSnapshot(): Promise<MarketSnapshot> {
  return getJSON<MarketSnapshot>(`/api/market-snapshot`, {
    revalidate: CATALOGUE_REVALIDATE_S,
  });
}
