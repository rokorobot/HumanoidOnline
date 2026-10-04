// ADR-027 §11 — JSON-LD for a Regional Research Resource.
//
// Pure builder over the SAME projection the HTML and JSON endpoint render, so
// the three surfaces cannot drift. It maps; it never computes a fact. Only
// robots present in the projection (published, qualifying) are listed, and the
// FAQ is exactly the visible FAQ. No licence is asserted (none has been decided).
import {
  RESEARCH_BASE_PATH,
  type ResearchProjection,
} from "./research";

export function buildResearchJsonLd(
  data: ResearchProjection,
  origin: string,
): Record<string, unknown> {
  const url = `${origin}${RESEARCH_BASE_PATH}/${data.region.slug}`;

  const seen = new Set<string>();
  const listed = data.offers.filter((o) => {
    if (seen.has(o.robot_slug)) return false;
    seen.add(o.robot_slug);
    return true;
  });

  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Dataset",
        "@id": `${url}#dataset`,
        name: `Humanoid robot availability in ${data.region.name}`,
        description: data.direct_answer,
        url,
        dateModified: data.snapshot_date,
        temporalCoverage: data.snapshot_date,
        spatialCoverage: { "@type": "Place", name: data.region.name },
        creator: { "@type": "Organization", name: "HumanoidOnline", url: origin },
        isBasedOn: `${origin}/robots`,
        variableMeasured: [
          "Availability status",
          "Transaction type",
          "Seller",
          "Published price",
          "Evidence date",
          "Confidence",
        ],
        distribution: {
          "@type": "DataDownload",
          encodingFormat: "application/json",
          contentUrl: `${url}.json`,
        },
      },
      {
        "@type": "ItemList",
        "@id": `${url}#robots`,
        name: `Humanoid robots with a confirmed offer in ${data.region.name}`,
        numberOfItems: listed.length,
        itemListElement: listed.map((o, i) => ({
          "@type": "ListItem",
          position: i + 1,
          name: o.robot_name,
          url: `${origin}/robots/${o.robot_slug}`,
        })),
      },
      {
        "@type": "FAQPage",
        "@id": `${url}#faq`,
        mainEntity: data.faq.map((f) => ({
          "@type": "Question",
          name: f.question,
          acceptedAnswer: { "@type": "Answer", text: f.answer },
        })),
      },
    ],
  };
}
