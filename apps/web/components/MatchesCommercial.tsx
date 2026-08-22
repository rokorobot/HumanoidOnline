"use client";

// WS7 commercial capture for /matches/[id]. Owns the interactive surfaces the
// server page can't: the per-card "Request commercial help" CTA, the whole-
// shortlist CTA, and the zero-match "Tell us anyway" CTA. All three open the one
// reusable LeadDialog. No new route — the dialog is a modal over this page.
//
// The robots sent per surface are decided HERE (never trusted from the browser
// on the server, but this is what a legitimate client submits): one slug for a
// card, every surfaced slug for the shortlist, none for zero-match. The server
// re-validates each against the requirement's persisted match_result.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { CompareLink } from "@/components/CompareLink";
import { LeadDialog } from "@/components/LeadDialog";
import { MatchCard } from "@/components/MatchCard";
import { SectionIndex } from "@/components/SectionIndex";
import type { Identity } from "@/lib/lead-form";
import type { MatchItem, RegionListItem } from "@/lib/types";

interface Props {
  requirementId: string;
  matches: MatchItem[];
  noMatchExplanation: string | null;
  countries: RegionListItem[];
  compareHref: string;
  adjustHref: string;
}

export function MatchesCommercial({
  requirementId,
  matches,
  noMatchExplanation,
  countries,
  compareHref,
  adjustHref,
}: Props) {
  const [open, setOpen] = useState(false);
  const [robotSlugs, setRobotSlugs] = useState<string[]>([]);
  const [title, setTitle] = useState("Request commercial help");
  const [context, setContext] = useState<string | undefined>(undefined);
  const [identity, setIdentity] = useState<Identity | null>(null);
  // Return focus to the CTA that opened the dialog (accessibility).
  const triggerRef = useRef<HTMLElement | null>(null);

  // Identity captured on the Find a Humanoid contact step, bridged here via
  // sessionStorage (client-only, keyed by this requirement id) so LeadDialog
  // can prefill without a new PII-exposing backend read endpoint. A
  // historical anonymous requirement, or a fresh session/browser, simply has
  // nothing stored — the dialog then opens empty exactly as before.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("ho.leadIdentity." + requirementId);
      if (raw) setIdentity(JSON.parse(raw) as Identity);
    } catch {
      /* sessionStorage unavailable or malformed value — fall back to empty */
    }
  }, [requirementId]);

  function openDialog(
    e: React.MouseEvent<HTMLElement>,
    opts: { robotSlugs: string[]; title: string; context?: string },
  ) {
    triggerRef.current = e.currentTarget;
    setRobotSlugs(opts.robotSlugs);
    setTitle(opts.title);
    setContext(opts.context);
    setOpen(true);
  }

  function closeDialog() {
    setOpen(false);
    // Restore focus to the trigger on the next tick (after the dialog unmounts).
    const el = triggerRef.current;
    window.setTimeout(() => el?.focus(), 0);
  }

  const nameBySlug = new Map(matches.map((m) => [m.robot.slug, m.robot.name]));
  const allSlugs = matches.map((m) => m.robot.slug);

  const dialog = (
    <LeadDialog
      open={open}
      onClose={closeDialog}
      title={title}
      context={context}
      requirementId={requirementId}
      robotSlugs={robotSlugs}
      countries={countries}
      identity={identity}
    />
  );

  // ---- zero-match: preserve the demand ("we track the market") -------------
  if (matches.length === 0) {
    return (
      <>
        <section className="wz-confirm" aria-live="polite">
          <SectionIndex>NO MATCH — HONEST ELIMINATION</SectionIndex>
          <h2 className="wz-confirm-title">No humanoid matched</h2>
          <p className="prose">{noMatchExplanation}</p>
          <p className="note">
            {"// We still track this demand. Tell us anyway, or adjust your requirements."}
          </p>
          <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
            <button
              type="button"
              className="btn btn--signal"
              onClick={(e) =>
                openDialog(e, {
                  robotSlugs: [],
                  title: "Tell us anyway — we track the market",
                  context:
                    "No robot matched your requirement yet. Share your details and we'll track this demand.",
                })
              }
            >
              Tell us anyway →
            </button>
            <Link className="btn" href={adjustHref}>
              Adjust requirements
            </Link>
            <Link className="btn" href="/robots">
              Browse robots
            </Link>
          </div>
        </section>
        {dialog}
      </>
    );
  }

  // ---- ranked matches: per-card + whole-shortlist capture ------------------
  const n = matches.length;
  return (
    <>
      <div className="results-head">
        <span className="count">
          <b>{n}</b> RANKED MATCH{n > 1 ? "ES" : ""}
        </span>
        <div className="actions">
          {n >= 2 && (
            // Emergency Compare Crawl Containment (v0.2) — same rationale as
            // CompareBar: a real <a href> here is followed by any link-parsing
            // mechanism regardless of Next's prefetch setting (see
            // components/CompareLink.tsx), so this must only become a request
            // on an explicit click.
            <CompareLink className="btn btn--ghost" href={compareHref}>
              Compare these →
            </CompareLink>
          )}
          <button
            type="button"
            className="btn btn--signal"
            onClick={(e) =>
              openDialog(e, {
                robotSlugs: allSlugs,
                title: "Request help with these matches",
                context: `Requesting commercial help with ${n} matched humanoid${n > 1 ? "s" : ""}.`,
              })
            }
          >
            Request help with these matches →
          </button>
        </div>
      </div>

      <div className="matchlist">
        {matches.map((m) => (
          <MatchCard
            key={m.robot.slug}
            match={m}
            onRequestHelp={(e) =>
              openDialog(e, {
                robotSlugs: [m.robot.slug],
                title: "Request commercial help",
                context: `Requesting commercial help with ${nameBySlug.get(m.robot.slug) ?? m.robot.slug}.`,
              })
            }
          />
        ))}
      </div>

      <p className="note" style={{ marginTop: "var(--ho-sp-5)" }}>
        {"// A commercial inquiry captures a qualified lead only — no checkout, no payment."}
      </p>
      {dialog}
    </>
  );
}
