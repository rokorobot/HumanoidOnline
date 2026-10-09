// StatusBadge (§6.4) — DIMENSION 1: commercial_status (platform MATURITY) only.
// Never obtainability. Rendered as a buyer-facing label (lib/labels.ts) with the
// raw enum kept in data-enum; a value ramp (ghost -> solid ink)
// encodes the maturity ladder. RAAS_DEPLOYMENT is a SUCCESS state (solid).
// DISCONTINUED is ghosted/struck. No colour implies "buyable".
import { maturityIndex } from "@/lib/format";
import { statusLabel } from "@/lib/labels";

const STRUCK = { textDecoration: "line-through", color: "var(--ho-text-faint)" };

export function StatusBadge({ status }: { status: string }) {
  const idx = maturityIndex(status);
  const discontinued = status === "DISCONTINUED";
  // Solid ink for the top of the ladder (COMMERCIAL / RAAS_DEPLOYMENT);
  // ghost for earlier maturity; dashed/struck for DISCONTINUED.
  let variant = "ho-badge--ghost";
  if (discontinued) variant = "ho-badge--ghost";
  else if (idx >= 6) variant = "ho-badge--solid";

  return (
    <span
      className={`ho-badge ${variant} ho-state`}
      data-enum={status}
      {...(discontinued ? { style: STRUCK } : {})}
    >
      {statusLabel(status)}
    </span>
  );
}

// Bracketed variant used inside RobotCards (matches the reference `[ COMMERCIAL ]`).
export function StatusBracket({ status }: { status: string }) {
  const discontinued = status === "DISCONTINUED";
  return (
    <span
      className="ho-bracket ho-state"
      data-enum={status}
      {...(discontinued ? { style: STRUCK } : {})}
    >
      {statusLabel(status)}
    </span>
  );
}
