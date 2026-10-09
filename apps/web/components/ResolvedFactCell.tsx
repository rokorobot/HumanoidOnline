// Renders one API-resolved fact (DR-G4). Presentation only: see lib/resolved-facts.ts.
import { describeResolved } from "@/lib/resolved-facts";
import type { ResolvedFact } from "@/lib/types";

export function ResolvedFactCell({ fact }: { fact: ResolvedFact }) {
  const d = describeResolved(fact);
  return (
    <span className="d-blk" data-resolved-state={fact.state} data-resolved-property={fact.property}>
      <span className="v">{d.headline}</span>
      {d.lines.map((l) => (
        <span
          key={l.scope ?? "product"}
          className={l.unknown ? "ho-syslabel" : undefined}
          style={{ display: "block" }}
        >
          {l.scope ? `${l.scope} — ` : ""}
          {l.text}
        </span>
      ))}
    </span>
  );
}
