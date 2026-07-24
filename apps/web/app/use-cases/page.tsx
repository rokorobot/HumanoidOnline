// Use-cases index — from /api/use-cases.
import Link from "next/link";

import { listUseCases } from "@/lib/api-client";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

export default async function UseCasesPage() {
  const page = await listUseCases({ limit: 100 });
  return (
    <>
      <SystemHeader
        title="USE-CASE INDEX"
        fields={[{ value: page.total, label: "" }, { value: "APPLICATIONS", label: "" }]}
      />
      <div className="wrap">
        <SiteNav active="use-cases" />
        <div className="pagebar">
          <div>
            <SectionIndex>USE CASES — BY APPLICATION</SectionIndex>
            <h1>Use cases</h1>
          </div>
          <span className="meta">{page.total} APPLICATIONS</span>
        </div>

        <div className="apps" style={{ marginBottom: "var(--ho-sp-8)" }}>
          {page.items.map((u, i) => (
            <Link className="app" href={`/use-cases/${u.slug}`} key={u.slug}>
              <SystemLabel>{String(i + 1).padStart(2, "0")}</SystemLabel>
              <span className="name">{u.name}</span>
              <SystemLabel>{u.robot_count} ROBOTS</SystemLabel>
            </Link>
          ))}
        </div>
        {page.items.length === 0 && (
          <p className="empty-state">No use cases on record.</p>
        )}
      </div>
      <SiteFooter />
    </>
  );
}
