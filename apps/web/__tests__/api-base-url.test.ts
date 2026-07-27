/**
 * WS8.7 / WS8-L5 — the server-side API origin must fail closed in production.
 *
 * Gap found while binding the real production topology: `lib/server.ts` fell
 * through to `http://localhost:8000` whenever `API_BASE_URL` was absent, and a
 * dead WS1 duplicate (`lib/api.ts`, now deleted) carried the same fallback. A
 * production web container with missing configuration would therefore point at
 * localhost silently rather than refusing to serve — exactly what WS8-L5 bans.
 *
 * Proven here:
 * 1. Development/test convenience survives (the fallback is not removed, only
 *    confined to the relaxed environments).
 * 2. Staging/production REQUIRE an explicit, well-formed `API_BASE_URL`.
 * 3. `NEXT_PUBLIC_API_BASE_URL` is NOT an alternate production path — there is
 *    exactly one authoritative server-side knob.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGINAL_ENV = { ...process.env };

function setEnv(env: Record<string, string | undefined>) {
  for (const key of ["APP_ENV", "API_BASE_URL", "NEXT_PUBLIC_API_BASE_URL"]) {
    delete process.env[key];
  }
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
  vi.resetModules();
  vi.restoreAllMocks();
});

async function load() {
  return import("@/lib/server");
}

async function configError() {
  return (await import("@/lib/site")).ConfigurationError;
}

describe("relaxed environments keep the convenience default", () => {
  for (const env of ["development", "test"]) {
    it(`${env}: an absent API_BASE_URL resolves to localhost`, async () => {
      setEnv({ APP_ENV: env });
      const { apiBaseUrl } = await load();
      expect(apiBaseUrl()).toBe("http://localhost:8000");
    });
  }
});

describe("staging/production fail closed (WS8-L5)", () => {
  for (const env of ["staging", "production"]) {
    it(`${env}: an absent API_BASE_URL throws instead of defaulting`, async () => {
      setEnv({ APP_ENV: env });
      const { apiBaseUrl } = await load();
      const ConfigurationError = await configError();
      expect(() => apiBaseUrl()).toThrow(ConfigurationError);
      // The message must name the variable and never present localhost as usable.
      expect(() => apiBaseUrl()).toThrow(/API_BASE_URL is required/);
    });
  }

  it("an UNSET APP_ENV is production, so it also fails closed", async () => {
    setEnv({}); // no APP_ENV at all
    const { apiBaseUrl } = await load();
    const ConfigurationError = await configError();
    expect(() => apiBaseUrl()).toThrow(ConfigurationError);
  });

  it("NEXT_PUBLIC_API_BASE_URL is NOT an alternate production path", async () => {
    setEnv({
      APP_ENV: "production",
      NEXT_PUBLIC_API_BASE_URL: "http://sneaky-alternate:8000",
    });
    const { apiBaseUrl } = await load();
    const ConfigurationError = await configError();
    expect(() => apiBaseUrl()).toThrow(ConfigurationError);
  });

  it("a whitespace-only API_BASE_URL is treated as absent", async () => {
    setEnv({ APP_ENV: "production", API_BASE_URL: "   " });
    const { apiBaseUrl } = await load();
    const ConfigurationError = await configError();
    expect(() => apiBaseUrl()).toThrow(ConfigurationError);
  });
});

describe("an explicit value must be a well-formed absolute origin", () => {
  it("accepts the internal service origin used in production", async () => {
    setEnv({ APP_ENV: "production", API_BASE_URL: "http://api:8000" });
    const { apiBaseUrl } = await load();
    expect(apiBaseUrl()).toBe("http://api:8000");
  });

  it("accepts https and normalises a trailing slash", async () => {
    setEnv({ APP_ENV: "production", API_BASE_URL: "https://api.example.com/" });
    const { apiBaseUrl } = await load();
    expect(apiBaseUrl()).toBe("https://api.example.com");
  });

  it("rejects a malformed value rather than concatenating it into a URL", async () => {
    for (const bad of ["not-a-url", "api:8000", "//api:8000"]) {
      setEnv({ APP_ENV: "production", API_BASE_URL: bad });
      const { apiBaseUrl } = await load();
      const ConfigurationError = await configError();
      expect(() => apiBaseUrl(), bad).toThrow(ConfigurationError);
      vi.resetModules();
    }
  });

  it("rejects a non-http(s) protocol", async () => {
    setEnv({ APP_ENV: "production", API_BASE_URL: "ftp://api.example.com" });
    const { apiBaseUrl } = await load();
    const ConfigurationError = await configError();
    expect(() => apiBaseUrl()).toThrow(ConfigurationError);
  });

  it("rejects a value carrying a path, query or fragment", async () => {
    // Call sites append "/api/..." — a base carrying a path would silently
    // produce "http://api:8000/v1/api/robots".
    for (const bad of [
      "http://api:8000/v1",
      "http://api:8000/?x=1",
      "http://api:8000/#frag",
    ]) {
      setEnv({ APP_ENV: "production", API_BASE_URL: bad });
      const { apiBaseUrl } = await load();
      const ConfigurationError = await configError();
      expect(() => apiBaseUrl(), bad).toThrow(ConfigurationError);
      vi.resetModules();
    }
  });

  it("an unrecognised APP_ENV is loud, not silently strict or relaxed", async () => {
    setEnv({ APP_ENV: "prod", API_BASE_URL: "http://api:8000" });
    const { apiBaseUrl } = await load();
    const ConfigurationError = await configError();
    expect(() => apiBaseUrl()).toThrow(ConfigurationError);
  });
});

describe("no second resolver survives to drift", () => {
  it("the dead duplicate lib/api.ts is gone", () => {
    // It was an unused WS1 helper carrying its own `?? "http://localhost:8000"`.
    // A second resolver is exactly the drift lib/site.ts warns about.
    expect(existsSync(join(process.cwd(), "lib", "api.ts"))).toBe(false);
  });

  it("lib/server.ts confines the localhost default to relaxed environments", () => {
    const source = readFileSync(join(process.cwd(), "lib", "server.ts"), "utf8");
    // The old shape was a bare `?? "http://localhost:8000"` fallback chain.
    expect(source).not.toMatch(/\?\?\s*["']http:\/\/localhost:8000["']/);
    expect(source).toContain("RELAXED_APP_ENVS");
  });
});
