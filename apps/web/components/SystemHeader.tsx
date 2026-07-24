// SystemHeader / MachineMeta (§5.1) — the slim black top strip. FUNCTIONAL, not
// decorative: it carries the real page record line (index title + record id,
// observed date, counts, evidence status). The reference-mockup disclaimer is
// gone in production — this is live data.
import type { ReactNode } from "react";

export interface MetaField {
  label?: string;
  value: ReactNode;
  /** Highlights the value in signal orange (e.g. evidence status HIGH/VERIFIED). */
  emphasis?: boolean;
}

export function SystemHeader({
  title,
  fields = [],
}: {
  title: ReactNode;
  fields?: MetaField[];
}) {
  return (
    <div className="ho-sysheader">
      <span className="title">
        <span className="ho-marker" aria-hidden="true" /> {title}
      </span>
      <span className="mm">
        {fields.map((f, i) => (
          <span className={`f${f.emphasis ? " ev-high" : ""}`} key={i}>
            {f.label ? `${f.label} ` : ""}
            <b>{f.value}</b>
          </span>
        ))}
      </span>
    </div>
  );
}
