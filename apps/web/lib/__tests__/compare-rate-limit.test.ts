// Emergency Compare Rate Containment v0.3 — policy unit tests.
// Pure logic only: no Deno runtime, no real Netlify Blobs. Concurrency tests
// use an in-memory fake that faithfully implements Blobs' documented
// compare-and-swap contract (onlyIfNew / onlyIfMatch, ETag bump per write),
// coordinated via explicit promise barriers — never timers or sleeps, so
// the races below are deterministic, not flaky.
//
// `/compare`'s native-rate-limit config is audited separately in
// netlify/edge-functions/__tests__/compare-native-rate-limit.test.ts — it
// has no app code to mock here (see that file's header for why).
import { describe, expect, it } from "vitest";

import {
  checkAndIncrement,
  decideRateLimit,
  isRobotsCompareRequest,
  MAX_CAS_RETRIES,
  RATE_LIMIT_MAX_REQUESTS,
  RATE_LIMIT_WINDOW_MS,
  type RateLimitCounter,
  type RateLimitStore,
} from "@/lib/compare-rate-limit";

function sp(query: string): URLSearchParams {
  return new URLSearchParams(query);
}

describe("isRobotsCompareRequest", () => {
  it("is false with no query at all", () => {
    expect(isRobotsCompareRequest(sp(""))).toBe(false);
  });

  it("is false with ordinary filters but no compare param", () => {
    expect(
      isRobotsCompareRequest(sp("commercial_status=COMMERCIAL&region=EU&q=unitree")),
    ).toBe(false);
  });

  it("is true for a non-empty compare param", () => {
    expect(isRobotsCompareRequest(sp("compare=unitree-g1,digit"))).toBe(true);
  });

  it("is false for an empty compare value", () => {
    expect(isRobotsCompareRequest(sp("compare="))).toBe(false);
  });

  it("is false for a whitespace-only compare value", () => {
    expect(isRobotsCompareRequest(sp("compare=%20%20"))).toBe(false);
  });
});

describe("decideRateLimit", () => {
  const WINDOW = RATE_LIMIT_WINDOW_MS;
  const LIMIT = RATE_LIMIT_MAX_REQUESTS;

  it("admits the first request on a cold key", () => {
    const d = decideRateLimit(null, 1_000);
    expect(d.allow).toBe(true);
    expect(d.next).toEqual({ count: 1, windowStart: 1_000 });
  });

  it("admits requests up to and including the limit within the window", () => {
    let counter = null as RateLimitCounter | null;
    let now = 0;
    for (let i = 0; i < LIMIT; i++) {
      const d = decideRateLimit(counter, now);
      expect(d.allow).toBe(true);
      counter = d.next;
      now += 100;
    }
    expect(counter).toEqual({ count: LIMIT, windowStart: 0 });
  });

  it("rejects the request that would exceed the limit within the window", () => {
    const atLimit = { count: LIMIT, windowStart: 0 };
    const d = decideRateLimit(atLimit, 5_000);
    expect(d.allow).toBe(false);
    expect(d.next).toEqual({ count: LIMIT, windowStart: 0 });
  });

  it("computes Retry-After as the seconds remaining in the current window", () => {
    const atLimit = { count: LIMIT, windowStart: 0 };
    const d = decideRateLimit(atLimit, WINDOW - 2_500);
    expect(d.allow).toBe(false);
    expect(d.retryAfterSeconds).toBe(3); // ceil(2500ms remaining / 1000)
  });

  it("resets the count once the window has elapsed", () => {
    const stale = { count: LIMIT, windowStart: 0 };
    const d = decideRateLimit(stale, WINDOW + 1);
    expect(d.allow).toBe(true);
    expect(d.next).toEqual({ count: 1, windowStart: WINDOW + 1 });
  });

  it("treats exactly windowMs elapsed as a new window (window is half-open)", () => {
    const stale = { count: LIMIT, windowStart: 0 };
    const d = decideRateLimit(stale, WINDOW);
    expect(d.allow).toBe(true);
    expect(d.next).toEqual({ count: 1, windowStart: WINDOW });
  });

  it("is deterministic for identical inputs", () => {
    const counter = { count: 10, windowStart: 12_345 };
    const a = decideRateLimit(counter, 12_400);
    const b = decideRateLimit(counter, 12_400);
    expect(a).toEqual(b);
  });
});

