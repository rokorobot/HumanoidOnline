/**
 * Signed preview sessions (lib/research-preview.ts): the cookie is an HMAC-signed
 * authorization assertion, never the secret.
 */
import { createHmac } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  PREVIEW_COOKIE,
  PREVIEW_COOKIE_PATH,
  PREVIEW_TTL_SECONDS,
  clearedCookieHeader,
  cookieFromHeader,
  issuePreviewSession,
  previewTokenMatches,
  sessionCookieHeader,
  verifyPreviewSession,
} from "../lib/research-preview";

const TOKEN = "correct horse battery staple";
const NOW = Date.UTC(2026, 9, 4, 12, 0, 0);

const parts = (session: string) => session.split(".");
const decode = (payload: string) => JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
const encode = (obj: unknown) => Buffer.from(JSON.stringify(obj)).toString("base64url");

describe("session issue and verify", () => {
  it("round-trips: a fresh session grants exactly its region", () => {
    const s = issuePreviewSession(TOKEN, "europe", NOW);
    expect(verifyPreviewSession(s, TOKEN, NOW + 1000)).toBe("europe");
  });

  it("the payload is only version, region and expiry, and never contains the secret", () => {
    const s = issuePreviewSession(TOKEN, "europe", NOW);
    expect(s).not.toContain(TOKEN);
    const [version, payload] = parts(s);
    expect(version).toBe("v1");
    expect(decode(payload)).toEqual({ v: 1, r: "europe", exp: Math.floor(NOW / 1000) + PREVIEW_TTL_SECONDS });
    expect(Buffer.from(payload, "base64url").toString()).not.toContain(TOKEN);
    expect(s).toMatch(/^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/); // cookie-safe characters only
  });

  it("expires after the TTL (one hour)", () => {
    const s = issuePreviewSession(TOKEN, "europe", NOW);
    expect(PREVIEW_TTL_SECONDS).toBe(3600);
    expect(verifyPreviewSession(s, TOKEN, NOW + 3599 * 1000)).toBe("europe");
    expect(verifyPreviewSession(s, TOKEN, NOW + 3600 * 1000)).toBeNull();
    expect(verifyPreviewSession(s, TOKEN, NOW + 86_400_000)).toBeNull();
  });

  it("rejects a tampered payload, signature, version or structure", () => {
    const s = issuePreviewSession(TOKEN, "europe", NOW);
    const [v, payload, sig] = parts(s);
    const longer = encode({ v: 1, r: "europe", exp: Math.floor(NOW / 1000) + 3000 });
    const otherRegion = encode({ v: 1, r: "asia", exp: Math.floor(NOW / 1000) + 3000 });
    for (const bad of [
      `${v}.${longer}.${sig}`,
      `${v}.${otherRegion}.${sig}`,
      `${v}.${payload}.${sig.slice(0, -1)}A`,
      `${v}.${payload}.`,
      `v2.${payload}.${sig}`,
      `${v}.${payload}`,
      `${v}.${payload}.${sig}.extra`,
      "",
      "garbage",
    ]) {
      expect(verifyPreviewSession(bad, TOKEN, NOW), bad).toBeNull();
    }
  });

  it("rejects a validly signed payload that is malformed or not one of ours", () => {
    const sign = (payloadObj: unknown) => {
      // The public issuer cannot sign arbitrary payloads, so craft them with the same
      // primitives the module uses (derived key, then HMAC over "v1.<payload>").
      const key = createHmac("sha256", TOKEN).update("humanoidonline:research-preview:session-key:v1").digest();
      const payload = Buffer.from(typeof payloadObj === "string" ? payloadObj : JSON.stringify(payloadObj)).toString("base64url");
      const sig = createHmac("sha256", key).update(`v1.${payload}`).digest("base64url");
      return `v1.${payload}.${sig}`;
    };
    const exp = Math.floor(NOW / 1000) + 600;
    expect(verifyPreviewSession(sign({ v: 1, r: "europe", exp }), TOKEN, NOW)).toBe("europe"); // control
    expect(verifyPreviewSession(sign({ v: 2, r: "europe", exp }), TOKEN, NOW)).toBeNull();
    expect(verifyPreviewSession(sign({ v: 1, exp }), TOKEN, NOW)).toBeNull();
    expect(verifyPreviewSession(sign({ v: 1, r: "europe" }), TOKEN, NOW)).toBeNull();
    expect(verifyPreviewSession(sign({ v: 1, r: "europe", exp: "soon" }), TOKEN, NOW)).toBeNull();
    expect(verifyPreviewSession(sign({ v: 1, r: "europe", exp: exp + 86_400 }), TOKEN, NOW)).toBeNull(); // far-future
    expect(verifyPreviewSession(sign("not json"), TOKEN, NOW)).toBeNull();
  });

  it("rotating the token invalidates every session issued under the old one", () => {
    const s = issuePreviewSession(TOKEN, "europe", NOW);
    expect(verifyPreviewSession(s, TOKEN, NOW)).toBe("europe");
    expect(verifyPreviewSession(s, `${TOKEN}-rotated`, NOW)).toBeNull();
    expect(verifyPreviewSession(s, "", NOW)).toBeNull();
    expect(verifyPreviewSession(s, undefined, NOW)).toBeNull();
  });

  it("never throws on hostile input", () => {
    for (const hostile of [null, undefined, "\u0000", "a.b.c", ".".repeat(50), "v1..", "%%%", "x".repeat(10_000)]) {
      expect(() => verifyPreviewSession(hostile as string, TOKEN, NOW)).not.toThrow();
      expect(verifyPreviewSession(hostile as string, TOKEN, NOW)).toBeNull();
    }
  });
});

