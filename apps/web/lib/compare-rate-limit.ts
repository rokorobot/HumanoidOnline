// Emergency Compare Rate Containment v0.3 — pure, framework-agnostic policy.
//
// v0.2 (compare-crawl-containment) removed the crawlable <a href> anchors that
// let a passive crawler discover compare permutations. Production evidence
// after that deploy showed the storm persisted: whatever is generating the
// traffic already holds the URLs (harvested pre-v0.2, or simply constructed
// directly) and does not need an anchor to keep requesting them. This module
// is the decision logic for the front-door containment that replaces "don't
// advertise the URL" with "don't let the URL be hit at machine-gun cadence".
//
// v0.3 protects the two expensive compare-state surfaces with two different
// mechanisms, chosen per-route rather than uniformly:
//   - `/compare` exists for nothing but comparison — even a bare `/compare`
//     with no `ids` is cheap (no backend call), so the whole path can safely
//     sit behind Netlify's *native*, platform-enforced per-IP rate limit
//     (declared in netlify/edge-functions/compare-native-rate-limit.ts).
//     No app-level counter, no concurrency exposure.
//   - `/robots?compare=...` cannot use that native primitive: Netlify's
//     declarative rate limiting matches on path only (query strings are
//     ignored), and blanket-limiting `/robots` would also throttle ordinary
//     catalogue browsing, which must stay unaffected. That route keeps a
//     custom, query-aware counter — the concurrency-hardened `checkAndIncrement`
//     below — in netlify/edge-functions/compare-rate-limit.ts.
//
// Kept separate from the Edge Functions that call it so the policy itself —
// which requests count as "compare state", the fixed-window admit/reject
// math, and the optimistic-concurrency retry loop — is testable with plain
// Vitest: no Deno runtime, no real Netlify Blobs, no wall-clock timing.

export const RATE_LIMIT_WINDOW_MS = 60_000;
export const RATE_LIMIT_MAX_REQUESTS = 30;

/**
 * True only for `/robots` carrying a non-empty `compare` param — never for
 * plain `/robots` (with or without ordinary filters), `/robots/[slug]`,
 * `/manufacturers`, `/`, or anything else. The caller (the Edge Function
 * bound to the `/robots` path) is what guarantees this only ever runs for
 * `/robots` in the first place; this function only needs to check the query.
 */
export function isRobotsCompareRequest(searchParams: URLSearchParams): boolean {
  return (searchParams.get("compare") ?? "").trim() !== "";
}

export interface RateLimitCounter {
  count: number;
  windowStart: number;
}

export interface RateLimitDecision {
  allow: boolean;
  /** The counter state to persist for this key, win or reject. */
  next: RateLimitCounter;
  /** Only meaningful when `allow` is false. */
  retryAfterSeconds: number;
}

/**
 * Fixed-window admit/reject decision. Pure function of its inputs — no clock,
 * no I/O — so the caller supplies `now` and the previously-stored counter
 * (or `null` on a cold key) and gets back both the verdict and the counter
 * value to persist. A window that has elapsed resets the count rather than
 * carrying it forward, matching a simple fixed (not sliding) window.
 *
 * This function makes no claim about *persisting* `next` safely under
 * concurrent callers — that is `checkAndIncrement`'s job. Calling this twice
 * with the same `existing` (as two truly concurrent requests would) yields
 * the same `next` from both calls by design; it is the caller's conditional
 * write, not this function, that must ensure only one of them actually wins.
 */
export function decideRateLimit(
  existing: RateLimitCounter | null,
  now: number,
  windowMs: number = RATE_LIMIT_WINDOW_MS,
  maxRequests: number = RATE_LIMIT_MAX_REQUESTS,
): RateLimitDecision {
  const withinWindow = existing !== null && now - existing.windowStart < windowMs;
  const windowStart = withinWindow ? existing!.windowStart : now;
  const count = (withinWindow ? existing!.count : 0) + 1;

  if (count > maxRequests) {
    const retryAfterSeconds = Math.max(
      1,
      Math.ceil((windowStart + windowMs - now) / 1000),
    );
    // Reject without consuming the slot the rejected request didn't earn —
    // persist the counter unchanged from what put us over, so a client that
    // stops immediately still sees the window expire on schedule.
    return { allow: false, next: { count: count - 1, windowStart }, retryAfterSeconds };
  }

  return { allow: true, next: { count, windowStart }, retryAfterSeconds: 0 };
}

