// Neon Transfer Optimization Phase 1 — proves the caching boundary the phase
// introduced: catalogue-static reads participate in Next's Data Cache, while
// every user-specific / write-adjacent / already-cached read keeps its exact
// original always-fresh behaviour. See lib/api-client.ts for the policy.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type FetchInit = RequestInit & { next?: { revalidate?: number } };

function mockFetchOnce(body: unknown, status = 200) {
  const fn = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  // @ts-expect-error - test double, not a full Fetch implementation
  global.fetch = fn;
  return fn;
}

function lastInit(fn: ReturnType<typeof mockFetchOnce>): FetchInit {
  const call = fn.mock.calls[0] as unknown as [string, FetchInit];
  return call[1];
}

describe("api-client — catalogue-static reads use Next's Data Cache", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("listRobots revalidates instead of forcing no-store", async () => {
    const fetchMock = mockFetchOnce({ items: [], total: 0, limit: 24, offset: 0 });
    const { listRobots } = await import("@/lib/api-client");
    await listRobots({ limit: 24 });

    const init = lastInit(fetchMock);
    expect(init.next).toEqual({ revalidate: 300 });
    expect(init.cache).toBeUndefined();
    // The X-Request-ID correlation header carries a fresh random value per
    // request. Next's fetch cache key includes headers (confirmed against the
    // installed Next 15 source), so sending it here would make every cache key
    // unique and silently defeat revalidation — it must be absent.
    expect(init.headers).toBeUndefined();
  });

  it("findRobot revalidates instead of forcing no-store", async () => {
    const fetchMock = mockFetchOnce({ slug: "unitree-g1" });
    const { findRobot } = await import("@/lib/api-client");
    await findRobot("unitree-g1");

    const init = lastInit(fetchMock);
    expect(init.next).toEqual({ revalidate: 300 });
    expect(init.cache).toBeUndefined();
    expect(init.headers).toBeUndefined();
  });

  it("listManufacturers / findManufacturer revalidate", async () => {
    const fetchMock = mockFetchOnce({ items: [], total: 0, limit: 24, offset: 0 });
    const { listManufacturers } = await import("@/lib/api-client");
    await listManufacturers();
    expect(lastInit(fetchMock).next).toEqual({ revalidate: 300 });

    vi.resetModules();
    const fetchMock2 = mockFetchOnce({ slug: "unitree" });
    const { findManufacturer } = await import("@/lib/api-client");
    await findManufacturer("unitree");
    expect(lastInit(fetchMock2).next).toEqual({ revalidate: 300 });
  });

  it("listUseCases / findUseCase revalidate", async () => {
    const fetchMock = mockFetchOnce({ items: [], total: 0, limit: 24, offset: 0 });
    const { listUseCases } = await import("@/lib/api-client");
    await listUseCases();
    expect(lastInit(fetchMock).next).toEqual({ revalidate: 300 });

    vi.resetModules();
    const fetchMock2 = mockFetchOnce({ slug: "warehouse-logistics" });
    const { findUseCase } = await import("@/lib/api-client");
    await findUseCase("warehouse-logistics");
    expect(lastInit(fetchMock2).next).toEqual({ revalidate: 300 });
  });

  it("listRegions revalidates", async () => {
    const fetchMock = mockFetchOnce([]);
    const { listRegions } = await import("@/lib/api-client");
    await listRegions({ type: "COUNTRY" });
    expect(lastInit(fetchMock).next).toEqual({ revalidate: 300 });
  });

  it("getMarketSnapshot revalidates", async () => {
    const fetchMock = mockFetchOnce({ total_tracked: 0 });
    const { getMarketSnapshot } = await import("@/lib/api-client");
    await getMarketSnapshot();
    expect(lastInit(fetchMock).next).toEqual({ revalidate: 300 });
  });
});

