// /insights — index of published editorial articles (DR-I1). Static typed content from lib/insights.ts;
// drafts never reach this list. Catalogue facts live on robot pages, not here.
import type { Metadata } from "next";
import Link from "next/link";

import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { insightPath, publishedInsights } from "@/lib/insights";
import { absoluteUrl } from "@/lib/site";

export function generateMetadata(): Metadata {
  return {
    title: "Insights",
    description:
      "Dated, sourced editorial analysis of the humanoid-robot market. Catalogue facts are shown live from the HumanoidOnline catalogue.",
    alternates: { canonical: absoluteUrl("/insights") },
  };
}

export default function InsightsIndexPage() {
  return (
    <>
      <SystemHeader title="INSIGHTS" fields={[{ value: "DATED · SOURCED", label: "" }]} />
      <div className="wrap" data-testid="insights-index">
        <SiteNav />
        <div className="pagebar">
          <div>
            <SectionIndex>INSIGHTS — EDITORIAL</SectionIndex>
            <h1>Insights</h1>
          </div>
        </div>
        <ul style={{ listStyle: "none", padding: 0, maxWidth: "72ch" }}>
          {publishedInsights.map((i) => (
            <li key={i.slug} style={{ marginBottom: "var(--ho-sp-7)" }}>
              <h2>
                <Link href={insightPath(i.slug)}>{i.title}</Link>
              </h2>
              <p className="meta">
                <time dateTime={i.publishedAt}>{i.publishedAt}</time>
              </p>
              <p>{i.description}</p>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
