import { describe, expect, it } from "vitest";

import { cmToFtIn, displayMetricValue, kgToLb, msToMph, isUnitSystem } from "../lib/units";

describe("unit conversions (presentation only, exact restatement)", () => {
  it("cm → ft/in", () => {
    expect(cmToFtIn(132)).toBe("4 ft 4 in"); // 132 cm ≈ 51.97 in → 52 in = 4 ft 4 in
    expect(cmToFtIn(180)).toBe("5 ft 11 in");
  });
  it("kg → lb", () => {
    expect(kgToLb(35)).toBe("77 lb");
    expect(kgToLb(100)).toBe("220 lb");
  });
  it("m/s → mph", () => {
    expect(msToMph(1.5)).toBe("3.4 mph");
    expect(msToMph(0)).toBe("0 mph");
  });
  it("isUnitSystem guards the toggle param", () => {
    expect(isUnitSystem("imperial")).toBe(true);
    expect(isUnitSystem("metric")).toBe(true);
    expect(isUnitSystem("furlongs")).toBe(false);
    expect(isUnitSystem(undefined)).toBe(false);
  });
});

describe("displayMetricValue — canonical stays visible in imperial", () => {
  it("metric shows canonical with unit; no redundant sub-line", () => {
    expect(displayMetricValue("height_cm", 132, "metric")).toEqual({ primary: "132 cm", canonical: null });
    expect(displayMetricValue("payload_kg", 25, "metric")).toEqual({ primary: "25 kg", canonical: null });
  });
  it("imperial converts but keeps the canonical metric value traceable", () => {
    expect(displayMetricValue("height_cm", 132, "imperial")).toEqual({ primary: "4 ft 4 in", canonical: "132 cm" });
    expect(displayMetricValue("payload_kg", 35, "imperial")).toEqual({ primary: "77 lb", canonical: "35 kg" });
    expect(displayMetricValue("walk_speed_ms", 1.5, "imperial")).toEqual({ primary: "3.4 mph", canonical: "1.5 m/s" });
  });
  it("counts and durations have no imperial form (shown identically, no sub)", () => {
    expect(displayMetricValue("runtime_minutes", 120, "imperial")).toEqual({ primary: "120 min", canonical: null });
    expect(displayMetricValue("degrees_of_freedom", 23, "imperial")).toEqual({ primary: "23", canonical: null });
  });
});
