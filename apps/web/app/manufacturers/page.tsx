// Manufacturers index — from /api/manufacturers.
import type { Metadata } from "next";

import { listManufacturers } from "@/lib/api-client";
import { ManufacturerCard } from "@/components/ManufacturerCard";
import { JsonLd } from "@/components/JsonLd";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";
import { buildCollectionJsonLd } from "@/lib/jsonld";
import { absoluteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

// WS8.5 / R22 — specific per-route title (no generic root inheritance).
export function generateMetadata(): Metadata {
  return {
    title: "Humanoid Robot Manufacturers & Companies",
    description:
      "Every humanoid robot manufacturer tracked by HumanoidOnline: the companies, their robots, commercial status and evidence-backed availability.",
    alternates: { canonical: absoluteUrl("/manufacturers") },
  };
}

export default async function ManufacturersPage() {
  const page = await listManufacturers({ limit: 100 });
  return (
    <>
      <JsonLd
        data={buildCollectionJsonLd(
          [{ name: "Manufacturers", path: "/manufacturers" }],
          page.items.map((m) => ({ name: m.name, path: `/manufacturers/${m.slug}` })),
        )}
      />
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
            <ManufacturerCard key={m.slug} manufacturer={m} />
          ))}
        </div>
        {page.items.length === 0 && (
          <p className="empty-state">
            <SystemLabel>No manufacturers on record.</SystemLabel>
          </p>
        )}
      </div>
    </>
  );
}
