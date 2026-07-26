// AGENT-01 (docs/10) — JSON-LD projection of the canonical governed robot read.
//
// Pure builder: `RobotDetail` (the SAME governed read the page renders) -> a
// schema.org `Product` + `Organization` graph. It NEVER invents facts:
//   - AGENT-01.2 semantic parity: mapped 1:1 from the governed read.
//   - AGENT-01.3 explicit uncertainty: a null/undefined spec is OMITTED (never
//     0/false/"" and never an UNKNOWN `PropertyValue`).
//   - AGENT-01.4: no fabricated provenance/freshness fields (Product has no
//     honest slot without Offers, which are a later slice) — freshness rides the
//     sitemap `lastmod`.
//   - MEDIA-01: `image` uses only the read's display-eligible images (the read
//     returns nothing else); omitted entirely when there are none.
// The is_published boundary (AGENT-01.7) is enforced upstream at the fetch layer
// (the public read returns only published robots); this builder just maps.
import { absoluteUrl } from "@/lib/site";
import type { RobotDetail } from "@/lib/types";

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
    manufacturer: { "@id": mfrUrl },
    additionalProperty: additionalProperty(robot),
  };

  const description = robot.summary ?? robot.description ?? undefined;
  if (isAssertableFact(description)) product.description = description;

  // MEDIA-01: only display-eligible images reach the read; omit when none.
  const images = (robot.images ?? []).map((i) => absoluteUrl(i.image_url));
  if (images.length > 0) product.image = images;

  if (robot.announced_year) product.productionDate = String(robot.announced_year);

  return {
    "@context": "https://schema.org",
    "@graph": [product, organization],
  };
}
