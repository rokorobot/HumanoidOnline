// SEO-04 — curated "A vs B" comparison pages at /compare/<a>-vs-<b>.
//
// Search demand is pairwise ("1x neo vs unitree h2", "<maker> competitors"), so each
// robot links to a small, fixed set of its closest alternatives. The set is bounded
// (ALTERNATIVES per robot), so the linked pair space grows linearly with the
// catalogue, never combinatorially. Pure and deterministic: same catalogue → same pairs.
import type { RobotListItem } from "@/lib/types";

export const ALTERNATIVES = 4;
const SEP = "-vs-";

type Candidate = Pick<
  RobotListItem,
  "slug" | "name" | "manufacturer" | "commercial_status" | "mobility" | "height_cm" | "payload_kg"
>;

/** The one canonical path for a pair: slugs sorted, so A-vs-B and B-vs-A are one page. */
export function pairPath(a: string, b: string): string {
  const [x, y] = [a, b].sort();
  return `/compare/${x}${SEP}${y}`;
}

/** Parses "<a>-vs-<b>". Null unless it splits into exactly two distinct non-empty slugs. */
export function parsePair(segment: string): [string, string] | null {
  const parts = decodeURIComponent(segment).split(SEP);
  if (parts.length !== 2) return null;
  const [a, b] = parts.map((s) => s.trim());
  if (!a || !b || a === b) return null;
  return [a, b];
}

// Within ±25% of each other; an unknown value never counts as similar.
function near(x: number | null | undefined, y: number | null | undefined): boolean {
  if (x == null || y == null || x <= 0 || y <= 0) return false;
  return Math.max(x, y) / Math.min(x, y) <= 1.25;
}

// Similarity from recorded facts only. A different maker scores higher because
// cross-maker comparisons are what buyers search for.
function score(r: Candidate, o: Candidate): number {
  let s = 0;
  if (r.commercial_status === o.commercial_status) s += 2;
  if (r.mobility && r.mobility === o.mobility) s += 2;
  if (near(r.height_cm, o.height_cm)) s += 1;
  if (near(r.payload_kg, o.payload_kg)) s += 1;
  if (r.manufacturer.slug !== o.manufacturer.slug) s += 1;
  return s;
}

/** The closest ALTERNATIVES robots to `robot`, best first, ties broken by slug. */
export function alternativesFor<T extends Candidate>(robot: Candidate, all: T[], n = ALTERNATIVES): T[] {
  return all
    .filter((o) => o.slug !== robot.slug)
    .map((o) => ({ o, s: score(robot, o) }))
    .sort((p, q) => q.s - p.s || p.o.slug.localeCompare(q.o.slug))
    .slice(0, n)
    .map((x) => x.o);
}

/** Every curated pair path across the catalogue, de-duplicated and sorted (sitemap order). */
export function curatedPairPaths(all: Candidate[]): string[] {
  const paths = new Set<string>();
  for (const r of all) for (const o of alternativesFor(r, all)) paths.add(pairPath(r.slug, o.slug));
  return [...paths].sort();
}
