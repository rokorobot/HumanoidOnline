// Metric (§6.9) — a single physical/technical spec: SystemLabel over a MACHINE
// value + unit. NULL -> explicit UNKNOWN (grey), never 0.
import { specValue } from "@/lib/format";
import { SystemLabel } from "./SystemLabel";

export function Metric({
  label,
  value,
  unit,
  rawEnum,
}: {
  label: string;
  value: number | string | boolean | null | undefined;
  unit?: string | null;
  /** Raw enum the visible label stands for (kept in data-enum). */
  rawEnum?: string | null;
}) {
  const resolved = specValue(value, unit);
  return (
    <div className="metric">
      <SystemLabel className="k">{label}</SystemLabel>
      <span className={resolved.unknown ? "v unk" : "v"} data-enum={resolved.unknown ? undefined : (rawEnum ?? undefined)}>{resolved.label}</span>
    </div>
  );
}
