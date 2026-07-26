// Match Results — /matches/[id] (WS6 + WS7). Server component: fetching the
// matches triggers deterministic matching on the first request (persisted
// server-side), then renders the ranked, explainable result cards. WS7 adds the
// commercial capture surfaces (per-card, whole-shortlist, and the zero-match
// "tell us anyway" path) via a client wrapper — a modal over this page, no new
// route. The server never reruns matching for a lead; it validates the buyer's
// selection against the persisted match_result.
import Link from "next/link";

import { MatchesCommercial } from "@/components/MatchesCommercial";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { getMatches, listRegions } from "@/lib/api-client";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Match results",
};

export default async function MatchesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [data, countries] = await Promise.all([
    getMatches(id),
    listRegions({ type: "COUNTRY" }),
  ]);
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

        <MatchesCommercial
          requirementId={id}
          matches={data.matches}
          noMatchExplanation={data.no_match_explanation ?? null}
          countries={countries}
          compareHref={compareHref}
          adjustHref={adjustHref}
        />
      </div>
    </>
  );
}