// Negative cache boundary — every path the task named explicitly must remain
// byte-identical to pre-Phase-1 behaviour: cache: "no-store" + the full
// X-Request-ID correlation header (GET reads), or cache: "no-store" with no
// caching semantics at all (POST/write proxies). Each item is its own test so
// a regression in any one of them fails by name, not buried in a loop.
describe("negative cache boundary — write / user-specific / admin-like paths stay fresh", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("getRequirement (buyer-specific requirement read) stays no-store + correlated", async () => {
    const fetchMock = mockFetchOnce({ id: "r1" });
    const { getRequirement } = await import("@/lib/api-client");
    await getRequirement("r1");

    const init = lastInit(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toContain(
      "x-request-id",
    );
  });

  it("getMatches (buyer-specific match results) stays no-store + correlated", async () => {
    const fetchMock = mockFetchOnce({ requirement_id: "r1", matches: [] });
    const { getMatches } = await import("@/lib/api-client");
    await getMatches("r1");

    const init = lastInit(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toContain(
      "x-request-id",
    );
  });

  it("buyer-requirement submission (POST) is never cached", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      text: async () => JSON.stringify({ id: "r1" }),
      headers: new Headers({ "Content-Type": "application/json" }),
    }));
    // @ts-expect-error - test double, not a full Fetch implementation
    global.fetch = fetchMock;
    const { POST } = await import("@/app/api/buyer-requirements/route");
    const req = new Request("http://test.invalid/api/buyer-requirements", {
      method: "POST",
      body: JSON.stringify({ use_case: "warehouse-logistics" }),
    });
    const res = await POST(req);

    expect(res.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const init = call[1];
    expect(init.cache).toBe("no-store");
    expect(init.method).toBe("POST");
  });

  it("commercial-lead submission (POST) is never cached", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      text: async () => JSON.stringify({ id: "l1", lead_status: "NEW" }),
      headers: new Headers({ "Content-Type": "application/json" }),
    }));
    // @ts-expect-error - test double, not a full Fetch implementation
    global.fetch = fetchMock;
    const { POST } = await import("@/app/api/commercial-leads/route");
    const req = new Request("http://test.invalid/api/commercial-leads", {
      method: "POST",
      body: JSON.stringify({ robot_slug: "unitree-g1" }),
    });
    const res = await POST(req);

    expect(res.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const init = call[1];
    expect(init.cache).toBe("no-store");
    expect(init.method).toBe("POST");
  });

  it("discovery-review / admin-like candidate reads stay no-store + correlated", async () => {
    const fetchMock = mockFetchOnce({ items: [], total: 0, limit: 24, offset: 0 });
    const { listDiscoveryCandidates } = await import("@/lib/api-client");
    await listDiscoveryCandidates();

    const init = lastInit(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toContain(
      "x-request-id",
    );
  });

  it("compareRobots (its own 60s backend cache, not this phase's mechanism) stays no-store + correlated", async () => {
    const fetchMock = mockFetchOnce({ robots: [], rows: [] });
    const { compareRobots } = await import("@/lib/api-client");
    await compareRobots(["a", "b"]);

    const init = lastInit(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toContain(
      "x-request-id",
    );
  });
});

// The cache-key test the review explicitly asked for: one cacheable GET and
// one dynamic GET, side by side, each asserting BOTH halves of its contract —
// not just "cache mode X" but also the header behaviour that makes Next's Data
// Cache actually work (or, for the dynamic case, that correlation survives).
describe("cache-key contract — the exact pairing that makes Phase 1 correct", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("a catalogue-cacheable GET uses next.revalidate and sends NO X-Request-ID header", async () => {
    const fetchMock = mockFetchOnce({ items: [], total: 0, limit: 24, offset: 0 });
    const { listRobots } = await import("@/lib/api-client");
    await listRobots({ limit: 24 });

    const init = lastInit(fetchMock);
    expect(init.next).toEqual({ revalidate: 300 });
    expect(init.headers).toBeUndefined(); // no headers object at all -> no x-request-id
  });

  it("a dynamic (buyer-specific) GET stays cache: no-store and keeps its X-Request-ID", async () => {
    const fetchMock = mockFetchOnce({ id: "r1" });
    const { getRequirement } = await import("@/lib/api-client");
    await getRequirement("r1");

    const init = lastInit(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
    const headerKeys = Object.keys(init.headers as Record<string, string>);
    expect(headerKeys).toContain("x-request-id");
    // FastAPI generates its own id when this header is absent (verified against
    // app/observability.py + the existing backend test
    // test_correlation_id_generated_when_absent), so correlation is preserved
    // either way — but the dynamic path is proven to still SEND it, unchanged.
  });
});

