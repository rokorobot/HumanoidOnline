// Variant-aware read model for the primary Physical / Intelligence / Developer
// panels. A robot-level canonical field that is NULL is UNKNOWN only when NO
// accepted evidence exists at robot OR variant scope. When variant-scoped
// extended specs speak to the property, the panel shows what they say.
// Presentation only: nothing here writes or fabricates a robot-wide value.
import type { ExtendedSpec, Variant } from "./types";

export type VariantFactKind = "uniform" | "varies" | "partial";

export interface VariantFactRow {
  variant: string;
  // null = this configuration has no evidence for the property (UNKNOWN).
  value: string | null;
}

export interface VariantFact {
  kind: VariantFactKind;
  // uniform: the one value every configuration establishes.
  value?: string;
  rows: VariantFactRow[];
  source?: { label: string | null; url: string | null; observed_at: string | null };
}

type Extract = (specs: ExtendedSpec[]) => string | null;

const text = (s: ExtendedSpec): string | null =>
  typeof s.value === "string" && s.value.trim() ? s.value.trim() : null;

const tokens = (specs: ExtendedSpec[]): string[] =>
  specs
    .filter((s) => s.category === "SOFTWARE")
    .flatMap((s) => (text(s) ?? "").split(/,\s*/))
    .map((t) => t.trim())
    .filter(Boolean);

const manipulation = (specs: ExtendedSpec[]): string | null => {
  const v = specs.filter((s) => s.category === "MANIPULATION").map(text).filter(Boolean);
  return v.length ? (v as string[]).join("; ") : null;
};

const matching = (re: RegExp, join: string): Extract => (specs) => {
  const t = tokens(specs).filter((x) => re.test(x));
  return t.length ? t.join(join) : null;
};

export type VariantProperty =
  | "has_manipulation"
  | "hand_dof"
  | "has_teleoperation"
  | "has_sdk"
  | "ros_support";

const EXTRACTORS: Record<VariantProperty, Extract> = {
  has_manipulation: manipulation,
  // Hand configuration as the manufacturer words it; no numeric hand_dof is derived.
  hand_dof: manipulation,
  // Teleoperation: the manufacturer LISTS it; absence from a list is not "no".
  has_teleoperation: (specs) =>
    tokens(specs).some((x) => /teleoperat/i.test(x)) ? "Listed by manufacturer" : null,
  has_sdk: matching(/\bSDK\b/i, " + "),
  ros_support: matching(/\bROS\b/i, " + "),
};

function orderedVariants(variants: Variant[], specs: ExtendedSpec[]) {
  const seen = new Map<string, string>();
  for (const v of variants) seen.set(v.slug, v.name);
  for (const s of specs) {
    if (s.variant_slug && !seen.has(s.variant_slug)) seen.set(s.variant_slug, s.variant ?? s.variant_slug);
  }
  const rank = (slug: string) => (/^(standard|base)$/.test(slug) ? 0 : 1);
  return [...seen.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
}

const evidenceFor = (specs: ExtendedSpec[], slug: string) =>
  specs.filter((s) => s.variant_slug === slug);

function sourceOf(specs: ExtendedSpec[]) {
  const s = specs.find((x) => x.variant_slug && (x.source_label || x.source_url));
  return s
    ? { label: s.source_label ?? null, url: s.source_url ?? null, observed_at: s.observed_at ?? null }
    : undefined;
}

// Returns null when no variant-scoped evidence speaks to the property: the
// caller then renders the ordinary UNKNOWN.
export function variantFact(
  property: VariantProperty,
  specs: ExtendedSpec[],
  variants: Variant[],
): VariantFact | null {
  const extract = EXTRACTORS[property];
  const rows: VariantFactRow[] = orderedVariants(variants, specs).map(([slug, name]) => ({
    variant: name,
    value: extract(evidenceFor(specs, slug)),
  }));
  const known = rows.filter((r) => r.value !== null);
  if (known.length === 0) return null;
  const distinct = new Set(known.map((r) => r.value));
  const kind: VariantFactKind =
    known.length < rows.length ? "partial" : distinct.size === 1 ? "uniform" : "varies";
  return {
    kind,
    value: kind === "uniform" ? known[0].value! : undefined,
    rows,
    source: sourceOf(specs),
  };
}

export interface InterfaceFacts {
  common: string[]; // established for every configuration
  extras: { variant: string; items: string[] }[];
  source?: VariantFact["source"];
}

// Connectivity / developer interfaces that are not SDK / ROS / teleoperation
// (those have their own rows). Common ones are shown once.
export function interfaceFacts(specs: ExtendedSpec[], variants: Variant[]): InterfaceFacts | null {
  const vs = orderedVariants(variants, specs);
  const per = vs.map(([slug, name]) => ({
    name,
    items: [
      ...new Set(
        tokens(evidenceFor(specs, slug)).filter((t) => !/\bSDK\b|\bROS\b|teleoperat/i.test(t)),
      ),
    ],
  }));
  if (per.every((p) => p.items.length === 0)) return null;
  const common = per[0].items.filter((i) => per.every((p) => p.items.includes(i)));
  const extras = per
    .map((p) => ({ variant: p.name, items: p.items.filter((i) => !common.includes(i)) }))
    .filter((e) => e.items.length > 0);
  return { common, extras, source: sourceOf(specs) };
}
