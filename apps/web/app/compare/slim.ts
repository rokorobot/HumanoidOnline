import type { CompareResponse, ResolvedFact } from "@/lib/types";

// G4: send the client only what it renders. The view shows a scoped state (uniform / varies /
// partial / conflict) from `rows[].resolved`; a product value or a truly unknown property renders
// from `values` exactly as before, so those entries (and the per-robot `resolved_facts` copy) are
// not delivered. Pure selection by the API-provided state; nothing is resolved here.
export function slimForClient(data: CompareResponse): CompareResponse {
  const scoped = (f: ResolvedFact) => f.state !== "PRODUCT_VALUE" && f.state !== "UNKNOWN";
  return {
    robots: data.robots.map((r) => ({ ...r, resolved_facts: undefined })),
    rows: data.rows.map((row) => ({
      ...row,
      resolved: row.resolved
        ? Object.fromEntries(Object.entries(row.resolved).filter(([, f]) => scoped(f)))
        : row.resolved,
    })),
  };
}
