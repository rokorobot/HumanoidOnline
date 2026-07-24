// AvailabilityState (§6.5) — DIMENSION 2: obtainability, independent of maturity.
// Card summary derives from available_modes (canonical commercially_accessible()
// predicate). Absence -> "AVAILABILITY UNKNOWN" (short), which is NOT
// NOT_AVAILABLE. Detail renders the full mode × region × status matrix.
import { resolveAvailabilitySummary, modeLabel } from "@/lib/format";
import type { AvailabilityOffer } from "@/lib/types";

// Card badge (SHORT single-line, never truncates).
export function AvailabilityBadge({
  modes,
}: {
  modes: string[] | null | undefined;
}) {
  const s = resolveAvailabilitySummary(modes, "short");
  if (s.isUnknown) {
    return <span className="ho-badge ho-badge--unknown ho-state">{s.label}</span>;
  }
  return (
    <span
      className="ho-badge ho-badge--ghost ho-state"
      title={`Accessible modes: ${s.modes.join(", ")}`}
    >
      {s.label}
    </span>
  );
}

// Detail obtainability matrix: one row per availability_offer, verbatim enums.
export function AvailabilityMatrix({
  offers,
}: {
  offers: AvailabilityOffer[];
}) {
  if (offers.length === 0) {
    return (
      <p className="stamp">
        No confirmed commercial availability. Absence of any availability_offer
        row is UNKNOWN — not NOT_AVAILABLE.
      </p>
    );
  }
  return (
    <div className="matrix">
      <div className="mrow head">
        <span>Mode</span>
        <span>Region</span>
        <span>Status</span>
      </div>
      {offers.map((o, i) => (
        <div className="mrow" key={i}>
          <span>{modeLabel(o.transaction_type)}</span>
          <span className={o.region ? "" : "na"}>{o.region ?? "—"}</span>
          <span>{o.availability_status}</span>
        </div>
      ))}
    </div>
  );
}
