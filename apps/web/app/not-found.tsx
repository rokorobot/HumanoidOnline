import Link from "next/link";

import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";

export default function NotFound() {
  return (
    <>
      <SystemHeader title="RECORD NOT FOUND / 404" />
      <div className="wrap">
        <SiteNav active={null} />
        <div className="pagebar">
          <div>
            <SectionIndex>404 — NO SUCH RECORD</SectionIndex>
            <h1>Not found</h1>
          </div>
        </div>
        <p className="empty-state" style={{ marginBottom: "var(--ho-sp-8)" }}>
          The requested record does not exist in the catalogue.{" "}
          <Link href="/robots" style={{ textDecoration: "underline" }}>
            Return to the catalogue
          </Link>
          .
        </p>
      </div>
    </>
  );
}
