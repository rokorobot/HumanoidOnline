// AGENT-01 (docs/10) — JSON-LD projection of the canonical governed robot read.
//
// Pure builder: `RobotDetail` (the SAME governed read the page renders) -> a
// schema.org `Product` + `Organization` graph. It NEVER invents facts:
//   - AGENT-01.2 semantic parity: mapped 1:1 from the governed read.
//   - AGENT-01.3 explicit uncertainty: a null/undefined spec is OMITTED (never
//     0/false/"" and never an UNKNOWN `PropertyValue`).
//   - AGENT-01.4: no fabricated provenance/freshness fields — freshness rides the
//     sitemap `lastmod`.
//   - SEO-03 (owner decision 2026-11-02): `offers` carries ONLY published,
//     evidence-linked one-time prices (see `buildOffers`). No other price state
//     ever becomes an Offer.
//   - MEDIA-01: `image` uses only the read's display-eligible images (the read
//     returns nothing else); omitted entirely when there are none.
// The is_published boundary (AGENT-01.7) is enforced upstream at the fetch layer
// (the public read returns only published robots); this builder just maps.
import { absoluteUrl } from "@/lib/site";
import type {
  ManufacturerDetail,
  PricingOffer,
  ProductLineDetail,
  RobotDetail,
  RobotListItem,
} from "@/lib/types";

interface PropertyValue {
  "@type": "PropertyValue";
  name: string;
  value: string | number;
  unitText?: string;
}

// Curated, canonical spec subset. Only emitted when the value is present.
const NUMERIC_SPECS: Array<{
  key: "height_cm" | "weight_kg" | "payload_kg" | "walk_speed_ms" | "runtime_minutes" | "degrees_of_freedom";
  name: string;
  unitText?: string;
}> = [
  { key: "height_cm", name: "Height", unitText: "cm" },
  { key: "weight_kg", name: "Weight", unitText: "kg" },
  { key: "payload_kg", name: "Payload", unitText: "kg" },
  { key: "walk_speed_ms", name: "Walk speed", unitText: "m/s" },
  { key: "runtime_minutes", name: "Runtime", unitText: "minutes" },
  { key: "degrees_of_freedom", name: "Degrees of freedom" },
];

const TEXT_SPECS: Array<{ key: "mobility" | "autonomy"; name: string }> = [
  { key: "mobility", name: "Mobility" },
  { key: "autonomy", name: "Autonomy" },
];

/**
 * WS8.3 / R14 — is this value a fact we may assert? (AGENT-01.3)
 *
 * The previous guard was `!== null && !== undefined`, which let an empty or
 * whitespace-only string through as a `PropertyValue`. A machine consumer
 * cannot tell an empty assertion from a meaningful one, so an empty string
 * becomes a fabricated fact — the precise coercion AGENT-01.3 forbids, arriving
 * from the other direction.
 *
 * `0` and `false` are deliberately KEPT: they are real canonical values, and
 * dropping them would be the mirror-image error of coercing UNKNOWN to `0`.
 * UNKNOWN is `null`/absent and is omitted entirely — never rendered as `0`,
 * `false`, `""`, "unknown" or "n/a".
 */
function isAssertableFact(value: unknown): value is string | number | boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return true;
}

function additionalProperty(robot: RobotDetail): PropertyValue[] {
  const props: PropertyValue[] = [];
  // Commercial maturity is a real canonical fact (kept distinct from
  // obtainability) — but only asserted when it actually carries a value.
  if (isAssertableFact(robot.commercial_status)) {
    props.push({
      "@type": "PropertyValue",
      name: "Commercial status",
      value: robot.commercial_status,
    });
  }
  for (const { key, name, unitText } of NUMERIC_SPECS) {
    const v = robot.specs[key];
    if (isAssertableFact(v)) {
      props.push({ "@type": "PropertyValue", name, value: v, ...(unitText ? { unitText } : {}) });
    }
  }
  for (const { key, name } of TEXT_SPECS) {
    const v = robot.specs[key];
    if (isAssertableFact(v)) {
      props.push({ "@type": "PropertyValue", name, value: v });
    }
  }
  return props;
}

