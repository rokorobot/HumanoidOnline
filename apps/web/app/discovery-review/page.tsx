// DATA-D1 operator review surface — NONCANONICAL, read-only.
//
// This page exists so a human can look at what acquisition has found and decide
// what to trace. It is NOT the catalogue, and every design decision here is made
// against one risk: that a reviewer (or a screenshot of this page) treats an
// unverified candidate as a HumanoidOnline fact.
//
// So it deliberately renders NO product surface — no specs, no price, no
// availability, no maturity badge, no imagery, no Compare, no Buy/Rent/Lease, no
// buyer-intent action. Those controls all mean "this is a real, verified option",
// and none of these records has earned that yet.
//
// Fail-closed: the API mounts /api/discovery-review only in relaxed environments,
// and this page refuses to render outside them too. Two tiers, same default.
import Link from "next/link";
import { notFound } from "next/navigation";

import { listDiscoveryCandidates } from "@/lib/api-client";
import { resolveAppEnv } from "@/lib/site";
import { SectionIndex } from "@/components/SectionIndex";
import { SystemHeader } from "@/components/SystemHeader";
import type { DiscoveryCandidateReview } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Discovery Review",
  description:
    "Internal review of unverified discovery candidates. Not the verified catalogue.",
  // Never index an operator surface carrying unverified records.
  robots: { index: false, follow: false },
};

const RELAXED = new Set(["development", "test"]);

/** Group by manufacturer, preserving the API's alphabetical order. */
function byManufacturer(
  items: DiscoveryCandidateReview[],
): [string, DiscoveryCandidateReview[]][] {
  const groups = new Map<string, DiscoveryCandidateReview[]>();
  for (const item of items) {
    const key = item.candidate_manufacturer ?? "UNKNOWN MANUFACTURER";
    const existing = groups.get(key);
    if (existing) existing.push(item);
    else groups.set(key, [item]);
  }
  return [...groups.entries()];
}

export default async function DiscoveryReviewPage() {
  // The same gate the API applies, on the page that consumes it. A strict
  // environment should not have a route here at all, rather than a route that
  // renders an error.
  if (!RELAXED.has(resolveAppEnv())) notFound();

  const page = await listDiscoveryCandidates({ limit: 100 });
  const groups = byManufacturer(page.items);

  return (
    <>
      <SystemHeader
        title="DISCOVERY REVIEW — UNVERIFIED"
        fields={[
          { value: page.total, label: "" },
          { value: "CANDIDATES", label: "" },
        ]}
      />
      <div className="wrap">
        {/* Deliberately NOT SiteNav: this is an operator surface, and giving it
            the same navigation authority as the catalogue is exactly how the
            canonical / noncanonical boundary gets blurred. A plain return link
            to the verified catalogue instead. */}
        <p className="meta" style={{ marginTop: "var(--ho-sp-4)" }}>
          <Link href="/robots">← VERIFIED ROBOT CATALOGUE</Link>
        </p>

        <div className="pagebar">
          <div>
            <SectionIndex>DATA-D1 — DISCOVERY QUEUE</SectionIndex>
            <h1>Discovery review</h1>
          </div>
          <span className="meta">
            {page.total} CANDIDATES · {groups.length} MANUFACTURERS
          </span>
        </div>

        {/* The warning is a first-class part of the page, not a footnote. */}
        <div
          role="note"
          aria-label="Unverified records"
          data-testid="unverified-warning"
          style={{
            border: "1px solid var(--ho-rule)",
            borderLeft: "3px solid var(--ho-text)",
            padding: "var(--ho-sp-4)",
            marginBottom: "var(--ho-sp-6)",
          }}
        >
          <p style={{ margin: 0, fontWeight: 600 }}>
            Discovery candidates for manual review.
          </p>
          <p style={{ margin: "var(--ho-sp-2) 0 0" }}>
            These records are <strong>not verified catalogue entries</strong> and
            cannot be used for comparison or commercial decisions until they pass
            trace and promotion gates.
          </p>
          <p className="meta" style={{ margin: "var(--ho-sp-2) 0 0" }}>
            Specifications, prices, commercial availability, maturity and imagery
            have <strong>not</strong> been confirmed for any record on this page.
          </p>
        </div>

        {page.total === 0 && (
          <p className="empty-state" data-testid="empty-state">
            No discovery candidates on record. Load a bootstrap dataset to
            populate the review queue.
          </p>
        )}

        {groups.map(([maker, candidates]) => (
          <section key={maker} style={{ marginBottom: "var(--ho-sp-6)" }}>
            <h2 className="ho-section-index" style={{ marginBottom: "var(--ho-sp-2)" }}>
              {maker} · {candidates.length}
            </h2>
            <ul
              style={{ listStyle: "none", margin: 0, padding: 0 }}
              data-testid={`group-${maker}`}
            >
              {candidates.map((candidate) => (
                <li
                  key={candidate.id}
                  data-testid="candidate-row"
                  style={{
                    borderTop: "1px solid var(--ho-rule)",
                    padding: "var(--ho-sp-3) 0",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "var(--ho-sp-3)",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                  }}
                >
                  <div>
                    <strong style={{ fontSize: "1.05rem" }}>
                      {candidate.candidate_name ?? "UNNAMED CANDIDATE"}
                    </strong>{" "}
                    <span className="meta">{candidate.candidate_manufacturer}</span>
                    <div className="meta">
                      <code>{candidate.external_ref}</code>
                      {" · "}
                      {candidate.source_name} ({candidate.source_class})
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: "var(--ho-sp-2)", flexWrap: "wrap" }}>
                    {/* Queue state, rendered verbatim. NOT StatusBadge: that
                        component encodes commercial MATURITY, and a candidate has
                        none — reusing it would state a fact we do not have. */}
                    <span className="ho-bracket ho-state">{candidate.status}</span>
                    <span className="ho-bracket ho-state">{candidate.identity_status}</span>
                    <span className="ho-bracket ho-state">{candidate.trace_state}</span>
                  </div>

                  <div className="meta" style={{ flexBasis: "100%" }}>
                    {candidate.official_url ? (
                      <a
                        href={candidate.official_url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                      >
                        OFFICIAL URL LEAD ↗
                      </a>
                    ) : (
                      // UNKNOWN stays UNKNOWN: no lead means nothing to trace
                      // yet, and an empty or invented link would be worse.
                      <span>NO OFFICIAL URL LEAD RECORDED</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}

        <p className="meta" style={{ marginTop: "var(--ho-sp-6)" }}>
          Promotion to the catalogue requires a confirmed authoritative trace and
          human approval (DATA-D1 gates P2 / P8). Nothing on this page can be
          promoted from here.
        </p>
      </div>
    </>
  );
}
