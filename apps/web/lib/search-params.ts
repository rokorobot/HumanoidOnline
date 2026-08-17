// Helpers to normalize Next's searchParams into a predictable shape and to
// forward them to the API. Filters are URL-addressable: the URL is the single
// source of truth for catalogue state.
import type { RobotListParams } from "./api-client";

export type RawSearchParams = Record<string, string | string[] | undefined>;

// The catalogue price filter is denominated in USD, which the control states
// visibly ("Max purchase price (USD)"). The API requires `price_max` and
// `price_currency` as a pair and applies no default currency, so the
// denomination is sent explicitly rather than assumed server-side.
// A multi-currency selector is a later UI enhancement; this constant is the one
// place the current single currency is declared.
export const PRICE_CURRENCY = "USD";

export function asArray(v: string | string[] | undefined): string[] {
  if (v == null) return [];
  return Array.isArray(v) ? v : [v];
}

export function asString(v: string | string[] | undefined): string | undefined {
  if (v == null) return undefined;
  return Array.isArray(v) ? v[0] : v;
}

function asNumber(v: string | string[] | undefined): number | undefined {
  const s = asString(v);
  if (s == null || s === "") return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function asBool(v: string | string[] | undefined): boolean | undefined {
  const s = asString(v);
  if (s === "true") return true;
  if (s === "false") return false;
  return undefined;
}

// What the /robots route must do with the price params before rendering, so the
// address bar and the API request can never disagree about the denomination.
export type PriceUrlAction =
  | { action: "ok" }
  | { action: "redirect"; params: RawSearchParams }
  | { action: "reject"; currency: string };

// Canonical URL state for the price filter: an active ceiling always carries an
// explicit denomination, and a denomination never appears without a ceiling.
//
// This exists because the URL is the single source of truth for catalogue state.
// Deriving the currency silently would let `?price_max=30000&price_currency=EUR`
// render EUR in the address bar while the API was asked about USD — the page
// would then be showing one thing and claiming another.
//
//   price_max, no currency   -> redirect, adding the explicit denomination
//                               (this is the no-JS GET form's output)
//   currency, no price_max   -> redirect, dropping the orphan: the API rejects a
//                               lone currency, and it constrains nothing
//   price_max + USD          -> canonical, render as-is
//   price_max + other        -> reject. This UI is USD-only and says so on the
//                               control; it cannot honour another currency, and
//                               it must not quietly reinterpret it as USD nor
//                               drop the ceiling and widen the result set.
//
// A non-numeric `price_max` is treated as no ceiling at all, matching
// `toRobotListParams`, so junk never produces a currency or a redirect loop.
export function canonicalizePriceParams(sp: RawSearchParams): PriceUrlAction {
  const priceMax = asNumber(sp.price_max);
  const raw = asString(sp.price_currency)?.trim();
  const currency = raw ? raw.toUpperCase() : undefined;

  if (priceMax == null) {
    if (!raw) return { action: "ok" };
    const next = { ...sp };
    delete next.price_currency;
    return { action: "redirect", params: next };
  }
  if (!currency) {
    return { action: "redirect", params: { ...sp, price_currency: PRICE_CURRENCY } };
  }
  if (currency !== PRICE_CURRENCY) {
    return { action: "reject", currency };
  }
  if (raw !== PRICE_CURRENCY) {
    // Same currency, non-canonical spelling ("usd", padded) — normalise once.
    return { action: "redirect", params: { ...sp, price_currency: PRICE_CURRENCY } };
  }
  return { action: "ok" };
}

// Map raw URL params -> the typed API list params (the API is the source of facts).
//
// The price pair is kept inseparable here as the last line of defence: the API
// rejects either half alone, so a lone `price_currency` is never forwarded and a
// ceiling always carries a denomination. The URL's own currency is honoured when
// present rather than overwritten — after `canonicalizePriceParams` the route
// only renders a canonical USD pair, and silently substituting a different
// explicit value is exactly the disagreement this module exists to prevent.
// `PRICE_CURRENCY` fills in only when the URL states no denomination at all.
export function toRobotListParams(sp: RawSearchParams): RobotListParams {
  const priceMax = asNumber(sp.price_max);
  const urlCurrency = asString(sp.price_currency)?.trim().toUpperCase();
  return {
    price_max: priceMax,
    price_currency:
      priceMax != null ? (urlCurrency || PRICE_CURRENCY) : undefined,
    q: asString(sp.q),
    manufacturer: asString(sp.manufacturer),
    commercial_status: asArray(sp.commercial_status),
    transaction_type: asArray(sp.transaction_type),
    availability_status: asArray(sp.availability_status),
    region: asString(sp.region),
    use_case: asString(sp.use_case),
    payload_min: asNumber(sp.payload_min),
    height_min: asNumber(sp.height_min),
    height_max: asNumber(sp.height_max),
    mobility: asString(sp.mobility),
    autonomy_min: asString(sp.autonomy_min),
    has_sdk: asBool(sp.has_sdk),
    ros_support: asBool(sp.ros_support),
    developer_edition: asBool(sp.developer_edition),
    has_manipulation: asBool(sp.has_manipulation),
    sort: asString(sp.sort) ?? "name",
  };
}

// Serialize a raw params object into a query string (stable, drops empties).
export function toQueryString(sp: RawSearchParams): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    for (const item of asArray(v)) {
      if (item !== "") usp.append(k, item);
    }
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}
