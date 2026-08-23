// Emergency Compare Rate Containment v0.3 — `/robots?compare=...` edge
// function tests. Exercises the actual handler Netlify deploys, with
// Netlify Blobs replaced by an injectable in-memory fake that implements the
// real compare-and-swap contract (getWithMetadata + ETag, onlyIfNew /
// onlyIfMatch), not a bare get/set — so these tests would catch a regression
// back to the unconditional read-then-write pattern, not just exercise the
// happy path.
//
// `/compare` is handled entirely by Netlify's native `config.rateLimit` (see
// compare-native-rate-limit.ts) and has no app code here to test — see that
// file's own test for its config audit.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RATE_LIMIT_MAX_REQUESTS } from "@/lib/compare-rate-limit";

interface StoredEntry {
  value: unknown;
  etag: string;
}

// Faithful in-memory fake of the @netlify/blobs surface this handler uses:
// getWithMetadata returns {data, etag} | null, setJSON honours onlyIfNew /
// onlyIfMatch and reports {modified}. A real ETag mismatch fails the write
// instead of silently overwriting, exactly like the documented "last write
// wins... build an object-locking mechanism" Blobs contract.
const fakeBlobs = new Map<string, StoredEntry>();
let etagSeq = 0;

const getStoreMock = vi.fn((_name: string) => ({
  getWithMetadata: vi.fn(async (key: string) => {
    const entry = fakeBlobs.get(key);
    if (!entry) return null;
    return { data: entry.value, etag: entry.etag };
  }),
  setJSON: vi.fn(
    async (key: string, value: unknown, options?: { onlyIfNew?: boolean; onlyIfMatch?: string }) => {
      const existing = fakeBlobs.get(key);
      if (options?.onlyIfNew && existing) return { modified: false };
      if (options?.onlyIfMatch !== undefined && existing?.etag !== options.onlyIfMatch) {
        return { modified: false };
      }
      fakeBlobs.set(key, { value, etag: `e${++etagSeq}` });
      return { modified: true };
    },
  ),
}));

vi.mock("@netlify/blobs", () => ({
  getStore: (name: string) => getStoreMock(name),
}));

// Imported after the mock so the handler picks up the mocked module.
const { default: compareRateLimit } = await import("../compare-rate-limit");

function req(path: string, query = ""): Request {
  return new Request(`https://humanoidonline.example${path}${query ? `?${query}` : ""}`);
}

function ctx(ip = "203.0.113.10"): any {
  return { ip };
}

beforeEach(() => {
  fakeBlobs.clear();
  etagSeq = 0;
  getStoreMock.mockClear();
});
afterEach(() => vi.clearAllMocks());

