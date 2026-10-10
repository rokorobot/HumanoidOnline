import { formatObservedDate } from "@/lib/format";
import { sourceTypeLabel } from "@/lib/labels";
import type { Evidence } from "@/lib/types";

/**
 * Provenance dates for a compared fact, kept STRICTLY SEPARATE — PUBLISHED,
 * OBSERVED, VERIFIED — never collapsed into one synthetic "freshness" value.
 * observed_at is always present (TIMESTAMPTZ NOT NULL); the other two rows are
 * omitted when genuinely absent. A ® rides along only when verified_at exists.
 */
export function EvidenceDates({ evidence }: { evidence?: Evidence | null }) {
  if (!evidence) {
    return <span className="stamp" style={{ color: "var(--ho-text-faint)" }}>— no evidence on record —</span>;
  }
  const published = formatObservedDate(evidence.published_at);
  const observed = formatObservedDate(evidence.observed_at);
  const verified = formatObservedDate(evidence.verified_at);
  return (
    <div className="src cmp-ev-dates">
      <div>
        SOURCE: <span data-enum={evidence.source_type}>{sourceTypeLabel(evidence.source_type)}</span>
      </div>
      {published && (
        <div>
          <span className="cmp-dlabel">PUBLISHED</span> {published}
        </div>
      )}
      {observed && (
        <div>
          <span className="cmp-dlabel">OBSERVED</span> {observed}
        </div>
      )}
      {verified && (
        <div>
          <span className="cmp-dlabel">VERIFIED</span> {verified} &reg;
        </div>
      )}
      {evidence.source_url && (
        <div>
          <a href={evidence.source_url} target="_blank" rel="noopener noreferrer">
            View source ↗
          </a>
        </div>
      )}
    </div>
  );
}
