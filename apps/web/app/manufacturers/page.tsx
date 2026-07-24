// Manufacturers index — from /api/manufacturers.
import Link from "next/link";

import { listManufacturers } from "@/lib/api-client";
import { formatRobotCount } from "@/lib/format";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

export default async function ManufacturersPage() {
  const page = await listManufacturers({ limit: 100 });
  return (
    <>
      <SystemHeader
        title="MANUFACTURER INDEX"
        fields={[{ value: page.total, label: "" }, { value: "MAKERS TRACKED", label: "" }]}
      />
      <div className="wrap">
        <SiteNav active="manufacturers" />
        <div className="pagebar">
          <div>
            <SectionIndex>MANUFACTURERS — WHO BUILDS THEM</SectionIndex>
            <h1>Manufacturers</h1>
          </div>
          <span className="meta">{page.total} TRACKED</span>
        </div>

        <div className="mfr-row" style={{ paddingBottom: "var(--ho-sp-8)" }}>
          {page.items.map((m) => (
            <Link className="mcard" href={`/manufacturers/${m.slug}`} key={m.slug}>
              <h3>{m.name}</h3>
              <div>
                <Leader k="REGION" v={m.country ?? "UNKNOWN"} unknown={!m.country} />
                <Leader
                  k="PORTFOLIO"
                  v={m.portfolio_status ?? "UNKNOWN"}
                  unknown={!m.portfolio_status}
                />
                <Leader k="ROBOTS" v={formatRobotCount(m.robot_count)} />
              </div>
            </Link>
          ))}
        </div>
        {page.items.length === 0 && (
          <p className="empty-state">
            <SystemLabel>No manufacturers on record.</SystemLabel>
          </p>
        )}
      </div>
      <SiteFooter />
    </>
  );
}

function Leader({ k, v, unknown }: { k: string; v: string; unknown?: boolean }) {
  return (
    <div className="ho-leader">
      <span>{k}</span>
      <span className="fill" />
      <span style={unknown ? { color: "var(--ho-unknown)" } : undefined}>{v}</span>
    </div>
  );
}
