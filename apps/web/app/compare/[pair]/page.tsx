// SEO-04 — clean, indexable "A vs B" page: /compare/<a>-vs-<b> (slugs sorted).
// The same comparison as /compare?ids=a,b (whose canonical points here), rendered at a
// stable path search engines can rank. Reverse order permanently redirects to the
// sorted path; a pair that does not resolve to two published robots is a 404.
// View-state changes inside CompareView navigate to /compare?ids=… as before.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { cache } from "react";

import { compareRobots } from "@/lib/api-client";
import { pairPath, parsePair } from "@/lib/compare-pairs";
import { fitDescription, fitTitle } from "@/lib/meta-text";
import { absoluteUrl } from "@/lib/site";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { CompareView } from "../CompareView";
import { slimForClient } from "../slim";
import "../compare.css";

export const dynamic = "force-dynamic";

// One API read per request, shared by generateMetadata and the page.
const loadPair = cache(async (segment: string) => {
  const pair = parsePair(segment);
  if (!pair) return null;
  const data = await compareRobots(pair);
  return data && data.robots.length === 2 ? data : null;
});

// "Unitree H2", not "Unitree Robotics Unitree H2"; "1X Technologies NEO" when the name lacks the maker.
function label(r: { name: string; manufacturer: { name: string } }): string {
  const first = r.manufacturer.name.split(/\s+/)[0].toLowerCase();
  return r.name.toLowerCase().startsWith(first) ? r.name : `${r.manufacturer.name.split(/\s+/)[0]} ${r.name}`;
}

export async function generateMetadata({ params }: { params: Promise<{ pair: string }> }): Promise<Metadata> {
  const { pair } = await params;
  const data = await loadPair(pair);
  if (!data) return { title: "Not found" };
  const [a, b] = data.robots.map(label);
  const [x, y] = data.robots.map((r) => r.slug);
  return {
    title: fitTitle(`${a} vs ${b}: Specs, Price & Availability`),
    description: fitDescription(
      `${a} vs ${b}: side-by-side comparison of specs, price, commercial availability and deployment evidence.`,
      "Every value links to its source; unknown stays unknown.",
    ),
    alternates: { canonical: absoluteUrl(pairPath(x, y)) },
  };
}

export default async function PairComparePage({ params }: { params: Promise<{ pair: string }> }) {
  const { pair } = await params;
  const parsed = parsePair(pair);
  if (!parsed) notFound();
  const canonical = pairPath(...parsed);
  if (canonical !== `/compare/${decodeURIComponent(pair)}`) permanentRedirect(canonical);
  const data = await loadPair(pair);
  if (!data) notFound();
  const [a, b] = data.robots.map(label);

  return (
    <>
      <SystemHeader
        title="COMPARISON MATRIX"
        fields={[
          { value: 2, label: "" },
          { value: "PLATFORMS SELECTED", label: "" },
        ]}
      />
      <div className="wrap">
        <SiteNav active="compare" />

        <div className="pagebar">
          <div>
            <SectionIndex>COMPARE — SIDE BY SIDE</SectionIndex>
            <h1>
              {a} vs {b}
            </h1>
            <p>
              <Link href={`/robots/${data.robots[0].slug}`}>{a}</Link> and{" "}
              <Link href={`/robots/${data.robots[1].slug}`}>{b}</Link> compared on specs, price,
              availability and deployment evidence.
            </p>
          </div>
        </div>

        <CompareView
          data={slimForClient(data)}
          ids={data.robots.map((r) => r.slug)}
          state={{ ref: null, units: "metric", view: "matrix", region: null, market: null }}
          context={{ region: null, market: null, applicable: null, marketCodes: null }}
        />
      </div>
    </>
  );
}
