// ADR-027 — the review access page for unpublished Research Resources.
//
//   GET  /research/preview  the access form (or "preview active" with End preview)
//   POST /research/preview  token -> signed HttpOnly session cookie, 303 to the page
//   POST /research/preview  action=end -> clears the cookie
//
// The token is only ever submitted in a POST body and compared timing-safely
// against RESEARCH_PREVIEW_TOKEN. The cookie is an HMAC-signed assertion, never the
// secret (lib/research-preview.ts). Every response is noindex and no-store.
import { researchPath } from "@/lib/research";
import {
  PREVIEW_COOKIE,
  PREVIEW_ACCESS_PATH,
  PREVIEW_TTL_SECONDS,
  clearedCookieHeader,
  cookieFromHeader,
  issuePreviewSession,
  previewTokenMatches,
  sessionCookieHeader,
  verifyPreviewSession,
} from "@/lib/research-preview";
import { siteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

const REGION = "europe";
const NO_INDEX_NO_STORE = {
  "cache-control": "no-store",
  "x-robots-tag": "noindex, nofollow",
} as const;

// Secure everywhere except plain-http local development.
function secureCookies(): boolean {
  return !/^http:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(siteUrl());
}

function html(body: string, status = 200): Response {
  const doc = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Research preview access</title>
<style>
body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;line-height:1.5}
input,button{font:inherit;padding:.5rem .75rem}
input{width:100%;box-sizing:border-box;margin:.25rem 0 1rem}
.err{color:#8a1c00}
</style>
</head>
<body>
${body}
</body>
</html>`;
  return new Response(doc, {
    status,
    headers: { ...NO_INDEX_NO_STORE, "content-type": "text/html; charset=utf-8" },
  });
}

const loginForm = (error?: string) => `<h1>Research preview</h1>
<p>Enter the review token to open the unpublished Research Resource. The session lasts one hour.</p>
${error ? `<p class="err" role="alert">${error}</p>` : ""}
<form method="post" action="${PREVIEW_ACCESS_PATH}">
<label for="token">Review token</label>
<input id="token" name="token" type="password" autocomplete="off" required>
<button type="submit">Open preview</button>
</form>`;

const activePage = `<h1>Research preview</h1>
<p>A preview session is active for ${PREVIEW_TTL_SECONDS / 60} minutes at most.</p>
<p><a href="${researchPath(REGION)}">Open the Europe resource</a></p>
<form method="post" action="${PREVIEW_ACCESS_PATH}">
<input type="hidden" name="action" value="end">
<button type="submit">End preview</button>
</form>`;

export async function GET(request: Request): Promise<Response> {
  const token = process.env.RESEARCH_PREVIEW_TOKEN?.trim();
  const cookie = cookieFromHeader(request.headers.get("cookie"), PREVIEW_COOKIE);
  const active = verifyPreviewSession(cookie, token) === REGION;
  return html(active ? activePage : loginForm());
}

export async function POST(request: Request): Promise<Response> {
  const form = await request.formData();
  const secure = secureCookies();

  if (form.get("action") === "end") {
    return new Response(null, {
      status: 303,
      headers: {
        ...NO_INDEX_NO_STORE,
        location: PREVIEW_ACCESS_PATH,
        "set-cookie": clearedCookieHeader(secure),
      },
    });
  }

  const token = process.env.RESEARCH_PREVIEW_TOKEN?.trim();
  const submitted = String(form.get("token") ?? "");
  // One generic answer whether the token is wrong or none is configured, and no
  // cookie either way.
  if (!previewTokenMatches(submitted, token)) {
    return html(loginForm("That token was not accepted."), 401);
  }
  return new Response(null, {
    status: 303,
    headers: {
      ...NO_INDEX_NO_STORE,
      // No query string, no secret: the session rides in the cookie.
      location: researchPath(REGION),
      "set-cookie": sessionCookieHeader(issuePreviewSession(token as string, REGION), secure),
    },
  });
}
