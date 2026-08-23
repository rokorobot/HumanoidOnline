// Emergency Compare Rate Containment v0.3 — `/compare` native rate limiting.
//
// `/compare` exists for nothing but comparison: `app/compare/page.tsx` makes
// no backend call at all when `ids` is absent or has fewer than 2 entries
// (it renders a static "select robots to compare" prompt), so a bare
// `/compare` hit is cheap regardless. That makes the whole path — not just
// `/compare?ids=...` — eligible for Netlify's *native*, platform-enforced
// per-IP rate limit, declared below via `config.rateLimit`. Unlike
// `/robots?compare=...` (see compare-rate-limit.ts), this needs no
// query-string awareness and therefore no app-level counter: the block
// decision is made by Netlify's own infrastructure, before this function
// body ever runs for a rejected request, with none of the Netlify Blobs
// concurrency exposure a hand-rolled counter would carry.
//
// `aggregateBy: ["ip", "domain"]` is the all-plans option — each visiting IP
// gets its own 30/60s budget. (The alternative, `["domain"]` alone, is a
// single shared budget across every visitor and is an Enterprise-only
// feature; not appropriate here regardless of plan.)
//
// This file's `config.rateLimit` is a declarative, platform-enforced rule —
// it is NOT exercised by the mocked-Blobs unit tests in this repo (there is
// nothing to mock: no app code runs the check). It is covered by a
// config-shape audit test only; genuine enforcement can only be verified
// against a live Netlify deployment (see docs/16_EMERGENCY_COMPARE_RATE_CONTAINMENT.md
// residual-risk note).
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
