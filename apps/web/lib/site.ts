// Canonical site origin for AGENT-01 machine projections (JSON-LD @id/url,
// sitemap, robots.txt, llms.txt). AGENT-01.1: entities have one stable canonical
// URI. Override per-env with NEXT_PUBLIC_SITE_URL; defaults to production.
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://humanoidonline.com"
).replace(/\/+$/, "");

/** Absolute canonical URL for a site-relative path (pass-through for absolute). */
export function absoluteUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${SITE_URL}/${path.replace(/^\/+/, "")}`;
}
