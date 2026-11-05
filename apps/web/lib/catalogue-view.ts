// DR-UI2 — catalogue mode tabs and the Cards / Board view switch. Pure URL helpers:
// the URL stays the single source of truth (filters live in searchParams).
//
// Tab and view links never carry `compare` (Emergency Compare Crawl Containment:
// no real <a href> may point at a compare selection), and never `offset`.
import { asArray, asString, toQueryString, type RawSearchParams } from "./search-params";

/** Tabs in display order. `null` = All (no transaction filter). */
export const MODE_TABS: { mode: string | null; label: string }[] = [
  { mode: null, label: "All" },
  { mode: "PURCHASE", label: "Purchase" },
  { mode: "RENTAL", label: "Rental" },
  { mode: "RAAS", label: "RaaS" },
  { mode: "LEASE", label: "Lease" },
];

export type CatalogueView = "cards" | "board";

export function catalogueView(sp: RawSearchParams): CatalogueView {
  return asString(sp.view) === "board" ? "board" : "cards";
}

function base(sp: RawSearchParams): RawSearchParams {
  const next: RawSearchParams = { ...sp };
  delete next.compare;
  delete next.offset;
  return next;
}

/** The tab that is active for the EFFECTIVE query: All when unfiltered, a mode when
 *  exactly that one transaction type is filtered, otherwise none (a mixed filter). */
export function activeModeTab(effective: RawSearchParams): string | null | undefined {
  const modes = asArray(effective.transaction_type);
  if (modes.length === 0) return null;
  if (modes.length === 1) return modes[0];
  return undefined;
}

export function modeTabHref(sp: RawSearchParams, mode: string | null): string {
  const next = base(sp);
  if (mode) next.transaction_type = mode;
  else delete next.transaction_type;
  return `/robots${toQueryString(next)}`;
}

export function viewHref(sp: RawSearchParams, view: CatalogueView): string {
  const next = base(sp);
  if (view === "board") next.view = "board";
  else delete next.view;
  return `/robots${toQueryString(next)}`;
}

/** The effective params minus the transaction filter: the base the tab counts share. */
export function withoutMode(effective: RawSearchParams): RawSearchParams {
  const next: RawSearchParams = { ...effective };
  delete next.transaction_type;
  return next;
}
