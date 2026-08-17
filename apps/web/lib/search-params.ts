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

// Map raw URL params -> the typed API list params (the API is the source of facts).
//
// `price_currency` is DERIVED from `price_max`, never read from the URL: the API
// rejects either half of the pair alone, so deriving it here makes an invalid
// request unrepresentable regardless of how the URL was formed — a hand-typed
// `?price_currency=USD`, a stale bookmark, or a no-JS form submission that
// carried only `price_max`.
export function toRobotListParams(sp: RawSearchParams): RobotListParams {
  const priceMax = asNumber(sp.price_max);
  return {
    price_max: priceMax,
    price_currency: priceMax != null ? PRICE_CURRENCY : undefined,
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
