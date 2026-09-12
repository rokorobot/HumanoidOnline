// PricingState (§6.6) — price with its epistemic quality. Six distinct states,
// SHORT (card) vs LONG (detail). QUOTE_ONLY ("Price on request") is NEVER the
// same look as UNKNOWN ("No confirmed pricing"). NULL never becomes $0/"free".
import { resolvePriceState, type LabelVariant } from "@/lib/format";
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
// to, the basis it is quoted on (VAT in or out) and its order status all come
// from the SAME offer row and are rendered with it. A price whose seller cannot
// currently take the order says so next to the number rather than reading as an
// ordinary listing.
export function PriceStateCard({
  price,
}: {
  price: PriceDisplay | null | undefined;
}) {
  const s = resolvePriceState(price, "short");
  const toneClass = TONE_CLASS[s.tone] ?? "";
  const hatch = s.tone === "unknown" ? "hatchbox" : "";
  const seller = price?.provider
    ? [price.provider, price.region].filter(Boolean).join(" · ")
    : null;
  return (
    <div className={`price ${toneClass}`.trim()}>
      <span className={`amt ${hatch} ho-state`.trim()}>{s.label}</span>
      {s.context && <span className="ctx">{s.context}</span>}
      {seller && <span className="ctx">{seller}</span>}
      {/* Only present when the headline came from a variant-scoped offer. Shown
          so the amount is never read as the price of every configuration. */}
      {price?.variant && <span className="ctx">Configuration: {price.variant}</span>}
      {price?.price_basis && <span className="ctx">{price.price_basis}</span>}
      {price?.order_status_note && (
        <span className="ctx" style={{ color: "var(--ho-caution)" }}>
          {price.order_status_note}
        </span>
      )}
    </div>
  );
}

// Inline (LONG) form for tables / matrix cells.
export function PriceStateLong({
  price,
  variant = "long",
}: {
  price: PriceDisplay | null | undefined;
  variant?: LabelVariant;
}) {
  const s = resolvePriceState(price, variant);
  const toneClass = TONE_CLASS[s.tone] ?? "";
  return (
    <span className={`val ${toneClass}`.trim()}>
      {s.label}
      {s.context && (
        <span
          className="ho-syslabel"
          style={{
            display: "block",
            color:
              s.tone === "quote" || s.tone === "estimated"
                ? "var(--ho-caution)"
                : s.tone === "unknown"
                  ? "var(--ho-unknown)"
                  : undefined,
          }}
        >
          {s.context}
        </span>
      )}
    </span>
  );
}
