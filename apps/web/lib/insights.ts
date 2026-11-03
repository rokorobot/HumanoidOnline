// /insights — on-site editorial articles (DR-I1). Typed static content: no Markdown library, no backend.
//
// Facts rule (AGENTS.md 6 and 7): live catalogue facts (commercial status, specs, availability) are NOT
// retyped here. Articles name robots in `robotSlugs`; the page renders each one from the API. Prose may
// state dated manufacturer statements, always with their source listed in `sources`.
// Drafts are never rendered, listed, sitemapped or routable: only `publishedInsights` leaves this module.

/** Plain text, or text with a link. Internal links start with "/"; external ones are https URLs. */
export type Inline = string | { text: string; href: string };

export type Block =
  | { type: "heading"; text: string }
  | { type: "paragraph"; content: Inline[] }
  | { type: "list"; ordered?: boolean; items: Inline[][] }
  | { type: "table"; caption: string; head: string[]; rows: string[][] };

export interface InsightSource {
  title: string;
  publisher: string;
  url: string;
  /** ISO date (YYYY-MM-DD) the source was published. */
  date: string;
}

export interface Insight {
  slug: string;
  title: string;
  /** Meta description, at most 160 characters. */
  description: string;
  /** ISO dates (YYYY-MM-DD). */
  publishedAt: string;
  updatedAt: string;
  status: "published" | "draft";
  /** Catalogue robots the article is about; each is rendered live from the API. */
  robotSlugs: string[];
  /** The short answer, shown first. */
  summary: string;
  body: Block[];
  sources: InsightSource[];
}

const AGILITY = "Agility Robotics";

