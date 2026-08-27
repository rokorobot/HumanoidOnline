// AI Citation Layer v0.1 / CID-02 (docs/23) — a concise, server-rendered
// factual summary of an ALREADY-FETCHED robot record.
//
// This component creates no facts. It is a pure projection of the same
// governed `RobotDetail` the rest of the page renders: no database access, no
// second API call, no inference, no parsing facts back out of rendered text.
// Its only job is to make facts that are already on the page easier for a
// human — or a retrieval system — to extract and cite in one place.
//
// The invariants it must never break (docs/23 §24):
//   CITATION-01.3 / CIT-B  UNKNOWN stays UNKNOWN. A null spec is OMITTED from
//     this block entirely rather than rendered as 0/false/""/"unavailable".
//     `0` and `false` are REAL canonical values and are kept — dropping them
//     would be the mirror-image error of coercing UNKNOWN to 0.
//   CITATION-01.4 / CIT-C  Evidence is never claimed here. This block carries
//     specifications and identity only; the page's own evidence section owns
//     provenance, attached per-claim. A record with one VERIFIED price does
//     not make its height "verified", so this block asserts nothing about it.
//   CITATION-01.5 / CIT-J  No timestamp is rendered here at all. `RobotDetail`
//     exposes no record-level `updated_at`, and evidence dates belong to their
//     specific claims, not to the record — see docs/23 §9 and the audit note in
//     the page component.
//   CIT-K  Commercial status is shown as maturity ONLY, never merged with
//     availability, transaction mode or price state.
import { specValue } from "@/lib/format";
import type { RobotDetail } from "@/lib/types";

interface Fact {
  label: string;
  value: string;
}

/**
 * Is this value one we may state as a fact?
 *
 * Mirrors `isAssertableFact` in lib/jsonld.ts deliberately — the visible block
 * and the machine projection must apply the SAME rule, or CIT-I (parity) is
 * decided by an accident of which file was edited last. null/undefined and
 * whitespace-only strings are not facts; `0` and `false` are.
 */
export function isCitableValue(
  value: number | string | boolean | null | undefined,
): value is number | string | boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return true;
}

/**
 * The ordered canonical-fact set, built from the governed read.
 *
 * Exported for direct unit testing: the projection rule is the thing worth
 * proving, and asserting it through rendered markup would test the markup.
 * Units are the catalogue's canonical units (cm/kg/min/m/s) — never converted
 * here; `lib/units.ts` presentation toggles are a separate, page-level concern.
 */
export function citationFacts(robot: RobotDetail): Fact[] {
  const s = robot.specs;
  const facts: Fact[] = [
    { label: "Robot", value: robot.name },
    { label: "Manufacturer", value: robot.manufacturer.name },
  ];

  // Maturity only. NOT obtainability, NOT "for sale" (CIT-K).
  if (isCitableValue(robot.commercial_status)) {
    facts.push({ label: "Commercial status", value: robot.commercial_status });
  }

  const specFields: Array<{
    label: string;
    value: number | string | boolean | null | undefined;
    unit?: string;
  }> = [
    { label: "Height", value: s.height_cm, unit: "cm" },
    { label: "Weight", value: s.weight_kg, unit: "kg" },
    { label: "Payload", value: s.payload_kg, unit: "kg" },
    { label: "Reach", value: s.reach_cm, unit: "cm" },
    { label: "Arm span", value: s.arm_span_cm, unit: "cm" },
    { label: "Walk speed", value: s.walk_speed_ms, unit: "m/s" },
    { label: "Runtime", value: s.runtime_minutes, unit: "min" },
    { label: "Degrees of freedom", value: s.degrees_of_freedom },
    { label: "Mobility", value: s.mobility },
    { label: "Autonomy", value: s.autonomy },
  ];

  for (const { label, value, unit } of specFields) {
    // UNKNOWN is omitted from the citation block rather than printed as an
    // "UNKNOWN" row: this block exists to be quoted, and a retrieval system
    // lifting "Payload: UNKNOWN" out of context reads as a claim about the
    // robot. The full spec tables below on the same page still render every
    // field WITH its explicit UNKNOWN state, so nothing is hidden — CIT-B is
    // about not fabricating a value, not about forcing every field to appear.
    if (!isCitableValue(value)) continue;
    const resolved = specValue(value, unit);
    if (resolved.unknown) continue; // defensive; isCitableValue already excluded it
    facts.push({ label, value: resolved.label });
  }

  if (isCitableValue(robot.announced_year)) {
    facts.push({ label: "Announced", value: String(robot.announced_year) });
  }

  return facts;
}

/**
 * CID-02 — the rendered block. Server component by default (no "use client",
 * no hooks, no effects), so CIT-D holds: these facts are in the delivered HTML
 * without any client interaction.
 */
export function CitationFacts({ robot }: { robot: RobotDetail }) {
  const facts = citationFacts(robot);
  return (
    <dl className="citation-facts">
      {facts.map((f) => (
        <div className="cf-row" key={f.label}>
          <dt>{f.label}</dt>
          <dd>{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}
