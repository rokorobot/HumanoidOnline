// Emergency Compare Rate Containment v0.3 — `/robots?compare=...` only.
//
// Runs as a genuine Netlify Edge Function (auto-discovered from this
// directory), the earliest point in the request chain Netlify exposes to
// application code: it executes before the Edge/Durable cache lookup and
// before the origin Function that performs Next.js SSR for `/robots`
// (`export const dynamic = "force-dynamic"`, so every hit is a full render).
// Returning a `Response` here — as this does for a rejected request — stops
// the chain outright; the origin SSR function is never invoked.
//
// `/compare` is deliberately NOT handled here — see
// compare-native-rate-limit.ts. `/compare` exists for nothing but
// comparison (even a bare `/compare` with no `ids` is cheap: no backend
// call), so it sits behind Netlify's native, platform-enforced per-IP rate
// limit instead, with no app-level counter and no concurrency exposure at
// all. `/robots?compare=...` can't use that native primitive: Netlify's
// declarative rate limiting matches on path only, ignoring the query
// string, so binding it to `/robots` would also throttle ordinary
// catalogue browsing — explicitly out of scope for this control. Only this
// route needs custom, query-aware logic, which means only this route needs
// a persistent counter at all.
//
// Deliberately NOT Next.js `middleware.ts`: Netlify does convert middleware
// into an edge function automatically, but (a) that conversion is a
// framework-adapter behaviour, one layer removed from the platform primitive
// this file uses directly, and (b) `context.ip` — the non-spoofable client
// identity Netlify's own docs name as the correct source, in preference to
// trusting any `X-Forwarded-For` — is documented for hand-authored Edge
// Functions, not confirmed for Next middleware's `NextRequest` signature.
//
// Concurrency (v0.3 hardening — see docs/16_EMERGENCY_COMPARE_RATE_CONTAINMENT.md):
// the first cut of this file did an unconditional `get` then `setJSON`, which
// Netlify's own Blobs docs call out by name as unsafe — "last write wins...
// no concurrency control mechanism" — and is exactly the shape of the
// production incident (concurrent sub-second bursts). `consistency: "strong"`
// only affects read *visibility*, not write atomicity; it does not fix this.
// `lib/compare-rate-limit.ts`'s `checkAndIncrement` replaces it with the
// object-locking pattern Netlify's docs themselves recommend on top of
// Blobs: `getWithMetadata` for an ETag, `onlyIfNew`/`onlyIfMatch` for a true
// compare-and-swap write, and a small bounded retry loop on collision — see
// that module for the full algorithm and its concurrency tests.
//
// Fail-open by design, in two distinct ways: a store *error* (Blobs
// unreachable) fails open silently — containment degrading to "off" under an
// outage is the correct failure mode for a human-safe throttle. Retry-budget
// *exhaustion* under genuine contention also fails open (never blocks a
// request whose true count is no longer knowable) but is logged distinctly
// (`degraded`), per the explicit requirement not to silently lose that
// signal even while choosing to admit the request.
import { getStore } from "@netlify/blobs";
import type { Config, Context } from "@netlify/edge-functions";

import {
  checkAndIncrement,
  isRobotsCompareRequest,
  type RateLimitCounter,
  type RateLimitStore,
} from "../../lib/compare-rate-limit";

const STORE_NAME = "compare-rate-limit";

function blobsRateLimitStore(store: ReturnType<typeof getStore>): RateLimitStore {
  return {
    async read(key) {
      const entry = await store.getWithMetadata(key, {
        type: "json",
        consistency: "strong",
      });
      if (entry === null) return null;
      // `etag` is typed optional by @netlify/blobs even when `data` is
      // present; in the (undocumented, presumably rare) case it's missing,
      // falling back to an etag that can never match a real one just means
      // the next conditional write harmlessly fails and retries with a
      // fresh read — never a runtime type violation, never a bad write.
      return { value: entry.data as RateLimitCounter, etag: entry.etag ?? "" };
    },
    async createIfAbsent(key, value) {
      return store.setJSON(key, value, { onlyIfNew: true });
    },
    async updateIfMatch(key, value, etag) {
      return store.setJSON(key, value, { onlyIfMatch: etag });
    },
  };
}

export default async function compareRateLimit(request: Request, context: Context) {
  const url = new URL(request.url);
  if (!isRobotsCompareRequest(url.searchParams)) {
    return; // not compare-state traffic — untouched, no store I/O, no delay.
  }

  const ip = context.ip || "unknown";
  const key = `ip:${ip}`;

  try {
    const store = getStore(STORE_NAME);
    const outcome = await checkAndIncrement(blobsRateLimitStore(store), key, Date.now());

    if (!outcome.allow) {
      return new Response("Too Many Requests", {
        status: 429,
        headers: {
          "Retry-After": String(outcome.retryAfterSeconds),
          "Content-Type": "text/plain",
          "Cache-Control": "no-store",
        },
      });
    }

    if (outcome.degraded) {
      // Retry budget exhausted under contention: admitted, but the count is
      // no longer trustworthy. Logged distinctly from a clean admit so this
      // is visible in production logs rather than indistinguishable from
      // normal traffic.
      console.warn("compare-rate-limit: contention exhausted, admitting without a confirmed count", {
        key,
      });
    }
  } catch (err) {
    console.error("compare-rate-limit: store unavailable, failing open", err);
  }

  return; // undefined -> continue the request chain toward Next.js SSR.
}

export const config: Config = {
  path: ["/robots"],
};
