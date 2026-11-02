// Use-cases index — from /api/use-cases.
import type { Metadata } from "next";

import { listUseCases } from "@/lib/api-client";
import { JsonLd } from "@/components/JsonLd";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { UseCaseTile } from "@/components/UseCaseTile";
import { buildCollectionJsonLd } from "@/lib/jsonld";
import { absoluteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

// WS8.5 / R22 — specific per-route title (no generic root inheritance).
export function generateMetadata(): Metadata {
  return {
    title: "Use Cases",
    description:
      "Humanoid-robot deployment use cases and the robots suited to each, ranked by fit.",
    alternates: { canonical: absoluteUrl("/use-cases") },
  };
}

export default async function UseCasesPage() {
  const page = await listUseCases({ limit: 100 });
  return (
    <>
      <JsonLd
        data={buildCollectionJsonLd(
          [{ name: "Use Cases", path: "/use-cases" }],
          page.items.map((u) => ({ name: u.name, path: `/use-cases/${u.slug}` })),
        )}
      />
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
    </>
  );
}