// ---- Concurrency-safe increment ---------------------------------------

/**
 * Minimal storage contract `checkAndIncrement` needs — deliberately narrower
 * than the full `@netlify/blobs` client, and expressed in terms of Netlify
 * Blobs' own documented compare-and-swap primitives rather than a bare
 * get/set pair:
 *   - `read` surfaces the ETag alongside the value (Blobs' `getWithMetadata`),
 *     because detecting a lost race requires knowing *which* version you read.
 *   - `createIfAbsent` maps to `set(..., { onlyIfNew: true })` — the only
 *     race-safe way to initialize a cold key (two simultaneous first hits
 *     for the same IP must not both "win" the create silently).
 *   - `updateIfMatch` maps to `set(..., { onlyIfMatch: etag })` — true
 *     compare-and-swap against the ETag from `read`.
 * Netlify's own Blobs docs are explicit that plain `get`/`set` is "last write
 * wins" with "no concurrency control mechanism" built in, and name exactly
 * this onlyIfNew/onlyIfMatch pattern as the way to "build an object-locking
 * mechanism into your application" on top of it.
 */
export interface RateLimitStore {
  read(key: string): Promise<{ value: RateLimitCounter; etag: string } | null>;
  createIfAbsent(key: string, value: RateLimitCounter): Promise<{ modified: boolean }>;
  updateIfMatch(
    key: string,
    value: RateLimitCounter,
    etag: string,
  ): Promise<{ modified: boolean }>;
}

/** Small, fixed retry budget — never spin indefinitely under contention. */
export const MAX_CAS_RETRIES = 3;

export type RateLimitOutcome =
  | { allow: true; degraded: false }
  | { allow: true; degraded: true }
  | { allow: false; degraded: false; retryAfterSeconds: number };

/**
 * Optimistic-concurrency admit/reject + persist, safe under truly concurrent
 * callers for the same key. Each attempt: read the freshest state (with its
 * ETag), decide against it, then persist with a conditional write that only
 * succeeds if nothing else has written since the read. A losing write means
 * another request won the race — loop back and recompute against the state
 * it left behind, up to `maxRetries` times.
 *
 * Two consequences worth stating plainly:
 *   - A reject never writes. The rejected request didn't change anything, so
 *     there's nothing to persist and nothing to race on the reject path.
 *   - If contention is high enough to exhaust the retry budget, this fails
 *     open (`degraded: true`) rather than blocking a request whose true
 *     count it can no longer safely determine — consistent with this
 *     control's existing "never take the site down over the limiter"
 *     availability policy, but callers MUST log the `degraded` case
 *     distinctly from an ordinary admit, per STEP 4: never silently lose
 *     the signal that the count is now unreliable.
 */
export async function checkAndIncrement(
  store: RateLimitStore,
  key: string,
  now: number,
  windowMs: number = RATE_LIMIT_WINDOW_MS,
  maxRequests: number = RATE_LIMIT_MAX_REQUESTS,
  maxRetries: number = MAX_CAS_RETRIES,
): Promise<RateLimitOutcome> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const existing = await store.read(key);
    const decision = decideRateLimit(existing?.value ?? null, now, windowMs, maxRequests);

    if (!decision.allow) {
      return {
        allow: false,
        degraded: false,
        retryAfterSeconds: decision.retryAfterSeconds,
      };
    }

    const result =
      existing === null
        ? await store.createIfAbsent(key, decision.next)
        : await store.updateIfMatch(key, decision.next, existing.etag);

    if (result.modified) {
      return { allow: true, degraded: false };
    }
    // Collision: another request wrote first. Retry with a fresh read.
  }

  return { allow: true, degraded: true };
}
