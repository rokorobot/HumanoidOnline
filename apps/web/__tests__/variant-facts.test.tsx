import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InterfaceFactsValue, VariantFactValue } from "../components/VariantFactCell";
import type { ExtendedSpec, Variant } from "../lib/types";
import { interfaceFacts, variantFact } from "../lib/variant-facts";

afterEach(cleanup);

const variants = [
  { slug: "pro", name: "Pro", is_developer: false },
  { slug: "standard", name: "Standard", is_developer: false },
] as Variant[];
const SRC = {
  source_label: "NEURA Robotics",
  source_url: "https://neura-robotics.com/product/4ne1-mini-reservation",
  observed_at: "2026-10-02",
  source_kind: "MANUFACTURER",
};
const spec = (variant: string, category: string, value: string): ExtendedSpec => ({
  key: `${category}-${value}`,
  label: "x",
  value,
  category,
  variant_slug: variant,
  variant: variant === "pro" ? "Pro" : "Standard",
  ...SRC,
});
const MINI: ExtendedSpec[] = [
  spec("pro", "MANIPULATION", "12 DoF dexterous hands"),
  spec("standard", "MANIPULATION", "Not included"),
  spec("pro", "SOFTWARE", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync"),
  spec("standard", "SOFTWARE", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync"),
  spec("pro", "SOFTWARE", "C++ SDK, digital twin access, teleoperation, ready for Neura Gym training"),
];

describe("variantFact", () => {
  it("returns null (-> UNKNOWN) with no variant evidence", () => {
    expect(variantFact("has_sdk", [], variants)).toBeNull();
    expect(variantFact("has_sdk", [spec("pro", "MANIPULATION", "x")], variants)).toBeNull();
  });
  it("identical evidence in every configuration is uniform", () => {
    const f = variantFact("ros_support", MINI, variants)!;
    expect(f.kind).toBe("uniform");
    expect(f.value).toBe("ROS 2 interface");
  });
  it("different values vary by configuration, verbatim wording", () => {
    const f = variantFact("has_manipulation", MINI, variants)!;
    expect(f.kind).toBe("varies");
    expect(f.rows).toEqual([
      { variant: "Standard", value: "Not included" },
      { variant: "Pro", value: "12 DoF dexterous hands" },
    ]);
  });
  it("partial evidence keeps UNKNOWN only for the unresolved configuration", () => {
    const f = variantFact("has_teleoperation", MINI, variants)!;
    expect(f.kind).toBe("partial");
    expect(f.rows).toEqual([
      { variant: "Standard", value: null },
      { variant: "Pro", value: "Listed by manufacturer" },
    ]);
  });
  it("SDK differs per configuration", () => {
    const f = variantFact("has_sdk", MINI, variants)!;
    expect(f.rows).toEqual([
      { variant: "Standard", value: "Python SDK" },
      { variant: "Pro", value: "Python SDK + C++ SDK" },
    ]);
  });
  it("hand configuration is surfaced without inventing a numeric hand_dof", () => {
    const f = variantFact("hand_dof", MINI, variants)!;
    expect(f.rows.map((r) => r.value)).toEqual(["Not included", "12 DoF dexterous hands"]);
    expect(f.value).toBeUndefined();
  });
  it("carries the accepted source", () => {
    expect(variantFact("has_sdk", MINI, variants)!.source).toEqual({
      label: "NEURA Robotics",
      url: SRC.source_url,
      observed_at: "2026-10-02",
    });
  });
  it("does not mutate its inputs", () => {
    const copy = JSON.stringify(MINI);
    variantFact("has_sdk", MINI, variants);
    interfaceFacts(MINI, variants);
    expect(JSON.stringify(MINI)).toBe(copy);
  });
});

describe("interfaceFacts", () => {
  it("shows common interfaces once and Pro extras separately", () => {
    const f = interfaceFacts(MINI, variants)!;
    expect(f.common).toEqual(["Wi-Fi 6", "Ethernet", "NEURA Sync"]);
    expect(f.extras).toEqual([
      { variant: "Pro", items: ["digital twin access", "ready for Neura Gym training"] },
    ]);
  });
});

describe("rendering", () => {
  it("renders Varies by configuration with both values and the source", () => {
    render(<VariantFactValue fact={variantFact("has_manipulation", MINI, variants)!} />);
    const t = document.body.textContent!;
    expect(t).toContain("Varies by configuration");
    expect(t).toContain("Standard — Not included");
    expect(t).toContain("Pro — 12 DoF dexterous hands");
    expect(t).toContain("NEURA Robotics");
  });
  it("renders partial teleoperation: Pro listed, Standard UNKNOWN", () => {
    render(<VariantFactValue fact={variantFact("has_teleoperation", MINI, variants)!} />);
    const t = document.body.textContent!;
    expect(t).toContain("Pro — Listed by manufacturer");
    expect(t).toMatch(/Standard — .*UNKNOWN/);
  });
  it("renders interfaces", () => {
    render(<InterfaceFactsValue facts={interfaceFacts(MINI, variants)!} />);
    expect(document.body.textContent).toContain("Pro — digital twin access, ready for Neura Gym training");
  });
});
