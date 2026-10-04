/**
 * /research/preview — the review access page (GET form, POST token -> signed cookie).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GET, POST } from "../app/research/preview/route";
import {
  PREVIEW_COOKIE,
  issuePreviewSession,
  verifyPreviewSession,
} from "../lib/research-preview";

const ORIGIN = "https://preview.test.invalid";
const URL_ = `${ORIGIN}/research/preview`;
const TOKEN = "review-token-s3cret";
const ENV_KEYS = ["RESEARCH_PREVIEW_TOKEN", "NEXT_PUBLIC_SITE_URL"] as const;
const saved: Record<string, string | undefined> = {};

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
  process.env.RESEARCH_PREVIEW_TOKEN = TOKEN;
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

const post = (fields: Record<string, string>, cookie?: string) =>
  POST(
    new Request(URL_, {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        ...(cookie ? { cookie } : {}),
      },
      body: new URLSearchParams(fields),
    }),
  );

const sessionFromSetCookie = (setCookie: string): string => {
  const m = setCookie.match(new RegExp(`^${PREVIEW_COOKIE}=([^;]*)`));
  return m ? m[1] : "";
};

describe("POST with the correct token", () => {
  it("303-redirects to the Europe page with no query string and no secret in the URL", async () => {
    const res = await post({ token: TOKEN });
    expect(res.status).toBe(303);
    const location = res.headers.get("location")!;
    expect(location).toBe("/research/humanoid-availability/europe");
    expect(location).not.toContain("?");
    expect(location).not.toContain(TOKEN);
  });

  it("sets a signed, HttpOnly, Secure, SameSite=Strict cookie scoped to /research", async () => {
    const res = await post({ token: TOKEN });
    const setCookie = res.headers.get("set-cookie")!;
    for (const attr of ["Path=/research", "HttpOnly", "Secure", "SameSite=Strict", "Max-Age=3600"]) {
      expect(setCookie).toContain(attr);
    }
    const value = sessionFromSetCookie(setCookie);
    expect(verifyPreviewSession(value, TOKEN)).toBe("europe");
  });

  it("never puts the raw token in the cookie, the headers or the body", async () => {
    const res = await post({ token: TOKEN });
    expect(res.headers.get("set-cookie")).not.toContain(TOKEN);
    for (const [, value] of res.headers.entries()) expect(value).not.toContain(TOKEN);
    expect(await res.text()).not.toContain(TOKEN);
  });

  it("is no-store and noindex", async () => {
    const res = await post({ token: TOKEN });
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
  });

  it("omits Secure only for plain-http local development", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "http://localhost:3000";
    const res = await post({ token: TOKEN });
    expect(res.headers.get("set-cookie")).not.toContain("Secure");
    expect(res.headers.get("set-cookie")).toContain("HttpOnly");
  });
});

describe("POST with a wrong or missing token", () => {
  it("grants nothing: 401, no cookie, the form again, and no echo of the attempt", async () => {
    const res = await post({ token: "not-the-token" });
    expect(res.status).toBe(401);
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("location")).toBeNull();
    const html = await res.text();
    expect(html).toContain('type="password"');
    expect(html).not.toContain("not-the-token");
    expect(html).not.toContain(TOKEN);
  });

  it("an empty submission and a near-miss are refused alike", async () => {
    const attempts: Record<string, string>[] = [{ token: "" }, {}, { token: `${TOKEN} ` }, { token: TOKEN.toUpperCase() }];
    for (const fields of attempts) {
      const res = await post(fields);
      expect(res.status).toBe(401);
      expect(res.headers.get("set-cookie")).toBeNull();
    }
  });

  it("with no token configured it refuses everything, identically", async () => {
    delete process.env.RESEARCH_PREVIEW_TOKEN;
    for (const fields of [{ token: TOKEN }, { token: "" }, { token: "anything" }]) {
      const res = await post(fields);
      expect(res.status).toBe(401);
      expect(res.headers.get("set-cookie")).toBeNull();
    }
  });
});

describe("End preview", () => {
  it("clears the cookie with the same scope and redirects to the access page", async () => {
    const res = await post({ action: "end" });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/research/preview");
    const setCookie = res.headers.get("set-cookie")!;
    expect(setCookie.startsWith(`${PREVIEW_COOKIE}=;`)).toBe(true);
    for (const attr of ["Max-Age=0", "Path=/research", "HttpOnly", "SameSite=Strict"]) {
      expect(setCookie).toContain(attr);
    }
  });

  it("needs no token and cannot be used to log in", async () => {
    const res = await post({ action: "end", token: TOKEN });
    expect(res.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(res.headers.get("location")).toBe("/research/preview");
  });
});

describe("GET access page", () => {
  it("is a noindex, no-store password form posting to itself", async () => {
    const res = await GET(new Request(URL_));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
    expect(res.headers.get("content-type")).toContain("text/html");
    const html = await res.text();
    expect(html).toContain('<meta name="robots" content="noindex, nofollow">');
    expect(html).toContain('<form method="post" action="/research/preview">');
    expect(html).toContain('name="token" type="password"');
    expect(html).toContain('autocomplete="off"');
    expect(html).not.toContain("End preview");
  });

  it("never reads or reflects a token from the query string", async () => {
    const res = await GET(new Request(`${URL_}?token=${TOKEN}&preview=${TOKEN}`));
    const html = await res.text();
    expect(html).not.toContain(TOKEN);
    expect(html).toContain('type="password"'); // still just the form: no access granted
  });

  it("shows the active state with End preview only for a valid session", async () => {
    const valid = issuePreviewSession(TOKEN, "europe");
    const active = await (await GET(new Request(URL_, { headers: { cookie: `${PREVIEW_COOKIE}=${valid}` } }))).text();
    expect(active).toContain("End preview");
    expect(active).toContain("/research/humanoid-availability/europe");
    expect(active).not.toContain(TOKEN);
    const forged = await (await GET(new Request(URL_, { headers: { cookie: `${PREVIEW_COOKIE}=v1.a.b` } }))).text();
    expect(forged).not.toContain("End preview");
    const rotated = issuePreviewSession("old-token", "europe");
    const stale = await (await GET(new Request(URL_, { headers: { cookie: `${PREVIEW_COOKIE}=${rotated}` } }))).text();
    expect(stale).not.toContain("End preview");
  });
});
