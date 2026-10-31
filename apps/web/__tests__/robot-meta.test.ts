import { describe, expect, it } from "vitest";

import { hasPublishedPrice, robotTitle } from "@/lib/robot-meta";
import type { PricingOffer } from "@/lib/types";

const offer = (o: Partial<PricingOffer>): PricingOffer =>
  ({ transaction_type: "PURCHASE", price_type: "PUBLIC", currency: "USD", billing_period: "ONE_TIME", ...o }) as PricingOffer;
const robot = (name: string, maker: string, offers: PricingOffer[] = []) => ({
  name,
  manufacturer: { slug: "m", name: maker },
  pricing_offers: offers,
});

describe("hasPublishedPrice", () => {
  it.each([
    [{ price_type: "PUBLIC", price: 16000 }, true],
    [{ price_type: "FROM", price: 5900 }, true],
    [{ price_type: "RANGE", price_min: 1, price_max: 2 }, true],
    [{ price_type: "QUOTE_ONLY" }, false],
    [{ price_type: "ESTIMATED", price: 100 }, false],
    [{ price_type: "MANUFACTURER_ESTIMATE", price: 100 }, false],
    [{ price_type: "PUBLIC", price: null }, false],
  ])("%o -> %s", (o, want) => expect(hasPublishedPrice([offer(o)])).toBe(want));

  it("is false with no offers (UNKNOWN stays unknown)", () => expect(hasPublishedPrice([])).toBe(false));
});

describe("robotTitle", () => {
  it("leads with the maker and names price only when one is published", () => {
    expect(robotTitle(robot("G1 Basic", "Unitree Robotics", [offer({ price: 16000 })]))).toBe(
      "Unitree Robotics G1 Basic: Price, Specs & Availability",
    );
    expect(robotTitle(robot("Digit", "Agility Robotics", [offer({ price_type: "QUOTE_ONLY" })]))).toBe(
      "Agility Robotics Digit: Specs, Status & Evidence",
    );
  });

  it("does not repeat a maker already in the model name", () => {
    expect(robotTitle(robot("Unitree H1", "Unitree Robotics"))).toBe("Unitree H1: Specs, Status & Evidence");
  });
});
