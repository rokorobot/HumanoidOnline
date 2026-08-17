// Catalogue /robots — controlled band. Filter rail + result RobotCards + sort,
// all wired to /api/robots. URL-addressable: filters live in searchParams and
// are forwarded verbatim to the API. No facts are computed here.
import { notFound, redirect } from "next/navigation";

import { listRobots } from "@/lib/api-client";
import {
  asArray,
  asString,
  canonicalizePriceParams,
  toQueryString,
  toRobotListParams,
  type RawSearchParams,
} from "@/lib/search-params";
import { resolveAppEnv } from "@/lib/site";
import { CompareBar } from "@/components/CompareBar";
import { FilterPanel } from "@/components/FilterPanel";
import { RobotCard } from "@/components/RobotCard";
import Link from "next/link";

import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SortSelect } from "@/components/SortSelect";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

// The review surface exists only in relaxed environments (the API does not mount
// its route elsewhere), so the link is rendered only where it would work.
const DISCOVERY_REVIEW_VISIBLE = ["development", "test"].includes(resolveAppEnv());

// WS8.5 / R22 — specific per-route title (no generic root inheritance).
export const metadata = {
  title: "Robot Catalogue",
  description:
    "Browse every verified humanoid robot — capabilities, commercial status, availability and evidence, kept as three independent facts.",
};

export default async function RobotsPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const sp = await searchParams;

  // Canonicalize the price pair BEFORE querying, so the address bar and the API
  // request can never state different denominations. An incomplete pair is
  // redirected once into canonical form (notably the no-JS GET form, which
  // submits `price_max` with no currency field); a currency this USD-only UI
  // cannot honour is refused outright rather than reinterpreted as USD or
  // dropped — dropping it would silently widen the result set, which is the
  // failure mode the whole price contract exists to prevent.
  const priceUrl = canonicalizePriceParams(sp);
  if (priceUrl.action === "reject") notFound();
  if (priceUrl.action === "redirect") {
    redirect(`/robots${toQueryString(priceUrl.params)}`);
  }

  const apiParams = toRobotListParams(sp);
  const page = await listRobots({ ...apiParams, limit: 100 });

  const compareSlugs = (asString(sp.compare) ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // Toggle a slug in the compare tray, preserving all current filter params.
  function compareHref(slug: string): string {
    const set = new Set(compareSlugs);
    if (set.has(slug)) set.delete(slug);
    else if (set.size < 4) set.add(slug);
    const next: RawSearchParams = { ...sp };
    const list = Array.from(set);
    if (list.length) next.compare = list.join(",");
    else delete next.compare;
    return `/robots${toQueryString(next)}`;
  }

  const activeFilterCount =
    asArray(sp.commercial_status).length +
    asArray(sp.transaction_type).length +
    ["region", "mobility", "autonomy_min", "payload_min", "height_min", "price_max",
      "has_sdk", "ros_support", "developer_edition", "has_manipulation", "q"].filter(
      (k) => asString(sp[k]),
    ).length;

  return (
    <>
      <SystemHeader
        title="HUMANOID MARKET INDEX"
        fields={[
          { value: page.total, label: "" },
          { value: "PLATFORMS TRACKED", label: "" },
          { label: "SHOWING", value: page.items.length },
        ]}
      />
      <div className="wrap">
        <SiteNav active="robots" />

        <div className="pagebar">
          <div>
            <SectionIndex>CATALOGUE — ALL TRACKED HUMANOIDS</SectionIndex>
            <h1>Robot catalogue</h1>
          </div>
          <span className="meta">
            3 DIMENSIONS: MATURITY / OBTAINABILITY / EVIDENCE — INDEPENDENT
          </span>
        </div>

        {/* DATA-D1 operator review link. Deliberately here rather than in
            SiteNav: the review queue holds UNVERIFIED candidates, and giving it
            equal navigation authority to the catalogue would blur the canonical /
            noncanonical boundary this page is the canonical side of. Rendered only
            where the surface exists (relaxed environments), so production shows
            nothing. */}
        {DISCOVERY_REVIEW_VISIBLE && (
          <p className="meta" style={{ marginBottom: "var(--ho-sp-4)" }}>
            <Link href="/discovery-review">
              DISCOVERY REVIEW — UNVERIFIED CANDIDATES (INTERNAL) →
            </Link>
          </p>
        )}

        <div className="layout">
          <FilterPanel params={sp} resultCount={page.total} />

          <section aria-label="Results">
            <div className="results-head">
              <div className="count">
                RESULTS <b>{page.items.length}</b> / {page.total} TRACKED
                {activeFilterCount > 0 && (
                  <SystemLabel className="" >
                    {" "}· {activeFilterCount} FILTER{activeFilterCount === 1 ? "" : "S"} ACTIVE
                  </SystemLabel>
                )}
              </div>
              <SortSelect params={sp} />
            </div>

            {page.items.length > 0 ? (
              <div className="grid">
                {page.items.map((r) => (
                  <RobotCard
                    key={r.slug}
                    robot={r}
                    compareHref={compareHref(r.slug)}
                    inCompare={compareSlugs.includes(r.slug)}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <p>No robots match the current filters.</p>
                <SystemLabel>Adjust or reset the filter rail.</SystemLabel>
              </div>
            )}

            <p className="note">
              {"// PRICE STATES: PUBLIC · FROM · RANGE · ESTIMATED · QUOTE_ONLY · UNKNOWN."}
              <br />
              {'// QUOTE_ONLY ("Price on request") ≠ UNKNOWN ("No confirmed pricing"). Absence of availability rows renders "Availability unknown", never NOT_AVAILABLE.'}
              <br />
              {"// Every price/status/availability on a record carries an evidence source — open a robot to drill in."}
            </p>
          </section>
        </div>
      </div>
      <CompareBar slugs={compareSlugs} />
    </>
  );
}