describe("llms.txt — no longer forces max-age=0/must-revalidate", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://neon-cache-policy.test.invalid";
    vi.resetModules();
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: [], total: 0 })),
      listManufacturers: vi.fn(async () => ({ items: [], total: 0 })),
      listUseCases: vi.fn(async () => ({ items: [], total: 0 })),
    }));
  });

  // `dynamic = "force-dynamic"` is deliberately KEPT (see the route's own
  // comment): removing it made `next build` attempt to statically prerender
  // the route, which requires a reachable API/Neon at BUILD time — reproduced
  // locally as a real build failure before this design was corrected. The
  // Neon-transfer win comes entirely from the underlying reads now carrying
  // their own `next: { revalidate }` (proven in the api-client describe blocks
  // above), which Next's Data Cache still honours inside a force-dynamic route.
  it("keeps dynamic = force-dynamic (build-time prerendering must stay off)", async () => {
    const mod = await import("@/app/llms.txt/route");
    expect((mod as { dynamic?: string }).dynamic).toBe("force-dynamic");
  });

  it("response Cache-Control allows shared caching (no must-revalidate)", async () => {
    const { GET } = await import("@/app/llms.txt/route");
    const res = await GET();
    const cacheControl = res.headers.get("cache-control") ?? "";
    expect(cacheControl).not.toContain("must-revalidate");
    expect(cacheControl).not.toContain("max-age=0, must-revalidate");
    expect(cacheControl).toContain("s-maxage=900");
  });
});

describe("sitemap.xml — no longer forces a fresh full-catalogue read per hit", () => {
  it("keeps dynamic = force-dynamic (build-time prerendering must stay off)", async () => {
    vi.resetModules();
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: [], total: 0 })),
      listManufacturers: vi.fn(async () => ({ items: [], total: 0 })),
      listUseCases: vi.fn(async () => ({ items: [], total: 0 })),
    }));
    const mod = await import("@/app/sitemap");
    expect((mod as { dynamic?: string }).dynamic).toBe("force-dynamic");
  });
});

// Phase 1 deliberately touches NO page-level `dynamic`/`revalidate` export —
// an earlier draft removed force-dynamic and added `revalidate`, which made
// `next build` attempt to statically prerender those routes (reproduced
// locally as a real build failure: fetch ECONNREFUSED against a database that
// doesn't exist at build time). Every route's segment config is therefore
// pinned as UNCHANGED — matching this repo's precedent for config assertions
// (__tests__/netlify-config.test.ts) rather than rendering full page trees.
describe("page segment config — untouched by Phase 1 (caching lives in lib/api-client.ts only)", () => {
  const webRoot = resolve(process.cwd());
  const read = (rel: string) => readFileSync(resolve(webRoot, rel), "utf8");

  it.each([
    "app/page.tsx",
    "app/robots/page.tsx",
    "app/robots/[slug]/page.tsx",
    "app/manufacturers/page.tsx",
    "app/manufacturers/[slug]/page.tsx",
    "app/compare/page.tsx",
    "app/use-cases/page.tsx",
    "app/use-cases/[slug]/page.tsx",
    "app/find-a-humanoid/page.tsx",
    "app/matches/[id]/page.tsx",
    "app/discovery-review/page.tsx",
  ])("%s: force-dynamic preserved exactly", (rel) => {
    const src = read(rel);
    expect(src).toMatch(/export const dynamic\s*=\s*["']force-dynamic["']/);
    expect(src).not.toMatch(/export const revalidate/);
  });

  it("write-proxy route handlers are untouched: force-dynamic + no-store preserved", () => {
    for (const rel of [
      "app/api/buyer-requirements/route.ts",
      "app/api/commercial-leads/route.ts",
    ]) {
      const src = read(rel);
      expect(src).toMatch(/export const dynamic\s*=\s*["']force-dynamic["']/);
      expect(src).toMatch(/cache:\s*["']no-store["']/);
    }
  });
});
