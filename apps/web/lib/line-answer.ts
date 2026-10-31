// DR-L1 — the generated direct answer of a product-line page.
//
// Pure: member `RobotDetail`s in, sentences out. Every number is read from a member
// edition and labelled with that edition; nothing is filled from a sibling and nothing
// is converted (L3, docs/23 CITATION-01.9). The line itself carries no facts.
//
// The "lowest published price" statement is a derived, reproducible statement over
// comparable offers only: a current NEW, one-time-billed offer of type PUBLIC, FROM or
// RANGE that holds a number. Per currency, the cheapest of those (a RANGE counts by its
// lower bound and keeps its range label). Currencies are never converted or compared.
// Quote-only, estimated and manufacturer-estimate prices are never "published prices".
import { formatDate, resolvePriceState } from "@/lib/format";
import { priceTypeLabel } from "@/lib/labels";
import type { PricingOffer, RobotDetail } from "@/lib/types";

const PUBLISHED = new Set(["PUBLIC", "FROM", "RANGE"]);

/** The numeric floor of a published offer, or null when the offer is not a comparable one. */
export function publishedFloor(o: PricingOffer): number | null {
  if (!PUBLISHED.has(o.price_type)) return null;
  if (o.condition && o.condition !== "NEW") return null;
  if (o.billing_period && o.billing_period !== "ONE_TIME") return null;
  const n = o.price_type === "RANGE" ? o.price_min : o.price;
  return n == null ? null : n;
}

export interface LowestPrice {
  currency: string;
  edition: string;
  editionSlug: string;
  /** Display label from the shared price formatter (e.g. "$13,500", "From $9,900"). */
  amountLabel: string;
  priceTypeLabel: string;
  seller: string | null;
  observed: string | null;
}

/** Lowest published price per currency across the editions, ordered by currency code. */
export function lowestPricesByCurrency(robots: RobotDetail[]): LowestPrice[] {
  const best = new Map<string, { floor: number; robot: RobotDetail; offer: PricingOffer }>();
  for (const robot of robots) {
    for (const offer of robot.pricing_offers ?? []) {
      const floor = publishedFloor(offer);
      if (floor == null) continue;
      const cur = best.get(offer.currency);
      if (!cur || floor < cur.floor) best.set(offer.currency, { floor, robot, offer });
    }
  }
  return [...best.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, { robot, offer }]) => ({
      currency,
      edition: robot.name,
      editionSlug: robot.slug,
      amountLabel: resolvePriceState(
        {
          type: offer.price_type,
          amount: offer.price,
          amount_min: offer.price_min,
          amount_max: offer.price_max,
          currency: offer.currency,
          billing_period: offer.billing_period,
        },
        "long",
      ).label,
      priceTypeLabel: priceTypeLabel(offer.price_type),
      seller: offer.provider_name ?? offer.provider ?? null,
      observed: formatDate(offer.evidence?.observed_at),
    }));
}

function list(items: string[]): string {
  return items.join(", ");
}

/** "<Line> is sold in <n> published editions: <names>." */
function editionsSentence(name: string, robots: RobotDetail[]): string {
  const n = robots.length;
  return `${name} is sold in ${n} published edition${n === 1 ? "" : "s"}: ${list(robots.map((r) => r.name))}.`;
}

function priceSentences(robots: RobotDetail[]): string[] {
  const lowest = lowestPricesByCurrency(robots);
  const out: string[] = [];
  if (lowest.length === 0) {
    out.push("No edition has a published price.");
  } else {
    for (const p of lowest) {
      out.push(
        `Lowest published price in ${p.currency}: ${p.amountLabel} (${p.edition}, ${p.priceTypeLabel}, ` +
          `seller: ${p.seller ?? "not recorded"}, observed ${p.observed ?? "date not recorded"}).`,
      );
    }
    out.push("Prices in different currencies are not converted or compared.");
  }
  // Editions with no published price of their own: say what is known, never a number.
  const hasPublished = (r: RobotDetail) => (r.pricing_offers ?? []).some((o) => publishedFloor(o) != null);
  const quoteOnly = robots.filter(
    (r) => !hasPublished(r) && (r.pricing_offers ?? []).some((o) => o.price_type === "QUOTE_ONLY"),
  );
  const none = robots.filter(
    (r) => !hasPublished(r) && !(r.pricing_offers ?? []).some((o) => o.price_type === "QUOTE_ONLY"),
  );
  if (quoteOnly.length > 0) out.push(`${list(quoteOnly.map((r) => r.name))}: price on request.`);
  if (none.length > 0) out.push(`${list(none.map((r) => r.name))}: no published price.`);
  return out;
}

function heightSentence(robots: RobotDetail[]): string {
  const heights = robots.map((r) => r.specs?.height_cm ?? null);
  const known = heights.filter((h): h is number => h != null);
  if (known.length === 0) {
    return robots.length === 1
      ? "Standing height: not published."
      : "Standing height: not published for any edition.";
  }
  if (robots.length === 1) return `Standing height: ${known[0]} cm.`;
  const allKnown = known.length === robots.length;
  if (allKnown && new Set(known).size === 1) {
    return `Standing height: ${known[0]} cm (all editions).`;
  }
  const parts = robots.map((r, i) => {
    const h = heights[i];
    return h == null ? `${r.name} not published` : `${r.name} ${h} cm`;
  });
  return `Standing height: ${parts.join("; ")}.`;
}

export interface LineAnswer {
  /** Paragraphs in display order: editions, prices, height. */
  paragraphs: string[];
  /** The same answer as one string (metadata, tests, parity checks). */
  text: string;
}

export function buildLineAnswer(name: string, robots: RobotDetail[]): LineAnswer {
  if (robots.length === 0) {
    const text = `${name} has no published editions.`;
    return { paragraphs: [text], text };
  }
  const paragraphs = [
    editionsSentence(name, robots),
    priceSentences(robots).join(" "),
    heightSentence(robots),
  ];
  return { paragraphs, text: paragraphs.join(" ") };
}
