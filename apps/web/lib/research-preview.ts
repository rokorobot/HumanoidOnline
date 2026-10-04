// ADR-027 — signed, short-lived review sessions for unpublished Research Resources.
//
// A reviewer submits RESEARCH_PREVIEW_TOKEN once (POST, never in a URL). On success
// the server issues a cookie that is an HMAC-signed AUTHORIZATION ASSERTION, not the
// secret: {version, region, expiry} signed with a key derived from the token. The
// raw token never appears in a URL, in markup, in browser JavaScript or in the
// cookie; the server alone attaches it to the API call (X-Research-Preview).
//
// Rotating RESEARCH_PREVIEW_TOKEN changes the derived key, so every existing
// session stops verifying at once. This module is pure apart from the clock
// argument, which tests inject.
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const PREVIEW_COOKIE = "research_preview";
/** The cookie is only ever sent to /research/* (never to the rest of the site). */
export const PREVIEW_COOKIE_PATH = "/research";
export const PREVIEW_TTL_SECONDS = 3600;
export const PREVIEW_ACCESS_PATH = "/research/preview";

const VERSION = "v1";
// Keeps the signing key distinct from the raw token and from any other HMAC use.
const KEY_CONTEXT = "humanoidonline:research-preview:session-key:v1";

const b64url = (buf: Buffer | string): string => Buffer.from(buf).toString("base64url");

function sessionKey(token: string): Buffer {
  return createHmac("sha256", token).update(KEY_CONTEXT).digest();
}

function sign(token: string, signedPart: string): string {
  return b64url(createHmac("sha256", sessionKey(token)).update(signedPart).digest());
}

function equal(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

/** Constant-time check of a submitted token. Hashing first hides length differences. */
export function previewTokenMatches(submitted: string, token: string | undefined): boolean {
  if (!token || !submitted) return false;
  const a = createHash("sha256").update(submitted).digest();
  const b = createHash("sha256").update(token).digest();
  return timingSafeEqual(a, b);
}

/** `v1.<payload>.<signature>`; the payload carries only version, region, expiry. */
export function issuePreviewSession(
  token: string,
  region: string,
  nowMs: number = Date.now(),
  ttlSeconds: number = PREVIEW_TTL_SECONDS,
): string {
  const payload = b64url(
    JSON.stringify({ v: 1, r: region, exp: Math.floor(nowMs / 1000) + ttlSeconds }),
  );
  const signedPart = `${VERSION}.${payload}`;
  return `${signedPart}.${sign(token, signedPart)}`;
}

/** The region a valid, unexpired session grants, or null. Never throws. */
export function verifyPreviewSession(
  value: string | null | undefined,
  token: string | undefined,
  nowMs: number = Date.now(),
): string | null {
  if (!value || !token) return null;
  const parts = value.split(".");
  if (parts.length !== 3 || parts[0] !== VERSION) return null;
  const [version, payload, signature] = parts;
  if (!equal(signature, sign(token, `${version}.${payload}`))) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      v?: unknown;
      r?: unknown;
      exp?: unknown;
    };
    if (data.v !== 1 || typeof data.r !== "string" || typeof data.exp !== "number") return null;
    const nowSeconds = nowMs / 1000;
    if (data.exp <= nowSeconds) return null; // expired
    if (data.exp > nowSeconds + PREVIEW_TTL_SECONDS + 60) return null; // not one of ours
    return data.r;
  } catch {
    return null;
  }
}

/** Value of one cookie from a raw Cookie header. */
export function cookieFromHeader(header: string | null | undefined, name: string): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i > -1 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return undefined;
}

function cookieAttributes(secure: boolean, maxAge: number): string {
  return [
    `Path=${PREVIEW_COOKIE_PATH}`,
    "HttpOnly",
    ...(secure ? ["Secure"] : []),
    "SameSite=Strict",
    `Max-Age=${maxAge}`,
  ].join("; ");
}

export function sessionCookieHeader(value: string, secure: boolean): string {
  return `${PREVIEW_COOKIE}=${value}; ${cookieAttributes(secure, PREVIEW_TTL_SECONDS)}`;
}

export function clearedCookieHeader(secure: boolean): string {
  return `${PREVIEW_COOKIE}=; ${cookieAttributes(secure, 0)}`;
}
