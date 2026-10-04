// ADR-027 §11 — JSON projection of the Europe Regional Research Resource.
// Same gate as the HTML page (closed -> 404; preview via `?preview=<token>`),
// and the same read-model projection, so HTML, JSON and JSON-LD cannot drift.
import { fetchResearchProjection, resolveResearchAccess } from "@/lib/research";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const preview = new URL(request.url).searchParams.get("preview");
  const access = resolveResearchAccess("europe", preview);
  const data = await fetchResearchProjection("europe", access);
  if (!data || access.mode === "closed") {
    return new Response("Not found", { status: 404 });
  }
  const headers: Record<string, string> =
    access.mode === "published"
      ? { "Cache-Control": "public, max-age=300" }
      : { "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" };
  return Response.json(data, { headers });
}
