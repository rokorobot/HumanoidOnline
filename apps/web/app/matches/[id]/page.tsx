// Match Results — /matches/[id] (WS6). Server component: fetching the matches
// triggers deterministic matching on the first request (persisted server-side),
// then renders the ranked, explainable result cards. Zero survivors renders an
// honest "no match" state with the dominant eliminating constraint. Requesting
// commercial help is reserved for WS7 — there is no form and no lead write here.
import Link from "next/link";

import { MatchCard } from "@/components/MatchCard";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { getMatches } from "@/lib/api-client";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Match results — HumanoidOnline",
};

export default async function MatchesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getMatches(id);
  const n = data.matches.length;
  const compareHref = `/compare?ids=${data.matches.map((m) => m.robot.slug).join(",")}`;
  const adjustHref = `/find-a-humanoid?from=${encodeURIComponent(id)}`;

  return (
    <>
      <SystemHeader
        title="MATCH RESULTS / DETERMINISTIC"
        fields={[
          { label: "MATCHES", value: n },
          { label: "EXCLUDED", value: data.excluded_count },
        ]}
      />
      <div className="wrap wrap--narrow">
        <SiteNav active="find" />

        <div className="pagebar">
          <div>
            <SectionIndex>RESULTS — DETERMINISTIC MATCH_RESULT</SectionIndex>
            <h1>{n > 0 ? `${n} humanoid${n > 1 ? "s" : ""} matched` : "No match"}</h1>
          </div>
          <Link className="btn btn--ghost" href={adjustHref}>
            Adjust requirements
          </Link>
        </div>

        {n === 0 ? (
          <section className="wz-confirm" aria-live="polite">
            <SectionIndex>NO MATCH — HONEST ELIMINATION</SectionIndex>
            <h2 className="wz-confirm-title">No humanoid matched</h2>
            <p className="prose">{data.no_match_explanation}</p>
            <p className="note">
              {/* We still capture the demand; lead capture arrives in WS7. */}
              // We still track this demand. Adjust your requirements or browse the catalogue.
            </p>
            <div className="actions" style={{ marginTop: "var(--ho-sp-5)" }}>
              <Link className="btn btn--signal" href={adjustHref}>
                Adjust requirements →
              </Link>
              <Link className="btn" href="/robots">
                Browse robots
              </Link>
            </div>
          </section>
        ) : (
          <>
            {n >= 2 && (
              <div className="results-head">
                <span className="count">
                  <b>{n}</b> RANKED MATCHES
                </span>
                <Link className="btn btn--ghost" href={compareHref}>
                  Compare these →
                </Link>
              </div>
            )}
            <div className="matchlist">
              {data.matches.map((m) => (
                <MatchCard key={m.robot.slug} match={m} />
              ))}
            </div>
            <p className="note" style={{ marginTop: "var(--ho-sp-5)" }}>
              // Requesting commercial help arrives in a later step — no contact is
              captured here.
            </p>
          </>
        )}
      </div>
      <SiteFooter />
    </>
  );
}
