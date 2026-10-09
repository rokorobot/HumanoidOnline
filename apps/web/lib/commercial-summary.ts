// Shared buyer-facing commercial summary (UX-01 / P0-A).
//
// ONE pure helper used identically by the catalogue card, the compare matrix and
// the robot-detail hero, so the three surfaces cannot tell a buyer different
// things about the same record. It only restates what the data says:
//   - absence stays UNKNOWN ("No confirmed availability or price"), never
//     "not available" and never zero;
//   - a price is never read as proof that ordering is possible, and an
//     availability signal is never read as having a price;
//   - QUOTE_ONLY ("Price on request") is a KNOWN fact and is kept distinct from
//     "no published price".
import { modeLabel } from "./format";
import type { PriceDisplay } from "./types";

export type CommercialSummaryKind =
  | "price_only"
  | "modes_only"
  | "modes_and_price"
  | "quote_only"
  | "quote_with_modes"
  | "none";

export interface CommercialSummary {
  kind: CommercialSummaryKind;
  line: string;
  /** Human labels of the accessible modes ([] when unknown). */
  modes: string[];
}

/** True when the price display carries at least one published number. */
export function hasPublishedAmount(pd: PriceDisplay | null | undefined): boolean {
  if (!pd) return false;
  if (pd.type === "QUOTE_ONLY") return false;
  return pd.amount != null || pd.amount_min != null || pd.amount_max != null;
}

export function commercialSummary(
  price: PriceDisplay | null | undefined,
  availableModes: string[] | null | undefined,
): CommercialSummary {
  const modes = (availableModes ?? []).map(modeLabel);
  const hasModes = modes.length > 0;
  const priced = hasPublishedAmount(price);
  const quote = !!price && price.type === "QUOTE_ONLY";
  const joined = modes.join(", ");

  if (priced && !hasModes) {
    return { kind: "price_only", line: "Price published; ordering not confirmed", modes };
  }
  if (priced && hasModes) {
    return { kind: "modes_and_price", line: `Offered via ${joined}`, modes };
  }
  // Price on request is a known commercial model, not an absence of price.
  if (quote && hasModes) {
    return { kind: "quote_with_modes", line: `Offered via ${joined}; price on request`, modes };
  }
  if (quote) {
    return { kind: "quote_only", line: "Price on request; ordering not confirmed", modes };
  }
  if (hasModes) {
    return { kind: "modes_only", line: `Offered via ${joined}; no published price`, modes };
  }
  return { kind: "none", line: "No confirmed availability or price", modes };
}

/**
 * Transaction modes (raw enums, de-duplicated) a robot's availability rows say are
 * obtainable: any status other than NOT_AVAILABLE / DISCONTINUED, NEW condition only.
 * Mirrors the API's `available_modes` for surfaces that only hold the offer rows.
 */
export function accessibleModes(
  offers: { transaction_type: string; availability_status: string; condition?: string }[],
): string[] {
  const out: string[] = [];
  for (const o of offers) {
    if (o.condition && o.condition !== "NEW") continue;
    if (o.availability_status === "NOT_AVAILABLE" || o.availability_status === "DISCONTINUED") continue;
    if (!out.includes(o.transaction_type)) out.push(o.transaction_type);
  }
  return out;
}

// ── Headline offer selection (compare matrix) ────────────────────────────────

export interface HeadlineOfferInput {
  transaction_type: string;
  variant?: string | null;
  price_type: string;
  price?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  currency: string | null;
  billing_period: string | null;
  region?: string | null;
  provider?: string | null;
  price_basis?: string | null;
  order_status_note?: string | null;
  edition_confirmed?: boolean | null;
  condition?: string;
}

const PRICE_TYPE_RANK: Record<string, number> = {
  PUBLIC: 0,
  FROM: 1,
  MANUFACTURER_ESTIMATE: 2,
  ESTIMATED: 3,
  RANGE: 4,
  QUOTE_ONLY: 5,
};

