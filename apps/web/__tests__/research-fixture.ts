import type { ResearchOffer, ResearchProjection } from "../lib/research";

const PUBLISHED_PRICE = (amount: number) => ({
  kind: "PUBLISHED" as const,
  price_type: "PUBLIC",
  amount,
  price_min: null,
  price_max: null,
  currency: "EUR",
  billing_period: "ONE_TIME",
  price_basis: "incl VAT",
});
const NOT_PUBLISHED = {
  kind: "NOT_PUBLISHED" as const,
  price_type: null,
  amount: null,
  price_min: null,
  price_max: null,
  currency: null,
  billing_period: null,
  price_basis: null,
};

function offer(overrides: Partial<ResearchOffer>): ResearchOffer {
  return {
    robot_slug: "bot-a",
    robot_name: "Bot A",
    manufacturer_slug: "maker-a",
    manufacturer_name: "Maker A",
    provider_slug: "shop-de",
    provider_type: "DISTRIBUTOR",
    region_code: "DE",
    transaction_type: "PURCHASE",
    availability_status: "AVAILABLE",
    evidence_date: "2026-09-26",
    confidence: "MEDIUM",
    human_verified: false,
    source_urls: ["https://shop.example/bot-a"],
    prices: [PUBLISHED_PRICE(9930)],
    ...overrides,
  };
}

export function projection(overrides: Partial<ResearchProjection> = {}): ResearchProjection {
  return {
    region: { slug: "europe", code: "EUROPE", name: "Europe" },
    snapshot_date: "2026-10-04",
    freshness_days: 90,
    latest_evidence_date: "2026-09-26",
    direct_answer:
      "As of 2026-10-04, HumanoidOnline lists 3 published humanoid robots with a confirmed offer in Europe. 2 can be purchased: 1 available and 1 on request.",
    key_figures: {
      published_population: 5,
      robots_with_confirmed_offer: 3,
      manufacturers_with_confirmed_offer: 3,
      robots_without_confirmed_offer: 2,
      purchase_robots: 2,
      purchase_by_best_status: [
        { status: "AVAILABLE", robots: 1 },
        { status: "LIMITED", robots: 0 },
        { status: "PREORDER", robots: 0 },
        { status: "WAITLIST", robots: 0 },
        { status: "ON_REQUEST", robots: 1 },
      ],
      robots_by_other_transaction: [{ transaction_type: "RENTAL", robots: 1 }],
      purchase_robots_with_published_price: 1,
      purchase_robots_price_on_request: 0,
      purchase_robots_price_not_published: 1,
    },
    offers: [
      offer({}),
      offer({
        robot_slug: "bot-b",
        robot_name: "Bot B",
        manufacturer_slug: "maker-b",
        manufacturer_name: "Maker B",
        provider_slug: "shop-eu",
        region_code: "EU",
        availability_status: "ON_REQUEST",
        prices: [NOT_PUBLISHED],
      }),
      offer({
        robot_slug: "bot-c",
        robot_name: "Bot C",
        manufacturer_slug: "maker-c",
        manufacturer_name: "Maker C",
        provider_slug: "rental-bg",
        region_code: "BG",
        transaction_type: "RENTAL",
        prices: [
          { ...PUBLISHED_PRICE(6500), billing_period: "WEEKLY", price_basis: "net of VAT" },
          {
            kind: "ESTIMATE",
            price_type: "MANUFACTURER_ESTIMATE",
            amount: 19999,
            price_min: null,
            price_max: null,
            currency: "EUR",
            billing_period: "ONE_TIME",
            price_basis: null,
          },
        ],
        confidence: "HIGH",
        human_verified: true,
      }),
    ],
    no_confirmed_offer: [
      {
        reason: "GLOBAL_ONLY",
        label: "Global offer only; no region-specific offer",
        robots: [{ slug: "bot-g", name: "Bot G", manufacturer_slug: "maker-g" }],
      },
      {
        reason: "NO_OFFERS",
        label: "No offer on file",
        robots: [{ slug: "bot-z", name: "Bot Z", manufacturer_slug: "maker-z" }],
      },
    ],
    methodology: {
      population: "Published humanoid robots in the HumanoidOnline catalogue.",
      region_membership: "Europe = the EUROPE region and every region beneath it.",
      qualifying_offer: "A region-specific availability offer that is current and evidenced.",
      unknown_treatment: "Unknown values stay unknown.",
      confidence: "Confidence is shown per offer and is not upgraded by publication.",
      calculation: "Deterministic and reproducible from the declared snapshot.",
    },
    faq: [
      { question: "Can I buy a humanoid robot in Europe?", answer: "As of 2026-10-04, 2 robots have a confirmed purchase offer on file." },
      { question: "How current is this data?", answer: "The snapshot date is 2026-10-04." },
    ],
    member_region_codes: ["EU", "EUROPE"],
    published: false,
    ...overrides,
  };
}
