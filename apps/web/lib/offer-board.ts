// DR-UI2 — the offer board: one row per offer, availability + price + evidence read
// together. Pure function, no I/O.
//
// SAFETY RULE: a price and an availability record share a row ONLY when they have
// the identical offer identity (mode × region × provider × configuration ×
// condition). This deliberately does NOT re-implement the wider eligibility of the
// `commercial_offer` view (parent region, GLOBAL, provider-agnostic prices — see
// docs/03 §4): the API does not expose that view, and re-deriving it here would be
// an ad-hoc second rule. A price that does not match exactly keeps its own row, with
// its availability shown as unknown. One seller's price is therefore never shown
// under another seller's (or region's) availability.
import type { AvailabilityOffer, PricingOffer } from "./types";

export interface OfferRow {
  key: string;
  mode: string;
  region: string | null;
  provider: string | null;
  providerName: string | null;
  variant: string | null;
  condition: string;
  /** The availability record(s) for this exact identity; [] = availability unknown. */
  availability: AvailabilityOffer[];
  /** The price record(s) for this exact identity; [] = no price on record. */
  prices: PricingOffer[];
}

type Offer = AvailabilityOffer | PricingOffer;

export function offerKey(o: Offer): string {
  return [
    o.transaction_type,
    o.region ?? "",
    o.provider ?? "",
    o.variant_slug ?? o.variant ?? "",
    o.condition ?? "NEW",
  ].join("|");
}

// Display order only — never a ranking of sellers. Obtainable-now statuses first
// (docs/03 §4 order of immediacy), then rows with no availability record, then
// NOT_AVAILABLE / DISCONTINUED.
const STATUS_ORDER = ["AVAILABLE", "LIMITED", "PREORDER", "WAITLIST", "ON_REQUEST"];
const MODE_ORDER = ["PURCHASE", "RENTAL", "LEASE", "RAAS", "SUBSCRIPTION", "PILOT", "DEVELOPER", "OTHER"];

function statusRank(row: OfferRow): number {
  if (row.availability.length === 0) return STATUS_ORDER.length;
  const best = Math.min(
    ...row.availability.map((a) => {
      const i = STATUS_ORDER.indexOf(a.availability_status);
      return i === -1 ? STATUS_ORDER.length + 1 : i;
    }),
  );
  return best;
}

function modeRank(mode: string): number {
  const i = MODE_ORDER.indexOf(mode);
  return i === -1 ? MODE_ORDER.length : i;
}

export function buildOfferRows(
  pricing: PricingOffer[],
  availability: AvailabilityOffer[],
): OfferRow[] {
  const rows = new Map<string, OfferRow>();
  const rowFor = (o: Offer): OfferRow => {
    const key = offerKey(o);
    let row = rows.get(key);
    if (!row) {
      row = {
        key,
        mode: o.transaction_type,
        region: o.region ?? null,
        provider: o.provider ?? null,
        providerName: o.provider_name ?? null,
        variant: o.variant ?? null,
        condition: o.condition ?? "NEW",
        availability: [],
        prices: [],
      };
      rows.set(key, row);
    }
    if (!row.providerName && o.provider_name) row.providerName = o.provider_name;
    return row;
  };
  for (const a of availability) rowFor(a).availability.push(a);
  for (const p of pricing) rowFor(p).prices.push(p);

  return [...rows.values()].sort(
    (a, b) =>
      statusRank(a) - statusRank(b) ||
      modeRank(a.mode) - modeRank(b.mode) ||
      (a.region ?? "").localeCompare(b.region ?? "") ||
      (a.providerName ?? a.provider ?? "").localeCompare(b.providerName ?? b.provider ?? "") ||
      a.key.localeCompare(b.key),
  );
}

// The lead form's preferred-transaction vocabulary (lib/lead-form.ts) for an offer
// mode. Modes with no lead-form equivalent map to "" (no preference): never guessed.
const LEAD_TRANSACTION: Record<string, string> = {
  PURCHASE: "BUY",
  RENTAL: "RENT",
  LEASE: "LEASE",
  RAAS: "RAAS",
};

export function leadTransactionFor(mode: string): string {
  return LEAD_TRANSACTION[mode] ?? "";
}
