// AvailabilityState (§6.5) — DIMENSION 2: obtainability, independent of maturity.
// Card summary derives from available_modes (canonical commercially_accessible()
// predicate). Absence -> "Availability unknown" (short), which is NOT
// NOT_AVAILABLE. Detail renders the full mode × region × status matrix.
import { resolveAvailabilitySummary, modeLabel } from "@/lib/format";
import { availabilityLabel } from "@/lib/labels";
import type { AvailabilityOffer } from "@/lib/types";

// Card badge (SHORT single-line, never truncates).
export function AvailabilityBadge({
  modes,
}: {
  modes: string[] | null | undefined;
}) {
  const s = resolveAvailabilitySummary(modes, "short");
  if (s.isUnknown) {
    return <span className="ho-badge ho-badge--unknown ho-state" data-enum="UNKNOWN">{s.label}</span>;
  }
  return (
    <span
      className="ho-badge ho-badge--ghost ho-state"
      data-enum="AVAILABLE"
      title={`Accessible modes: ${s.modes.join(", ")}`}
    >
      {s.label}
    </span>
  );
}

// Detail obtainability matrix: one row per availability_offer (buyer-facing
// status labels, raw enum in data-enum).
export function AvailabilityMatrix({
  offers,
}: {
  offers: AvailabilityOffer[];
}) {
  if (offers.length === 0) {
    return (
      <p className="stamp">
        No confirmed commercial availability. No source has confirmed whether
        this robot can be obtained, so its availability is unknown rather than
        ruled out.
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
          <span>
            {modeLabel(o.transaction_type)}
            {o.variant && (
              <span className="ho-syslabel" style={{ display: "block" }}>
                {o.variant} configuration
              </span>
            )}
          </span>
          <span className={o.region ? "" : "na"}>{o.region ?? "—"}</span>
          <span data-enum={o.availability_status}>
            {availabilityLabel(o.availability_status)}
            {/* The enum is our normalization; the seller's own sentence and the
                geography their estimate was given for are shown beneath it, so a
                domestic estimate is never read as wider coverage. */}
            {o.seller_wording && (
              <span className="ho-syslabel" style={{ display: "block" }}>
                “{o.seller_wording}”
              </span>
            )}
            {o.delivery_estimate_label && (
              <span className="ho-syslabel" style={{ display: "block" }}>
                {o.delivery_estimate_label}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
