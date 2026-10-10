// Buyer context (UX-03) — Region and Offer market as two separate questions.
//
// The catalogue filter (FilterPanel) and the compare view's optional Buyer
// context share these lists and help texts, so the two surfaces cannot describe
// the same control differently.
//
// NO GEOGRAPHY IS DERIVED HERE. Whether a region code is "in scope" is decided
// by the API's canonical resolvers (apps/api/app/services/regions.py), exposed
// as code lists by GET /api/regions/{code}/scope. This module only tests
// membership in those lists, plus the one rule the resolvers leave to the
// caller: an offer with no region recorded is in scope everywhere.
import type { AvailabilityOffer, PricingOffer, RobotDetail } from "./types";

export const REGIONS = ["US", "EU", "CN", "DE", "UK", "NO", "CA"];
// Offer market is NOT a second region filter. `region` asks where a robot is
// offered as the record states it; this asks which market's storefronts to
// search, and an economic zone admits its member countries' suppliers — an EU
// buyer should find what a German distributor lists. Only zones with member
// regions on record appear: for a plain country the two questions collapse into
// one, and a second control would imply a distinction that isn't there.
// Unset by default — no listing is hidden until the buyer narrows.
export const OFFER_MARKETS = ["EU"];

// UX-02D - wording derived from the real predicates (apps/api/app/services/robot_filters.py,
// regions.py). `region` = a CURRENT, NEW, commercially-accessible AVAILABILITY offer whose
// region is the chosen region, an ancestor of it, GLOBAL, or unspecified (NULL). `offered_in`
// = a CURRENT pricing OR availability record (any status) whose region is the market, an
// ancestor, a descendant (member country), GLOBAL, or unspecified. Neither asserts delivery.
export const REGION_HELP =
  "Shows robots with a current, accessible availability offer that applies to this region: " +
  "an offer for the region itself, for a wider area that includes it (for example the EU for " +
  "Germany), a worldwide offer, or an offer with no region recorded. An offer being recorded " +
  "for a region is not proof that the robot can be bought there, and it does not establish " +
  "shipping, customs or delivery eligibility. Missing regional information is unknown, not " +
  "unavailable.";
export const MARKET_HELP =
  "Shows robots with a recorded price or availability entry tied to this market, including " +
  "entries for member countries of an economic zone (for example a German supplier for the EU), " +
  "worldwide entries and entries with no region recorded, whatever the entry's status. It says " +
  "only that such an entry exists: not that the robot can be ordered, shipped or cleared " +
  "through customs there. Missing market information is unknown, not unavailable.";

/**
 * The compare view's Buyer context. `applicable` / `marketCodes` are the scope
 * lists the API returned for the chosen codes; null means that question is not
 * being asked (control unset) and nothing is annotated for it.
 */
export interface BuyerContext {
  region: string | null;
  market: string | null;
  applicable: string[] | null;
  marketCodes: string[] | null;
}

export const NO_BUYER_CONTEXT: BuyerContext = {
  region: null,
  market: null,
  applicable: null,
  marketCodes: null,
};

/** A URL value is accepted only if it is one of the offered codes; else unset. */
export function parseContextCode(
  value: string | null | undefined,
  allowed: readonly string[],
): string | null {
  if (!value) return null;
  const v = value.trim().toUpperCase();
  return allowed.includes(v) ? v : null;
}

/**
 * Is a recorded offer in scope? `scope` is a code list from the API. An offer
 * with no region recorded is in scope everywhere (the filters' NULL rule).
 */
export function inScope(offerRegion: string | null | undefined, scope: string[]): boolean {
  return offerRegion == null || scope.includes(offerRegion);
}

type Offer = Pick<PricingOffer | AvailabilityOffer, "region">;

/** Region codes of the given offers that fall in `scope`, de-duplicated, in order. */
export function scopedRegions(offers: Offer[], scope: string[]): string[] {
  const out: string[] = [];
  for (const o of offers) {
    if (o.region && scope.includes(o.region) && !out.includes(o.region)) out.push(o.region);
  }
  return out;
}

/**
 * The availability rows the `region` question is asked of: NEW condition and a
 * commercially accessible status, as the catalogue's region filter defines it
 * (see REGION_HELP). A used or refurbished listing never makes a robot "apply".
 */
export function eligibleForRegion(a: AvailabilityOffer): boolean {
  if (a.condition && a.condition !== "NEW") return false;
  return a.availability_status !== "NOT_AVAILABLE" && a.availability_status !== "DISCONTINUED";
}

/**
 * How many compared robots each question matches, by the same predicates the
 * catalogue filters describe: `region` counts an accessible availability offer
 * in the applicable scope; the market counts any price or availability entry
 * in the market scope. A count is a statement about records, never delivery.
 */
export function contextCounts(
  robots: RobotDetail[],
  ctx: BuyerContext,
): { region: number | null; market: number | null } {
  const region = ctx.applicable
    ? robots.filter((r) =>
        r.availability_offers.some((a) => eligibleForRegion(a) && inScope(a.region, ctx.applicable!)),
      ).length
    : null;
  const market = ctx.marketCodes
    ? robots.filter((r) =>
        [...r.pricing_offers, ...r.availability_offers].some((o) =>
          inScope(o.region, ctx.marketCodes!),
        ),
      ).length
    : null;
  return { region, market };
}