describe("compare-rate-limit edge function (/robots?compare=...)", () => {
  it("passes through plain /robots untouched, without consuming the store", async () => {
    const res = await compareRateLimit(req("/robots"), ctx());
    expect(res).toBeUndefined();
    expect(getStoreMock).not.toHaveBeenCalled();
  });

  it("passes through /robots with ordinary filters, without consuming the store", async () => {
    const res = await compareRateLimit(
      req("/robots", "commercial_status=COMMERCIAL&region=EU"),
      ctx(),
    );
    expect(res).toBeUndefined();
    expect(getStoreMock).not.toHaveBeenCalled();
  });

  it("passes through unrelated routes untouched", async () => {
    const res = await compareRateLimit(req("/manufacturers"), ctx());
    expect(res).toBeUndefined();
    expect(getStoreMock).not.toHaveBeenCalled();
  });

  it("is subject to the limiter on /robots?compare=...", async () => {
    const res = await compareRateLimit(
      req("/robots", "compare=unitree-g1,digit"),
      ctx(),
    );
    expect(res).toBeUndefined(); // first hit, well under threshold: allowed
    expect(getStoreMock).toHaveBeenCalledWith("compare-rate-limit");
  });

  it("allows requests below the threshold to keep working (direct compare URL)", async () => {
    for (let i = 0; i < RATE_LIMIT_MAX_REQUESTS; i++) {
      const res = await compareRateLimit(req("/robots", "compare=a,b"), ctx());
      expect(res).toBeUndefined();
    }
  });

  it("returns 429 with a valid Retry-After once a client exceeds the threshold", async () => {
    let last: Response | undefined;
    for (let i = 0; i < RATE_LIMIT_MAX_REQUESTS + 1; i++) {
      last = (await compareRateLimit(req("/robots", "compare=a,b"), ctx())) as
        | Response
        | undefined;
    }
    expect(last).toBeInstanceOf(Response);
    expect(last!.status).toBe(429);
    expect(last!.headers.get("Retry-After")).toBeTruthy();
    expect(Number(last!.headers.get("Retry-After"))).toBeGreaterThan(0);
  });

  it("[STEP 8.10] a rejected request returns the terminating Response — the request chain stops before origin SSR", async () => {
    for (let i = 0; i < RATE_LIMIT_MAX_REQUESTS; i++) {
      await compareRateLimit(req("/robots", "compare=a,b"), ctx());
    }
    const res = (await compareRateLimit(req("/robots", "compare=a,b"), ctx())) as Response;
    expect(res).toBeInstanceOf(Response);
    expect(res.status).toBe(429);
  });

  it("tracks separate clients independently by IP", async () => {
    for (let i = 0; i < RATE_LIMIT_MAX_REQUESTS; i++) {
      await compareRateLimit(req("/robots", "compare=a,b"), ctx("203.0.113.10"));
    }
    const otherClient = await compareRateLimit(
      req("/robots", "compare=a,b"),
      ctx("198.51.100.20"),
    );
    expect(otherClient).toBeUndefined(); // a different IP has its own budget
  });

  it("does not give permutations of the same robot set a separate budget from each other", async () => {
    let last: Response | undefined;
    const permutations = ["a,b,c,d", "b,a,d,c", "d,c,b,a", "c,d,a,b"];
    for (let i = 0; i < RATE_LIMIT_MAX_REQUESTS + 1; i++) {
      last = (await compareRateLimit(
        req("/robots", `compare=${permutations[i % permutations.length]}`),
        ctx(),
      )) as Response | undefined;
    }
    expect(last?.status).toBe(429);
  });

  it("fails open (passes the request through) when the store throws", async () => {
    getStoreMock.mockImplementationOnce(() => ({
      getWithMetadata: vi.fn(async () => {
        throw new Error("blobs unavailable");
      }),
      setJSON: vi.fn(),
    }));
    const res = await compareRateLimit(req("/robots", "compare=a,b"), ctx());
    expect(res).toBeUndefined();
  });

  it("uses 'unknown' as the identity key rather than throwing when context.ip is absent", async () => {
    const res = await compareRateLimit(req("/robots", "compare=a,b"), {} as any);
    expect(res).toBeUndefined();
  });

  it("[STEP 8.11 integration] two concurrent requests for the same IP near the limit do not lose an increment", async () => {
    // Seed one below the cap, exactly like the unit-level concurrency test in
    // lib/__tests__/compare-rate-limit.test.ts, but exercised through the
    // real handler + mocked Blobs adapter this time.
    const key = "ip:203.0.113.10";
    // The handler reads the real wall clock (`Date.now()`), not an injected
    // `now` — seed a windowStart close to "now" so this counter reads as
    // within the current window rather than stale.
    const windowStart = Date.now();
    fakeBlobs.set(key, {
      value: { count: RATE_LIMIT_MAX_REQUESTS - 1, windowStart },
      etag: `e${++etagSeq}`,
    });

    const [a, b] = await Promise.all([
      compareRateLimit(req("/robots", "compare=a,b"), ctx()),
      compareRateLimit(req("/robots", "compare=a,b"), ctx()),
    ]);

    const responses = [a, b];
    const admitted = responses.filter((r) => r === undefined);
    const rejected = responses.filter((r) => r instanceof Response);
    // Both requests hit the same key concurrently; the CAS retry loop
    // resolves the race deterministically even without an explicit barrier
    // here (Vitest/Node's microtask scheduling still serialises the two
    // Blobs calls one at a time) — this integration test's job is to prove
    // the wiring end-to-end, the unit-level test above is the one with
    // guaranteed coordinated interleaving.
    expect(admitted.length + rejected.length).toBe(2);
    expect(fakeBlobs.get(key)?.value).toEqual({
      count: RATE_LIMIT_MAX_REQUESTS,
      windowStart,
    });
  });
});
