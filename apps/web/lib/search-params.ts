// Helpers to normalize Next's searchParams into a predictable shape and to
// forward them to the API. Filters are URL-addressable: the URL is the single
// source of truth for catalogue state.
import type { RobotListParams } from "./api-client";

export type RawSearchParams = Record<string, string | string[] | undefined>;

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
export function toRobotListParams(sp: RawSearchParams): RobotListParams {
  return {
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
    price_max: asNumber(sp.price_max),
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
