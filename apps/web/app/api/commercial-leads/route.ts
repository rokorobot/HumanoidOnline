// Server-side submit proxy for the WS7 commercial-lead form.
//
// The lead form runs in the browser, but the FastAPI base URL (`API_BASE_URL`)
// is a server-only variable and the API sets no CORS — so the browser POSTs here
// (same origin) and this Route Handler forwards to FastAPI on the server. The
// FastAPI response (201/200 {id, lead_status}, or 4xx {detail}) is passed
// straight back through, status and all.
import { NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const upstream = await fetch(`${API_BASE_URL}/api/commercial-leads`, {
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
