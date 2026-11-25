import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";

// AGENT-01 (A4): INBOUND crawler policy for HumanoidOnline — a DIFFERENT axis
// from DATA-D1.9 (our OUTBOUND crawling of external sources, which is
// affirmative-permission-gated). Deliberate v0.1 stance: the site WANTS to be
// discovered by search + LLM answer engines, so public content is open to all
// reputable crawlers. There is no admin surface in this app (the internal admin
// is on the network-gated backend), so no public content is disallowed here. A stricter
// per-bot / training-bot policy is a business decision the owner can tighten later.
//
// One exception (owner request 2026-11-25): `/compare?` — the query-state compare
// space. Every 2–4 robot selection in every order is a distinct URL (millions of
// them), each a server render; a crawl burst over them in Oct 2026 put 20.7K URLs
// in Search Console as 5xx. They are noindex or canonicalised away already, so
// crawling them only spends origin compute and crawl budget. The bare `/compare`
// and the curated `/compare/<a>-vs-<b>` pages (the ones in the sitemap) have no
// `?` and stay crawlable. Same rule for every agent: no per-bot split.
export const COMPARE_QUERY_SPACE = "/compare?";

export default function robots(): MetadataRoute.Robots {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: COMPARE_QUERY_SPACE }],
    sitemap: `${origin}/sitemap.xml`,
    host: origin,
  };
}
