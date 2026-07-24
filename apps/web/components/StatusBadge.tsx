// StatusBadge (§6.4) — DIMENSION 1: commercial_status (platform MATURITY) only.
// Never obtainability. Enum rendered verbatim; a value ramp (ghost -> solid ink)
// encodes the maturity ladder. RAAS_DEPLOYMENT is a SUCCESS state (solid).
// DISCONTINUED is ghosted/struck. No colour implies "buyable".
import { maturityIndex } from "@/lib/format";

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
      style={
        discontinued
          ? { textDecoration: "line-through", color: "var(--ho-text-faint)" }
          : undefined
      }
    >
      {status}
    </span>
  );
}

// Bracketed variant used inside RobotCards (matches the reference `[ COMMERCIAL ]`).
export function StatusBracket({ status }: { status: string }) {
  const discontinued = status === "DISCONTINUED";
  return (
    <span
      className="ho-bracket ho-state"
      style={
        discontinued
          ? { textDecoration: "line-through", color: "var(--ho-text-faint)" }
          : undefined
      }
    >
      {status}
    </span>
  );
}