// One-time acquisitions only: a recurring rental/lease price is not a sale price.
const ONE_TIME_TRANSACTIONS = new Set(["PURCHASE", "DEVELOPER"]);

const CONDITION: Record<string, string> = {
  NEW: "https://schema.org/NewCondition",
  USED: "https://schema.org/UsedCondition",
  REFURBISHED: "https://schema.org/RefurbishedCondition",
};

const hasNumber = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * SEO-03 — schema.org `Offer`s from the robot's pricing offers. An offer qualifies
 * only when ALL hold: a published number (PUBLIC, FROM or RANGE — never QUOTE_ONLY,
 * ESTIMATED or MANUFACTURER_ESTIMATE), linked evidence (AGENTS rule 7), a currency,
 * and a one-time purchase. `price` is asserted only for PUBLIC (the price) and FROM
 * (the stated starting price, with `minPrice`); a RANGE states only its bounds.
 * Availability is omitted: it is a separate, separately-evidenced fact.
 */
export function buildOffers(offers: PricingOffer[], url: string): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  for (const o of offers) {
    if (!o.evidence || !isAssertableFact(o.currency)) continue;
    if (!ONE_TIME_TRANSACTIONS.has(o.transaction_type) || o.billing_period !== "ONE_TIME") continue;

    const offer: Record<string, unknown> = { "@type": "Offer", url, priceCurrency: o.currency };
    if (o.price_type === "PUBLIC" && hasNumber(o.price)) {
      offer.price = o.price;
    } else if (o.price_type === "FROM" && hasNumber(o.price ?? o.price_min)) {
      const from = (o.price ?? o.price_min) as number;
      offer.price = from;
      offer.priceSpecification = { "@type": "PriceSpecification", minPrice: from, priceCurrency: o.currency };
    } else if (o.price_type === "RANGE" && hasNumber(o.price_min) && hasNumber(o.price_max)) {
      offer.priceSpecification = {
        "@type": "PriceSpecification",
        minPrice: o.price_min,
        maxPrice: o.price_max,
        priceCurrency: o.currency,
      };
    } else {
      continue;
    }
    if (isAssertableFact(o.variant)) offer.name = o.variant;
    if (o.condition && CONDITION[o.condition]) offer.itemCondition = CONDITION[o.condition];
    if (isAssertableFact(o.provider_name)) offer.seller = { "@type": "Organization", name: o.provider_name };
    out.push(offer);
  }
  return out;
}

/** schema.org Product + Organization graph for a robot detail page. */
export function buildRobotJsonLd(robot: RobotDetail): Record<string, unknown> {
  const robotUrl = absoluteUrl(`/robots/${robot.slug}`);
  const mfrUrl = absoluteUrl(`/manufacturers/${robot.manufacturer.slug}`);

  const organization = {
    "@type": "Organization",
    "@id": mfrUrl,
    name: robot.manufacturer.name,
    url: mfrUrl,
  };

  const product: Record<string, unknown> = {
    "@type": "Product",
    "@id": robotUrl,
    url: robotUrl,
    name: robot.name,
    category: "Humanoid robot",
    // SEO-03: brand is the manufacturer, exactly as on the product-line ProductGroup.
    brand: { "@type": "Brand", name: robot.manufacturer.name },
    manufacturer: { "@id": mfrUrl },
    additionalProperty: additionalProperty(robot),
  };

  const description = robot.summary ?? robot.description ?? undefined;
  if (isAssertableFact(description)) product.description = description;

  // MEDIA-01: only display-eligible images reach the read; omit when none.
  const images = (robot.images ?? []).map((i) => absoluteUrl(i.image_url));
  if (images.length > 0) product.image = images;

  if (robot.announced_year) product.productionDate = String(robot.announced_year);

  const offers = buildOffers(robot.pricing_offers ?? [], robotUrl);
  if (offers.length > 0) product.offers = offers;

  return {
    "@context": "https://schema.org",
    "@graph": [product, organization],
  };
}

type Crumb = { name: string; path: string };

