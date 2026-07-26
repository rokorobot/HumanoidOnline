import { beforeAll, describe, expect, it } from "vitest";

import { buildRobotJsonLd } from "@/lib/jsonld";
import type { RobotDetail } from "@/lib/types";

// WS8.2 / R8: the canonical origin is no longer defaulted to production
// (gap B4), so this suite states the origin it is asserting against instead of
// inheriting a hard-coded hostname. Stronger, not weaker: the assertions below
// now prove the emitted URLs track the CONFIGURED origin rather than a constant
// that happened to be baked into `lib/site.ts`.
const ORIGIN = "https://jsonld.test.invalid";

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});

function robot(overrides: Partial<RobotDetail> = {}): RobotDetail {
  return {
    id: "r1",
    slug: "test-bot",
    name: "Test Bot",
    manufacturer: { slug: "acme", name: "Acme Robotics" },
    commercial_status: "COMMERCIAL",
    summary: "A test humanoid.",
    description: null,
    announced_year: 2024,
    specs: {
      height_cm: 170,
      weight_kg: null, // UNKNOWN -> must be omitted
      payload_kg: null, // UNKNOWN -> must be omitted
      mobility: "BIPEDAL",
      autonomy: null,
    },
    images: [{ image_url: "/robots/test-bot.jpg", image_type: "FRONT", source_type: "MANUFACTURER", is_official: true, is_primary: true }],
    ...overrides,
  } as unknown as RobotDetail;
}

function graphOf(r: RobotDetail) {
  const jsonld = buildRobotJsonLd(r) as { "@context": string; "@graph": Array<Record<string, unknown>> };
  const product = jsonld["@graph"].find((n) => n["@type"] === "Product")!;
  const org = jsonld["@graph"].find((n) => n["@type"] === "Organization")!;
  return { jsonld, product, org };
}

describe("buildRobotJsonLd", () => {
  it("emits a schema.org Product + Organization graph with canonical URLs", () => {
    const { jsonld, product, org } = graphOf(robot());
    expect(jsonld["@context"]).toBe("https://schema.org");
    expect(product["@id"]).toMatch(/\/robots\/test-bot$/);
    expect(product.url).toBe(product["@id"]);
    expect(product.name).toBe("Test Bot");
    expect(org["@id"]).toMatch(/\/manufacturers\/acme$/);
    // Product links to the Organization by @id (single source of truth).
    expect((product.manufacturer as { "@id": string })["@id"]).toBe(org["@id"]);
  });

  it("omits UNKNOWN specs (never coerces to 0/false) — AGENT-01.3", () => {
    const { product } = graphOf(robot());
    const props = product.additionalProperty as Array<{ name: string; value: unknown }>;
    const names = props.map((p) => p.name);
    expect(names).toContain("Height");
    expect(names).toContain("Mobility");
    expect(names).toContain("Commercial status");
    // null specs must not appear at all.
    expect(names).not.toContain("Payload");
    expect(names).not.toContain("Weight");
    expect(names).not.toContain("Autonomy");
    // no property ever carries a null/undefined value.
    for (const p of props) {
      expect(p.value).not.toBeNull();
      expect(p.value).not.toBeUndefined();
    }
  });

  it("maps present specs with units and the announced year", () => {
    const { product } = graphOf(robot());
    const props = product.additionalProperty as Array<{ name: string; value: unknown; unitText?: string }>;
    const height = props.find((p) => p.name === "Height")!;
    expect(height.value).toBe(170);
    expect(height.unitText).toBe("cm");
    expect(product.productionDate).toBe("2024");
    expect(product.description).toBe("A test humanoid.");
  });

  it("includes images only when present, as absolute URLs (MEDIA-01)", () => {
    const { product } = graphOf(robot());
    expect(product.image).toEqual([`${ORIGIN}/robots/test-bot.jpg`]);
    const noImg = graphOf(robot({ images: [] }));
    expect(noImg.product.image).toBeUndefined();
  });
});
