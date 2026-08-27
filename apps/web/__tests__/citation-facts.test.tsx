/**
 * AI Citation Layer v0.1 acceptance gates (docs/23 §24) — the pure-projection
 * half. CID-02 / CID-03.
 *
 * Gates proven here:
 *   CIT-B  UNKNOWN safety      — no absent value becomes a factual value
 *   CIT-C  evidence honesty    — the block asserts no evidence relationship
 *   CIT-I  projection parity   — CitationFacts and JSON-LD never disagree
 *   CIT-J  freshness honesty   — no timestamp is emitted by this block
 *   CIT-K  separate semantics  — maturity is not merged with obtainability
 *   CIT-L  no new truth store  — pure function of the governed RobotDetail
 */
import { beforeAll, describe, expect, it } from "vitest";

import { CitationFacts, citationFacts, isCitableValue } from "@/components/CitationFacts";
import { buildRobotJsonLd } from "@/lib/jsonld";
import type { RobotDetail } from "@/lib/types";

const ORIGIN = "https://citation.test.invalid";

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
      weight_kg: null,
      payload_kg: null,
      walk_speed_ms: null,
      runtime_minutes: 120,
      degrees_of_freedom: 23,
      mobility: "BIPEDAL",
      autonomy: null,
      arm_span_cm: null,
      reach_cm: null,
    },
    pricing_offers: [],
    availability_offers: [],
    deployments: [],
    extended_specs: [],
    capabilities: [],
    images: [],
    ...overrides,
  } as unknown as RobotDetail;
}

const labelsOf = (r: RobotDetail) => citationFacts(r).map((f) => f.label);
const valueOf = (r: RobotDetail, label: string) =>
  citationFacts(r).find((f) => f.label === label)?.value;

// ---- CIT-B — UNKNOWN safety -------------------------------------------------

describe("CIT-B — UNKNOWN is never converted into a factual value", () => {
  it("omits null specs entirely rather than emitting 0/false/empty", () => {
    const labels = labelsOf(robot());
    expect(labels).not.toContain("Weight");
    expect(labels).not.toContain("Payload");
    expect(labels).not.toContain("Autonomy");
    expect(labels).not.toContain("Walk speed");
  });

  it("emits no value that is empty, 'UNKNOWN', 'n/a' or a bare dash", () => {
    for (const f of citationFacts(robot())) {
      expect(f.value.trim()).not.toBe("");
      expect(f.value).not.toMatch(/^(unknown|n\/a|none|null|undefined|—|-)$/i);
    }
  });

  it("PRESERVES a real canonical zero (0 is a fact, not an absence)", () => {
    const r = robot({ specs: { ...robot().specs, payload_kg: 0, hand_dof: 0 } } as Partial<RobotDetail>);
    expect(valueOf(r, "Payload")).toBe("0 kg");
  });

  it("PRESERVES a real canonical false", () => {
    expect(isCitableValue(false)).toBe(true);
    expect(isCitableValue(0)).toBe(true);
  });

  it("rejects null, undefined and whitespace-only strings", () => {
    expect(isCitableValue(null)).toBe(false);
    expect(isCitableValue(undefined)).toBe(false);
    expect(isCitableValue("")).toBe(false);
    expect(isCitableValue("   ")).toBe(false);
  });

  it("omits an empty-string mobility rather than asserting it", () => {
    const r = robot({ specs: { ...robot().specs, mobility: "  " } } as Partial<RobotDetail>);
    expect(labelsOf(r)).not.toContain("Mobility");
  });
});

// ---- CIT-C — evidence honesty ----------------------------------------------

describe("CIT-C — the citation block asserts no evidence relationship", () => {
  it("emits no verified/confidence/evidence wording even when evidence exists", () => {
    const r = robot({
      pricing_offers: [
        {
          transaction_type: "PURCHASE",
          price_type: "PUBLIC",
          price: 13500,
          currency: "USD",
          billing_period: "ONE_TIME",
          evidence: {
            source_type: "MANUFACTURER_STORE",
            confidence: "VERIFIED",
            observed_at: "2026-07-24T00:00:00Z",
            verified_at: "2026-07-24T00:00:00Z",
          },
        },
      ],
    } as Partial<RobotDetail>);
    const serialized = JSON.stringify(citationFacts(r)).toLowerCase();
    // One VERIFIED price must never make the spec block claim verification.
    expect(serialized).not.toContain("verified");
    expect(serialized).not.toContain("confidence");
    expect(serialized).not.toContain("evidence");
  });
});

// ---- CIT-J — freshness honesty ---------------------------------------------