// ---- Concurrency: the bug, then the fix -----------------------------------

/**
 * A barrier that blocks the first `n` calls until all `n` have arrived, then
 * releases all of them at once; calls after the `n`th pass straight through.
 * Used to force two "concurrent" async calls to both complete their read
 * before either proceeds to write — deterministically, with no timers.
 */
function coordinatedBarrier(n: number): () => Promise<void> {
  let arrived = 0;
  let released = false;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  return async () => {
    arrived++;
    if (arrived === n) {
      released = true;
      release();
    }
    if (!released) await gate;
  };
}

describe("concurrency — the naive unconditional read-then-write pattern loses updates", () => {
  // This reproduces, in isolation, exactly the algorithm
  // netlify/edge-functions/compare-rate-limit.ts used before the v0.3
  // CAS hardening: an unconditional `get` (even with `consistency: "strong"`
  // — that only affects read *visibility*, not write atomicity) followed by
  // an unconditional `set`. It is NOT production code and is NOT imported
  // from anywhere else; it exists purely as documentation-by-test of the bug
  // `checkAndIncrement` below replaces. Netlify's own Blobs docs are explicit
  // that plain get/set is "last write wins" with "no concurrency control
  // mechanism" — this test demonstrates exactly that failure mode.
  it("two concurrent requests that both read count=29 can both be admitted while only one increment survives", async () => {
    const fake = new Map<string, RateLimitCounter>();
    fake.set("k", { count: 29, windowStart: 0 }); // one slot left before the 30 cap

    const arriveAtBarrier = coordinatedBarrier(2);
    async function naiveGet(key: string): Promise<RateLimitCounter | null> {
      await arriveAtBarrier(); // both reads must land before either proceeds
      return fake.get(key) ?? null;
    }
    async function naiveSet(key: string, value: RateLimitCounter): Promise<void> {
      fake.set(key, value);
    }
    async function naiveRequest() {
      const existing = await naiveGet("k");
      const decision = decideRateLimit(existing, 1_000);
      if (decision.allow) await naiveSet("k", decision.next);
      return decision;
    }

    const [a, b] = await Promise.all([naiveRequest(), naiveRequest()]);

    // The bug: BOTH requests were admitted (each independently saw 29, one
    // below the cap)...
    expect(a.allow).toBe(true);
    expect(b.allow).toBe(true);
    // ...but the store only reflects one of the two increments — last write
    // wins. Two real requests got through; the counter thinks only one did.
    expect(fake.get("k")).toEqual({ count: 30, windowStart: 0 });
  });
});

class FakeCasStore implements RateLimitStore {
  private data = new Map<string, { value: RateLimitCounter; etag: string }>();
  private etagSeq = 0;
  /** Optional hook invoked on every `read`, e.g. to coordinate a race. */
  onRead?: () => Promise<void>;
  /** Optional hook to force conditional writes to always report a collision. */
  alwaysCollide = false;

  seed(key: string, value: RateLimitCounter): void {
    this.data.set(key, { value, etag: `seed-${++this.etagSeq}` });
  }

  peek(key: string): RateLimitCounter | null {
    return this.data.get(key)?.value ?? null;
  }

  async read(key: string) {
    if (this.onRead) await this.onRead();
    const entry = this.data.get(key);
    return entry ? { value: entry.value, etag: entry.etag } : null;
  }

  async createIfAbsent(key: string, value: RateLimitCounter) {
    if (this.alwaysCollide || this.data.has(key)) return { modified: false };
    this.data.set(key, { value, etag: `c-${++this.etagSeq}` });
    return { modified: true };
  }

  async updateIfMatch(key: string, value: RateLimitCounter, etag: string) {
    const entry = this.data.get(key);
    if (this.alwaysCollide || !entry || entry.etag !== etag) return { modified: false };
    this.data.set(key, { value, etag: `u-${++this.etagSeq}` });
    return { modified: true };
  }
}

