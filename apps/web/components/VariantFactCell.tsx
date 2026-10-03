// Renders a variant-aware fact inside a spec row (see lib/variant-facts.ts).
import { formatDate } from "@/lib/format";
import type { InterfaceFacts, VariantFact } from "@/lib/variant-facts";
import { UnknownState } from "./UnknownState";

function Source({ source }: { source?: VariantFact["source"] }) {
  if (!source) return null;
  const t = [source.label, source.observed_at ? `observed ${formatDate(source.observed_at)}` : null]
    .filter(Boolean)
    .join(" · ");
  if (!t) return null;
  return (
    <span className="ho-syslabel" style={{ display: "block" }}>
      {source.url ? (
        <a href={source.url} target="_blank" rel="noopener noreferrer">
          {t} ↗
        </a>
      ) : (
        t
      )}
    </span>
  );
}

export function VariantFactValue({ fact }: { fact: VariantFact }) {
  if (fact.kind === "uniform") {
    return (
      <span style={{ display: "block" }} data-variant-fact="uniform">
        <span className="v">{fact.value}</span>
        <span className="ho-syslabel" style={{ display: "block" }}>
          {fact.rows.map((r) => r.variant).join(" + ")}
        </span>
        <Source source={fact.source} />
      </span>
    );
  }
  return (
    <span style={{ display: "block" }} data-variant-fact={fact.kind}>
      {fact.kind === "varies" && <span className="v">Varies by configuration</span>}
      {fact.rows.map((r) => (
        <span key={r.variant} style={{ display: "block" }}>
          {r.variant} — {r.value ?? <UnknownState />}
        </span>
      ))}
      <Source source={fact.source} />
    </span>
  );
}

export function InterfaceFactsValue({ facts }: { facts: InterfaceFacts }) {
  return (
    <span style={{ display: "block" }} data-variant-fact="interfaces">
      {facts.common.length > 0 && (
        <span style={{ display: "block" }}>{facts.common.join(", ")}</span>
      )}
      {facts.extras.map((e) => (
        <span key={e.variant} style={{ display: "block" }}>
          {e.variant} — {e.items.join(", ")}
        </span>
      ))}
      <Source source={facts.source} />
    </span>
  );
}
