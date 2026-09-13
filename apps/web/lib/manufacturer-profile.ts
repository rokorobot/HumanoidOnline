// Manufacturer detail compatibility.
//
// The detail page must render the PREVIOUS API's response as safely as the
// current one. Netlify (web) and Vercel (API) deploy independently, so the new
// page can go live while the old API is still serving — and that API returns
// none of the profile fields added with migration 0013. Reading `.length` on an
// absent list is exactly what turned the page into an HTTP 500.
//
// Absent fields become explicit "not provided" states, never invented values:
//   - a missing list is `null` (the API did not provide it); an empty list `[]`
//     means the API provided it and nothing is recorded;
//   - a missing count is `null`, except the published count, which is DERIVED
//     from the published `robots` list both API versions return;
//   - listing status stays exactly what the API sent (`null` when absent).
import type { ManufacturerDetail, ManufacturerSource } from "@/lib/types";

export interface ManufacturerProfileView {
  headquartersCity: string | null;
  incorporation: string | null;
  operatingLocations: string[] | null;
  targetMarkets: string[] | null;
  deploymentNote: string | null;
  isPublicCompany: boolean | null;
  parentCompany: string | null;
  parentListing: string | null;
  parentRelationship: string | null;
  publishedModelCount: number;
  trackedModelCount: number | null;
  sources: ManufacturerSource[] | null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function stringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  return value.filter((item): item is string => typeof item === "string");
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function manufacturerProfileView(m: ManufacturerDetail): ManufacturerProfileView {
  const robots = Array.isArray(m.robots) ? m.robots : [];
  return {
    headquartersCity: text(m.headquarters_city),
    incorporation: text(m.incorporation),
    operatingLocations: stringList(m.operating_locations),
    targetMarkets: stringList(m.target_markets),
    deploymentNote: text(m.deployment_note),
    isPublicCompany: typeof m.is_public_company === "boolean" ? m.is_public_company : null,
    parentCompany: text(m.parent_company),
    parentListing: text(m.parent_listing),
    parentRelationship: text(m.parent_relationship),
    publishedModelCount: count(m.published_robot_count) ?? robots.length,
    trackedModelCount: count(m.tracked_robot_count),
    sources: Array.isArray(m.sources)
      ? m.sources.map((s) => ({
          ...s,
          claim_fields: Array.isArray(s.claim_fields) ? s.claim_fields : [],
        }))
      : null,
  };
}
