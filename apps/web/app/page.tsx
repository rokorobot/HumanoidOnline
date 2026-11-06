// Home (highly experimental band). Hero claim is fixed. All numbers come from
// /api/market-snapshot and /api/robots at runtime — no illustrative values.
import type { Metadata } from "next";
import Link from "next/link";

import {
  getMarketSnapshot,
  listManufacturers,
  listRobots,
  listUseCases,
} from "@/lib/api-client";
import { buildHomeJsonLd } from "@/lib/entity";
import { formatObservedDate, formatRobotCoverage } from "@/lib/format";
import { absoluteUrl } from "@/lib/site";
import { DotMatrix, GraphicMarker } from "@/components/GraphicMarker";
import { MachineCode } from "@/components/MachineCode";
import { ManufacturerCard } from "@/components/ManufacturerCard";
import { HomeOfferBoard } from "@/components/HomeOfferBoard";
import { SectionIndex } from "@/components/SectionIndex";
import { DarkNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";
import { UseCaseTile } from "@/components/UseCaseTile";

export const dynamic = "force-dynamic";

// Title and description come from the root layout; the home page adds only its canonical.
export function generateMetadata(): Metadata {
  return { alternates: { canonical: absoluteUrl("/") } };
}

export default async function HomePage() {
  const [snapshot, robotPage, useCasePage, manufacturerPage, ...modeTotals] = await Promise.all([
    getMarketSnapshot(),
    listRobots({ limit: 100, sort: "name" }),
    listUseCases({ limit: 100 }),
    listManufacturers({ limit: 100 }),
    // DR-UI2 board tabs: live per-mode totals from the same cached list read.
    ...HOME_MODES.map((m) =>
      listRobots({ transaction_type: [m.mode], limit: 1 }).then((p) => p.total),
    ),
  ]);

  // Catalogue freshness: the last committed change to public catalogue content,
  // recorded by the database (never a deploy, schedule or evidence-observation date).
  const catalogueUpdated = formatObservedDate(snapshot.latest_catalogue_updated_at);
  // "Obtainable now" = robots with a current commercially-accessible offer
  // (available_modes computed by the canonical predicate). Never re-derived here.
  // DR-UI2: shown as a board (name order — a display order, never a ranking).
  const obtainable = robotPage.items
    .filter((r) => r.available_modes.length > 0)
    .slice(0, 8);
  const modeTabs = HOME_MODES.map((m, i) => ({ ...m, count: modeTotals[i] }));
  const accessible = snapshot.commercially_accessible;

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(buildHomeJsonLd()) }}
      />
      <SystemHeader
        title="HUMANOIDONLINE / COMMERCIAL INTELLIGENCE"
        fields={[
          { value: snapshot.total_tracked, label: "" },
          { value: "PLATFORMS TRACKED", label: "" },
          ...(catalogueUpdated
            ? [{ label: "CATALOGUE UPDATED", value: catalogueUpdated }]
            : []),
        ]}
      />

      {/* HERO (dark) */}
      <div className="hero-shell ho-dark ho-scan">
        <div className="hero-inner">
          <div className="topbar topbar--nav">
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
            <div className="seg logo">
              <Link href="/">
                <b>HUMANOIDONLINE</b>
              </Link>
            </div>
            <div className="seg mid">MARKET INTELLIGENCE PLATFORM</div>
            <div className="seg">
              <DarkNav active={null} />
            </div>
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
          </div>

          <div className="hero-body">
            <div className="hero-side l">
              <span className="ho-vertical">
                PROJECT: HUMANOID MARKET INTELLIGENCE
              </span>
            </div>
            <div className="hero-side r">
              <span className="ho-vertical">BUILT FOR OPERATORS</span>
            </div>

            <div className="hero-kicker">
              <SectionIndex>00 — THE HUMANOID MARKET, INSTRUMENTED</SectionIndex>
              <span className="ho-reg-box">&reg;</span>
            </div>

            {/* DR-UI2: the headline leads with a live, server-rendered fact (never a
                placeholder 0); the fixed claim stays inside the same H1. */}
            <h1 className="hero-h1">
              <span className="hero-count">
                <span className="n">{accessible}</span> {accessible === 1 ? "humanoid" : "humanoids"}{" "}
                <br />
                obtainable now
              </span>{" "}
              <span className="hero-claim">
                Find the right <em>humanoid.</em>
              </span>
            </h1>

            <div className="subrow">
              <div className="cell">
                Compare capabilities, commercial availability, pricing and
                deployment evidence across the humanoid-robot market.
              </div>
              <div className="cell">
                Maturity, obtainability and evidence kept as three independent
                facts. Unknown stays unknown — no fabricated numbers.
              </div>
              <Link className="act" href="/find-a-humanoid">
                Find a
                <br />
                Humanoid
              </Link>
            </div>

            <div className="hero-tools">
              <div>
                <form className="searchbar" action="/robots" method="get" role="search">
                  <input
                    type="text"
                    name="q"
                    placeholder="SEARCH ROBOTS, MANUFACTURERS, CAPABILITIES…"
                    aria-label="Search robots"
                  />
                  <button type="submit">Search</button>
                </form>
                <div className="hero-actions">
                  <Link className="btn" href="/robots">
                    <GraphicMarker /> Explore Robots
                  </Link>
                  <Link className="btn btn--signal" href="/find-a-humanoid">
                    <GraphicMarker /> Find a Humanoid
                  </Link>
                </div>
              </div>
              <div className="readout">
                <Leader
                  k="ROBOTS"
                  v={formatRobotCoverage(snapshot.total_tracked, snapshot.total_published)}
                />
                <Leader
                  k="MAKERS"
                  v={formatRobotCoverage(
                    snapshot.manufacturers_tracked,
                    snapshot.manufacturers_published,
                  )}
                />
                <Leader
                  k="ACCESSIBLE"
                  v={`${snapshot.commercially_accessible} NOW`}
                />
                <Leader
                  k="RENTAL"
                  v={snapshot.rental_offers_present ? "OFFERS PRESENT" : "NONE CURRENT"}
                />
                <Leader k="UPDATED" v={catalogueUpdated ?? "UNKNOWN"} />
              </div>
            </div>

            <section className="hero-board" aria-labelledby="obtainable-now">
              <div className="hero-board__head">
                <SectionIndex>01 — COMMERCIAL ACCESS</SectionIndex>
                <h2 id="obtainable-now" className="ho-section-title">
                  Obtainable now
                </h2>
                <SystemLabel>
                  <abbr title="Current offers that are not marked unavailable or discontinued">
                    CURRENT CONFIRMED OFFERS
                  </abbr>
                </SystemLabel>
              </div>
              <HomeOfferBoard robots={obtainable} tabs={modeTabs} />
            </section>
          </div>
        </div>
      </div>

      {/* DR-UI2: TELL US THE JOB — the requirement brief as a pass. Real links into the
          deterministic wizard (prefilled use case via ?use_case=). */}
      <section className="block">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>02 — MATCH BY REQUIREMENT</SectionIndex>
              <h2 className="ho-section-title">Tell us the job</h2>
            </div>
            <SystemLabel>Same input, same result. No account needed.</SystemLabel>
          </div>
          <div className="brief">
            <div className="brief-pass">
              <div className="brief-pass__form">
                <p className="brief-pass__t">Requirement brief</p>
                <p className="ho-syslabel">Start with the job. Four short steps, then a deterministic match.</p>
                <ul className="brief-uc" aria-label="Start with a use case">
                  {useCasePage.items.slice(0, 8).map((u) => (
                    <li key={u.slug}>
                      <Link href={`/find-a-humanoid?use_case=${encodeURIComponent(u.slug)}`}>{u.name}</Link>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="brief-pass__stub ho-dark">
                <p className="ho-syslabel">Your brief</p>
                <ol>
                  <li>Use case</li>
                  <li>How you want it: buy, rent, lease or RaaS</li>
                  <li>Region and budget</li>
                  <li>Contact</li>
                </ol>
                <span className="lead-stub__code" aria-hidden="true" />
                <Link className="btn btn--signal" href="/find-a-humanoid">
                  <GraphicMarker /> Start the brief
                </Link>
              </div>
            </div>
            <ol className="brief-why">
              <li>
                <b>Three facts, never one flag.</b> Maturity, obtainability and evidence stay separate.
              </li>
              <li>
                <b>Unknown stays unknown.</b> &ldquo;Price on request&rdquo; and &ldquo;no published price&rdquo; are different answers.
              </li>
              <li>
                <b>Every fact has a source.</b> Prices, status and availability link to where they came from.
              </li>
              <li>
                <b>Manufacturer-neutral.</b> No maker can buy a better ranking. Matching is a pure, testable function.
              </li>
            </ol>
          </div>
        </div>
      </section>

      {/* EXPLORE BY USE CASE (live /api/use-cases) */}
      <section className="block">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>03 — EXPLORE BY USE CASE</SectionIndex>
              <h2 className="ho-section-title">Explore by use case</h2>
            </div>
            <SystemLabel>{useCasePage.total} APPLICATIONS</SystemLabel>
          </div>
          {useCasePage.items.length > 0 ? (
            <div className="apps">
              {useCasePage.items.slice(0, 8).map((u, i) => (
                <UseCaseTile key={u.slug} useCase={u} index={i + 1} />
              ))}
            </div>
          ) : (
            <p className="empty-state">No use cases on record.</p>
          )}
        </div>
      </section>

      {/* ORANGE ALERT STRIP (loud status only) */}
      <section className="ho-orange">
        <div className="wrap alert-strip">
          <div className="big">
            <DotMatrix count={6} /> HUMANOID MARKET: ACTIVE
          </div>
          <div className="facts">
            {snapshot.commercially_accessible} COMMERCIALLY ACCESSIBLE ·{" "}
            {snapshot.in_deployment_or_pilot} IN PILOT/DEPLOYMENT ·{" "}
            {snapshot.rental_offers_present
              ? "LIVE RENTAL OFFERS PRESENT"
              : "NO LIVE RENTAL OFFERS"}
          </div>
          <MachineCode href="/robots" inverted>
            OPEN CATALOGUE →
          </MachineCode>
        </div>
      </section>

      {/* WHO BUILDS THEM (live /api/manufacturers) */}
      <section className="block">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>04 — WHO BUILDS THEM</SectionIndex>
              <h2 className="ho-section-title">Who builds them</h2>
            </div>
            <SystemLabel>{manufacturerPage.total} TRACKED</SystemLabel>
          </div>
          {manufacturerPage.items.length > 0 ? (
            <div className="mfr-row">
              {manufacturerPage.items.slice(0, 8).map((m) => (
                <ManufacturerCard key={m.slug} manufacturer={m} />
              ))}
            </div>
          ) : (
            <p className="empty-state">No manufacturers on record.</p>
          )}
        </div>
      </section>

      {/* MARKET SNAPSHOT (dark) */}
      <section className="snapshot ho-dark ho-scan">
        <div className="wrap">
          <SectionIndex>05 — MARKET SNAPSHOT</SectionIndex>
          <div className="snap-grid">
            <Snap
              n={snapshot.total_tracked}
              label="Humanoids tracked"
              sub={`${snapshot.total_published} published profiles`}
            />
            <Snap
              n={snapshot.commercially_accessible}
              label="Commercially accessible"
              signal
            />
            <Snap n={snapshot.in_deployment_or_pilot} label="In pilot / deployment" />
            <Snap
              n={snapshot.manufacturers_tracked}
              label="Manufacturers tracked"
              sub={`${snapshot.manufacturers_published} with published profiles`}
            />
          </div>
          <hr
            className="ho-rule"
            style={{ borderColor: "var(--ho-grey-800)", marginTop: "var(--ho-sp-6)" }}
          />
          <p
            className="ho-syslabel"
            style={{ marginTop: "var(--ho-sp-4)", maxWidth: "72ch", lineHeight: 1.8 }}
          >
            {catalogueUpdated ? (
              <>CATALOGUE UPDATED {catalogueUpdated}. </>
            ) : null}
            Every commercial fact carries an evidence source and confidence level —
            no commercial fact without evidence.
          </p>
        </div>
      </section>

      {/* DR-UI2: ONE RECORD, FOUR PLATFORMS — real platform status only. */}
      <section className="block eco-section ho-dark">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>06 — ONE RECORD, FOUR PLATFORMS</SectionIndex>
              <h2 className="ho-section-title">From research to robot on site</h2>
            </div>
            <SystemLabel>HumanoidOnline is the evidence layer of the Humanoid.Company family</SystemLabel>
          </div>
          <ul className="eco-grid">
            {ECOSYSTEM.map((p) => (
              <li key={p.code} className={`eco-card eco-card--${p.tone}`}>
                <span className="eco-card__code" aria-hidden="true">{p.code}</span>
                <h3>{p.name}</h3>
                <p>{p.job}</p>
                {p.href ? (
                  <a href={p.href}>{p.status} ↗</a>
                ) : (
                  <span className="eco-card__status">{p.status}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>

    </>
  );
}

const HOME_MODES = [
  { mode: "PURCHASE", label: "Purchase" },
  { mode: "RENTAL", label: "Rental" },
  { mode: "RAAS", label: "RaaS" },
  { mode: "LEASE", label: "Lease" },
];

const ECOSYSTEM: { code: string; name: string; job: string; status: string; tone: string; href?: string }[] = [
  { code: "HO", name: "HumanoidOnline", job: "Intelligence and comparison: catalogue, evidence, prices.", status: "You are here", tone: "ho" },
  { code: "RH", name: "RentHumanoid", job: "Live board of humanoids you can rent, lease or hire as a service.", status: "Live · renthumanoid.com", tone: "rh", href: "https://renthumanoid.com/" },
  { code: "HM", name: "HumanoidMart", job: "Buy a humanoid robot from a named seller.", status: "Live · humanoidmart.com", tone: "hm", href: "https://humanoidmart.com/" },
  { code: "HL", name: "HumanoidLease", job: "Long-term leasing and robot-as-a-service structures.", status: "In development", tone: "soon" },
];

function Leader({ k, v }: { k: string; v: string }) {
  return (
    <div className="ho-leader">
      <span>{k}</span>
      <span className="fill" />
      <span>{v}</span>
    </div>
  );
}

function Snap({
  n,
  label,
  signal,
  sub,
}: {
  n: number;
  label: string;
  signal?: boolean;
  // Optional second line: the published subset behind a tracked headline.
  sub?: string;
}) {
  return (
    <div className="snap">
      <div className={signal ? "num sig" : "num"}>{n}</div>
      <div className="lbl ho-syslabel">{label}</div>
      {sub ? <div className="lbl ho-syslabel">{sub}</div> : null}
    </div>
  );
}
