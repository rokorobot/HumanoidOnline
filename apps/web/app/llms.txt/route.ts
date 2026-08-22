import { siteUrl } from "@/lib/site";
import { listAllManufacturers, listAllRobots, listAllUseCases } from "@/lib/seo";

// AGENT-01 (A6): `/llms.txt` — a concise, LLM-friendly description of the site.
// CANONICAL-ONLY: built from the governed reads, so it lists only is_published
// entities (AGENT-01.7) — discovery candidates are never part of the public
// knowledge surface. Dynamic so it stays current; llms.txt is a useful-but-
// non-canonical proposal; we provide it without architecting around it.
//
// Neon Transfer Optimization Phase 1 — `dynamic = "force-dynamic"` is kept
// deliberately (removing it made `next build` attempt to statically prerender
// this route, which requires a reachable API/Neon at BUILD time — verified by
// reproducing the build failure locally). The Neon-transfer win instead comes
// from listAllRobots/listAllManufacturers/listAllUseCases now going through
// governed reads that carry their own `revalidate` (see lib/api-client.ts):
// Next's per-fetch Data Cache still applies within a force-dynamic route
// whenever the fetch itself sets `next: { revalidate }`, so repeated crawl
// hits (this path is specifically the kind AI-agent crawlers seek out) within
// the TTL reuse the cached catalogue data instead of re-querying Neon, without
// changing this route's build-time behaviour at all.
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();

  // WS8.5 / R23 — enumerate the ENTIRE published canonical set of every public
  // entity type, paginated via the governed reads (no 100-entity ceiling).
  const [robots, manufacturers, useCases] = await Promise.all([
    listAllRobots(),
    listAllManufacturers(),
    listAllUseCases(),
  ]);

  const lines: string[] = [
    "# HumanoidOnline",
    "",
    "> Verified humanoid-robot market intelligence. Every catalogue fact is",
    "> canonical and evidence-backed; this surface exposes only published,",
    "> verified data — never unverified discovery candidates.",
    "",
    "## Semantics (read before citing)",
    '- UNKNOWN is not 0, false, or "unavailable" — a missing value is omitted, never guessed.',
    "- Commercial maturity (commercial_status) is distinct from obtainability (availability).",
    "- Evidence status (confidence / verified_at) is distinct from commercial status.",
    "- Provenance is exposed where canonical evidence exists; it is never fabricated.",
    "",
    "## Canonical entry points",
    `- Catalogue: ${origin}/robots`,
    `- Manufacturers: ${origin}/manufacturers`,
    `- Use cases: ${origin}/use-cases`,
    `- Sitemap: ${origin}/sitemap.xml`,
    "",
    "## Robots (published, canonical)",
    ...robots.map(
      (r) => `- ${r.name} (${r.manufacturer.name}): ${origin}/robots/${r.slug}`,
    ),
    "",
    "## Manufacturers (published, canonical)",
    ...manufacturers.map((m) => `- ${m.name}: ${origin}/manufacturers/${m.slug}`),
    "",
    "## Use cases (published, canonical)",
    ...useCases.map((u) => `- ${u.name}: ${origin}/use-cases/${u.slug}`),
    "",
  ];

  return new Response(lines.join("\n"), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      // Was "public, max-age=0, must-revalidate" (caching forbidden). Neon
      // Transfer Optimization Phase 1: allow shared/edge caches to reuse this
      // response for up to 15 minutes, matching the route's `revalidate` above.
      "cache-control": "public, max-age=0, s-maxage=900, stale-while-revalidate=86400",
    },
  });
}
