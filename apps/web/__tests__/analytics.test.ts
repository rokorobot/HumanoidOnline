import { describe, expect, it } from "vitest";

import { analyticsEnabled } from "@/components/Analytics";

describe("Analytics (Clarity + GA4) gating", () => {
  it("loads on the production origin", () => {
    expect(analyticsEnabled("https://humanoidonline.com")).toBe(true);
    expect(analyticsEnabled("https://www.humanoidonline.com")).toBe(true);
  });

  it("stays off on preview, staging and local origins", () => {
    expect(analyticsEnabled("https://deploy-preview-12--humanoidonline.netlify.app")).toBe(false);
    expect(analyticsEnabled("http://localhost:3000")).toBe(false);
  });
});
