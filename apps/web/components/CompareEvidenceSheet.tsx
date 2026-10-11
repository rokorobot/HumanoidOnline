"use client";

// UX-03 — "Offers & evidence" sheet for one compared robot.
//
// The compare matrix keeps each price / availability cell to the few facts that
// make it safe to read. Everything else recorded on the SAME offer rows — basis,
// shipping, contents, warranty, seller wording, order status, source and dates —
// is listed here, one entry per offer row, nothing summarised or merged.
//
// Rendered only while open, so it adds nothing to the delivered document.
//
// Accessibility: a native modal <dialog>. The browser makes the rest of the page
// inert (focus stays inside), Escape closes it, and focus returns to the control
// that opened it. The scroll area is the dialog body, not the page.
import { useEffect, useId, useRef } from "react";

import { inScope, type BuyerContext } from "@/lib/buyer-context";
import { priceDisplayFromHeadline } from "@/lib/commercial-summary";
import { formatObservedDate, modeLabel, resolvePriceState } from "@/lib/format";
import { availabilityLabel, priceTypeLabel } from "@/lib/labels";
import { providerLabel } from "@/lib/providers";
import type { AvailabilityOffer, Evidence, PricingOffer, RobotDetail } from "@/lib/types";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { EvidenceDates } from "@/components/EvidenceDates";

