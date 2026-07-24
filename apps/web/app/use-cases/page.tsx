// Use-cases index — from /api/use-cases.
import { listUseCases } from "@/lib/api-client";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { UseCaseTile } from "@/components/UseCaseTile";

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
            <UseCaseTile key={u.slug} useCase={u} index={i + 1} />
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
