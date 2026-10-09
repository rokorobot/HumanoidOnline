// EvidenceStamp (§6.7) — DIMENSION 3: provenance for a commercial fact.
// "No commercial fact without evidence." Renders source_type (buyer-facing label,
// raw enum in data-enum) + dates
// (observed/published/verified) + a source link affordance. A ® rides along
// only when verified_at is present.
import { formatDate } from "@/lib/format";
import { sourceTypeLabel } from "@/lib/labels";
import type { Evidence } from "@/lib/types";

export function EvidenceStamp({ evidence }: { evidence?: Evidence | null }) {
  if (!evidence) {
    return <span className="stamp" style={{ color: "var(--ho-text-faint)" }}>— no evidence on record —</span>;
  }
  const verified = formatDate(evidence.verified_at);
  const published = formatDate(evidence.published_at);
  return (
    <div className="src">
      SOURCE: <span data-enum={evidence.source_type}>{sourceTypeLabel(evidence.source_type)}</span>
      <br />
      {published && <>PUBLISHED {published} </>}
      {verified && (
        <>
          {published ? "· " : ""}VERIFIED {verified} &reg;
        </>
      )}
      {!published && !verified && <>Unverified claim</>}
      {evidence.source_url && (
        <>
          <br />
          <a
            href={evidence.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            View source ↗
          </a>
        </>
      )}
    </div>
  );
}
