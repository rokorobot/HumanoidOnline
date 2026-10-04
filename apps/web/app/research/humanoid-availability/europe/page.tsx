// ADR-027 Step 3 — the Europe Regional Research Resource (HTML).
//
// Publication-gated: closed by default (404). It becomes public only when
// RESEARCH_PUBLISHED_REGIONS lists "europe"; until then a reviewer opens it with
// `?preview=<RESEARCH_PREVIEW_TOKEN>`, and a preview is noindex and absent from
// the sitemap. All facts come from the API read model via one governed read.
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { ResearchResource } from "@/components/ResearchResource";
import { SiteNav } from "@/components/SiteNav";
import { loadResearch, researchPath } from "@/lib/research";
import { buildResearchJsonLd } from "@/lib/research-jsonld";
import { absoluteUrl, siteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

const REGION = "europe" as const;

type SearchParams = Promise<{ preview?: string | string[] }>;

function previewParam(sp: { preview?: string | string[] }): string | undefined {
  return Array.isArray(sp.preview) ? sp.preview[0] : sp.preview;
}

// One gate + governed read shared by the page and generateMetadata (per-request memo).
const load = cache((preview: string) => loadResearch(REGION, preview || null));

async function resolve(searchParams: SearchParams) {
  return load((previewParam(await searchParams) ?? ""));
}

export async function generateMetadata({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<Metadata> {
  const { access, data } = await resolve(searchParams);
  if (!data) return { title: "Not found", robots: { index: false, follow: false } };
  return {
    title: `Humanoid robot availability in ${data.region.name}`,
    description: data.direct_answer,
    alternates: { canonical: absoluteUrl(researchPath(REGION)) },
    // A preview must never be indexed; only a published resource is.
    robots: access.mode === "published" ? undefined : { index: false, follow: false },
  };
}

export default async function EuropeResearchPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { access, data } = await resolve(searchParams);
  if (!data || access.mode === "closed") notFound();

  const origin = siteUrl();
  const canonicalUrl = `${origin}${researchPath(REGION)}`;
  const preview = access.mode === "preview";
  const jsonLd = buildResearchJsonLd(data, origin);

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <SiteNav />
      <main id="main">
        <ResearchResource data={data} preview={preview} canonicalUrl={canonicalUrl} />
      </main>
    </>
  );
}
