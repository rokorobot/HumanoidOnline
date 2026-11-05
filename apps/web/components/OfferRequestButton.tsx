"use client";

// DR-UI2 — "Request" on one offer-board row. Opens the existing WS7 lead dialog
// (lead capture only, AGENTS rule 9) with a stub naming the selected offer, the
// matching preferred transaction preselected and an editable message that names
// the offer. The buyer's own country is NOT prefilled from the offer region.
import { useRef, useState } from "react";

import { LeadDialog } from "@/components/LeadDialog";
import type { RegionListItem } from "@/lib/types";

export function OfferRequestButton({
  robotSlug,
  robotName,
  countries,
  offer,
  leadTransaction,
  message,
}: {
  robotSlug: string;
  robotName: string;
  countries: RegionListItem[];
  offer: { label: string; value: string }[];
  leadTransaction: string;
  message: string;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const summary = offer.map((o) => o.value).join(" · ");
  return (
    <>
      <button
        type="button"
        className="ob-req"
        ref={triggerRef}
        onClick={() => setOpen(true)}
        aria-label={`Request this offer: ${summary}`}
      >
        Request →
      </button>
      <LeadDialog
        open={open}
        onClose={() => {
          setOpen(false);
          const el = triggerRef.current;
          window.setTimeout(() => el?.focus(), 0);
        }}
        title={`Request availability — ${robotName}`}
        context={`Requesting availability and commercial help for ${robotName}, about the offer shown.`}
        requirementId={null}
        robotSlugs={[robotSlug]}
        countries={countries}
        offer={offer}
        initialTransaction={leadTransaction}
        initialMessage={message}
      />
    </>
  );
}
