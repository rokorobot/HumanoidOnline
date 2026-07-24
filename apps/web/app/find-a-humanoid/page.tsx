// Find a Humanoid — PURELY INFORMATIONAL reference surface. WS3 keeps the nav
// entry and states the boundary plainly. It establishes NO wizard step contract,
// contains NOTHING selectable/interactive, and implements NO requirement
// persistence, scoring, matches, or lead capture (hard scope boundary). The
// frozen Buyer-Intent flow (12 steps) is shown only as static, non-interactive
// architectural preview text.
import Link from "next/link";

import { GraphicMarker } from "@/components/GraphicMarker";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const metadata = {
  title: "Find a Humanoid — HumanoidOnline",
};

// The frozen Buyer-Intent requirement flow (12 steps). Static reference only.
const FUTURE_STEPS = [
  "TASK",
  "INDUSTRY",
  "COUNTRY",
  "ENVIRONMENT",
  "PAYLOAD",
  "HOURS",
  "MANIPULATION",
  "AUTONOMY",
  "BUDGET",
  "TIMELINE",
  "TRANSACTION",
  "REVIEW",
];

export default function FindAHumanoidPage() {
  return (
    <>
      <SystemHeader
        title="FIND A HUMANOID / GUIDED REQUIREMENT MATCHING"
        fields={[{ label: "STATUS", value: "PLANNED — BUYER INTENT STAGE" }]}
      />
      <div className="wrap wrap--narrow">
        <SiteNav active="find" />

        <div className="pagebar">
          <div>
            <SectionIndex>FIND A HUMANOID / GUIDED REQUIREMENT MATCHING</SectionIndex>
            <h1>Find a humanoid</h1>
          </div>
          <span className="ho-badge ho-badge--caution">
            COMING IN BUYER INTENT / MATCHING
          </span>
        </div>

        <section className="blk" style={{ borderTop: 0 }}>
          <p className="prose" style={{ fontSize: "1.05rem" }}>
            A guided requirement wizard is planned for the Buyer Intent stage. It
            will capture use case, payload, autonomy, budget, region and commercial
            preferences, then return explainable ranked matches grounded in the
            evidence-backed catalogue.
          </p>
          <p className="note" style={{ marginTop: 12 }}>
            // Nothing here persists data or computes a score.
          </p>
          <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
            <Link className="btn btn--signal" href="/robots">
              <GraphicMarker /> Browse the catalogue →
            </Link>
          </div>
        </section>

        {/* Non-interactive architectural preview: static text, no inputs. */}
        <section className="blk" style={{ marginBottom: "var(--ho-sp-8)" }}>
          <div className="blk-head">
            <div>
              <SectionIndex>PREVIEW — FUTURE REQUIREMENT FLOW</SectionIndex>
              <h2>The planned 12-step flow</h2>
            </div>
            <SystemLabel>NON-INTERACTIVE · NO DATA CAPTURE</SystemLabel>
          </div>
          <ol
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "var(--ho-sp-3)",
            }}
          >
            {FUTURE_STEPS.map((step, i) => (
              <li
                key={step}
                className="ho-leader"
                style={{
                  border: "var(--ho-rule-hair) solid var(--ho-line-soft)",
                  padding: "10px 12px",
                }}
              >
                <span style={{ color: "var(--ho-text-faint)" }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="fill" />
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <p className="note" style={{ marginTop: "var(--ho-sp-4)" }}>
            // Requirement capture, scoring, match results and lead capture are
            delivered by later workstreams (Buyer Intent / Matching). This page is
            a reference only.
          </p>
        </section>
      </div>
      <SiteFooter />
    </>
  );
}
