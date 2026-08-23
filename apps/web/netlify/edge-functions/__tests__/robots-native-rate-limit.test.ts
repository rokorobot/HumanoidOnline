// Emergency Compare Rate Containment v0.3.2 — `/robots` native rate limit.
//
// This is a CONFIG-SHAPE AUDIT, not a functional test of rate limiting.
// `config.rateLimit` is a declarative rule enforced by Netlify's own
// platform infrastructure before this file's function body ever runs for a
// blocked request — there is no application code here to mock or exercise
// locally. Do not read a pass here as proof the limit is enforced in
// production; only a live Netlify deployment can prove that. What this test
// *does* prove: the declared policy matches the documented v0.3.2 policy
// (60 req / 60s / IP) and is bound to exactly `/robots`, not silently to
// some other or broader path — and that this file carries no
// `@netlify/blobs` runtime dependency, the exact thing that made the prior
// custom counter undeployable.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { config, default as handler } from "../robots-native-rate-limit";

describe("robots-native-rate-limit config audit", () => {
  it("is bound to exactly /robots", () => {
    expect(config.path).toBe("/robots");
  });

  it("declares the documented policy: 60 requests / 60 seconds / IP", () => {
    expect(config.rateLimit).toBeDefined();
    expect(config.rateLimit?.windowLimit).toBe(60);
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

  it("carries no @netlify/blobs runtime import (the file's own comments may still name it, explaining why it's gone)", () => {
    const source = readFileSync(
      resolve(process.cwd(), "netlify/edge-functions/robots-native-rate-limit.ts"),
      "utf8",
    );
    expect(source).not.toMatch(/from\s+["']@netlify\/blobs["']|require\(\s*["']@netlify\/blobs["']\s*\)/);
  });
});