describe("checkAndIncrement — concurrency-hardened counter", () => {
  it("admits a single request on a cold key and persists count=1", async () => {
    const store = new FakeCasStore();
    const outcome = await checkAndIncrement(store, "k", 1_000);
    expect(outcome).toEqual({ allow: true, degraded: false });
    expect(store.peek("k")).toEqual({ count: 1, windowStart: 1_000 });
  });

  it("rejects over the limit without writing anything", async () => {
    const store = new FakeCasStore();
    store.seed("k", { count: RATE_LIMIT_MAX_REQUESTS, windowStart: 0 });
    const before = store.peek("k");
    const outcome = await checkAndIncrement(store, "k", 5_000);
    expect(outcome.allow).toBe(false);
    if (!outcome.allow) expect(outcome.retryAfterSeconds).toBeGreaterThan(0);
    expect(store.peek("k")).toEqual(before); // untouched — no I/O on reject
  });

  it("[STEP 8.11] two truly concurrent requests for the last remaining slot: exactly one wins, the other is correctly rejected on retry — no lost update, no over-admission", async () => {
    const store = new FakeCasStore();
    store.seed("k", { count: RATE_LIMIT_MAX_REQUESTS - 1, windowStart: 0 }); // one slot left
    store.onRead = coordinatedBarrier(2); // force both initial reads to see the same state

    const [a, b] = await Promise.all([
      checkAndIncrement(store, "k", 1_000),
      checkAndIncrement(store, "k", 1_000),
    ]);

    const outcomes = [a, b];
    expect(outcomes.filter((o) => o.allow)).toHaveLength(1);
    expect(outcomes.filter((o) => !o.allow)).toHaveLength(1);
    // The persisted count is exactly the true number of admitted requests —
    // not under-counted (the naive-pattern bug above) and not over-admitted.
    expect(store.peek("k")).toEqual({ count: RATE_LIMIT_MAX_REQUESTS, windowStart: 0 });
  });

  it("[STEP 8.12] two simultaneous first-ever requests for a cold key (new-window init) both get safely counted", async () => {
    const store = new FakeCasStore();
    store.onRead = coordinatedBarrier(2); // force both to see the key as cold

    const [a, b] = await Promise.all([
      checkAndIncrement(store, "k", 1_000),
      checkAndIncrement(store, "k", 1_000),
    ]);

    expect(a).toEqual({ allow: true, degraded: false });
    expect(b).toEqual({ allow: true, degraded: false });
    // One createIfAbsent won; the other collided (modified: false) and
    // retried via updateIfMatch against the freshly-created entry.
    expect(store.peek("k")).toEqual({ count: 2, windowStart: 1_000 });
  });

  it("[STEP 8.13] a single lost collision is retried and recomputed against the fresher state, not blindly reapplied", async () => {
    const store = new FakeCasStore();
    store.seed("k", { count: 5, windowStart: 0 });

    let updateCalls = 0;
    const realUpdate = store.updateIfMatch.bind(store);
    store.updateIfMatch = async (key, value, etag) => {
      updateCalls++;
      if (updateCalls === 1) {
        // Simulate another writer winning the very first attempt: bump the
        // stored state behind this call's back, then report the collision
        // exactly as a real ETag mismatch would.
        store.seed(key, { count: 6, windowStart: 0 });
        return { modified: false };
      }
      return realUpdate(key, value, etag);
    };

    const outcome = await checkAndIncrement(store, "k", 1_000);

    expect(outcome).toEqual({ allow: true, degraded: false });
    expect(updateCalls).toBe(2); // exactly one retry, not zero and not more
    // Recomputed from the fresher count=6 the retry observed, not from the
    // stale count=5 the first attempt started with.
    expect(store.peek("k")).toEqual({ count: 7, windowStart: 0 });
  });

  it("[STEP 8.14] bounded retry exhaustion under permanent contention fails open, flagged as degraded, without spinning indefinitely", async () => {
    const store = new FakeCasStore();
    store.alwaysCollide = true; // every conditional write collides, forever
    let reads = 0;
    const realRead = store.read.bind(store);
    store.read = async (key) => {
      reads++;
      return realRead(key);
    };

    const outcome = await checkAndIncrement(store, "k", 1_000);

    expect(outcome).toEqual({ allow: true, degraded: true });
    // Bounded: exactly maxRetries+1 attempts (the initial try plus the
    // configured retry budget), never more.
    expect(reads).toBe(MAX_CAS_RETRIES + 1);
  });

  it("is deterministic — replaying identical inputs against a fresh store gives the same outcome", async () => {
    const run = async () => {
      const store = new FakeCasStore();
      store.seed("k", { count: 3, windowStart: 0 });
      return checkAndIncrement(store, "k", 1_000);
    };
    expect(await run()).toEqual(await run());
  });
});
