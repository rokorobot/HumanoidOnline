// UX-02A - applies an interpretation of the free-text `q` to the catalogue URL state.
//
// The URL stays the single source of truth: `q` holds the buyer's raw text, and on
// every render the SERVER re-interprets it. Explicit filter parameters (from the
// filter panel / a shared URL) always win over interpreted ones; when they disagree
// the interpreted part is NOT applied and is reported as such.
import { interpretQuery, type Chip, type ChipKind, type Interpretation, type InterpreterVocab } from "./query-interpreter";
import { asArray, asString, type RawSearchParams } from "./search-params";

export interface CatalogueQuery {
  /** Search params to send to the API (q = residual words; interpreted filters merged). */
  effective: RawSearchParams;
  interpretation: Interpretation | null;
  /** Chip kinds whose interpreted value lost to an explicit, different URL filter. */
  overridden: Set<ChipKind>;
  /** Chips with their final status (an overridden chip becomes "not_applied"). */
  chips: Chip[];
}

const KIND_LABEL: Record<ChipKind, string> = {
  manufacturer: "manufacturer",
  use_case: "use case",
  transaction_type: "obtainability",
  price: "price",
};

export function resolveCatalogueQuery(sp: RawSearchParams, vocab: InterpreterVocab | null): CatalogueQuery {
  const rawQ = asString(sp.q)?.trim();
  if (!rawQ || !vocab) {
    return { effective: sp, interpretation: null, overridden: new Set(), chips: [] };
  }
  const interp = interpretQuery(rawQ, vocab);
  const effective: RawSearchParams = { ...sp };
  const overridden = new Set<ChipKind>();

  if (interp.residual) effective.q = interp.residual;
  else delete effective.q;

  const f = interp.filters;
  if (f.manufacturer) {
    const explicit = asString(sp.manufacturer);
    if (explicit && explicit !== f.manufacturer) overridden.add("manufacturer");
    else effective.manufacturer = f.manufacturer;
  }
  if (f.use_case) {
    const explicit = asString(sp.use_case);
    if (explicit && explicit !== f.use_case) overridden.add("use_case");
    else effective.use_case = f.use_case;
  }
  if (f.transaction_type?.length) {
    const explicit = asArray(sp.transaction_type);
    const same =
      explicit.length === f.transaction_type.length && f.transaction_type.every((t) => explicit.includes(t));
    if (explicit.length && !same) overridden.add("transaction_type");
    else effective.transaction_type = f.transaction_type;
  }
  if (f.price_max != null && f.price_currency) {
    const explicitMax = asString(sp.price_max);
    const explicitCur = asString(sp.price_currency)?.trim().toUpperCase();
    if (explicitMax && (Number(explicitMax) !== f.price_max || (explicitCur && explicitCur !== f.price_currency))) {
      overridden.add("price");
    } else {
      effective.price_max = String(f.price_max);
      effective.price_currency = f.price_currency;
    }
  }

  const chips = interp.chips.map((c) =>
    c.status === "applied" && overridden.has(c.kind)
      ? {
          ...c,
          status: "not_applied" as const,
          note: `Not applied: the ${KIND_LABEL[c.kind]} filter in the URL is already set to something else.`,
        }
      : c,
  );
  return { effective, interpretation: interp, overridden, chips };
}

/** True when part of the query could not be turned into a filter (shown on no-result and always). */
export function partlyUninterpreted(cq: Pick<CatalogueQuery, "interpretation" | "overridden">): boolean {
  const i = cq.interpretation;
  if (!i) return false;
  return i.needsCurrency || i.unsupported.length > 0 || i.conflicts.length > 0 || cq.overridden.size > 0;
}
