// Product line /lines/[slug] (DR-L1). Direct answer, edition table, ProductGroup JSON-LD.
// All facts come from the governed `/api/product-lines/{slug}` read (member RobotDetails);
// 404 for an unknown or unpublished line.
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { ProductLinePage } from "@/components/ProductLinePage";
import { findProductLine } from "@/lib/api-client";
import { buildProductLineJsonLd } from "@/lib/jsonld";
import { buildLineAnswer } from "@/lib/line-answer";
import { lineTitle } from "@/lib/robot-meta";
import { absoluteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

// One governed read shared by the page and generateMetadata (React cache()).
const getLineCached = cache(findProductLine);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const line = await getLineCached(slug);
  if (!line) return { title: "Not found" };
  return {
    title: lineTitle(line),
    // The description is the first sentence of the direct answer (editions only): it
    // makes no price or availability claim the page might not carry.
    description: buildLineAnswer(line.name, line.robots).paragraphs[0],
    alternates: { canonical: absoluteUrl(`/lines/${line.slug}`) },
  };
}

export default async function ProductLineRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const line = await getLineCached(slug);
  if (!line) notFound();
  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(buildProductLineJsonLd(line)) }}
      />
      <ProductLinePage line={line} />
    </>
  );
}
