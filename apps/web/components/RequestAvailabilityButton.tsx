"use client";

// WS7 "Request Availability" for Robot Detail. This CTA no longer redirects to
// the wizard — it is a real commercial action that (server-side) creates a fresh
// minimal buyer_requirement + commercial_lead for this one robot in a single
// transaction (a direct capture: no prior requirement, match_score NULL).
import { useRef, useState } from "react";

import { GraphicMarker } from "@/components/GraphicMarker";
import { LeadDialog } from "@/components/LeadDialog";
import type { RegionListItem } from "@/lib/types";

interface Props {
  robotSlug: string;
  robotName: string;
  countries: RegionListItem[];
  className?: string;
}

export function RequestAvailabilityButton({
  robotSlug,
  robotName,
  countries,
  className = "btn btn--signal",
}: Props) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        type="button"
        className={className}
        ref={triggerRef}
        onClick={() => setOpen(true)}
      >
        <GraphicMarker /> Request Availability
      </button>
      <LeadDialog
        open={open}
        onClose={() => {
          setOpen(false);
          const el = triggerRef.current;
          window.setTimeout(() => el?.focus(), 0);
        }}
        title={`Request availability — ${robotName}`}
        context={`Requesting availability and commercial help for ${robotName}.`}
        requirementId={null}
        robotSlugs={[robotSlug]}
        countries={countries}
      />
    </>
  );
}
