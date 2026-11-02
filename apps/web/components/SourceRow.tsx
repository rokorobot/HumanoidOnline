// One evidence source row. Shared by /manufacturers/[slug] (company sources) and
// /use-cases/[slug] (DR-C2), so both pages render provenance identically.
import { confidenceLabel, sourceTypeLabel } from "@/lib/labels";
import { formatDate } from "@/lib/format";
import type { ManufacturerSource } from "@/lib/types";

// Human labels for the fields an evidence source can support: manufacturer profile
// fields and use-case text fields.
export const FIELD_LABELS: Record<string, string> = {
  legal_name: "legal entity",
  country_region_code: "headquarters country",
  headquarters_city: "headquarters city",
  incorporation: "incorporation",
  operating_locations: "other locations",
  founded_year: "founded",
  website_url: "website",
  description: "description",
  target_markets: "target markets",
  commercial_model: "business model",
  deployment_status: "humanoid deployment",
  deployment_note: "deployment basis",
  is_public_company: "public company",
  ticker: "listing",
  parent_company: "parent",
  parent_listing: "parent listing",
  parent_relationship: "ownership",
  // Use-case text (DR-C2).
  typical_requirements: "typical requirements",
  key_limitations: "key limitations",
  typical_tasks: "typical tasks",
};

export function SourceRow({ source: s }: { source: ManufacturerSource }) {
  const published = formatDate(s.published_at);
  const observed = formatDate(s.observed_at);
  const verified = formatDate(s.verified_at);
  const supports = s.claim_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ");
  return (
    <div className="evrow">
      <div className="subj">
        {s.source_url ? (
          <a href={s.source_url} target="_blank" rel="noopener noreferrer">
            {s.source_title ?? s.source_url} ↗
          </a>
        ) : (
          (s.source_title ?? "Untitled source")
        )}
        <br />
        <span className="stamp">{supports ? `Supports: ${supports}` : "No field claim recorded"}</span>
      </div>
      <div className="src">
        SOURCE: <span data-enum={s.source_type}>{sourceTypeLabel(s.source_type)}</span>
        <br />
        {published && <>PUBLISHED {published} · </>}
        {observed && <>OBSERVED {observed}</>}
        <br />
        {verified ? (
          <>VERIFIED {verified} &reg;</>
        ) : s.retrieval === "AGENT_ASSISTED_RESEARCH" ? (
          <>Agent-assisted research · not human-verified</>
        ) : (
          <>Unverified claim</>
        )}
      </div>
      <div className="conf-cell stamp" data-enum={s.confidence}>
        {confidenceLabel(s.confidence)}
      </div>
    </div>
  );
}
