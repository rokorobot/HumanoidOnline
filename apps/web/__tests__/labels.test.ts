// UX-01 / P0-B - buyer-facing enum labels: totality, required wording, safe fallback.
import { describe, expect, it } from "vitest";

import {
  ENUM_VALUES,
  enumLabel,
  humanizeToken,
  nameFromSlug,
  statusLabel,
  type EnumKind,
} from "../lib/labels";

// The frozen enum lists from db/schema.sql (docs/03_DATA_DICTIONARY.md).
const SCHEMA: Record<EnumKind, string[]> = {
  commercial_status: [
    "UNKNOWN", "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
  ],
  availability_status: [
    "NOT_AVAILABLE", "WAITLIST", "PREORDER", "LIMITED", "AVAILABLE", "ON_REQUEST", "DISCONTINUED",
  ],
  price_type: ["PUBLIC", "ESTIMATED", "MANUFACTURER_ESTIMATE", "QUOTE_ONLY", "FROM", "RANGE"],
  autonomy: ["TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS", "HIGHLY_AUTONOMOUS"],
  mobility: ["BIPEDAL", "WHEELED", "HYBRID", "QUADRUPED", "STATIONARY", "OTHER"],
  transaction: ["PURCHASE", "RENTAL", "SUBSCRIPTION", "LEASE", "RAAS", "PILOT", "DEVELOPER", "OTHER"],
  source_type: [
    "MANUFACTURER_STORE", "MANUFACTURER_SITE", "PRESS_RELEASE", "NEWS_ARTICLE", "ANALYST_REPORT",
    "FINANCIAL_FILING", "DIRECT_QUOTE", "CONFERENCE", "INTERVIEW", "OTHER",
  ],
  confidence: ["LOW", "MEDIUM", "HIGH", "VERIFIED"],
};

describe("enum labels are total over the schema enums", () => {
  for (const kind of Object.keys(SCHEMA) as EnumKind[]) {
    it(`${kind}: every schema value has a readable label`, () => {
      expect([...ENUM_VALUES[kind]].sort()).toEqual([...SCHEMA[kind]].sort());
      for (const v of SCHEMA[kind]) {
        const label = enumLabel(kind, v);
        expect(label.length).toBeGreaterThan(0);
        expect(label).not.toMatch(/_/);
        expect(label).not.toBe(label.toUpperCase().length > 3 ? label.toUpperCase() : "");
      }
    });
  }
});

describe("required wording", () => {
  it("maps the owner-specified labels", () => {
    expect(enumLabel("commercial_status", "RAAS_DEPLOYMENT")).toBe("Robot-as-a-service");
    expect(enumLabel("commercial_status", "LIMITED_COMMERCIAL")).toBe("Limited commercial availability");
    expect(enumLabel("price_type", "QUOTE_ONLY")).toBe("Price on request");
    expect(enumLabel("availability_status", "ON_REQUEST")).toBe("Availability on request");
    expect(enumLabel("autonomy", "SUPERVISED_AUTONOMY")).toBe("Supervised autonomy");
    expect(enumLabel("source_type", "MANUFACTURER_SITE")).toBe("Manufacturer website");
    expect(enumLabel("source_type", "OTHER")).toBe("Other source");
  });
  it("keeps QUOTE_ONLY distinct from unknown, and an unverified status is not 'not available'", () => {
    expect(enumLabel("price_type", "QUOTE_ONLY")).not.toMatch(/unknown/i);
    expect(statusLabel("UNKNOWN")).not.toMatch(/not available|discontinued/i);
  });
});

describe("safe fallback", () => {
  it("renders an unknown enum as readable prose, never dropped", () => {
    expect(enumLabel("commercial_status", "SOME_NEW_STATE")).toBe("Some new state");
    expect(humanizeToken("A_B_C")).toBe("A b c");
    expect(enumLabel("price_type", "WEIRD")).toBe("Weird");
  });
  it("returns an empty string only for an absent value", () => {
    expect(enumLabel("mobility", null)).toBe("");
    expect(enumLabel("mobility", undefined)).toBe("");
    expect(enumLabel("mobility", "")).toBe("");
  });
});

describe("nameFromSlug", () => {
  it("de-slugs to Title Case", () => {
    expect(nameFromSlug("agibot-a2-ultra")).toBe("Agibot A2 Ultra");
    expect(nameFromSlug("4ne1-mini")).toBe("4NE1 Mini");
  });
});
