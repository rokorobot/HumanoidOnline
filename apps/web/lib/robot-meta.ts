// CID-04 — robot page <title>. Leads with the maker and model, the way people ask
// ("Unitree Robotics G1 Basic", not "G1 Basic by …"), and names "price" only when the
// record holds a published number. Quote-only and estimated prices do not qualify, so
// the title never promises a price the page cannot show (docs/23 §10, CIT-K).
import type { PricingOffer, RobotDetail } from "@/lib/types";

const PUBLISHED = new Set(["PUBLIC", "FROM", "RANGE"]);

export function hasPublishedPrice(offers: PricingOffer[]): boolean {
  return offers.some(
    (o) => PUBLISHED.has(o.price_type) && (o.price != null || o.price_min != null || o.price_max != null),
  );
}

export function robotTitle(robot: Pick<RobotDetail, "name" | "manufacturer" | "pricing_offers">): string {
  const maker = robot.manufacturer.name;
  const firstWord = maker.split(/\s+/)[0].toLowerCase();
  const name = robot.name.toLowerCase().startsWith(firstWord) ? robot.name : `${maker} ${robot.name}`;
  return hasPublishedPrice(robot.pricing_offers ?? [])
    ? `${name}: Price, Specs & Availability`
    : `${name}: Specs, Status & Evidence`;
}
