// ADR-027 §11 — JSON projection of the Europe Regional Research Resource
// (gate and headers shared with every region: lib/research-json.ts).
import { researchJsonResponse } from "@/lib/research-json";

export const dynamic = "force-dynamic";

export function GET(request: Request): Promise<Response> {
  return researchJsonResponse("europe", request);
}