describe("CIT-J — no date meanings are conflated", () => {
  it("emits no timestamp of any kind from the citation block", () => {
    const r = robot({
      pricing_offers: [
        {
          transaction_type: "PURCHASE",
          price_type: "PUBLIC",
          price: 1,
          currency: "USD",
          billing_period: "ONE_TIME",
          evidence: {
            source_type: "MANUFACTURER_STORE",
            confidence: "VERIFIED",
            observed_at: "2026-07-24T00:00:00Z",
            verified_at: "2026-07-24T00:00:00Z",
            published_at: "2026-01-01T00:00:00Z",
          },
        },
      ],
    } as Partial<RobotDetail>);
    const serialized = JSON.stringify(citationFacts(r));
    expect(serialized).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  it("treats announced_year as a year, never as a freshness date", () => {
    // 2024 is a production/announcement year, printed bare. It must not be
    // rendered as, or alongside, an updated/verified/checked timestamp.
    expect(valueOf(robot(), "Announced")).toBe("2024");
  });
});

// ---- CIT-K — commercial semantics stay separate -----------------------------

describe("CIT-K — maturity is not merged with obtainability or price", () => {
  it("emits commercial_status verbatim as maturity only", () => {
    expect(valueOf(robot(), "Commercial status")).toBe("COMMERCIAL");
  });

  it("never emits an availability/price/'for sale' assertion", () => {
    const r = robot({
      availability_offers: [
        {
          transaction_type: "PURCHASE",
          availability_status: "AVAILABLE",
          region: "US",
        },
      ],
      pricing_offers: [
        {
          transaction_type: "PURCHASE",
          price_type: "PUBLIC",
          price: 13500,
          currency: "USD",
          billing_period: "ONE_TIME",
        },
      ],
    } as Partial<RobotDetail>);
    const labels = labelsOf(r);
    expect(labels).not.toContain("Availability");
    expect(labels).not.toContain("Price");
    const serialized = JSON.stringify(citationFacts(r)).toLowerCase();
    expect(serialized).not.toContain("for sale");
    expect(serialized).not.toContain("available");
    expect(serialized).not.toContain("13500");
  });
});

// ---- CIT-I — parity with the JSON-LD projection -----------------------------

describe("CIT-I — CitationFacts and JSON-LD never contradict each other", () => {
  it("agrees on every spec both surfaces choose to emit", () => {
    const r = robot();
    const facts = new Map(citationFacts(r).map((f) => [f.label, f.value]));
    const jsonld = buildRobotJsonLd(r) as { "@graph": Array<Record<string, unknown>> };
    const product = jsonld["@graph"].find((n) => n["@type"] === "Product")!;
    const props = (product.additionalProperty ?? []) as Array<{
      name: string;
      value: unknown;
      unitText?: string;
    }>;

    // CIT-I is about factual CONSISTENCY, not identical formatting. The two
    // surfaces legitimately spell one unit differently — the page and this
    // block use the catalogue's short form ("min", matching the existing
    // SpecRow), while JSON-LD emits the long form ("minutes") for machine
    // consumers. That is a presentation difference; asserting literal string
    // equality would be testing the label, not the fact. What must never
    // differ is the VALUE and the unit's MEANING.
    const UNIT_ALIASES: Record<string, string> = {
      minutes: "min",
      min: "min",
      cm: "cm",
      kg: "kg",
      "m/s": "m/s",
    };
    const normalizeUnit = (u?: string) => (u ? (UNIT_ALIASES[u] ?? u) : "");

    for (const p of props) {
      const visible = facts.get(p.name);
      if (visible === undefined) continue; // JSON-LD may carry a superset; never a CONFLICT
      const [visibleValue, ...visibleUnitParts] = visible.split(" ");
      expect(visibleValue).toBe(String(p.value));
      expect(normalizeUnit(visibleUnitParts.join(" ") || undefined)).toBe(
        normalizeUnit(p.unitText),
      );
    }
  });

  it("neither surface asserts a spec the other omits as UNKNOWN", () => {
    const r = robot();
    const jsonld = buildRobotJsonLd(r) as { "@graph": Array<Record<string, unknown>> };
    const product = jsonld["@graph"].find((n) => n["@type"] === "Product")!;
    const jsonldNames = new Set(
      ((product.additionalProperty ?? []) as Array<{ name: string }>).map((p) => p.name),
    );
    // weight/payload/autonomy are UNKNOWN in the fixture: absent from BOTH.
    for (const omitted of ["Weight", "Payload", "Autonomy"]) {
      expect(jsonldNames.has(omitted)).toBe(false);
      expect(labelsOf(r)).not.toContain(omitted);
    }
  });

  it("shares one assertability rule with the JSON-LD builder", () => {
    // An empty-string description is rejected by jsonld's isAssertableFact; the
    // citation block's isCitableValue must agree, or the two surfaces drift.
    const r = robot({ summary: "   ", description: null } as Partial<RobotDetail>);
    const jsonld = buildRobotJsonLd(r) as { "@graph": Array<Record<string, unknown>> };
    const product = jsonld["@graph"].find((n) => n["@type"] === "Product")!;
    expect(product.description).toBeUndefined();
    expect(isCitableValue("   ")).toBe(false);
  });
});

// ---- CIT-L — no new source of truth ----------------------------------------

describe("CIT-L — pure projection, no independent data access", () => {
  it("is a pure function of the passed record (same input -> same output)", () => {
    const r = robot();
    expect(citationFacts(r)).toEqual(citationFacts(r));
  });

  it("derives every value from the record it was given", () => {
    const renamed = robot({ name: "Renamed Unit" } as Partial<RobotDetail>);
    expect(valueOf(renamed, "Robot")).toBe("Renamed Unit");
  });

  it("exports a component that takes only the governed record as input", () => {
    // Structural, not behavioural: a component needing anything beyond the
    // record would have to accept it here.
    expect(CitationFacts.length).toBe(1);
  });
});

// ---- units are canonical ----------------------------------------------------

describe("canonical units are preserved", () => {
  it("keeps catalogue units (cm/kg/min) and never converts", () => {
    const r = robot();
    expect(valueOf(r, "Height")).toBe("170 cm");
    expect(valueOf(r, "Runtime")).toBe("120 min");
    expect(valueOf(r, "Degrees of freedom")).toBe("23");
  });
});
