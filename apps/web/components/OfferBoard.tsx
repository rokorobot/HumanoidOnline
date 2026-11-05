// DR-UI2 — robot-detail offer board. One row per offer (lib/offer-board.ts):
// availability status, price with its full terms, and the evidence for EACH of the
// two records, read together. Replaces the pricing-only table; the three-dimension
// cards above it are unchanged. Unknown stays unknown on both sides of a row.
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { OfferRequestButton } from "@/components/OfferRequestButton";
import { PriceStateLong } from "@/components/PricingState";
import { formatDate, modeLabel, resolvePriceState } from "@/lib/format";
import { availabilityLabel, sourceTypeLabel } from "@/lib/labels";
import { buildOfferRows, leadTransactionFor, type OfferRow } from "@/lib/offer-board";
import { providerLabel, type ProviderNames } from "@/lib/providers";
import type {
  AvailabilityOffer,
  Evidence,
  PriceDisplay,
  PricingOffer,
  RegionListItem,
} from "@/lib/types";

function priceOf(p: PricingOffer): PriceDisplay {
  return {
    type: p.price_type,
    amount: p.price,
    amount_min: p.price_min,
    amount_max: p.price_max,
    currency: p.currency,
    billing_period: p.billing_period,
  };
}

function EvidenceLine({ kind, evidence }: { kind: string; evidence?: Evidence | null }) {
  if (!evidence) {
    return <span className="ob-ev ob-ev--none">{kind}: no evidence on record</span>;
  }
  const observed = formatDate(evidence.observed_at);
  return (
    <span className="ob-ev">
      <span className="ob-ev__k">{kind}</span>
      <ConfidenceIndicator level={evidence.confidence} verifiedAt={evidence.verified_at} />
      <span className="ob-ev__d">
        <span data-enum={evidence.source_type}>{sourceTypeLabel(evidence.source_type)}</span>
        {observed && <> · observed {observed}</>}
      </span>
      {evidence.source_url && (
        <a href={evidence.source_url} target="_blank" rel="noopener noreferrer">
          View source ↗
        </a>
      )}
    </span>
  );
}

function StatusCell({ offers }: { offers: AvailabilityOffer[] }) {
  if (offers.length === 0) {
    return (
      <span className="val unknown ob-st ob-st--unk">
        No availability on record
        <span className="ho-syslabel d-blk unk-c">Unknown, not ruled out</span>
      </span>
    );
  }
  return (
    <>
      {offers.map((o, i) => (
        <span key={i} className={`ob-st ob-st--${o.availability_status.toLowerCase()}`} data-enum={o.availability_status}>
          {availabilityLabel(o.availability_status)}
          {o.seller_wording && <span className="ho-syslabel d-blk">“{o.seller_wording}”</span>}
          {o.delivery_estimate_label && (
            <span className="ho-syslabel d-blk">{o.delivery_estimate_label}</span>
          )}
        </span>
      ))}
    </>
  );
}

function PriceCell({ prices }: { prices: PricingOffer[] }) {
  // No price record for this exact offer: the explicit UNKNOWN state, never $0.
  if (prices.length === 0) return <PriceStateLong price={null} />;
  return (
    <>
      {prices.map((offer, i) => (
        <div key={i} className="ob-price">
          <PriceStateLong price={priceOf(offer)} />
          {/* The terms belong to THIS offer row and render with it, so one seller's
              number is never read under another seller's terms. */}
          {offer.price_basis && <span className="ho-syslabel d-blk">{offer.price_basis}</span>}
          {offer.shipping_terms && <span className="ho-syslabel d-blk">{offer.shipping_terms}</span>}
          {offer.package_contents && (
            <span className="ho-syslabel d-blk">Includes: {offer.package_contents}</span>
          )}
          {offer.warranty_terms && (
            <span className="ho-syslabel d-blk">Warranty (this seller): {offer.warranty_terms}</span>
          )}
          {offer.order_status_note && (
            <span className="ho-syslabel d-blk">{offer.order_status_note}</span>
          )}
          {/* Only an explicit FALSE is a warning; null was never assessed. */}
          {offer.edition_confirmed === false && (
            <span className="ho-syslabel d-blk">
              ⚠ {offer.edition_note ?? "This listing is not confirmed to be this edition."}
            </span>
          )}
        </div>
      ))}
    </>
  );
}

