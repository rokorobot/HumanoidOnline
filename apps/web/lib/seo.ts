// WS8.5 / R23 — machine-surface helpers: full published-set pagination + a
// defensive lastModified. AGENT-01 (docs/10): these consume the existing PUBLIC
// governed reads only (lib/api-client) — never raw DB/catalogue — so the sitemap
// and llms.txt remain projections of the governed model, not an independent
// truth source. The reads already return only is_published canonical entities
// (AGENT-01.7), so pagination changes coverage completeness, never eligibility.
import { listManufacturers, listRobots, listUseCases } from "@/lib/api-client";
import type {
  ManufacturerListItem,
  RobotListItem,
  UseCaseListItem,
} from "@/lib/types";

// The API clamps every list endpoint to a maximum page of 100 (routers: le=100 /
// min(limit,100)). Pagination walks the set in pages of this size.
export const PAGE_SIZE = 100;
// Safety backstop: a bad/overstated `total` can never spin forever. Far above any
// realistic catalogue scale; hitting it means the API is misbehaving, and we stop
// with what we have rather than loop.
export const MAX_PAGES = 1000;

// Walk every page of a governed list read until the entire published set is
// collected. Termination is defensive on three independent conditions, so an
// empty page, a short (final) page, or a `total` that disagrees with reality all
// stop cleanly — never an infinite loop.
export async function collectAll<T>(
  // Only items + total are needed to paginate; accept any page-shaped read (a
  // real Page<T> satisfies this structurally).
  fetchPage: (p: {
    limit: number;
    offset: number;
  }) => Promise<{ items: T[]; total: number }>,
): Promise<T[]> {
  const all: T[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const { items, total } = await fetchPage({
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    });
    all.push(...items);
    if (items.length === 0) break; // empty page (incl. an overstated total) -> stop
    if (items.length < PAGE_SIZE) break; // short page = the last page
    if (all.length >= total) break; // collected the whole declared set
  }
  return all;
}

export const listAllRobots = (): Promise<RobotListItem[]> =>
  collectAll<RobotListItem>((p) => listRobots(p));

export const listAllManufacturers = (): Promise<ManufacturerListItem[]> =>
  collectAll<ManufacturerListItem>((p) => listManufacturers(p));

export const listAllUseCases = (): Promise<UseCaseListItem[]> =>
  collectAll<UseCaseListItem>((p) => listUseCases(p));

// Defensive lastModified for sitemap entries: an invalid/missing timestamp must
// not emit an Invalid Date (which throws on sitemap serialization) — omit
// lastModified instead of guessing one.
export function lastMod(value: string | null | undefined): {
  lastModified?: Date;
} {
  if (!value) return {};
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? {} : { lastModified: d };
}
