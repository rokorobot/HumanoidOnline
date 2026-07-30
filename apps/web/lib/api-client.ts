// Typed, server-side fetch layer over the FastAPI knowledge API.
// All reads use { cache: "no-store" } so pages reflect the live catalogue.
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

async function getJSON<T>(
  path: string,
  { notFoundOn404 = false }: { notFoundOn404?: boolean } = {},
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: await correlationHeader(),
  });
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
async function getJSONOrNull<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: await correlationHeader(),
  });
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
  );
}

// Non-throwing detail read (404 -> null). Detail pages wrap this in React
// cache() so the page render and generateMetadata share a single governed fetch.
export function findRobot(slug: string): Promise<RobotDetail | null> {
  return getJSONOrNull<RobotDetail>(`/api/robots/${encodeURIComponent(slug)}`);
}

// compare returns 422 for <2 or >4 valid slugs — surfaced to the caller as null
// so the compare page can render an explanatory empty state instead of crashing.
export async function compareRobots(
  ids: string[],
): Promise<CompareResponse | null> {
  const clean = ids.map((s) => s.trim()).filter(Boolean);
  const res = await fetch(
    `${API_BASE_URL}/api/robots/compare${buildQuery({ ids: clean.join(",") })}`,
    { cache: "no-store", headers: await correlationHeader() },
  );
  if (res.status === 422 || res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status} for /api/robots/compare`);
  return (await res.json()) as CompareResponse;
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
  );
}

export function findManufacturer(
  slug: string,
): Promise<ManufacturerDetail | null> {
  return getJSONOrNull<ManufacturerDetail>(
    `/api/manufacturers/${encodeURIComponent(slug)}`,
  );
}

// ---- Use cases -------------------------------------------------------------

export function listUseCases(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<UseCaseListItem>> {
  return getJSON<Page<UseCaseListItem>>(
    `/api/use-cases${buildQuery(params as Record<string, QueryValue>)}`,
  );
}

export function findUseCase(slug: string): Promise<UseCaseDetail | null> {
  return getJSONOrNull<UseCaseDetail>(
    `/api/use-cases/${encodeURIComponent(slug)}`,
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
  return getJSON<MarketSnapshot>(`/api/market-snapshot`);
}
