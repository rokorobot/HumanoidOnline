// Typed, server-side fetch layer over the FastAPI knowledge API.
// All reads use { cache: "no-store" } so pages reflect the live catalogue.
// A 404 from a detail endpoint triggers Next's notFound(); other non-2xx
// responses throw so the error boundary / build surfaces the failure.
import { notFound } from "next/navigation";

import { API_BASE_URL } from "./server";
import type {
  CompareResponse,
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
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (res.status === 404 && notFoundOn404) {
    notFound();
  }
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

export function getRobot(slug: string): Promise<RobotDetail> {
  return getJSON<RobotDetail>(`/api/robots/${encodeURIComponent(slug)}`, {
    notFoundOn404: true,
  });
}

// compare returns 422 for <2 or >4 valid slugs — surfaced to the caller as null
// so the compare page can render an explanatory empty state instead of crashing.
export async function compareRobots(
  ids: string[],
): Promise<CompareResponse | null> {
  const clean = ids.map((s) => s.trim()).filter(Boolean);
  const res = await fetch(
    `${API_BASE_URL}/api/robots/compare${buildQuery({ ids: clean.join(",") })}`,
    { cache: "no-store" },
  );
  if (res.status === 422 || res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status} for /api/robots/compare`);
  return (await res.json()) as CompareResponse;
}

// ---- Manufacturers ---------------------------------------------------------

export function listManufacturers(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<ManufacturerListItem>> {
  return getJSON<Page<ManufacturerListItem>>(
    `/api/manufacturers${buildQuery(params as Record<string, QueryValue>)}`,
  );
}

export function getManufacturer(slug: string): Promise<ManufacturerDetail> {
  return getJSON<ManufacturerDetail>(
    `/api/manufacturers/${encodeURIComponent(slug)}`,
    { notFoundOn404: true },
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

export function getUseCase(slug: string): Promise<UseCaseDetail> {
  return getJSON<UseCaseDetail>(`/api/use-cases/${encodeURIComponent(slug)}`, {
    notFoundOn404: true,
  });
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
