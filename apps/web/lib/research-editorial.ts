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
    // DRAFT (HO-RESEARCH-NA-01/02, 2026-10-23): NOT owner-reviewed. It renders only in
    // preview, marked DRAFT, until the owner sets reviewed_at; review approves the
    // text only and does not publish the resource. No price, status, count or
    // robot-specific commercial claim: those come only from the governed projection.
    reviewed_at: null,
    reviewed_by: null,
    // Paragraph 1: UN Statistics Division M49 page (lists the 021 / 013 / 029
    // members). The continental grouping 003 "North America" = 021 + 029 + 013 is not
    // shown as a row on the current UNSD page; it is attested by the BCP 47
    // registration of region 003 citing UN M.49 (IANA record, second source).
    // Paragraph 5: FCC fact sheet DOC-423682A1 (2026-07-28) and Public Notices
    // DA 26-786 (2026-07-28) and DA 26-1130 (2026-10-21).
    // Paragraphs 2-4 explain HumanoidOnline's own semantics.
    sources: [
      "https://unstats.un.org/unsd/methodology/m49/",
      "https://www.iana.org/assignments/lang-subtags-templates/003.txt",
      "https://docs.fcc.gov/public/attachments/DOC-423682A1.pdf",
      "https://docs.fcc.gov/public/attachments/DA-26-786A1.pdf",
      "https://docs.fcc.gov/public/attachments/DA-26-1130A1.pdf",
    ],
    paragraphs: [
      "In this resource \"North America\" is a research grouping, not a political or trade claim. It follows the UN M49 North America classification: Northern America, Central America and the Caribbean, so it covers Canada, Mexico and the United States together with the Central American and Caribbean countries and territories. It is not defined by where a manufacturer is headquartered.",
      "An offer counts only for the country its seller documents. A United States listing is not evidence of availability in Canada, Mexico or elsewhere in North America, and a manufacturer store that sells worldwide without naming countries is shown as a global offer, not as North American availability. Each offer names its seller and whether it is the manufacturer or a distributor, reseller or integrator; a third-party seller is not the manufacturer and is not assumed to be authorized by it.",
      "Offers differ in how close they are to a purchase. An available or limited offer can be ordered directly, although a limited or special-order item may still have to be sourced after the order. A preorder or waitlist reserves a place for a product that is not yet shipping. A quote or contact-sales offer confirms a sales route, not stock, a price or a delivery date. Each offer shows when it was last observed: an offer stays current until newer evidence replaces it.",
      "Public news about humanoid robots in North America ranges from demonstrations and pilot projects to multi-year service agreements with a single customer and to seller listings. Deployments show real use and are listed separately; a pilot or a customer contract is not an offer a new buyer can take up. A robot with no confirmed North America offer may well be obtainable; it means only that HumanoidOnline holds no qualifying North America evidence for it yet.",
      "United States regulation is a separate question from commercial availability. On 28 July 2026 the US Federal Communications Commission added foreign-produced \"advanced robotic devices\", including humanoid robots, to its Covered List, so new models generally cannot receive FCC equipment authorization unless the Department of War has granted a Conditional Approval. The FCC states that this does not stop the import, sale or use of models it authorized earlier, or affect devices already bought. The listing depends on where a product is produced, not on a named company. HumanoidOnline does not record whether a particular robot is FCC-authorized; buyers should confirm the authorization of the exact model with the seller.",
    ],
  },
  asia: {
    // DRAFT (HO-RESEARCH-ASIA-01, 2026-10-24): NOT owner-reviewed. It renders only in
    // preview, marked DRAFT, until the owner sets reviewed_at; review approves the
    // text only and does not publish the resource. No price, status, count or
    // robot-specific commercial claim: those come only from the governed projection.
    reviewed_at: null,
    reviewed_by: null,
    // Paragraph 1: UN Statistics Division M49 page (Asia 142 and its five
    // sub-regions; Cyprus is listed under Western Asia). The Cyprus and Taiwan
    // handling is HumanoidOnline's own coding (db/catalogue/regions.json, owner
    // decisions D1/D2). Paragraphs 2-5 explain HumanoidOnline's own semantics.
    sources: ["https://unstats.un.org/unsd/methodology/m49/overview/"],
    paragraphs: [
      "In this resource \"Asia\" is a market geography for research, not a statement about political status or about common customs and trade rules. It follows the UN M49 Asia classification: Central, Eastern, South-eastern, Southern and Western Asia. Two coding choices are disclosed: Cyprus, which M49 places in Western Asia, is counted with the European Union in the Europe resource and not here, and Taiwan, which the catalogue codes as a separate commercial destination, is included as a market; that is not a claim that M49 lists it as a separate entry. Russia is counted in Europe. Asia here is not Asia-Pacific: Australia, New Zealand and the Pacific are not included.",
      "An offer counts only for the country its seller documents. A manufacturer headquartered in China, Japan or South Korea is not evidence that its robots can be bought in every Asian country, and an offer documented for China says nothing about Japan, South Korea, India or Singapore. A manufacturer store that sells worldwide without naming countries is shown as a global offer, not as Asian availability. Each offer names its seller and whether it is the manufacturer or a distributor, reseller or integrator.",
      "Offers differ in how close they are to a purchase. An available or limited offer can be ordered directly, although a limited or special-order item may still have to be sourced after the order. A preorder or waitlist reserves a place for a product that is not yet shipping. A quote or contact-sales offer confirms a sales route, not stock, a price or a delivery date. A rental or lease offer is not a purchase offer. Each offer shows when it was last observed: an offer stays current until newer evidence replaces it.",
      "Public news about humanoid robots in Asia ranges from showroom demonstrations and factory trials to volume orders from a single industrial customer. Deployments show real use and are listed separately; a pilot, a demonstration or a customer contract is not an offer a new buyer can take up. A robot with no confirmed Asia offer may well be obtainable; it means only that HumanoidOnline holds no qualifying Asia evidence for it yet.",
      "Import rules, radio and safety certification, warranty, language support and after-sales service differ between Asian markets. HumanoidOnline does not record whether a particular robot is certified or may be imported in a given country; buyers should confirm this for the exact model with the seller. This resource is commercial research, not legal or regulatory clearance.",
    ],
  },
};

// Readable citation text for a source URL (shown beside the link). An unlisted host
// falls back to its hostname, so a source is never shown without a label.
const SOURCE_LABELS: Record<string, string> = {
  "unstats.un.org": "UN Statistics Division \u2014 M49 Standard Country or Area Codes",
  "https://www.iana.org/assignments/lang-subtags-templates/003.txt":
    "IANA \u2014 BCP 47 registration of region 003 (North America, UN M.49)",
  "https://docs.fcc.gov/public/attachments/DOC-423682A1.pdf":
    "FCC \u2014 Fact sheet: Covered List update, advanced robotic devices (28 July 2026)",
  "https://docs.fcc.gov/public/attachments/DA-26-786A1.pdf":
    "FCC \u2014 Public Notice DA 26-786 (28 July 2026)",
  "https://docs.fcc.gov/public/attachments/DA-26-1130A1.pdf":
    "FCC \u2014 Public Notice DA 26-1130, Conditional Approvals (21 October 2026)",
};

/** Label for a source: an exact-URL label first, then a host label, then the host. */
export function editorialSourceLabel(url: string): string {
  if (SOURCE_LABELS[url]) return SOURCE_LABELS[url];
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
