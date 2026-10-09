// Catalogue /robots — controlled band. Filter rail + result RobotCards + sort,
// all wired to /api/robots. URL-addressable: filters live in searchParams and
// are forwarded verbatim to the API. No facts are computed here.
import { notFound, redirect } from "next/navigation";

import { listManufacturers, listRobots, listUseCases } from "@/lib/api-client";
import { partlyUninterpreted, resolveCatalogueQuery } from "@/lib/catalogue-query";
import {
  asArray,
  asString,
  canonicalizePriceParams,
  countActiveFilters,
  toQueryString,
  toRobotListParams,
  type RawSearchParams,
} from "@/lib/search-params";
import { resolveAppEnv } from "@/lib/site";
import { CompareBar } from "@/components/CompareBar";
import { FilterPanel } from "@/components/FilterPanel";
import { RobotCard } from "@/components/RobotCard";
import Link from "next/link";

import { InterpretationBar } from "@/components/InterpretationBar";
import { SearchBox } from "@/components/SearchBox";
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

  // UX-02A: the free-text `q` is interpreted deterministically on EVERY render (the URL
  // stays the single source of truth). Vocabulary comes from the existing cached reads and
  // is only fetched when there is a query.
  const rawQ = (asString(sp.q) ?? "").trim();
  const vocab = rawQ
    ? await Promise.all([listManufacturers({ limit: 100 }), listUseCases({ limit: 100 })]).then(
        ([m, u]) => ({
          manufacturers: m.items.map((x) => ({ slug: x.slug, name: x.name })),
          useCases: u.items.map((x) => ({ slug: x.slug, name: x.name })),
        }),
      )
    : null;
  const cq = resolveCatalogueQuery(sp, vocab);
  const apiParams = toRobotListParams(cq.effective);
  const page = await listRobots({ ...apiParams, limit: 100 });
  const interp = cq.interpretation;
  const residualUnmatched = page.total === 0 && interp?.residual ? interp.residual.split(" ") : [];

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

  const activeFilterCount = countActiveFilters(sp);

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

        <SearchBox q={rawQ} />
        {interp && (
          <InterpretationBar
            text={interp.text}
            chips={cq.chips}
            base={toQueryString(Object.fromEntries(Object.entries(sp).filter(([k]) => k !== "q"))).slice(1)}
            residualUnmatched={residualUnmatched}
            unsupported={interp.unsupported}
            conflicts={[
              ...interp.conflicts,
              ...[...cq.overridden].map((k) => `The ${k.replace("_", " ")} filter in the URL differs from the search text, so the URL filter was used.`),
            ]}
            hasAppliedPrice={cq.chips.some((c) => c.kind === "price" && c.status === "applied")}
          />
        )}

        <div className="layout">
          <FilterPanel params={sp} resultCount={page.total} activeCount={activeFilterCount} />

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
              <div className="empty-state" data-testid="no-results">
                <p>No robots match the current filters.</p>
                {rawQ && (
                  <p>
                    You searched for <b>{"“"}{rawQ}{"”"}</b>.
                    {interp && interp.chips.length > 0 && (
                      <> It was read as: {cq.chips.map((c) => c.label + (c.status === "applied" ? "" : " (not applied)")).join("; ")}.</>
                    )}
                    {residualUnmatched.length > 0 && (
                      <> Not understood: {residualUnmatched.map((w) => `“${w}”`).join(", ")}.</>
                    )}
                  </p>
                )}
                {(partlyUninterpreted(cq) || residualUnmatched.length > 0) && (
                  <p>The query could not be fully interpreted, so some of it was not applied.</p>
                )}
                <p>
                  Zero matches means nothing in the catalogue matched these recorded facts, not that no
                  such robot exists.
                </p>
                <p>
                  <Link className="btn" href="/robots">
                    Clear search and filters
                  </Link>
                </p>
              </div>
            )}

            <p className="note">
              Each price or availability comes from one sourced offer. Unknown stays unknown, never
              zero or unavailable.
            </p>
          </section>
        </div>
      </div>
      <CompareBar
        slugs={compareSlugs}
        names={Object.fromEntries(page.items.map((r) => [r.slug, r.name]))}
      />
    </>
  );
}