describe("token check", () => {
  it("accepts only the exact token, and nothing when none is configured", () => {
    expect(previewTokenMatches(TOKEN, TOKEN)).toBe(true);
    expect(previewTokenMatches(`${TOKEN} `, TOKEN)).toBe(false);
    expect(previewTokenMatches(TOKEN.slice(0, -1), TOKEN)).toBe(false);
    expect(previewTokenMatches("", TOKEN)).toBe(false);
    expect(previewTokenMatches(TOKEN, undefined)).toBe(false);
    expect(previewTokenMatches(TOKEN, "")).toBe(false);
    expect(previewTokenMatches("", "")).toBe(false);
  });
});

describe("cookie attributes", () => {
  it("is HttpOnly, SameSite=Strict, scoped to /research, one-hour, and Secure when asked", () => {
    const header = sessionCookieHeader("v1.x.y", true);
    expect(header.startsWith(`${PREVIEW_COOKIE}=v1.x.y; `)).toBe(true);
    for (const attr of [`Path=${PREVIEW_COOKIE_PATH}`, "HttpOnly", "Secure", "SameSite=Strict", "Max-Age=3600"]) {
      expect(header).toContain(attr);
    }
    expect(PREVIEW_COOKIE_PATH).toBe("/research");
    expect(sessionCookieHeader("v1.x.y", false)).not.toContain("Secure");
  });

  it("is cleared with the same scope and Max-Age=0", () => {
    const header = clearedCookieHeader(true);
    expect(header.startsWith(`${PREVIEW_COOKIE}=; `)).toBe(true);
    for (const attr of [`Path=${PREVIEW_COOKIE_PATH}`, "HttpOnly", "Secure", "SameSite=Strict", "Max-Age=0"]) {
      expect(header).toContain(attr);
    }
  });

  it("reads one cookie out of a Cookie header", () => {
    expect(cookieFromHeader(`a=1; ${PREVIEW_COOKIE}=v1.x.y; b=2`, PREVIEW_COOKIE)).toBe("v1.x.y");
    expect(cookieFromHeader("a=1", PREVIEW_COOKIE)).toBeUndefined();
    expect(cookieFromHeader(null, PREVIEW_COOKIE)).toBeUndefined();
    expect(cookieFromHeader(`x${PREVIEW_COOKIE}=nope`, PREVIEW_COOKIE)).toBeUndefined();
  });
});
