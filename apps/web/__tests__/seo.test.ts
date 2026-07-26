/**
 * WS8.5 / R23 — machine-surface pagination + defensive lastMod.
 *
 * R23 requires the sitemap and llms.txt to enumerate the ENTIRE published
 * canonical set (the 100-entity ceiling removed, not merely documented), and the
 * lastMod() fallback to be tested. These are the pure units behind both surfaces;
 * the rendered coverage is proven end-to-end in e2e/seo.spec.ts.
 */
import { describe, expect, it } from "vitest";

import { collectAll, lastMod, PAGE_SIZE } from "../lib/seo";

// A paged data source that records every page request, so tests can assert the
// loop both collects everything AND terminates without a wasteful extra fetch.
function pagedSource<T>(data: T[], reportedTotal: number = data.length) {
  const calls: { limit: number; offset: number }[] = [];
  const fetchPage = async ({ limit, offset }: { limit: number; offset: number }) => {
    calls.push({ limit, offset });
    return { items: data.slice(offset, offset + limit), total: reportedTotal };
  };
  return { fetchPage, calls };
}

const seq = (n: number) => Array.from({ length: n }, (_, i) => i);

describe("collectAll — full published-set pagination (R23 / Q10)", () => {
  it("collects a single short page in one request", async () => {
    const { fetchPage, calls } = pagedSource(seq(3));
    expect(await collectAll(fetchPage)).toEqual(seq(3));
    expect(calls).toHaveLength(1);
  });

  it("collects MORE than one page (>100 entities) across pages", async () => {
    const data = seq(250); // 100 + 100 + 50
    const { fetchPage, calls } = pagedSource(data);
    expect(await collectAll(fetchPage)).toEqual(data);
    expect(calls).toHaveLength(3);
    expect(calls.map((c) => c.offset)).toEqual([0, PAGE_SIZE, PAGE_SIZE * 2]);
  });

  it("stops once the whole declared set is collected — no wasteful extra fetch", async () => {
    // total is an exact multiple of the page size: after two full pages the set
    // is complete and the loop must NOT issue a third (empty) request.
    const data = seq(PAGE_SIZE * 2);
    const { fetchPage, calls } = pagedSource(data);
    expect(await collectAll(fetchPage)).toHaveLength(PAGE_SIZE * 2);
    expect(calls).toHaveLength(2);
  });

  it("terminates defensively on an empty page (total overstated, API returns nothing)", async () => {
    const { fetchPage, calls } = pagedSource<number>([], /* reportedTotal */ 100);
    expect(await collectAll(fetchPage)).toEqual([]);
    expect(calls).toHaveLength(1);
  });

  it("terminates on a short page even when total disagrees (mismatch)", async () => {
    // API claims 200 but only 30 exist: the short first page ends the loop.
    const { fetchPage, calls } = pagedSource(seq(30), /* reportedTotal */ 200);
    expect(await collectAll(fetchPage)).toEqual(seq(30));
    expect(calls).toHaveLength(1);
  });
});

describe("lastMod — defensive sitemap timestamp (R23 / Q11)", () => {
  it("returns a Date for a valid timestamp", () => {
    const r = lastMod("2026-07-01T12:00:00Z");
    expect(r.lastModified).toBeInstanceOf(Date);
    expect(r.lastModified?.getTime()).toBe(Date.parse("2026-07-01T12:00:00Z"));
  });

  it("accepts a date-only string", () => {
    expect(lastMod("2026-07-01").lastModified).toBeInstanceOf(Date);
  });

  it("omits lastModified for an invalid/NaN-equivalent date", () => {
    expect(lastMod("not-a-date")).toEqual({});
    expect(lastMod("2026-13-99")).toEqual({});
  });

  it("omits lastModified for empty / null / undefined", () => {
    expect(lastMod("")).toEqual({});
    expect(lastMod(null)).toEqual({});
    expect(lastMod(undefined)).toEqual({});
  });
});
