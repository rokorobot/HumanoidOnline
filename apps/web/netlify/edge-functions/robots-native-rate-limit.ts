// Emergency Compare Rate Containment v0.3.2 — `/robots` native rate limit.
//
// v0.3/v0.3.1 tried to protect only `/robots?compare=...` — narrower than
// this — with a custom, query-aware Edge Function backed by Netlify Blobs
// for a concurrency-safe counter. That implementation was correct and fully
// tested, but never actually deployable: Netlify's real bundler rejects
// npm-module imports in Edge Functions as experimental, and `@netlify/blobs`
// failed to load there under both the current major (11.0.1) and the last
// pre-major release (10.7.13) — reproduced directly against Netlify's own
// local build pipeline, not inferred. A disposable `npm:` specifier probe
// failed even earlier, at Next's own TypeScript compile step, and fixing
// that would have needed a type shim or a tsconfig exclusion carving the
// edge-functions directory out of the Next.js TS project — exactly the kind
// of source-adjacent workaround this repair was told not to reach for.
//
// v0.3.2 replaces it with Netlify's *native* declarative `config.rateLimit`
// — the same platform primitive already used for `/compare` (see
// compare-native-rate-limit.ts) — applied to the whole `/robots` path. That
// primitive can only match on path, not query string, so this necessarily
// widens the protected surface from "`/robots?compare=...` only" to "all of
// `/robots`": plain browsing, ordinary filters, and the specific compare
// query all now share one generous per-IP budget. That's an explicit,
// authorized tradeoff, not an oversight — `/robots` is itself
// `export const dynamic = "force-dynamic"` and calls `listRobots()` on
// every hit regardless of query, so it was never free to begin with, and
// 60 requests/60s/IP is well above anything ordinary human browsing
// produces while still capping a sustained automated flood. Ordinary
// `/robots` traffic remains fully functional below that threshold — it is
// no longer literally untouched by this control, and should not be
// described that way.
//
// No app-level counter, no Blobs, no persistence: the platform itself owns
// the distributed per-IP rate counters, exactly like `/compare`.
import type { Config } from "@netlify/edge-functions";

export default async function robotsNativeRateLimit() {
  // Nothing to do here for an admitted request — the platform's declarative
  // rateLimit below has already decided by the time this body runs at all.
  return;
}

export const config: Config = {
  path: "/robots",
  rateLimit: {
    windowSize: 60,
    windowLimit: 60,
    aggregateBy: ["ip", "domain"],
  },
};
