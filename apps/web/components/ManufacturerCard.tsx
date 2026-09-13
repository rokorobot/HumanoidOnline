// ManufacturerCard (§6.12) — whole-card manufacturer link used on both the
// /manufacturers index and the homepage "Who builds them" section. Shows the
// DERIVED status of PUBLISHED catalogue models (not the company's humanoid
// deployment column) and the tracked/published model counts. Live data only.
import Link from "next/link";

import { formatPublishedModelStatus, formatRobotCoverage } from "@/lib/format";
import type { ManufacturerListItem } from "@/lib/types";

function Leader({
  k,
  v,
  unknown,
  title,
}: {
  k: string;
  v: string;
  unknown?: boolean;
  title?: string;
}) {
  return (
    <div className="ho-leader" title={title}>
      <span>{k}</span>
      <span className="fill" />
      <span style={unknown ? { color: "var(--ho-unknown)" } : undefined}>{v}</span>
    </div>
  );
}

export function ManufacturerCard({ manufacturer: m }: { manufacturer: ManufacturerListItem }) {
  const modelStatus = formatPublishedModelStatus(m.portfolio_status, m.published_robot_count);
  return (
    <Link className="mcard" href={`/manufacturers/${m.slug}`}>
      <h3>{m.name}</h3>
      <div>
        <Leader k="HQ" v={m.country ?? "UNKNOWN"} unknown={!m.country} />
        <Leader
          k="PUBLISHED MODEL STATUS"
          v={modelStatus.label}
          unknown={modelStatus.unknown}
          title="Derived from published catalogue records only"
        />
        <Leader
          k="CATALOGUE MODELS"
          v={formatRobotCoverage(m.tracked_robot_count, m.published_robot_count)}
        />
      </div>
    </Link>
  );
}
