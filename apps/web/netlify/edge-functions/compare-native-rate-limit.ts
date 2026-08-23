// Emergency Compare Rate Containment v0.3.2 — `/compare` native rate limit.
//
// `/compare` exists for nothing but comparison: `app/compare/page.tsx` makes
// no backend call at all when `ids` is absent or has fewer than 2 entries
// (it renders a static "select robots to compare" prompt), so a bare
// `/compare` hit is cheap regardless. That makes the whole path — not just
// `/compare?ids=...` — eligible for Netlify's *native*, platform-enforced
// per-IP rate limit, declared below via `config.rateLimit`: no app-level
// counter, no persistence, no concurrency exposure at all. The platform
// itself owns the distributed per-IP counters.
//
// v0.3.2 note: `/robots` is protected the same way, by a sibling file
// (robots-native-rate-limit.ts) — see that file for why the earlier
// query-aware, Netlify-Blobs-backed `/robots?compare=...` limiter was
// removed entirely (it could never bundle in Netlify's actual Edge Function
// runtime — npm-module imports in Edge Functions are experimental and
// `@netlify/blobs` failed to load there regardless of package version).
//
// `aggregateBy: ["ip", "domain"]` is the all-plans option — each visiting IP
// gets its own 30/60s budget. (The alternative, `["domain"]` alone, is a
// single shared budget across every visitor and is an Enterprise-only
// feature; not appropriate here regardless of plan.)
//
// This file's `config.rateLimit` is a declarative, platform-enforced rule —
// it is NOT exercised by the unit tests in this repo (there is no
// application code here to run or mock). Those tests are a config-shape
// audit only: they prove the declared policy matches what's documented,
// not that Netlify enforces it — only a live deployment can prove that.
import type { Config } from "@netlify/edge-functions";

export default async function compareNativeRateLimit() {
  // Nothing to do here for an admitted request — the platform's declarative
  // rateLimit below has already decided by the time this body runs at all.
  return;
}

export const config: Config = {
  path: "/compare",
  rateLimit: {
    windowSize: 60,
    windowLimit: 30,
    aggregateBy: ["ip", "domain"],
  },
};
