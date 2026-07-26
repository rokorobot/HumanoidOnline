// WS8.6 / R25 — web->API request correlation seam.
//
// So a request can be traced across the Next -> FastAPI boundary, the server-
// side governed reads (lib/api-client) send an `X-Request-ID`. It reuses a
// sanitized inbound id (set by a proxy) or generates one, memoized for the
// render pass via React cache() so every governed call in one request shares it.
//
// This is a correlation seam ONLY — no general Next logging, no PII, no query or
// body content. The header carries an opaque id and nothing else.
import "server-only";

import { cache } from "react";
import { headers } from "next/headers";

export const REQUEST_ID_HEADER = "x-request-id";

const REQUEST_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

// Accept a proxy/client-supplied id only if it is safe; otherwise generate one.
// This mirrors the API's sanitizer so a hostile inbound value is never forwarded.
function sanitize(raw: string | null | undefined): string | null {
  if (!raw || raw.length > 128) return null;
  return REQUEST_ID_RE.test(raw) ? raw : null;
}

export const getRequestId = cache(async (): Promise<string> => {
  try {
    const inbound = (await headers()).get(REQUEST_ID_HEADER);
    return sanitize(inbound) ?? globalThis.crypto.randomUUID();
  } catch {
    // headers() unavailable outside a request scope — generate a standalone id.
    return globalThis.crypto.randomUUID();
  }
});

// The correlation header to attach to an outbound governed API call.
export async function correlationHeader(): Promise<Record<string, string>> {
  return { [REQUEST_ID_HEADER]: await getRequestId() };
}
