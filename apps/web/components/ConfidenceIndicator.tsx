// ConfidenceIndicator (§6.8) — expose confidence_level as a four-segment value
// ramp (NOT a hue rainbow) + the literal enum label. Only VERIFIED renders the
// "Verified" indicator, and only when verified_at is present.
const LEVELS = ["LOW", "MEDIUM", "HIGH", "VERIFIED"] as const;

export function ConfidenceIndicator({
  level,
  verifiedAt,
}: {
  level: string;
  verifiedAt?: string | null;
}) {
  // Guard the frozen rule: VERIFIED requires verified_at. Without it, the meter
  // caps at HIGH and never claims verification.
  const effective =
    level === "VERIFIED" && !verifiedAt ? "HIGH" : level;
  const known = (LEVELS as readonly string[]).includes(effective);
  return (
    <span className="ho-conf" data-level={known ? effective : "LOW"}>
      <span className="bars" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
      <span>{known ? effective : level}</span>
    </span>
  );
}
