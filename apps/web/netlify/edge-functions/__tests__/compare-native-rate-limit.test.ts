// Emergency Compare Rate Containment v0.3 — `/compare` native rate limit.
//
// This is a CONFIG-SHAPE AUDIT, not a functional test of rate limiting.
// `config.rateLimit` is a declarative rule enforced by Netlify's own
// platform infrastructure before this file's function body ever runs for a
// blocked request — there is no application code here to mock or exercise
// locally. Do not read a pass here as proof the limit is enforced in
// production; only a live Netlify deployment can prove that (see the
// residual-risk note in docs/16_EMERGENCY_COMPARE_RATE_CONTAINMENT.md).
// What this test *does* prove: the declared policy matches the documented
// STEP 4 policy (30 req / 60s / IP) and is bound to exactly `/compare`, not
// silently to some other or broader path.
import { describe, expect, it } from "vitest";

import { config, default as handler } from "../compare-native-rate-limit";

describe("compare-native-rate-limit config audit", () => {
  it("is bound to exactly /compare", () => {
    expect(config.path).toBe("/compare");
  });

  it("declares the documented policy: 30 requests / 60 seconds / IP", () => {
    expect(config.rateLimit).toBeDefined();
    expect(config.rateLimit?.windowLimit).toBe(30);
    expect(config.rateLimit?.windowSize).toBe(60);
    expect(config.rateLimit?.aggregateBy).toContain("ip");
  });

  it("does not override the default block action (429), e.g. into a silent rewrite", () => {
    expect(config.rateLimit?.action).toBeUndefined();
  });

  it("the function body is a harmless no-op pass-through for an admitted request", async () => {
    const result = await handler();
    expect(result).toBeUndefined();
  });
});
