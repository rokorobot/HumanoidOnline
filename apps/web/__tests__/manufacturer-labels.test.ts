import { describe, expect, it } from "vitest";

import {
  boolLabel,
  deploymentMeaning,
  formatPublishedModelStatus,
  regionLabel,
} from "../lib/format";

describe("formatPublishedModelStatus — scoped to published catalogue models", () => {
  it("no published models is its own explicit state, not an unknown maturity", () => {
    expect(formatPublishedModelStatus(null, 0)).toEqual({
      label: "NONE PUBLISHED",
      unknown: true,
    });
    // Even a stray status cannot speak for zero published models.
    expect(formatPublishedModelStatus("COMMERCIAL", 0).label).toBe("NONE PUBLISHED");
  });

  it("every published model discontinued says so about the models, not the maker", () => {
    expect(formatPublishedModelStatus("DISCONTINUED", 1)).toEqual({
      label: "ALL DISCONTINUED",
      unknown: false,
    });
  });

  it("published models with unverified maturity stay UNKNOWN", () => {
    expect(formatPublishedModelStatus("UNKNOWN", 2)).toEqual({ label: "UNKNOWN", unknown: true });
    expect(formatPublishedModelStatus(null, 2)).toEqual({ label: "UNKNOWN", unknown: true });
  });

  it("an active status passes through verbatim", () => {
    expect(formatPublishedModelStatus("PILOT", 3)).toEqual({ label: "PILOT", unknown: false });
  });
});

describe("public-company status is three-state", () => {
  it("null renders UNKNOWN, never NO", () => {
    expect(boolLabel(null)).toEqual({ label: "UNKNOWN", unknown: true });
    expect(boolLabel(undefined).label).toBe("UNKNOWN");
    expect(boolLabel(false)).toEqual({ label: "NO", unknown: false });
    expect(boolLabel(true)).toEqual({ label: "YES", unknown: false });
  });
});

describe("deploymentMeaning — pilot and commercial stay distinct", () => {
  it("names what each status asserts", () => {
    expect(deploymentMeaning("PILOT")).toBe("Customer pilots or trials");
    expect(deploymentMeaning("COMMERCIAL")).toBe("Commercially available");
    expect(deploymentMeaning("RAAS_DEPLOYMENT")).toBe("Deployed commercially as a service");
    expect(deploymentMeaning("PILOT")).not.toBe(deploymentMeaning("COMMERCIAL"));
  });
  it("asserts nothing for unknown or missing status", () => {
    expect(deploymentMeaning(null)).toBeNull();
    expect(deploymentMeaning("UNKNOWN")).toBeNull();
  });
});

describe("headquarters region labels cover the catalogue's codes", () => {
  it("names Hong Kong, Spain and Poland", () => {
    expect(regionLabel("HK")).toBe("HONG KONG / HK");
    expect(regionLabel("ES")).toBe("SPAIN / ES");
    expect(regionLabel("PL")).toBe("POLAND / PL");
  });
});
