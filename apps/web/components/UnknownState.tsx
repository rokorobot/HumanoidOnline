// UnknownState — the DESIGNED unknown state (§0.1). NULL renders as an explicit,
// styled unknown; never $0 / "N/A" / false. Grey + optional hatch/dashed box.
import { GraphicMarker } from "./GraphicMarker";

export function UnknownState({
  label = "UNKNOWN",
  box = false,
  marker = false,
}: {
  label?: string;
  box?: boolean;
  marker?: boolean;
}) {
  return (
    <span
      className="ho-state"
      style={{
        color: "var(--ho-unknown)",
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        ...(box
          ? {
              border: "var(--ho-rule-hair) dashed var(--ho-grey-400)",
              padding: "1px 7px",
            }
          : {}),
      }}
    >
      {marker && (
        <GraphicMarker style={{ background: "var(--ho-grey-400)" }} />
      )}
      {label}
    </span>
  );
}
