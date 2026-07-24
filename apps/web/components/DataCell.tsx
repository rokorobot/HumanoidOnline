// DataCell (§6.10) — atom of every spec table row. Guarantees the three states:
//   value | UNKNOWN (null -> hatch/grey) | not-applicable ("—", a DIFFERENT thing).
import { specValue } from "@/lib/format";
import { UnknownState } from "./UnknownState";

export function SpecRow({
  label,
  value,
  unit,
  notApplicable = false,
}: {
  label: string;
  value?: number | string | boolean | null;
  unit?: string | null;
  notApplicable?: boolean;
}) {
  return (
    <div className="srow">
      <span className="k">{label}</span>
      <SpecValue value={value} unit={unit} notApplicable={notApplicable} />
    </div>
  );
}

export function SpecValue({
  value,
  unit,
  notApplicable = false,
}: {
  value?: number | string | boolean | null;
  unit?: string | null;
  notApplicable?: boolean;
}) {
  if (notApplicable) {
    return <span className="v unk">—</span>;
  }
  const resolved = specValue(value, unit);
  if (resolved.unknown) {
    return (
      <span className="v unk">
        <UnknownState marker />
      </span>
    );
  }
  return <span className="v">{resolved.label}</span>;
}
