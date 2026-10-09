// CommercialTriad — the three-dimension readout kept ALWAYS separate (§0.1):
//   ① maturity (commercial_status)  ② obtainability (available modes/offers)
//   ③ evidence (deployments / confidence). Never collapsed into one flag.
import { modeLabel } from "@/lib/format";
import { availabilityLabel, statusLabel } from "@/lib/labels";
import type { AvailabilityOffer } from "@/lib/types";

function Pair({
  kicker,
  value,
  mono,
  tone,
  rawEnum,
}: {
  kicker: string;
  value: string;
  /** Raw enum the visible label stands for (kept in data-enum). */
  rawEnum?: string;
  mono?: string;
  tone?: "signal" | "verified" | "caution" | "unknown";
}) {
  const toneClass = tone ? ` is-${tone}` : "";
  return (
    <div className={`ho-pair${toneClass}`}>
      <span className="k">{kicker}</span>
      <span className="s" {...(rawEnum ? { "data-enum": rawEnum } : {})}>
        {value}
        {mono && <span className="mono">· {mono}</span>}
      </span>
    </div>
  );
}

export function CommercialTriad({
  status,
  availabilityOffers,
  deploymentCount,
  strongestConfidence,
}: {
  status: string;
  availabilityOffers: AvailabilityOffer[];
  deploymentCount: number;
  strongestConfidence?: string | null;
}) {
  // ② obtainability summary from the offer rows, absence = unknown.
  const accessible = availabilityOffers.filter(
    (o) =>
      o.availability_status !== "NOT_AVAILABLE" &&
      o.availability_status !== "DISCONTINUED",
  );
  const obtainValue =
    availabilityOffers.length === 0
      ? "Availability unknown"
      : availabilityLabel(
          accessible.length > 0
            ? accessible[0].availability_status
            : availabilityOffers[0].availability_status,
        );
  const obtainEnum =
    availabilityOffers.length === 0
      ? undefined
      : accessible.length > 0
        ? accessible[0].availability_status
        : availabilityOffers[0].availability_status;
  const obtainMono =
    availabilityOffers.length === 0
      ? undefined
      : accessible.length > 0
        ? [modeLabel(accessible[0].transaction_type), accessible[0].region]
            .filter(Boolean)
            .join(" · ")
        : undefined;

  const evValue =
    deploymentCount > 0
      ? `${deploymentCount} deployment${deploymentCount === 1 ? "" : "s"}`
      : "No deployments on record";

  return (
    <div className="triad" role="group" aria-label="Three commercial dimensions">
      <div className="t">
        <Pair
          kicker="① Commercial maturity"
          value={statusLabel(status)}
          rawEnum={status}
          tone={status === "DISCONTINUED" ? "unknown" : "signal"}
        />
      </div>
      <div className="t">
        <Pair
          kicker="② Obtainability"
          value={obtainValue}
          rawEnum={obtainEnum}
          mono={obtainMono}
          tone={availabilityOffers.length === 0 ? "unknown" : undefined}
        />
      </div>
      <div className="t">
        <Pair
          kicker="③ Deployment evidence"
          value={evValue}
          mono={strongestConfidence ?? undefined}
          tone={
            strongestConfidence === "VERIFIED"
              ? "verified"
              : deploymentCount > 0
                ? undefined
                : "unknown"
          }
        />
      </div>
    </div>
  );
}
