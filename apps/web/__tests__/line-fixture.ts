// DR-L1 test fixtures: minimal RobotDetail / ProductLineDetail objects.
import type { PricingOffer, ProductLineDetail, RobotDetail } from "../lib/types";

export function offer(o: Partial<PricingOffer> & Pick<PricingOffer, "price_type">): PricingOffer {
  return {
    transaction_type: "PURCHASE",
    currency: "USD",
    billing_period: "ONE_TIME",
    condition: "NEW",
    provider: "unitree-store",
    provider_name: "Unitree Store",
    evidence: { source_type: "MANUFACTURER_STORE", confidence: "HIGH", observed_at: "2026-10-18T00:00:00Z" },
    ...o,
  };
}

export function edition(
  slug: string,
  name: string,
  over: Partial<RobotDetail> & { height?: number | null } = {},
): RobotDetail {
  const { height, ...rest } = over;
  return {
    id: slug,
    slug,
    name,
    manufacturer: { slug: "unitree", name: "Unitree Robotics", country: "CN" },
    product_line: { slug: "unitree-g1", name: "Unitree G1" },
    commercial_status: "COMMERCIAL",
    status_history: [],
    specs: { height_cm: height === undefined ? null : height },
    spec_caveats: [],
    extended_specs: [],
    capabilities: [],
    variants: [],
    use_case_fits: [],
    pricing_offers: [],
    availability_offers: [],
    deployments: [],
    images: [],
    ...rest,
  } as RobotDetail;
}

export function line(robots: RobotDetail[], over: Partial<ProductLineDetail> = {}): ProductLineDetail {
  return {
    slug: "unitree-g1",
    name: "Unitree G1",
    manufacturer: { slug: "unitree", name: "Unitree Robotics", country: "CN" },
    source_url: "https://www.unitree.com/g1/",
    observed_at: "2026-10-31",
    robots,
    ...over,
  };
}
