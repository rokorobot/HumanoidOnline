import type { MetadataRoute } from "next";

import { listManufacturers, listRobots } from "@/lib/api-client";
import { siteUrl } from "@/lib/site";

// AGENT-01 (docs/10): the sitemap is a projection of the governed read, so it
// lists ONLY is_published canonical entities (AGENT-01.7) — discovery candidates
// and promoted-but-unpublished robots never appear. Dynamic so it stays current;
// `lastModified` is the real canonical `updated_at`.
export const dynamic = "force-dynamic";

// Defensive: an invalid/missing timestamp must not 500 the whole sitemap — omit
// lastModified rather than emit an Invalid Date (which throws on serialization).
function lastMod(value: string): { lastModified?: Date } {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? {} : { lastModified: d };
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();
  // limit=100 is the API's max page; it covers the catalogue at current scale.
  // Pagination (loop until total) is the scale path when entities exceed 100.
  const [robots, manufacturers] = await Promise.all([
    listRobots({ limit: 100 }),
    listManufacturers({ limit: 100 }),
  ]);

  const core: MetadataRoute.Sitemap = [
    { url: `${origin}/`, changeFrequency: "daily", priority: 1 },
    { url: `${origin}/robots`, changeFrequency: "daily", priority: 0.9 },
    { url: `${origin}/manufacturers`, changeFrequency: "weekly", priority: 0.7 },
  ];

  const robotPages: MetadataRoute.Sitemap = robots.items.map((r) => ({
    url: `${origin}/robots/${r.slug}`,
    ...lastMod(r.updated_at),
    changeFrequency: "weekly",
    priority: 0.8,
  }));

  const mfrPages: MetadataRoute.Sitemap = manufacturers.items.map((m) => ({
    url: `${origin}/manufacturers/${m.slug}`,
    ...lastMod(m.updated_at),
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  // Grouped by entity type. At catalogue scale this is one file; Next's
  // generateSitemaps() is the split-by-type path when the catalogue grows.
  return [...core, ...robotPages, ...mfrPages];
}
