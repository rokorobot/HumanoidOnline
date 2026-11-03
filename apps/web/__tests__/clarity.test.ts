import { describe, expect, it } from "vitest";

import { clarityEnabled } from "@/components/ClarityScript";

describe("Microsoft Clarity gating", () => {
  it("loads on the production origin", () => {
    expect(clarityEnabled("https://humanoidonline.com")).toBe(true);
    expect(clarityEnabled("https://www.humanoidonline.com")).toBe(true);
  });

  it("stays off on preview, staging and local origins", () => {
    expect(clarityEnabled("https://deploy-preview-12--humanoidonline.netlify.app")).toBe(false);
    expect(clarityEnabled("http://localhost:3000")).toBe(false);
  });
});
