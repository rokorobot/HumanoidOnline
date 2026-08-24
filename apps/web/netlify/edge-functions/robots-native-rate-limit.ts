// Emergency Compare Rate Containment v0.3.3 — `/robots` native rate limit.
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
// v0.3.2 replaced it with Netlify's *native* declarative `config.rateLimit`
// — the same platform primitive already used for `/compare` (see
// compare-native-rate-limit.ts) — applied to the whole `/robots` path. That
// primitive can only match on path, not query string, so this necessarily
// widens the protected surface from "`/robots?compare=...` only" to "all of
// `/robots`": plain browsing, ordinary filters, and the specific compare
// query all now share one generous per-IP budget. That's an explicit,
// authorized tradeoff, not an oversight — `/robots` is itself
// `export const dynamic = "force-dynamic"` and calls `listRobots()` on
// every hit regardless of query, so it was never free to begin with.
//
// v0.3.3 tightens 60->30 req/60s alongside the `/compare` tightening
// (30->10), following production evidence (2026-08-24) of automated
// traffic pacing itself under the old thresholds. Unlike `/compare`, this
// is a KNOWINGLY HIGHER-RISK tradeoff for real users: `/robots` re-renders
// on every filter change, every pagination click, AND every compare-tray
// toggle (`compareHref` in app/robots/page.tsx updates the URL and
// re-renders on each add/remove), so an engaged human filtering the
// catalogue while building a compare selection can plausibly fire several
// hits within a few seconds. 30/60s is accepted as the smallest direct
// containment step available right now, not asserted to be safely above
// all legitimate rapid browsing — watch for user-facing throttling reports
// after this ships, the way `/compare`'s tighter 10/60s is not expected to
// need the same scrutiny.
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
    windowLimit: 30,
    aggregateBy: ["ip", "domain"],
  },
};
