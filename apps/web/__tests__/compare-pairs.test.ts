// SEO-04 — curated "A vs B" pages: one sorted path per pair, a bounded linear set.
import { describe, expect, it } from "vitest";

import { ALTERNATIVES, alternativesFor, curatedPairPaths, pairPath, parsePair } from "@/lib/compare-pairs";

const r = (slug: string, maker: string, extra: Partial<{ commercial_status: string; mobility: string; height_cm: number; payload_kg: number }> = {}) => ({
  slug,
  name: slug.toUpperCase(),
  manufacturer: { slug: maker, name: maker },
  commercial_status: "PILOT",
  mobility: null,
  height_cm: null,
  payload_kg: null,
  ...extra,
});

describe("pairPath / parsePair", () => {
  it("folds both orders into one sorted path", () => {
    expect(pairPath("unitree-h2", "1x-neo")).toBe("/compare/1x-neo-vs-unitree-h2");
    expect(pairPath("1x-neo", "unitree-h2")).toBe("/compare/1x-neo-vs-unitree-h2");
  });

  it("round-trips a path segment", () => {
    expect(parsePair("1x-neo-vs-unitree-h2")).toEqual(["1x-neo", "unitree-h2"]);
  });

  it.each(["1x-neo", "a-vs-a", "-vs-b", "a-vs-b-vs-c", ""])("rejects %s", (seg) => {
    expect(parsePair(seg)).toBeNull();
  });
});

describe("alternativesFor", () => {
  const all = [
    r("a1", "acme", { mobility: "BIPEDAL", height_cm: 170 }),
    r("a2", "acme", { mobility: "BIPEDAL", height_cm: 170 }),
    r("b1", "beta", { mobility: "BIPEDAL", height_cm: 175 }),
    r("c1", "gamma", { mobility: "WHEELED", commercial_status: "CONCEPT" }),
  ];

  it("never includes the robot itself and ranks by recorded similarity", () => {
    expect(alternativesFor(all[0], all).map((o) => o.slug)).toEqual(["b1", "a2", "c1"]);
  });

  it("is deterministic and capped", () => {
    const many = Array.from({ length: 20 }, (_, i) => r(`r${String(i).padStart(2, "0")}`, `m${i}`));
    expect(alternativesFor(many[0], many)).toHaveLength(ALTERNATIVES);
    expect(alternativesFor(many[0], many)).toEqual(alternativesFor(many[0], [...many].reverse()));
  });
});

it("curated pairs grow linearly, are unique and sorted", () => {
  const many = Array.from({ length: 50 }, (_, i) => r(`r${String(i).padStart(2, "0")}`, `m${i % 7}`));
  const paths = curatedPairPaths(many);
  expect(paths.length).toBeLessThanOrEqual(50 * ALTERNATIVES);
  expect(new Set(paths).size).toBe(paths.length);
  expect(paths).toEqual([...paths].sort());
  for (const p of paths) expect(p).toBe(pairPath(...parsePair(p.slice("/compare/".length))!));
});
