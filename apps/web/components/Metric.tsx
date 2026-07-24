// Metric (§6.9) — a single physical/technical spec: SystemLabel over a MACHINE
// value + unit. NULL -> explicit UNKNOWN (grey), never 0.
import { specValue } from "@/lib/format";
import { SystemLabel } from "./SystemLabel";

export function Metric({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | string | boolean | null | undefined;
  unit?: string | null;
}) {
  const resolved = specValue(value, unit);
  return (
    <div className="metric">
      <SystemLabel className="k">{label}</SystemLabel>
      <span className={resolved.unknown ? "v unk" : "v"}>{resolved.label}</span>
    </div>
  );
}
