// ADR-027 — the HTML route of a Regional Research Resource, shared by every
// region so their gate, metadata and JSON-LD cannot drift apart.
//
// Publication-gated: closed by default (404). A region becomes public only when
// RESEARCH_PUBLISHED_REGIONS lists it; until then a reviewer opens it with a
// signed preview session (POST the token to /research/preview; the cookie is an
// HMAC assertion, never the secret), and a preview is noindex, no-store and absent
// from the sitemap. A token in the URL grants nothing. All facts come from the API
// read model via one governed read.
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import { cache } from "react";

import { ResearchResource } from "@/components/ResearchResource";
import { SiteNav } from "@/components/SiteNav";
import { type ResearchRegion, loadResearch, researchPath } from "@/lib/research";
import { buildResearchJsonLd } from "@/lib/research-jsonld";
import { PREVIEW_COOKIE } from "@/lib/research-preview";
import { absoluteUrl, siteUrl } from "@/lib/site";

// One gate + governed read shared by the page and generateMetadata (per-request memo).
const load = cache((region: ResearchRegion, sessionCookie: string) =>
  loadResearch(region, sessionCookie || null),
);

async function resolve(region: ResearchRegion) {
  const store = await cookies();
  return load(region, store.get(PREVIEW_COOKIE)?.value ?? "");
}

export function researchRegionRoute(region: ResearchRegion) {
  async function generateMetadata(): Promise<Metadata> {
    const { access, data } = await resolve(region);
    if (!data) return { title: "Not found", robots: { index: false, follow: false } };
    return {
      title: `Humanoid robot availability in ${data.region.name}`,
      description: data.direct_answer,
      alternates: { canonical: absoluteUrl(researchPath(region)) },
      // A preview must never be indexed; only a published resource is.
      robots: access.mode === "published" ? undefined : { index: false, follow: false },
    };
  }

  async function ResearchRegionPage() {
    const { access, data } = await resolve(region);
    if (!data || access.mode === "closed") notFound();

    const origin = siteUrl();
    const canonicalUrl = `${origin}${researchPath(region)}`;
    const preview = access.mode === "preview";
    const jsonLd = buildResearchJsonLd(data, origin);

    return (
      <>
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {/* The root layout already provides the single <main> landmark. */}
        <div className="wrap">
          <SiteNav active="research" />
          <ResearchResource data={data} preview={preview} canonicalUrl={canonicalUrl} />
        </div>
      </>
    );
  }

  return { generateMetadata, ResearchRegionPage };
}
