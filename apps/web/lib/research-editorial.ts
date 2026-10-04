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
  /** Externally verifiable claims need a source; this draft makes none. */
  sources: string[];
  paragraphs: string[];
}

export const EDITORIAL: Record<ResearchRegion, EditorialFragment> = {
  europe: {
    reviewed_at: null,
    reviewed_by: null,
    sources: [],
    paragraphs: [
      "In this resource \"Europe\" is a research grouping, not a political claim. It combines the European Union with the other sovereign European states in the UN M49 Europe classification.",
      "Each offer names its seller. Read a row's status, seller, evidence date and confidence together rather than any one of them alone.",
      "A robot with no confirmed Europe offer may well be obtainable; it means only that HumanoidOnline holds no qualifying Europe evidence for it yet.",
    ],
  },
};

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