export interface Headline<T extends HeadlineOfferInput> {
  /** The single offer row everything displayed is read from. */
  offer: T;
  /**
   * Greater than 1 only when several configurations carry a priced offer of the
   * same transaction type + price type + currency + billing period: `offer` is
   * then the lowest of them and the UI must say "From ..." and how many were priced.
   */
  configurationsPriced: number;
}

/**
 * Pick the headline offer for a robot from its pricing offers, as ONE row.
 *
 * Mirrors the API's card headline in spirit (purchase before other modes, a
 * published figure before an estimate, a robot-level offer before a
 * configuration-scoped one, a confirmed edition before an unassessed one) so the
 * catalogue card and the compare matrix agree. Offers that are not NEW or are
 * edition-excluded are never a headline.
 */
export function selectHeadline<T extends HeadlineOfferInput>(offers: T[]): Headline<T> | null {
  const eligible = offers.filter(
    (o) => (o.condition == null || o.condition === "NEW") && o.edition_confirmed !== false,
  );
  if (eligible.length === 0) return null;
  const key = (o: T): number[] => [
    o.transaction_type === "PURCHASE" ? 0 : 1,
    PRICE_TYPE_RANK[o.price_type] ?? 9,
    o.variant ? 1 : 0,
    o.edition_confirmed === true ? 0 : 1,
  ];
  const cmp = (a: T, b: T) => {
    const ka = key(a);
    const kb = key(b);
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i];
    return 0;
  };
  const sorted = [...eligible].sort(cmp);
  const best = sorted[0];
  const finalists = sorted.filter((o) => cmp(o, best) === 0);

  // Among equally-ranked finalists the amount decides only inside one money +
  // billing basis; otherwise the amounts are incomparable and are not ranked.
  const sameMoney = finalists.every(
    (o) =>
      o.currency === best.currency && o.billing_period === best.billing_period && o.price != null,
  );
  let chosen = best;
  if (sameMoney && finalists.length > 1) {
    chosen = finalists.reduce((lo, o) => ((o.price as number) < (lo.price as number) ? o : lo));
  }

  // "From ... N configurations priced": only in the data-supported case - several
  // distinct configurations priced the same way (same mode, price type, money).
  let configurationsPriced = 0;
  if (chosen.variant && sameMoney) {
    const variants = new Set(finalists.filter((o) => o.variant).map((o) => o.variant as string));
    if (variants.size > 1) configurationsPriced = variants.size;
  }
  return { offer: chosen, configurationsPriced };
}

/** PriceDisplay for a headline offer, carrying its own configuration, basis and order note. */
export function priceDisplayFromHeadline<T extends HeadlineOfferInput>(
  h: Headline<T> | null,
): PriceDisplay | null {
  if (!h) return null;
  const p = h.offer;
  return {
    type: p.price_type,
    amount: p.price,
    amount_min: p.price_min,
    amount_max: p.price_max,
    currency: p.currency,
    billing_period: p.billing_period,
    provider: p.provider ?? null,
    region: p.region ?? null,
    price_basis: p.price_basis ?? null,
    order_status_note: p.order_status_note ?? null,
    edition_confirmed: p.edition_confirmed ?? null,
    variant: p.variant ?? null,
  };
}

/**
 * Short, conservative VAT/tax tag derived from a price_basis sentence - only when
 * the text is unambiguous. Both or neither pattern matching yields null; the full
 * sentence is always available in the "Price terms" disclosure.
 */
export function shortBasisTag(basis: string | null | undefined): string | null {
  if (!basis) return null;
  const incl = /VAT included|incl\.?\s*VAT|including VAT/i.test(basis);
  const excl = /net of VAT|excl(uding|\.)?\s*(VAT|tax)|excludes\s+(VAT|tax)/i.test(basis);
  if (incl && !excl) return "Incl. VAT";
  if (excl && !incl) return "Excl. VAT/tax";
  return null;
}
