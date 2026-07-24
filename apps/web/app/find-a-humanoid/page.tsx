// Find a Humanoid — DORMANT reference surface. WS3 keeps the nav entry and the
// approved visual reference, but implements NO requirement persistence, scoring,
// match results, or lead capture (hard scope boundary). MatchScore stays
// dormant. This page renders the approved shell and states the boundary plainly.
import Link from "next/link";

import { GraphicMarker } from "@/components/GraphicMarker";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const metadata = {
  title: "Find a Humanoid — HumanoidOnline",
};

export default function FindAHumanoidPage() {
  return (
    <>
      <SystemHeader
        title="FIND A HUMANOID / GUIDED MATCH"
        fields={[{ label: "STATUS", value: "REFERENCE — NOT YET WIRED" }]}
      />
      <div className="wrap wrap--narrow">
        <SiteNav active="find" />

        <div className="pagebar">
          <div>
            <SectionIndex>FIND A HUMANOID — GUIDED MATCH</SectionIndex>
            <h1>Find a humanoid</h1>
          </div>
        </div>

        <div
          className="action-panel"
          style={{ marginTop: "var(--ho-sp-4)", alignItems: "flex-start" }}
        >
          <div>
            <SystemLabel as="div">Guided requirement matching</SystemLabel>
            <p className="prose" style={{ marginTop: 10 }}>
              A guided wizard will capture your requirements — use case, payload,
              autonomy, budget, region, preferred transaction — and return ranked
              matches with reasons and warnings, each grounded in the same
              evidence-backed catalogue.
            </p>
            <p className="note" style={{ marginTop: 12 }}>
              // This surface is a visual reference in WS3. Requirement capture,
              scoring, match results and lead capture are delivered by later
              workstreams (Buyer Intent / Matching). Nothing here persists data or
              computes a score.
            </p>
          </div>
          <Link className="btn" href="/robots">
            <GraphicMarker /> Browse the catalogue instead
          </Link>
        </div>

        {/* Approved wizard-shell reference (dormant — no inputs are wired). */}
        <section className="blk" style={{ marginBottom: "var(--ho-sp-8)" }} aria-hidden="true">
          <div className="blk-head">
            <div>
              <SectionIndex>PREVIEW — WIZARD SHELL</SectionIndex>
              <h2>Step 01 / 06</h2>
            </div>
            <SystemLabel>USABILITY-FIRST · DORMANT PREVIEW</SystemLabel>
          </div>
          <div style={{ opacity: 0.55, pointerEvents: "none" }}>
            <p className="prose" style={{ fontWeight: 700, fontSize: "1.4rem" }}>
              What is the primary use case?
            </p>
            <div className="apps" style={{ marginTop: 16 }}>
              {["Manufacturing", "Warehouse / Logistics", "Research / Education", "Hospitality"].map(
                (c, i) => (
                  <div className="app" key={c}>
                    <SystemLabel>{String(i + 1).padStart(2, "0")}</SystemLabel>
                    <span className="name">{c}</span>
                  </div>
                ),
              )}
            </div>
          </div>
        </section>
      </div>
      <SiteFooter />
    </>
  );
}
