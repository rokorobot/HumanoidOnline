// PricingState (§6.6) — price with its epistemic quality. Six distinct states,
// SHORT (card) vs LONG (detail). QUOTE_ONLY ("Price on request") is NEVER the
// same look as UNKNOWN ("No confirmed pricing"). NULL never becomes $0/"free".
import { shortBasisTag } from "@/lib/commercial-summary";
import { resolvePriceState, type LabelVariant } from "@/lib/format";
import { providerLabel, type ProviderNames } from "@/lib/providers";
import type { PriceDisplay } from "@/lib/types";

const TONE_CLASS: Record<string, string> = {
  public: "public",
  quote: "quote",
  estimated: "estimated",
  unknown: "unknown",
  default: "",
};

// Card footer form (SHORT).
//
// The amount never travels alone: the seller, the region that offer is scoped
// to, the configuration it was quoted for, a SHORT basis tag and its order
// status all come from the SAME offer row and are rendered with it. The full
// price_basis sentence (VAT / legal wording) is kept verbatim inside a
// "Price terms" disclosure so the card stays compact without dropping any term.
// A price whose seller cannot currently take the order says so next to the
// number rather than reading as an ordinary listing.
export function PriceStateCard({
  price,
  names,
}: {
  price: PriceDisplay | null | undefined;
  names?: ProviderNames | null;
}) {
  const s = resolvePriceState(price, "short");
  const toneClass = TONE_CLASS[s.tone] ?? "";
  const hatch = s.tone === "unknown" ? "hatchbox" : "";
  // The API gives a seller SLUG only; cards have no authoritative name map, so the
  // neutral identifier form is used (see lib/providers.ts). Region is unchanged.
  const label = price?.provider ? providerLabel(price.provider, names, price.provider_name) : null;
  const seller = label ? [label.text, price?.region].filter(Boolean).join(" · ") : null;
  const tag = shortBasisTag(price?.price_basis);
  return (
    <div className={`price ${toneClass}`.trim()}>
      <span
        className={`amt ${hatch} ho-state`.trim()}
        {...(price ? { "data-enum": price.type } : {})}
      >
        {s.label}
      </span>
      {s.context && <span className="ctx">{s.context}</span>}
      {seller && (
        <span className="ctx" data-provider={price?.provider ?? undefined}>
          {seller}
        </span>
      )}
      {/* Only present when the headline came from a variant-scoped offer. Shown
          so the amount is never read as the price of every configuration. */}
      {price?.variant && <span className="ctx">Configuration: {price.variant}</span>}
      {price?.order_status_note && (
        <span className="ctx caution">
          {price.order_status_note}
        </span>
      )}
      {price?.price_basis && <PriceTerms basis={price.price_basis} tag={tag} />}
    </div>
  );
}

/** The full, unmodified price_basis text behind a native, keyboard-accessible disclosure. */
export function PriceTerms({ basis, tag }: { basis: string; tag?: string | null }) {
  // The short VAT/tax tag (when unambiguous) rides in the summary line.
  return (
    <details className="price-terms">
      <summary>{tag ? `${tag} · Price terms` : "Price terms"}</summary>
      <p>{basis}</p>
    </details>
  );
}

// Inline (LONG) form for tables / matrix cells.
//
// With `detailed`, the cell also carries what makes the number safe to read: the
// configuration it belongs to, the "From ... / N configurations priced" framing
// when several configurations were priced, a short basis tag, the seller's order
// note and the full terms - all from the same offer row as the amount.
export function PriceStateLong({
  price,
  variant = "long",
  detailed = false,
  fromLowest = false,
  configurationsPriced = 0,
}: {
  price: PriceDisplay | null | undefined;
  variant?: LabelVariant;
  detailed?: boolean;
  fromLowest?: boolean;
  configurationsPriced?: number;
}) {
  const s = resolvePriceState(price, variant);
  const toneClass = TONE_CLASS[s.tone] ?? "";
  const tag = detailed ? shortBasisTag(price?.price_basis) : null;
  return (
    <span className={`val ${toneClass}`.trim()} {...(price ? { "data-enum": price.type } : {})}>
      {fromLowest && price && price.type !== "FROM" ? "From " : ""}
      {s.label}
      {s.context && (
        <span
          className={`ho-syslabel d-blk${
            s.tone === "quote" || s.tone === "estimated" ? " caution" : s.tone === "unknown" ? " unk-c" : ""
          }`}
        >
          {s.context}
        </span>
      )}
      {detailed && price?.variant && (
        <span className="ho-syslabel d-blk">
          {price.variant} configuration
        </span>
      )}
      {detailed && configurationsPriced > 1 && (
        <span className="ho-syslabel d-blk">
          {configurationsPriced} configurations priced
        </span>
      )}
      {detailed && price?.order_status_note && (
        <span className="ho-syslabel d-blk caution">
          {price.order_status_note}
        </span>
      )}
      {detailed && price?.price_basis && <PriceTerms basis={price.price_basis} tag={tag} />}
    </span>
  );
}