function breadcrumb(id: string, trail: Crumb[]): Record<string, unknown> {
  return {
    "@type": "BreadcrumbList",
    "@id": id,
    itemListElement: [{ name: "Home", path: "/" }, ...trail].map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: absoluteUrl(c.path),
    })),
  };
}

/**
 * SEO-02 / SEO-03 — CollectionPage + ItemList + BreadcrumbList for an index page.
 * Lists only the entries the page actually renders, by name and canonical URL; no
 * commercial facts are asserted here. `trail` is the breadcrumb below Home, ending
 * with this page.
 */
export function buildCollectionJsonLd(
  trail: Crumb[],
  items: Array<{ name: string; path: string }>,
): Record<string, unknown> {
  const self = trail[trail.length - 1];
  const url = absoluteUrl(self.path);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": url,
        url,
        name: self.name,
        breadcrumb: { "@id": `${url}#breadcrumb` },
        mainEntity: { "@id": `${url}#list` },
      },
      {
        "@type": "ItemList",
        "@id": `${url}#list`,
        numberOfItems: items.length,
        itemListElement: items.map((it, i) => ({
          "@type": "ListItem",
          position: i + 1,
          url: absoluteUrl(it.path),
          name: it.name,
        })),
      },
      breadcrumb(`${url}#breadcrumb`, trail),
    ],
  };
}

/** SEO-02 — the bare /robots catalogue. */
export function buildCatalogueJsonLd(items: RobotListItem[]): Record<string, unknown> {
  return buildCollectionJsonLd(
    [{ name: "Robot Catalogue", path: "/robots" }],
    items.map((r) => ({ name: r.name, path: `/robots/${r.slug}` })),
  );
}

/**
 * SEO-03 — schema.org `Organization` + BreadcrumbList for a manufacturer page. Same
 * `@id` as the Organization on its robot pages, so the graphs join. Only recorded
 * profile facts are asserted; absent ones are omitted (AGENT-01.3).
 */
export function buildManufacturerJsonLd(m: ManufacturerDetail): Record<string, unknown> {
  const path = `/manufacturers/${m.slug}`;
  const url = absoluteUrl(path);
  const org: Record<string, unknown> = { "@type": "Organization", "@id": url, url, name: m.name };
  if (isAssertableFact(m.legal_name)) org.legalName = m.legal_name;
  if (isAssertableFact(m.description)) org.description = m.description;
  if (isAssertableFact(m.website_url)) org.sameAs = [m.website_url];
  if (isAssertableFact(m.founded_year)) org.foundingDate = String(m.founded_year);
  return {
    "@context": "https://schema.org",
    "@graph": [
      org,
      breadcrumb(`${url}#breadcrumb`, [
        { name: "Manufacturers", path: "/manufacturers" },
        { name: m.name, path },
      ]),
    ],
  };
}

/**
 * DR-L1 — schema.org `ProductGroup` for a product-line page. Mapped 1:1 from the governed
 * line read: name, brand (the manufacturer) and one `hasVariant` Product per published
 * edition, by canonical URL and name. The group asserts NO offers and no specs: price,
 * availability and specs belong to the edition pages (AGENT-01.3, DR-L1 §4).
 */
export function buildProductLineJsonLd(line: ProductLineDetail): Record<string, unknown> {
  const url = absoluteUrl(`/lines/${line.slug}`);
  const mfrUrl = absoluteUrl(`/manufacturers/${line.manufacturer.slug}`);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "ProductGroup",
        "@id": url,
        url,
        name: line.name,
        category: "Humanoid robot",
        brand: { "@type": "Brand", name: line.manufacturer.name },
        manufacturer: { "@id": mfrUrl },
        productGroupID: line.slug,
        hasVariant: line.robots.map((r) => {
          const robotUrl = absoluteUrl(`/robots/${r.slug}`);
          return { "@type": "Product", "@id": robotUrl, url: robotUrl, name: r.name };
        }),
      },
      {
        "@type": "Organization",
        "@id": mfrUrl,
        name: line.manufacturer.name,
        url: mfrUrl,
      },
    ],
  };
}
