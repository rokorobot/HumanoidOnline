// CID-04 — index policy for query-state routes. /compare and /robots render from URL
// parameters, so every permutation is a distinct URL; without these signals search
// engines index hundreds of thousands of near-duplicates of a few dozen real pages.
// Pure: same input → same decision. `follow` stays on so links still pass through.
import type { Metadata } from "next";

const NOINDEX: Metadata["robots"] = { index: false, follow: true };

function uniqueIds(raw: string | string[] | undefined): string[] {
  const joined = Array.isArray(raw) ? raw.join(",") : (raw ?? "");
  return [...new Set(joined.split(",").map((s) => s.trim()).filter(Boolean))];
}

// Indexable: the bare /compare page and exactly-two-robot pairs. A pair's canonical is
// its sorted, parameter-free URL, so ordering and view state (ref/units/view/region)
// fold into one page. Every other selection is noindex.
export function comparePolicy(raw: string | string[] | undefined): {
  pair: [string, string] | null;
  meta: Pick<Metadata, "robots" | "alternates">;
} {
  const ids = uniqueIds(raw);
  if (ids.length === 0) return { pair: null, meta: { alternates: { canonical: "/compare" } } };
  if (ids.length !== 2) return { pair: null, meta: { robots: NOINDEX } };
  const pair = [...ids].sort() as [string, string];
  return { pair, meta: { alternates: { canonical: `/compare?ids=${pair.join(",")}` } } };
}

// The unfiltered catalogue is the canonical page; any filter, sort or query is noindex.
export function cataloguePolicy(
  sp: Record<string, string | string[] | undefined>,
): Pick<Metadata, "robots" | "alternates"> {
  return Object.keys(sp).length === 0
    ? { alternates: { canonical: "/robots" } }
    : { robots: NOINDEX };
}

// A match result belongs to one buyer's request; it is never a search result.
export const MATCH_RESULT_ROBOTS: Metadata["robots"] = { index: false, follow: false };
