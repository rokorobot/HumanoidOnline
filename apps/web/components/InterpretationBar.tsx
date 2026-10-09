"use client";

// InterpretationBar - "Interpreted as" chips for the catalogue search (UX-02A).
//
// Removing a chip, or choosing a currency for a price that has none, edits the query TEXT
// and navigates with router.push to the same URL with the new `q` - buttons, never
// selection-specific anchors, so no query-combinatorial href reaches the server HTML
// (crawl containment, see components/CompareLink.tsx).
import { useRouter } from "next/navigation";

import { addCurrencyToChip, removeChip, SUPPORTED_CURRENCIES, type Chip } from "@/lib/query-interpreter";

export function InterpretationBar({
  text,
  chips,
  base,
  residualUnmatched,
  unsupported,
  conflicts,
  hasAppliedPrice,
}: {
  /** The raw query text (trimmed) the chip spans refer to. */
  text: string;
  chips: Chip[];
  /** Query string of every OTHER URL parameter (no leading "?"), preserved on edits. */
  base: string;
  /** Name-search words that matched no robot ("Not understood"). */
  residualUnmatched: string[];
  unsupported: string[];
  conflicts: string[];
  hasAppliedPrice: boolean;
}) {
  const router = useRouter();
  function go(nextText: string) {
    const usp = new URLSearchParams(base);
    if (nextText) usp.set("q", nextText);
    else usp.delete("q");
    const qs = usp.toString();
    router.push(qs ? `/robots?${qs}` : "/robots", { scroll: false });
  }
  const issues = [...unsupported, ...conflicts];
  if (chips.length === 0 && residualUnmatched.length === 0 && issues.length === 0) return null;
  return (
    <section className="interp" aria-label="How your search was read">
      <span className="ho-syslabel">Interpreted as</span>
      <ul className="chips">
        {chips.map((c) => (
          <li key={`${c.start}-${c.end}`} className={`chip chip--${c.status}`}>
            <span className="chip-label">{c.label}</span>
            {c.note && <span className="chip-note">{c.note}</span>}
            {c.status === "needs_currency" && (
              <span className="chip-choices" role="group" aria-label="Choose a currency">
                {SUPPORTED_CURRENCIES.map((cur) => (
                  <button key={cur} type="button" onClick={() => go(addCurrencyToChip(text, c, cur))}>
                    {cur}
                  </button>
                ))}
              </span>
            )}
            <button
              type="button"
              className="chip-x"
              aria-label={`Remove: ${c.label}`}
              onClick={() => go(removeChip(text, c))}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      {hasAppliedPrice && (
        <p className="note">
          Maximum purchase price matches recorded purchase prices in that currency only (no
          conversion). Robots without a recorded price in that currency are not shown, which is not
          evidence that they cost more.
        </p>
      )}
      {residualUnmatched.length > 0 && (
        <p className="note">
          Not understood: {residualUnmatched.map((w) => `“${w}”`).join(", ")} (no robot name or
          description contains it).
        </p>
      )}
      {issues.length > 0 && (
        <ul className="note interp-issues">
          {issues.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
