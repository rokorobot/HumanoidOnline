// /research — the permanent Research hub (ADR-027).
//
// Publication-aware: the hub exists only while at least one Research Resource is
// actually published and served. With none, it is a 404 (not an empty section),
// absent from the sitemap and from navigation. It lists a region as a live
// resource only when that region is live; others are shown as "in preparation"
// and are never linked. It states no catalogue figure: numbers belong to the
// resources themselves, generated from the governed catalogue.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";
import {
  HUB_REGIONS,
  RESEARCH_HUB_PATH,
  liveResearchRegions,
  researchPath,
} from "@/lib/research";
import { absoluteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

const getLive = cache(() => liveResearchRegions());

export async function generateMetadata(): Promise<Metadata> {
  const live = await getLive();
  if (live.length === 0) return { title: "Not found", robots: { index: false, follow: false } };
  return {
    title: "Research",
    description:
      "HumanoidOnline Research Resources: snapshot-dated, evidence-linked analysis generated from the humanoid-robot catalogue, starting with humanoid availability by region.",
    alternates: { canonical: absoluteUrl(RESEARCH_HUB_PATH) },
  };
}

// What every Research Resource guarantees. Deliberately number-free.
const PRINCIPLES: { label: string; title: string; body: string }[] = [
  {
    label: "01",
    title: "Snapshot-dated",
    body: "Every resource states the date of the data it was generated from. Nothing is presented as current without it.",
  },
  {
    label: "02",
    title: "Evidence-linked",
    body: "Each commercial fact carries its source, evidence date and confidence. Confidence is shown as recorded and never upgraded.",
  },
  {
    label: "03",
    title: "Deterministic",
    body: "Figures and answers are computed from the catalogue by fixed rules, so the same data always gives the same result.",
  },
  {
    label: "04",
    title: "Unknown stays unknown",
    body: "A missing price is shown as not published, never as zero. No offer on file is never presented as not available.",
  },
  {
    label: "05",
    title: "Availability is not deployment",
    body: "Whether a robot can be obtained in a region and whether it has been used there are separate evidence, shown separately.",
  },
];

export default async function ResearchHubPage() {
  const live = await getLive();
  if (live.length === 0) notFound();

  return (
    <>
      <SystemHeader title="RESEARCH RESOURCES" fields={[{ value: "SNAPSHOT-DATED", label: "" }]} />
      <div className="wrap" data-testid="research-hub">
        <SiteNav active="research" />
        <div className="pagebar">
          <div>
            <SectionIndex>RESEARCH — GENERATED FROM THE CATALOGUE</SectionIndex>
            <h1>Research</h1>
          </div>
        </div>

        <p style={{ maxWidth: "72ch", marginBottom: "var(--ho-sp-7)" }}>
          Research Resources are living analyses generated directly from the HumanoidOnline
          catalogue. They are not written once and left to age: each is rebuilt from governed,
          evidence-linked data and states the snapshot it describes.
        </p>

        <SectionIndex>HOW RESEARCH RESOURCES WORK</SectionIndex>
        <ul className="apps research-principles" style={{ marginBottom: "var(--ho-sp-7)" }}>
          {PRINCIPLES.map((p) => (
            <li key={p.title} className="app">
              <SystemLabel>{p.label}</SystemLabel>
              <span className="name">{p.title}</span>
              <span className="research-principle-body">{p.body}</span>
            </li>
          ))}
        </ul>

        <SectionIndex>HUMANOID AVAILABILITY BY REGION</SectionIndex>
        <p style={{ maxWidth: "72ch", margin: "var(--ho-sp-3) 0 var(--ho-sp-5)" }}>
          Which humanoid robots can be obtained in each region, from whom, with what evidence and how
          recently it was observed.
        </p>
        <ul className="apps research-regions" style={{ marginBottom: "var(--ho-sp-8)" }}>
          {HUB_REGIONS.map((r, i) => {
            const isLive = (live as readonly string[]).includes(r.slug);
            const label = String(i + 1).padStart(2, "0");
            return isLive ? (
              <li key={r.slug} data-region-state="live">
                <Link className="app" href={researchPath(r.slug as (typeof live)[number])}>
                  <SystemLabel>{label}</SystemLabel>
                  <span className="name">{r.name}</span>
                  <SystemLabel>AVAILABILITY RESOURCE</SystemLabel>
                </Link>
              </li>
            ) : (
              <li key={r.slug} data-region-state="preparing">
                <div className="app">
                  <SystemLabel>{label}</SystemLabel>
                  <span className="name">{r.name}</span>
                  <SystemLabel>IN PREPARATION</SystemLabel>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </>
  );
}
