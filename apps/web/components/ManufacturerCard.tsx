// ManufacturerCard (§6.12) — whole-card manufacturer link used on both the
// /manufacturers index and the homepage "Who builds them" section. Shows the
// DERIVED portfolio status (not the coarse deployment column). Live data only.
import Link from "next/link";

import { formatRobotCoverage } from "@/lib/format";
import type { ManufacturerListItem } from "@/lib/types";

function Leader({ k, v, unknown }: { k: string; v: string; unknown?: boolean }) {
  return (
    <div className="ho-leader">
      <span>{k}</span>
      <span className="fill" />
      <span style={unknown ? { color: "var(--ho-unknown)" } : undefined}>{v}</span>
    </div>
  );
}

export function ManufacturerCard({ manufacturer: m }: { manufacturer: ManufacturerListItem }) {
  return (
    <Link className="mcard" href={`/manufacturers/${m.slug}`}>
      <h3>{m.name}</h3>
      <div>
        <Leader k="REGION" v={m.country ?? "UNKNOWN"} unknown={!m.country} />
        <Leader
          k="PORTFOLIO"
          v={m.portfolio_status ?? "UNKNOWN"}
          unknown={!m.portfolio_status}
        />
        <Leader
          k="ROBOTS"
          v={formatRobotCoverage(m.tracked_robot_count, m.published_robot_count)}
        />
      </div>
    </Link>
  );
}