function stubFor(row: OfferRow, robotName: string, seller: string): { label: string; value: string }[] {
  const price = row.prices[0];
  const listed = price ? resolvePriceState(priceOf(price), "short") : null;
  return [
    { label: "Robot", value: robotName },
    {
      label: "Mode · region",
      value: [modeLabel(row.mode), row.region ?? "Region not stated"].join(" · "),
    },
    { label: "Seller", value: seller },
    ...(row.variant ? [{ label: "Configuration", value: row.variant }] : []),
    {
      label: "Listed",
      value: listed
        ? [listed.label, listed.context].filter(Boolean).join(" · ")
        : "No confirmed pricing",
    },
  ];
}

export function OfferBoard({
  robotSlug,
  robotName,
  pricing,
  availability,
  names,
  countries,
}: {
  robotSlug: string;
  robotName: string;
  pricing: PricingOffer[];
  availability: AvailabilityOffer[];
  names: ProviderNames;
  countries: RegionListItem[];
}) {
  const rows = buildOfferRows(pricing, availability);
  return (
    // WS8.4 / R17: horizontally scrollable on narrow viewports, so keyboard-focusable
    // (WCAG 2.1.1) with a named region.
    <div className="ptable offer-board" tabIndex={0} role="group" aria-label="Offer board">
      <table>
        <thead>
          <tr>
            <th scope="col">Mode</th>
            <th scope="col">Region</th>
            <th scope="col">Seller</th>
            <th scope="col">Listed price</th>
            <th scope="col">Status</th>
            <th scope="col">Evidence</th>
            <th scope="col">
              <span className="sr-only">Request</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="val unknown">—</td>
              <td className="val unknown">—</td>
              <td className="val unknown">—</td>
              <td>
                <PriceStateLong price={null} />
              </td>
              <td>
                <StatusCell offers={[]} />
              </td>
              <td className="stamp faint">— absence claims nothing —</td>
              <td />
            </tr>
          ) : (
            rows.map((row) => {
              const seller = row.provider
                ? providerLabel(row.provider, names, row.providerName).text
                : "Seller not stated";
              const stub = stubFor(row, robotName, seller);
              return (
                <tr key={row.key}>
                  <td>
                    <span className="ob-flap">{modeLabel(row.mode)}</span>
                    {row.variant && <span className="ho-syslabel d-blk">{row.variant} configuration</span>}
                    {row.condition !== "NEW" && (
                      <span className="ho-syslabel d-blk caution" data-enum={row.condition}>
                        Condition: {row.condition.replace("_", " ").toLowerCase()}
                      </span>
                    )}
                  </td>
                  <td>
                    {row.region ? (
                      <span className="ob-flap">{row.region}</span>
                    ) : (
                      <span className="val unknown">—</span>
                    )}
                  </td>
                  <td {...(row.provider ? { "data-provider": row.provider } : {})}>
                    {row.provider ? seller : <span className="val unknown">—</span>}
                  </td>
                  <td>
                    <PriceCell prices={row.prices} />
                  </td>
                  <td>
                    <StatusCell offers={row.availability} />
                  </td>
                  <td>
                    {row.availability.map((a, i) => (
                      <EvidenceLine key={`a${i}`} kind="Availability" evidence={a.evidence} />
                    ))}
                    {row.prices.map((p, i) => (
                      <EvidenceLine key={`p${i}`} kind="Price" evidence={p.evidence} />
                    ))}
                  </td>
                  <td>
                    <OfferRequestButton
                      robotSlug={robotSlug}
                      robotName={robotName}
                      countries={countries}
                      offer={stub}
                      leadTransaction={leadTransactionFor(row.mode)}
                      message={`About this offer: ${stub
                        .filter((s) => s.label !== "Robot")
                        .map((s) => `${s.label}: ${s.value}`)
                        .join("; ")}.`}
                    />
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
