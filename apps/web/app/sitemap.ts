import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";
import {
  lastMod,
  listAllManufacturers,
  listAllRobots,
  listAllUseCases,
} from "@/lib/seo";

// AGENT-01 (docs/10): the sitemap is a projection of the governed reads, so it
// lists ONLY is_published canonical entities (AGENT-01.7) — discovery candidates
// and promoted-but-unpublished robots never appear. Dynamic so it stays current;
// `lastModified` is the real canonical `updated_at`.
//
// Neon Transfer Optimization Phase 1 — `dynamic = "force-dynamic"` is kept
// deliberately (removing it made `next build` attempt to statically prerender
// this route, which requires a reachable API/Neon at BUILD time — verified by
// reproducing the build failure locally). The Neon-transfer win instead comes
// from listAllRobots/listAllManufacturers/listAllUseCases now going through
// governed reads that carry their own `revalidate` (see lib/api-client.ts):
// Next's per-fetch Data Cache still applies within a force-dynamic route
// whenever the fetch itself sets `next: { revalidate }`, so repeated crawl
// hits within the TTL reuse the cached catalogue data instead of re-querying
// Neon, without changing this route's build-time behaviour at all.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();

  // WS8.5 / R23 — enumerate the ENTIRE published canonical set of every public
  // entity type (robots, manufacturers, use cases), paginated via the governed
  // reads. No 100-entity ceiling.
  const [robots, manufacturers, useCases] = await Promise.all([
    listAllRobots(),
    listAllManufacturers(),
    listAllUseCases(),
  ]);

  const core: MetadataRoute.Sitemap = [
    { url: `${origin}/`, changeFrequency: "daily", priority: 1 },
    { url: `${origin}/robots`, changeFrequency: "daily", priority: 0.9 },
    { url: `${origin}/manufacturers`, changeFrequency: "weekly", priority: 0.7 },
    { url: `${origin}/use-cases`, changeFrequency: "weekly", priority: 0.7 },
  ];

  const robotPages: MetadataRoute.Sitemap = robots.map((r) => ({
    url: `${origin}/robots/${r.slug}`,
    ...lastMod(r.updated_at),
    changeFrequency: "weekly",
    priority: 0.8,
  }));

  const mfrPages: MetadataRoute.Sitemap = manufacturers.map((m) => ({
    url: `${origin}/manufacturers/${m.slug}`,
    ...lastMod(m.updated_at),
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  // Use-case list items carry no `updated_at`, so lastModified is honestly
  // omitted (never fabricated).
  const useCasePages: MetadataRoute.Sitemap = useCases.map((u) => ({
    url: `${origin}/use-cases/${u.slug}`,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  // Grouped by entity type. At catalogue scale this is one file; Next's
  // generateSitemaps() is the split-by-type path when the catalogue grows.
  return [...core, ...robotPages, ...mfrPages, ...useCasePages];
}
