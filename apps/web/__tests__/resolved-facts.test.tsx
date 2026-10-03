import { cleanup, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { ResolvedFactCell } from "../components/ResolvedFactCell";
import { RobotCard } from "../components/RobotCard";
import { buildRobotJsonLd } from "../lib/jsonld";
import { describeResolved, factsByProperty, hasScopedKnowledge } from "../lib/resolved-facts";
import type { ResolvedFact, RobotDetail, RobotListItem } from "../lib/types";

afterEach(cleanup);

const v = (slug: string, name: string, value: boolean | null, tokens: string[] = [],
  source: { key: string; label: string; value: string }[] = []) => ({
  slug, name, value,
  evidence: tokens.map((t) => ({ spec_key: "k", token: t })),
  source_facts: source,
});

// The API's resolution of the 4NE1 Mini (DR-G4 section 5.1), exactly as the endpoint returns it.
const SDK: ResolvedFact = {
  property: "has_sdk", state: "UNIFORM_VARIANTS", value: true, product_value: null,
  product_source: null, registry_version: "0.1.0-g4-initial",
  variants: [v("standard", "Standard", true, ["Python SDK"]),
    v("pro", "Pro", true, ["Python SDK", "C++ SDK"])],
};
const ROS: ResolvedFact = {
  property: "ros_support", state: "UNIFORM_VARIANTS", value: true, product_value: null,
  product_source: null, registry_version: "0.1.0-g4-initial",
  variants: [v("standard", "Standard", true, ["ROS 2 interface"]),
    v("pro", "Pro", true, ["ROS 2 interface"])],
};
const TELE: ResolvedFact = {
  property: "has_teleoperation", state: "PARTIAL_VARIANTS", value: null, product_value: null,
  product_source: null, registry_version: "0.1.0-g4-initial",
  variants: [v("standard", "Standard", null), v("pro", "Pro", true, ["teleoperation"])],
};
const MANIP: ResolvedFact = {
  property: "has_manipulation", state: "PARTIAL_VARIANTS", value: null, product_value: null,
  product_source: null, registry_version: "0.1.0-g4-initial",
  variants: [
    v("standard", "Standard", null, [], [{ key: "dexterous_hand_option", label: "Dexterous hand option", value: "Not included" }]),
    v("pro", "Pro", true, ["12 DoF dexterous hands"]),
  ],
};
const stateOf = (state: ResolvedFact["state"], value: boolean | null = null): ResolvedFact => ({
  property: "has_sdk", state, value, product_value: null, product_source: null,
  registry_version: "0.1.0-g4-initial", variants: [v("a", "A", true), v("b", "B", null)],
});

describe("describeResolved (presentation of an API-resolved fact)", () => {
  it("SDK on every documented configuration", () => {
    const d = describeResolved(SDK);
    expect(d.headline).toBe("Supported on all documented configurations (Standard + Pro)");
    expect(d.lines.map((l) => `${l.scope} — ${l.text}`)).toEqual([
      "Standard — Supported (Python SDK)", "Pro — Supported (Python SDK + C++ SDK)"]);
  });
  it("ROS 2 on every documented configuration", () => {
    expect(describeResolved(ROS).headline).toContain("all documented configurations");
  });
  it("teleoperation: Pro supported, Standard UNKNOWN, never false", () => {
    const d = describeResolved(TELE);
    expect(d.headline).toBe("Known on some configurations; others unknown");
    expect(d.lines.map((l) => `${l.scope} — ${l.text}`)).toEqual([
      "Standard — UNKNOWN", "Pro — Supported (teleoperation)"]);
    expect(d.lines.some((l) => /not supported|false/i.test(l.text))).toBe(false);
  });
  it("manipulation keeps the verbatim detail and is not turned into false", () => {
    const d = describeResolved(MANIP);
    expect(d.lines.map((l) => `${l.scope} — ${l.text}`)).toEqual([
      "Standard — UNKNOWN (Dexterous hand option: Not included)",
      "Pro — Supported (12 DoF dexterous hands)"]);
    expect(d.lines.some((l) => /not supported/i.test(l.text))).toBe(false);
  });
  it("covers every state without collapsing them", () => {
    const heads = (["PRODUCT_VALUE", "UNIFORM_VARIANTS", "VARIES_BY_VARIANT", "PARTIAL_VARIANTS",
      "UNKNOWN", "CONFLICT"] as const).map((s) => describeResolved(stateOf(s, s === "PRODUCT_VALUE" || s === "UNIFORM_VARIANTS" ? true : null)).headline);
    expect(new Set(heads).size).toBe(6);
    expect(describeResolved(stateOf("VARIES_BY_VARIANT")).headline).toBe("Varies by configuration");
    expect(describeResolved(stateOf("CONFLICT")).headline).toMatch(/conflict/i);
  });
  it("knows when a fact carries scoped knowledge the plain column does not show", () => {
    expect(hasScopedKnowledge(SDK)).toBe(true);
    expect(hasScopedKnowledge(TELE)).toBe(true);
    expect(hasScopedKnowledge(stateOf("UNKNOWN"))).toBe(false);
    expect(hasScopedKnowledge(stateOf("PRODUCT_VALUE", true))).toBe(false);
    expect(hasScopedKnowledge(undefined)).toBe(false);
    expect(Object.keys(factsByProperty([SDK, TELE]))).toEqual(["has_sdk", "has_teleoperation"]);
  });
});

describe("ResolvedFactCell", () => {
  it("renders the Mini's scoped knowledge, never a blanket UNKNOWN", () => {
    const { container } = render(<ResolvedFactCell fact={SDK} />);
    const t = container.textContent ?? "";
    expect(t).toContain("Supported on all documented configurations");
    expect(t).toContain("Standard — Supported (Python SDK)");
    expect(t).toContain("Pro — Supported (Python SDK + C++ SDK)");
    expect(t).not.toContain("UNKNOWN");
    expect(container.querySelector("[data-resolved-state]")?.getAttribute("data-resolved-state")).toBe("UNIFORM_VARIANTS");
  });
  it("renders partial teleoperation and manipulation with the detail visible", () => {
    const a = render(<ResolvedFactCell fact={TELE} />).container.textContent ?? "";
    expect(a).toContain("Standard — UNKNOWN");
    expect(a).toContain("Pro — Supported (teleoperation)");
    cleanup();
    const b = render(<ResolvedFactCell fact={MANIP} />).container.textContent ?? "";
    expect(b).toContain("Standard — UNKNOWN (Dexterous hand option: Not included)");
    expect(b).toContain("Pro — Supported (12 DoF dexterous hands)");
  });
});

describe("list card scope note (ANY-VARIANT disclosure)", () => {
  const item: RobotListItem = {
    id: "1", slug: "x", name: "X", manufacturer: { slug: "m", name: "M" },
    commercial_status: "UNKNOWN", available_modes: [], deployment_count: 0,
    updated_at: "2026-10-03T00:00:00Z",
    scope_notes: [{ property: "has_sdk", label: "Available on some configurations", configurations: ["pro"] }],
  };
  it("discloses a match that holds on only some configurations", () => {
    render(<RobotCard robot={item} />);
    expect(screen.getByText("Available on some configurations")).toBeTruthy();
  });
  it("shows nothing for a product-wide match", () => {
    render(<RobotCard robot={{ ...item, scope_notes: [] }} />);
    expect(screen.queryByText("Available on some configurations")).toBeNull();
  });
});

describe("JSON-LD never overstates scoped capabilities", () => {
  beforeAll(() => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://example.test";
  });
  const robot = {
    id: "1", slug: "mini", name: "Mini", manufacturer: { slug: "n", name: "NEURA" },
    commercial_status: "UNKNOWN",
    specs: { has_sdk: null, has_manipulation: null, has_teleoperation: null, ros_support: null,
      height_cm: null, weight_kg: null, payload_kg: null, walk_speed_ms: null,
      runtime_minutes: null, degrees_of_freedom: null, mobility: null, autonomy: null },
    resolved_facts: [SDK, ROS, TELE, MANIP],
    status_history: [], spec_caveats: [], extended_specs: [], capabilities: [], variants: [],
    use_case_fits: [], pricing_offers: [], availability_offers: [], deployments: [], images: [],
  } as unknown as RobotDetail;
  it("asserts no product-wide capability for PARTIAL / VARIES facts", () => {
    const text = JSON.stringify(buildRobotJsonLd(robot));
    expect(text).not.toMatch(/teleoperation|manipulation/i);
    expect(text).not.toMatch(/Python SDK|C\+\+ SDK|ROS 2/);
  });
});

// One semantic resolver, in the API. The web layer must not match registered tokens itself.
describe("no second resolver in the web layer", () => {
  const roots = ["app", "components", "lib"].map((d) => join(__dirname, "..", d));
  const tokens = ["Python SDK", "C++ SDK", "ROS 2 interface", "teleoperation", "12 DoF dexterous hands"];
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(name)) files.push(p);
    }
  };
  roots.forEach(walk);
  it("contains no quoted registry token", () => {
    const offenders: string[] = [];
    for (const f of files) {
      const body = readFileSync(f, "utf8");
      for (const t of tokens) {
        if (new RegExp(`["'\`]${t.replace(/[+.*?^${}()|[\]\\]/g, "\\$&")}["'\`]`).test(body)) offenders.push(`${f}: ${t}`);
      }
    }
    expect(offenders).toEqual([]);
  });
  it("has no variant-reconciliation module left over from the PR #105 client logic", () => {
    expect(files.some((f) => /variant-facts|VariantFactCell/.test(f))).toBe(false);
  });
});
