// Server-side submit proxy for the buyer-intent wizard.
//
// The wizard runs in the browser, but the FastAPI base URL (`API_BASE_URL`) is a
// server-only variable and the API sets no CORS — so the browser POSTs here
// (same origin) and this Route Handler forwards to FastAPI on the server. The
// FastAPI response (201 {id} or 422 {detail}) is passed straight back through.
import { NextResponse } from "next/server";

import { apiBaseUrl } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const upstream = await fetch(`${apiBaseUrl()}/api/buyer-requirements`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
