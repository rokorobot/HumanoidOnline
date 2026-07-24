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
export function PriceStateCard({
  price,
}: {
  price: PriceDisplay | null | undefined;
}) {
  const s = resolvePriceState(price, "short");
  const toneClass = TONE_CLASS[s.tone] ?? "";
  const hatch = s.tone === "unknown" ? "hatchbox" : "";
  return (
    <div className={`price ${toneClass}`.trim()}>
      <span className={`amt ${hatch} ho-state`.trim()}>{s.label}</span>
      {s.context && <span className="ctx">{s.context}</span>}
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
