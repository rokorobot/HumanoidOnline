// COMPARE BACKEND CDN KEY CANONICALIZATION v0.4 (2026-08-24) — proves
// compareRobots() sends a canonical (sorted, de-duplicated) `ids` query so
// every permutation of the same robot set hits the identical backend URL
// (and therefore the same Vercel CDN cache entry), while the caller's
// originally-requested order is preserved end-to-end in the returned data.
// See lib/api-client.ts compareRobots() for the mechanism.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CompareResponse, RobotDetail } from "@/lib/types";

type FetchInit = RequestInit;

function mockFetch(body: unknown, status = 200) {
  const fn = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  // @ts-expect-error - test double, not a full Fetch implementation
  global.fetch = fn;
  return fn;
}

function fetchUrl(fn: ReturnType<typeof mockFetch>, callIndex = 0): string {
  const call = fn.mock.calls[callIndex] as unknown as [string, FetchInit];
  return call[0];
}

function stubRobot(slug: string): RobotDetail {
  return { slug } as unknown as RobotDetail;
}

// Backend response shaped as routers/robots.py actually returns it: robots +
// row values ordered to match whatever `ids` order the request carried — i.e.
// canonical (sorted) order, since that's what the client now sends.
function canonicalResponse(slugs: string[]): CompareResponse {
  const sorted = [...slugs].sort();
  return {
    robots: sorted.map(stubRobot),
    rows: [
      {
        group: "specs",
        key: "payload_kg",
        label: "Payload",
        values: Object.fromEntries(sorted.map((s, i) => [s, i])),
      },
    ],
  };
}

describe("compareRobots — CDN key canonicalization", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("1. two permutations of the same set generate the exact same backend fetch URL", async () => {
    const { compareRobots } = await import("@/lib/api-client");

    const fetch1 = mockFetch(canonicalResponse(["a", "b", "c", "d"]));
    await compareRobots(["a", "b", "c", "d"]);
    const url1 = fetchUrl(fetch1);

    vi.resetModules();
    const { compareRobots: compareRobots2 } = await import("@/lib/api-client");
    const fetch2 = mockFetch(canonicalResponse(["a", "b", "c", "d"]));
    await compareRobots2(["d", "a", "c", "b"]);
    const url2 = fetchUrl(fetch2);

    vi.resetModules();
    const { compareRobots: compareRobots3 } = await import("@/lib/api-client");
    const fetch3 = mockFetch(canonicalResponse(["a", "b", "c", "d"]));
    await compareRobots3(["b", "d", "a", "c"]);
    const url3 = fetchUrl(fetch3);

    expect(url1).toContain("ids=a%2Cb%2Cc%2Cd");
    expect(url1).toBe(url2);
    expect(url1).toBe(url3);
  });

  it("2. returned data.robots follows the original caller-requested order", async () => {
    const { compareRobots } = await import("@/lib/api-client");
    mockFetch(canonicalResponse(["a", "b", "c", "d"]));

    const result = await compareRobots(["d", "a", "c", "b"]);

    expect(result?.robots.map((r) => r.slug)).toEqual(["d", "a", "c", "b"]);
  });

  it("3. row values remain associated with the correct slug after reordering", async () => {
    const { compareRobots } = await import("@/lib/api-client");
    // canonical (sorted) response: a=0, b=1, c=2, d=3
    mockFetch(canonicalResponse(["a", "b", "c", "d"]));

    const result = await compareRobots(["d", "a", "c", "b"]);
    const row = result?.rows[0];

    expect(row?.values).toEqual({ d: 3, a: 0, c: 2, b: 1 });
    expect(Object.keys(row?.values ?? {})).toEqual(["d", "a", "c", "b"]);
  });

  it("4. duplicate IDs collapse to first occurrence, same as backend dict.fromkeys semantics", async () => {
    const fetchMock = mockFetch(canonicalResponse(["a", "b"]));
    const { compareRobots } = await import("@/lib/api-client");

    const result = await compareRobots(["b", "a", "b"]);

    // Wire request de-duplicates + sorts: {b,a} -> canonical "a,b".
    expect(fetchUrl(fetchMock)).toContain("ids=a%2Cb");
    // Caller-visible order follows first-occurrence of the de-duplicated
    // request order ("b" then "a"), matching the pre-canonicalization
    // behaviour where the backend's own dict.fromkeys dedupe did the same.
    expect(result?.robots.map((r) => r.slug)).toEqual(["b", "a"]);
  });

  it("5. already-canonical (sorted) input behaves identically to any other permutation", async () => {
    const fetchMock = mockFetch(canonicalResponse(["a", "b", "c"]));
    const { compareRobots } = await import("@/lib/api-client");

    const result = await compareRobots(["a", "b", "c"]);

    expect(fetchUrl(fetchMock)).toContain("ids=a%2Cb%2Cc");
    expect(result?.robots.map((r) => r.slug)).toEqual(["a", "b", "c"]);
  });

  it("6a. 422 still surfaces as null", async () => {
    mockFetch({ detail: "compare requires 2-4 valid robot slugs" }, 422);
    const { compareRobots } = await import("@/lib/api-client");

    const result = await compareRobots(["a"]);

    expect(result).toBeNull();
  });

  it("6b. 404 still surfaces as null", async () => {
    mockFetch({}, 404);
    const { compareRobots } = await import("@/lib/api-client");

    const result = await compareRobots(["a", "b"]);

    expect(result).toBeNull();
  });

  it("6c. a slug the backend drops (not found) is dropped from the result too, never fabricated", async () => {
    // Requested a, x, b — backend only knows a and b.
    mockFetch(canonicalResponse(["a", "b"]));
    const { compareRobots } = await import("@/lib/api-client");

    const result = await compareRobots(["a", "x", "b"]);

    expect(result?.robots.map((r) => r.slug)).toEqual(["a", "b"]);
  });

  it("stays no-store + correlated (unchanged transport contract)", async () => {
    const fetchMock = mockFetch(canonicalResponse(["a", "b"]));
    const { compareRobots } = await import("@/lib/api-client");
    await compareRobots(["a", "b"]);

    const call = fetchMock.mock.calls[0] as unknown as [string, FetchInit];
    const init = call[1];
    expect(init.cache).toBe("no-store");
    expect(Object.keys(init.headers as Record<string, string>)).toContain(
      "x-request-id",
    );
  });
});
