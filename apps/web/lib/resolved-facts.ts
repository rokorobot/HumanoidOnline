// Presentation of the API's G4 `resolved_facts` (DR-G4). PRESENTATION ONLY.
//
// The semantic resolution (which states exist, which tokens project to which property, what a
// conflict is) happens once, in the API (`apps/api/app/services/fact_resolution.py`). This module
// never inspects specification text, never matches tokens and never decides a state: it only turns
// an already-resolved fact into words. A second resolver in the web layer would be a second truth.
import type { ResolvedFact, ResolvedVariantValue } from "./types";

export interface ResolvedLine {
  /** The configuration (variant) this line is about, or null for a product-wide line. */
  scope: string | null;
  /** Visible words, e.g. "Supported (Python SDK + C++ SDK)" or "UNKNOWN". */
  text: string;
  /** True when the configuration's value is unknown (rendered with the UNKNOWN treatment). */
  unknown: boolean;
}

export interface ResolvedDescription {
  /** One headline for the whole property, e.g. "Supported on Standard + Pro". */
  headline: string;
  lines: ResolvedLine[];
}

const joinNames = (vs: ResolvedVariantValue[]): string => vs.map((v) => v.name).join(" + ");

function tokens(v: ResolvedVariantValue): string {
  return v.evidence.map((e) => e.token).join(" + ");
}

function variantLine(v: ResolvedVariantValue): ResolvedLine {
  if (v.value === true) {
    const t = tokens(v);
    return { scope: v.name, text: t ? `Supported (${t})` : "Supported", unknown: false };
  }
  if (v.value === false) {
    return { scope: v.name, text: "Not supported", unknown: false };
  }
  // Unknown for this configuration. Any verbatim accepted fact stays visible beside it.
  const facts = v.source_facts.map((f) => `${f.label}: ${f.value}`).join("; ");
  return { scope: v.name, text: facts ? `UNKNOWN (${facts})` : "UNKNOWN", unknown: true };
}

export function describeResolved(fact: ResolvedFact): ResolvedDescription {
  const lines = fact.variants.map(variantLine);
  switch (fact.state) {
    case "PRODUCT_VALUE":
      return {
        headline: fact.value === true ? "Supported" : fact.value === false ? "Not supported" : "UNKNOWN",
        lines: [],
      };
    case "UNIFORM_VARIANTS":
      return {
        headline:
          fact.value === true
            ? `Supported on all documented configurations (${joinNames(fact.variants)})`
            : `Not supported on any documented configuration (${joinNames(fact.variants)})`,
        lines,
      };
    case "VARIES_BY_VARIANT":
      return { headline: "Varies by configuration", lines };
    case "PARTIAL_VARIANTS":
      return { headline: "Known on some configurations; others unknown", lines };
    case "CONFLICT":
      // An integrity state: never silently pick a side.
      return { headline: "Conflicting sources — not resolved", lines };
    case "UNKNOWN":
    default:
      return { headline: "UNKNOWN", lines: [] };
  }
}

/** True when the property has accepted knowledge that the plain core column does not show. */
export function hasScopedKnowledge(fact: ResolvedFact | undefined): fact is ResolvedFact {
  return !!fact && fact.state !== "UNKNOWN" && fact.state !== "PRODUCT_VALUE";
}

export function factsByProperty(facts: ResolvedFact[] | undefined): Record<string, ResolvedFact> {
  const out: Record<string, ResolvedFact> = {};
  for (const f of facts ?? []) out[f.property] = f;
  return out;
}
