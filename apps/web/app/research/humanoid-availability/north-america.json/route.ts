// ADR-027 §11 — JSON projection of the North America Regional Research Resource
// (gate and headers shared with every region: lib/research-json.ts).
import { researchJsonResponse } from "@/lib/research-json";

export const dynamic = "force-dynamic";

export function GET(request: Request): Promise<Response> {
  return researchJsonResponse("north-america", request);
}