export function CompareEvidenceSheet({
  robot,
  context,
  onClose,
}: {
  robot: RobotDetail;
  context: BuyerContext;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const opener = document.activeElement as HTMLElement | null;
    // showModal() is what provides the focus trap, Escape and the backdrop.
    if (typeof d.showModal === "function") {
      if (!d.open) d.showModal();
    } else {
      d.setAttribute("open", "");
    }
    return () => {
      if (d.open && typeof d.close === "function") d.close();
      // Browsers restore focus on close(); this covers unmount paths that skip it.
      if (opener && document.contains(opener)) opener.focus();
    };
  }, []);

  // close() fires the dialog's own `close` event, which is what calls onClose.
  function closeSheet() {
    const d = ref.current;
    if (d && d.open && typeof d.close === "function") d.close();
    else onClose();
  }

  const prices = (
    <Section title={`Price entries · ${robot.pricing_offers.length}`}>
      {robot.pricing_offers.length === 0 ? (
        <Absent label="No confirmed pricing">
          The catalogue holds no price entry for this robot. That is unknown, not free and not
          &quot;on request&quot;.
        </Absent>
      ) : (
        robot.pricing_offers.map((p, i) => <PriceEntry key={i} offer={p} context={context} />)
      )}
    </Section>
  );
  const availability = (
    <Section title={`Availability entries · ${robot.availability_offers.length}`}>
      {robot.availability_offers.length === 0 ? (
        <Absent label="Availability not recorded">
          The catalogue holds no availability entry for this robot. This is missing evidence, not a
          statement that the robot is unavailable; a published price does not establish that it can
          be ordered.
        </Absent>
      ) : (
        robot.availability_offers.map((a, i) => (
          <AvailabilityEntry key={i} offer={a} context={context} />
        ))
      )}
    </Section>
  );

  return (
    // The backdrop click is a pointer convenience only; Escape (native to a modal
    // dialog) and the close button are the keyboard paths.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      className="cmp-sheet"
      aria-labelledby={titleId}
      onClose={onClose}
      // A click on the backdrop lands on the <dialog> element itself.
      onClick={(e) => {
        if (e.target === ref.current) closeSheet();
      }}
    >
      <div className="cmp-sheet-head">
        <div>
          <span className="ho-syslabel">Offers &amp; evidence</span>
          <h2 id={titleId}>{robot.name}</h2>
          <span className="ho-syslabel">{robot.manufacturer.name}</span>
        </div>
        <button
          type="button"
          className="btn cmp-sheet-close"
          aria-label="Close offers and evidence"
          onClick={closeSheet}
        >
          ✕
        </button>
      </div>
      {/* The scrolling region is focusable so it can be scrolled from the keyboard. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="cmp-sheet-body" tabIndex={0} role="group" aria-label="Offer entries">
        {prices}
        {availability}
      </div>
    </dialog>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="cmp-sheet-sec">
      <h3 className="cmp-ev-h">{title}</h3>
      {children}
    </section>
  );
}

function Absent({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cmp-entry cmp-entry--absent">
      <span className="hatch">{label}</span>
      <p className="note">{children}</p>
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <div className="cf-row">
      <dt>{k}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Region as recorded, plus what the Buyer context (when set) says about it. */
function RegionRows({ region, context }: { region?: string | null; context: BuyerContext }) {
  return (
    <>
      <Row k="Region">{region ?? "Not recorded on this entry"}</Row>
      {context.region && context.applicable && (
        <Row k={`Region ${context.region}`}>
          {inScope(region, context.applicable) ? "Applies" : "Does not apply"}
        </Row>
      )}
      {context.market && context.marketCodes && (
        <Row k={`${context.market} market`}>
          {inScope(region, context.marketCodes) ? "In this market" : "Not in this market"}
        </Row>
      )}
    </>
  );
}

function Seller({ slug, name }: { slug?: string | null; name?: string | null }) {
  if (!slug) return null;
  return <span data-provider={slug}>{providerLabel(slug, null, name).text}</span>;
}

function EvidenceBlock({ evidence }: { evidence?: Evidence | null }) {
  return (
    <div className="cmp-entry-ev">
      <EvidenceDates evidence={evidence} />
      {evidence && <ConfidenceIndicator level={evidence.confidence} verifiedAt={evidence.verified_at} />}
    </div>
  );
}

function PriceEntry({ offer, context }: { offer: PricingOffer; context: BuyerContext }) {
  const state = resolvePriceState(
    priceDisplayFromHeadline({ offer, configurationsPriced: 0 }),
    "long",
  );
  return (
    <article className="cmp-entry">
      <p className="cmp-entry-main" data-enum={offer.price_type}>
        {state.label}
      </p>
      {state.context && <p className="ho-syslabel">{state.context}</p>}
      <dl className="mfr-facts">
        <Row k="Price type">{priceTypeLabel(offer.price_type)}</Row>
        <Row k="Transaction">{modeLabel(offer.transaction_type)}</Row>
        <Row k="Configuration">{offer.variant}</Row>
        <RegionRows region={offer.region} context={context} />
        <Row k="Seller">{offer.provider && <Seller slug={offer.provider} name={offer.provider_name} />}</Row>
        <Row k="Price basis">{offer.price_basis}</Row>
        <Row k="Shipping">{offer.shipping_terms}</Row>
        <Row k="Package">{offer.package_contents}</Row>
        <Row k="Seller warranty">{offer.warranty_terms}</Row>
        <Row k="Order status">{offer.order_status_note}</Row>
        <Row k="Edition">{offer.edition_note}</Row>
        <Row k="Condition">{offer.condition && offer.condition !== "NEW" ? offer.condition : null}</Row>
      </dl>
      <EvidenceBlock evidence={offer.evidence} />
    </article>
  );
}

function AvailabilityEntry({ offer, context }: { offer: AvailabilityOffer; context: BuyerContext }) {
  const observed = formatObservedDate(offer.evidence?.observed_at);
  return (
    <article className="cmp-entry">
      <p className="cmp-entry-main" data-enum={offer.availability_status}>
        {availabilityLabel(offer.availability_status)}
      </p>
      {observed && (
        <p className="note">As observed {observed}. Not a live stock check.</p>
      )}
      <dl className="mfr-facts">
        <Row k="Transaction">{modeLabel(offer.transaction_type)}</Row>
        <Row k="Configuration">{offer.variant}</Row>
        <RegionRows region={offer.region} context={context} />
        <Row k="Seller">{offer.provider && <Seller slug={offer.provider} name={offer.provider_name} />}</Row>
        <Row k="Seller wording">{offer.seller_wording}</Row>
        <Row k="Delivery estimate">{offer.delivery_estimate_label}</Row>
        <Row k="Lead time">{offer.lead_time_days != null ? `${offer.lead_time_days} days` : null}</Row>
        <Row k="Available from">{formatObservedDate(offer.available_from)}</Row>
        <Row k="Condition">{offer.condition && offer.condition !== "NEW" ? offer.condition : null}</Row>
      </dl>
      <EvidenceBlock evidence={offer.evidence} />
    </article>
  );
}
