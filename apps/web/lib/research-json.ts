// ADR-027 §11 — JSON projection of a Regional Research Resource, shared by every
// region. Same gate as the HTML page (closed -> 404; preview only with a valid
// signed session cookie, never a URL token), and the same read-model projection,
// so HTML, JSON and JSON-LD cannot drift.
import { type ResearchRegion, loadResearch } from "./research";
import { PREVIEW_COOKIE, cookieFromHeader } from "./research-preview";

export async function researchJsonResponse(
  region: ResearchRegion,
  request: Request,
): Promise<Response> {
  const session = cookieFromHeader(request.headers.get("cookie"), PREVIEW_COOKIE);
  const { access, data } = await loadResearch(region, session);
  if (!data || access.mode === "closed") {
    return new Response("Not found", { status: 404 });
  }
  const headers: Record<string, string> =
    access.mode === "published"
      ? { "Cache-Control": "public, max-age=300" }
      : { "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" };
  return Response.json(data, { headers });
}