const DIGIT_5_EUROPE: Insight = {
  slug: "agility-digit-5-europe-2027",
  title: "Agility Digit 5 plans to enter Europe in 2027: what is confirmed so far",
  description:
    "Agility plans to offer Digit 5 in the EU and UK from 2027. What the manufacturer has stated, what is not yet confirmed, and how Digit 4 and Digit 5 differ.",
  publishedAt: "2026-11-03",
  updatedAt: "2026-11-03",
  status: "published",
  robotSlugs: ["agility-digit-5", "agility-digit"],
  summary:
    "Agility Robotics plans to offer Digit 5 for commercial deployment in the EU and the UK. It would be the first time Digit is offered outside North America. Agility expects early customer access in the first half of 2027 and general availability by the end of 2027. As of 3 November 2026, Digit 5 can't be bought or deployed in Europe. It has no published price, and its CE marking is expected but not confirmed.",
  body: [
    { type: "heading", text: "What Agility announced" },
    {
      type: "paragraph",
      content: [
        "On 15 September 2026, Agility unveiled Digit 5, the fifth generation of its bipedal humanoid. Agility says it built the robot from customer requirements gathered over about three years of Digit 4 deployments. It is aimed at manufacturing, warehouse and logistics operators. Digit 5 now has a record on HumanoidOnline: ",
        { text: "Agility Digit 5", href: "/robots/agility-digit-5" },
        ". The block below the article text shows its current catalogue status.",
      ],
    },
    {
      type: "table",
      caption: "Manufacturer-reported specifications at the 15 September 2026 unveiling (pre-production, not independently tested)",
      head: ["Specification", "Digit 5"],
      rows: [
        ["Height", "1.81 m"],
        ["Weight", "129 kg"],
        ["Maximum reach height", "2.2 m"],
        ["Repeated lifting payload", "22.7 kg (50 lb)"],
        ["Runtime", "90 minutes"],
        ["Charging time", "9 minutes (10:1 run-to-charge ratio)"],
        ["End effectors", "Swappable grippers, ISO-standard mounting flanges"],
        ["Fleet software", "Agility Arc"],
      ],
    },
    { type: "heading", text: "Europe and the UK: a plan, not an offer" },
    {
      type: "paragraph",
      content: [
        'Agility states that Digit 5 is expected to carry a CE mark and other regulatory marks for the EU, Great Britain and Northern Ireland. For a European buyer, three points matter:',
      ],
    },
    {
      type: "list",
      ordered: true,
      items: [
        [
          "No European availability yet. HumanoidOnline records no EU or UK availability offer for Digit 5. We will add one only when Agility or an authorised provider publishes terms.",
        ],
        [
          'Certification is still in progress. Agility describes Digit 5 as designed for "cooperatively safe" work near people. In October 2026 it said the safety evaluation is ongoing, "ahead of final third-party certification". Treat cooperative safety as a design goal until certification is published.',
        ],
        [
          "No published terms. No price, purchase terms or Robots-as-a-Service terms have been published for Digit 5.",
        ],
      ],
    },
    { type: "heading", text: "Digit 5 and Digit 4 are separate records" },
    {
      type: "paragraph",
      content: [
        "Digit's commercial record so far belongs to Digit 4. That includes its multi-year Robots-as-a-Service deployment with GXO in the United States. In October 2026 GXO and Agility said new GXO deployments would start on Digit 4 and later move to Digit 5. HumanoidOnline keeps the two generations in separate records, and deployment evidence stays with the generation it describes: ",
        { text: "Digit (Digit 4)", href: "/robots/agility-digit" },
        ".",
      ],
    },
    {
      type: "paragraph",
      content: [
        "Agility also reports more than $300 million in multi-year Digit 5 orders. Those orders depend on contractual milestones, so they are commitments, not revenue or deployed robots.",
      ],
    },
    { type: "heading", text: "Which workflows Agility plans for Digit 5" },
    {
      type: "paragraph",
      content: [
        "Digit 4 has mostly handled totes. For Digit 5, Agility describes a wider set of workflows: depalletizing, machine tending, kitting and sequencing, quality inspection and palletizing. These are planned capabilities. They have not yet been shown in a Digit 5 customer deployment.",
      ],
    },
    {
      type: "paragraph",
      content: [
        "On HumanoidOnline, Digit 5 is listed under ",
        { text: "Manufacturing", href: "/use-cases/manufacturing" },
        " and ",
        { text: "Warehouse & Logistics", href: "/use-cases/warehouse-logistics" },
        ", labelled as an announced robot.",
      ],
    },
    { type: "heading", text: "What European buyers can do now" },
    {
      type: "paragraph",
      content: [
        "If you are planning automation projects for 2027, put Digit 5 on your evaluation list but not on your budget line yet. The details to ask Agility for are the CE marking date, the commercial model (purchase or RaaS), the service model in your country, and Digit 5 references in workflows like yours.",
      ],
    },
  ],
  sources: [
    {
      title: "Agility Unveils Digit 5 Humanoid Robot Built for Cooperatively Safe Work at Scale",
      publisher: AGILITY,
      url: "https://www.agilityrobotics.com/content/agility-unveils-digit-5-humanoid-robot-built-for-cooperatively-safe-work-at-scale",
      date: "2026-09-15",
    },
    {
      title: "Agility Robotics Expands NVIDIA Collaboration as It Prepares Digit 5 for Commercial Scale",
      publisher: AGILITY,
      url: "https://www.agilityrobotics.com/content/agility-robotics-expands-nvidia-collaboration-as-it-prepares-digit-5-for-commercial-scale",
      date: "2026-10-22",
    },
    {
      title: "GXO and Agility Robotics Expand Partnership to Accelerate Deployment of Humanoids in U.S. Operations",
      publisher: AGILITY,
      url: "https://www.agilityrobotics.com/content/gxo-and-agility-robotics-expand-partnership-to-accelerate-deployment-of-humanoids-in-u-s-operations",
      date: "2026-10-26",
    },
  ],
};

export const ALL_INSIGHTS: Insight[] = [DIGIT_5_EUROPE];

/** Published only, newest first. The sole export the site reads from. */
export const publishedInsights: Insight[] = ALL_INSIGHTS.filter((i) => i.status === "published").sort((a, b) =>
  b.publishedAt.localeCompare(a.publishedAt),
);

export const findInsight = (slug: string): Insight | undefined => publishedInsights.find((i) => i.slug === slug);

export const insightPath = (slug: string): string => `/insights/${slug}`;
