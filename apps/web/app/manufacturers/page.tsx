// Manufacturers index — from /api/manufacturers.
import { listManufacturers } from "@/lib/api-client";
import { ManufacturerCard } from "@/components/ManufacturerCard";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
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
