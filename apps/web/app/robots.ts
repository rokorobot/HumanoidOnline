import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";

// AGENT-01 (A4): INBOUND crawler policy for HumanoidOnline — a DIFFERENT axis
// from DATA-D1.9 (our OUTBOUND crawling of external sources, which is
// affirmative-permission-gated). Deliberate v0.1 stance: the site WANTS to be
// discovered by search + LLM answer engines, so public content is open to all
// reputable crawlers. There is no admin surface in this app (the internal admin
// is on the network-gated backend), so nothing is disallowed here. A stricter
// per-bot / training-bot policy is a business decision the owner can tighten later.
export default function robots(): MetadataRoute.Robots {
  // WS8.2 / R8 — one authoritative origin resolver for every machine surface.
  const origin = siteUrl();
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: `${origin}/sitemap.xml`,
    host: origin,
  };
}
