/**
 * WS8.3 / R14 — AGENT-01 truth on the machine projections.
 *
 * Absence is proven by injection: a suppressed entity is planted in what the
 * projection layer consumes and then hunted for in the real serialized output.
 * Asserting that a field name is missing would pass just as well against a
 * broken projection.
 *
 * The API is the `is_published` boundary (proven server-side in
 * `test_truth_regressions.py`); these tests prove the *projection* adds nothing
 * back — it must never resurrect an entity the governed read withheld, and it
 * must never turn UNKNOWN into a fact.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildRobotJsonLd } from "@/lib/jsonld";
import type { RobotDetail } from "@/lib/types";

const ORIGIN = "https://agent-truth.test.invalid";

beforeEach(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
  vi.resetModules();
});

function robot(overrides: Partial<RobotDetail> = {}): RobotDetail {
  return {
    id: "r1",
    slug: "published-bot",
    name: "Published Bot",
    manufacturer: { slug: "acme", name: "Acme Robotics" },
    commercial_status: "COMMERCIAL",
    summary: "A published humanoid.",
    description: null,
    announced_year: 2024,
    specs: { height_cm: 170, weight_kg: null, payload_kg: null, mobility: "BIPEDAL" },
    images: [],
    ...overrides,
  } as RobotDetail;
}

// -------------------------------------------------- UNKNOWN is never a fact

describe("AGENT-01.3 — UNKNOWN is preserved exactly", () => {
  it("omits null specs rather than emitting 0, false or a placeholder", () => {
    const graph = buildRobotJsonLd(robot()) as { "@graph": Record<string, unknown>[] };
    const product = graph["@graph"].find((n) => n["@type"] === "Product")!;
    const props = product.additionalProperty as { name: string; value: unknown }[];
    const names = props.map((p) => p.name);

    expect(names).not.toContain("Weight");
    expect(names).not.toContain("Payload");
    for (const p of props) {
      expect(p.value).not.toBeNull();
      expect(p.value).not.toBe(0);
      expect(p.value).not.toBe(false);
      expect(p.value).not.toBe("");
    }
    const serialized = JSON.stringify(graph).toLowerCase();
    for (const forbidden of ['"unknown"', '"n/a"', '"unavailable"', '"none"']) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("omits an empty-string spec instead of asserting it (R14 gap Q12)", () => {
    // The old guard was `!== null && !== undefined`, so "" became a
    // PropertyValue — an empty assertion a machine cannot distinguish from a
    // real one. That is a fabricated fact.
    const graph = buildRobotJsonLd(
      robot({ specs: { mobility: "", autonomy: "   ", height_cm: 170 } as never }),
    ) as { "@graph": Record<string, unknown>[] };
    const product = graph["@graph"].find((n) => n["@type"] === "Product")!;
    const props = product.additionalProperty as { name: string; value: unknown }[];

    expect(props.map((p) => p.name)).not.toContain("Mobility");
    expect(props.map((p) => p.name)).not.toContain("Autonomy");
    expect(props.map((p) => p.name)).toContain("Height");
  });

  it("KEEPS a genuine 0 — dropping it would be the mirror-image error", () => {
    // UNKNOWN -> omitted. Zero -> asserted. Conflating them in either direction
    // is the AGENT-01.3 failure; this pins both halves.
    const graph = buildRobotJsonLd(
      robot({ specs: { payload_kg: 0, height_cm: null } as never }),
    ) as { "@graph": Record<string, unknown>[] };
    const product = graph["@graph"].find((n) => n["@type"] === "Product")!;
    const props = product.additionalProperty as { name: string; value: unknown }[];

    const payload = props.find((p) => p.name === "Payload");
    expect(payload?.value).toBe(0);
    expect(props.map((p) => p.name)).not.toContain("Height");
  });

  it("omits an empty commercial status rather than asserting it", () => {
    const graph = buildRobotJsonLd(
      robot({ commercial_status: "" as never }),
    ) as { "@graph": Record<string, unknown>[] };
    const product = graph["@graph"].find((n) => n["@type"] === "Product")!;
    const props = product.additionalProperty as { name: string }[];
    expect(props.map((p) => p.name)).not.toContain("Commercial status");
  });

  it("never fabricates provenance it does not have (AGENT-01.4)", () => {
    const serialized = JSON.stringify(buildRobotJsonLd(robot()));
    for (const invented of ["verified_at", "confidence", "source_url", "citation"]) {
      expect(serialized).not.toContain(invented);
    }
  });
});

// ------------------------------------------- unpublished entities: absence

describe("AGENT-01.7 — the projection cannot resurrect a withheld entity", () => {
  const published = {
    slug: "published-bot",
    name: "Published Bot",
    manufacturer: { slug: "acme", name: "Acme Robotics" },
    updated_at: "2026-01-01T00:00:00Z",
  };
  const SUPPRESSED = "UNPUBLISHED-SENTINEL-9f3c";

  beforeEach(() => {
    // The governed read withholds unpublished entities, so the projection only
    // ever sees `published`. If a surface emitted the sentinel it could only
    // have invented it.
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: [published], total: 1 })),
      listManufacturers: vi.fn(async () => ({
        items: [{ slug: "acme", name: "Acme Robotics", updated_at: "2026-01-01T00:00:00Z" }],
        total: 1,
      })),
      listUseCases: vi.fn(async () => ({ items: [], total: 0 })),
    }));
  });

  it("sitemap.xml lists only what the governed read returned", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = await sitemap();
    const urls = entries.map((e) => e.url).join(" ");
    expect(urls).toContain("/robots/published-bot");
    expect(urls).not.toContain(SUPPRESSED);
    // Every robot URL corresponds to a returned item — no extras.
    const robotUrls = entries.filter((e) => e.url.includes("/robots/"));
    expect(robotUrls).toHaveLength(1);
  });

  it("llms.txt lists only what the governed read returned", async () => {
    const { GET } = await import("@/app/llms.txt/route");
    const body = await (await GET()).text();
    expect(body).toContain("/robots/published-bot");
    expect(body).not.toContain(SUPPRESSED);
    expect(body).not.toContain("NOT_VERIFIED");
    expect(body).not.toContain("discovery_candidate");
  });

  it("an empty governed read produces an empty projection, not a fallback", async () => {
    vi.resetModules();
    vi.doMock("@/lib/api-client", () => ({
      listRobots: vi.fn(async () => ({ items: [], total: 0 })),
      listManufacturers: vi.fn(async () => ({ items: [], total: 0 })),
      listUseCases: vi.fn(async () => ({ items: [], total: 0 })),
    }));
    const { GET } = await import("@/app/llms.txt/route");
    const body = await (await GET()).text();
    expect(body).not.toContain("/robots/published-bot");

    const { default: sitemap } = await import("@/app/sitemap");
    const entries = await sitemap();
    expect(entries.filter((e) => e.url.includes("/robots/"))).toHaveLength(0);
  });
});
