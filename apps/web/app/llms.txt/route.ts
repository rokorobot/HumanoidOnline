import { listRobots } from "@/lib/api-client";
import { siteUrl } from "@/lib/site";

// AGENT-01 (A6): `/llms.txt` — a concise, LLM-friendly description of the site.
// CANONICAL-ONLY: built from the governed read, so it lists only is_published
// robots (AGENT-01.7) — discovery candidates are never part of the public
// knowledge surface. Dynamic so it stays current. llms.txt is a useful-but-
// non-canonical proposal; we provide it without architecting around it.
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();
  // limit=100 is the API's max page (covers the catalogue at current scale;
  // pagination is the scale path).
  const robots = await listRobots({ limit: 100 });

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
    `- Sitemap: ${origin}/sitemap.xml`,
    "",
    "## Robots (published, canonical)",
    ...robots.items.map(
      (r) => `- ${r.name} (${r.manufacturer.name}): ${origin}/robots/${r.slug}`,
    ),
    "",
  ];

  return new Response(lines.join("\n"), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "public, max-age=0, must-revalidate",
    },
  });
}
