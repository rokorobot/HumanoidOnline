// ADR-027 §10 — editorial context fragments for Regional Research Resources.
//
// A fragment may frame and interpret; it must NEVER contain a price, status,
// count or robot-specific commercial claim (those come only from the governed
// catalogue). It is shown as final only once it carries `reviewed_at`, and a
// reviewed fragment older than EDITORIAL_REVIEW_DAYS is labelled as possibly
// outdated. An unreviewed fragment renders only in preview, marked DRAFT.
import type { ResearchRegion } from "./research";

export const EDITORIAL_REVIEW_DAYS = 180;

export interface EditorialFragment {
  /** ISO date of the owner's review; null = DRAFT, never shown publicly. */
  reviewed_at: string | null;
  reviewed_by: string | null;
  /** Sources for any externally verifiable claim in the paragraphs. */
  sources: string[];
  paragraphs: string[];
}

export const EDITORIAL: Record<ResearchRegion, EditorialFragment> = {
  europe: {
    // Owner-reviewed 2026-10-04. Review approves this text only; it does not
    // publish the resource (publication is gated separately, ADR-027 §12).
    reviewed_at: "2026-10-04",
    reviewed_by: "Robert Konecny (Product Owner)",
    // Paragraph 1: UN Statistics Division, M49 standard country or area codes
    // (region 150 "Europe"). Paragraphs 2-3 explain HumanoidOnline's own semantics.
    sources: ["https://unstats.un.org/unsd/methodology/m49/overview/"],
    paragraphs: [
      "In this resource \"Europe\" is a research grouping, not a political claim. It combines the European Union with the other sovereign European states in the UN M49 Europe classification.",
      "Each offer names its seller. Read a row's status, seller, evidence date and confidence together rather than any one of them alone.",
      "A robot with no confirmed Europe offer may well be obtainable; it means only that HumanoidOnline holds no qualifying Europe evidence for it yet.",
    ],
  },
  "north-america": {
    // DRAFT (HO-RESEARCH-NA-01, 2026-10-23): NOT owner-reviewed. It renders only in
    // preview, marked DRAFT, until the owner sets reviewed_at; review approves the
    // text only and does not publish the resource.
    reviewed_at: null,
    reviewed_by: null,
    // Paragraph 1: UN Statistics Division, M49 standard country or area codes (lists
    // the 021 / 013 / 029 members). The continental grouping 003 "North America" =
    // 021 + 029 + 013 is not shown as a row on the current UNSD page; it is attested
    // by the BCP 47 registration of region 003 citing UN M.49
    // (https://www.iana.org/assignments/lang-subtags-templates/003.txt).
    // Paragraphs 2-4 explain HumanoidOnline's own semantics.
    sources: ["https://unstats.un.org/unsd/methodology/m49/"],
    paragraphs: [
      "In this resource \"North America\" is a research grouping, not a political or trade claim. It follows the UN M49 North America classification: Northern America, Central America and the Caribbean, so it covers Canada, Mexico and the United States together with the Central American and Caribbean countries and territories. It is not defined by where a manufacturer is headquartered.",
      "An offer counts only for the country its seller documents. A United States listing is not evidence of availability in Canada, Mexico or elsewhere in North America, and a manufacturer store that sells worldwide without naming countries is shown as a global offer, not as North American availability.",
      "Public news about humanoid robots in North America ranges from demonstrations and pilot projects to multi-year service agreements and seller listings. Only a current, evidenced seller offer makes a robot count as obtainable here. Deployments show real use and are listed separately; a pilot or a customer contract is not an offer a new buyer can take up.",
      "Read each row's seller, country, status, evidence date and confidence together. A robot with no confirmed North America offer may well be obtainable; it means only that HumanoidOnline holds no qualifying, current North America evidence for it yet.",
    ],
  },
};

// Readable citation text for a source URL (shown beside the link). An unlisted host
// falls back to its hostname, so a source is never shown without a label.
const SOURCE_LABELS: Record<string, string> = {
  "unstats.un.org": "UN Statistics Division \u2014 M49 Standard Country or Area Codes",
};

export function editorialSourceLabel(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    return SOURCE_LABELS[host] ?? host;
  } catch {
    return url;
  }
}

export type EditorialState =
  | { show: false }
  | { show: true; draft: boolean; outdated: boolean; fragment: EditorialFragment };

/** Pure: decides whether and how the fragment is shown, from the snapshot date. */
export function editorialState(
  region: ResearchRegion,
  snapshotDate: string,
  preview: boolean,
): EditorialState {
  const fragment = EDITORIAL[region];
  if (!fragment.reviewed_at) {
    return preview ? { show: true, draft: true, outdated: false, fragment } : { show: false };
  }
  const age =
    (Date.parse(snapshotDate) - Date.parse(fragment.reviewed_at)) / 86_400_000;
  return { show: true, draft: false, outdated: age > EDITORIAL_REVIEW_DAYS, fragment };
}
