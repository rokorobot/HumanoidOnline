// Home (highly experimental band). Hero claim is fixed. All numbers come from
// /api/market-snapshot and /api/robots at runtime — no illustrative values.
import Link from "next/link";

import { getMarketSnapshot, listRobots } from "@/lib/api-client";
import { formatObservedDate } from "@/lib/format";
import { DotMatrix, GraphicMarker } from "@/components/GraphicMarker";
import { MachineCode } from "@/components/MachineCode";
import { RobotCard } from "@/components/RobotCard";
import { SectionIndex } from "@/components/SectionIndex";
import { DarkNav, SiteFooter } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [snapshot, robotPage] = await Promise.all([
    getMarketSnapshot(),
    listRobots({ limit: 24, sort: "name" }),
  ]);

  const observed = formatObservedDate(snapshot.latest_observed_at);
  // "Obtainable now" = robots with a current commercially-accessible offer
  // (available_modes computed by the canonical predicate). Never re-derived here.
  const obtainable = robotPage.items
    .filter((r) => r.available_modes.length > 0)
    .slice(0, 4);

  return (
    <>
      <SystemHeader
        title="HUMANOIDONLINE / COMMERCIAL INTELLIGENCE"
        fields={[
          { value: snapshot.total_tracked, label: "" },
          { value: "PLATFORMS TRACKED", label: "" },
          ...(observed ? [{ label: "DATA OBSERVED", value: observed }] : []),
        ]}
      />

      {/* HERO (dark) */}
      <div className="hero-shell ho-dark ho-scan">
        <div className="hero-inner">
          <div className="topbar">
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

            <h1>
              Find the right
              <br />
              <em>humanoid.</em>
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
                  v={`${snapshot.total_tracked} TRACKED`}
                />
                <Leader
                  k="MAKERS"
                  v={`${snapshot.manufacturers} MANUFACTURERS`}
                />
                <Leader
                  k="ACCESSIBLE"
                  v={`${snapshot.commercially_accessible} NOW`}
                />
                <Leader
                  k="RENTAL"
                  v={snapshot.rental_offers_present ? "OFFERS PRESENT" : "NONE CURRENT"}
                />
                <Leader k="UPDATED" v={observed ?? "UNKNOWN"} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* OBTAINABLE NOW */}
      <section className="block">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>01 — COMMERCIAL ACCESS</SectionIndex>
              <h2 className="ho-section-title">Obtainable now</h2>
            </div>
            <SystemLabel>
              <abbr title="Predicate: is_current AND status ∉ {NOT_AVAILABLE, DISCONTINUED}">
                CURRENT CONFIRMED OFFERS
              </abbr>
            </SystemLabel>
          </div>
          {obtainable.length > 0 ? (
            <div className="card-row">
              {obtainable.map((r) => (
                <RobotCard key={r.slug} robot={r} />
              ))}
            </div>
          ) : (
            <p className="empty-state">
              No robots currently expose a commercially-accessible offer.
            </p>
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

      {/* MARKET SNAPSHOT (dark) */}
      <section className="snapshot ho-dark ho-scan">
        <div className="wrap">
          <SectionIndex>02 — MARKET SNAPSHOT</SectionIndex>
          <div className="snap-grid">
            <Snap n={snapshot.total_tracked} label="Humanoids tracked" />
            <Snap
              n={snapshot.commercially_accessible}
              label="Commercially accessible"
              signal
            />
            <Snap n={snapshot.in_deployment_or_pilot} label="In pilot / deployment" />
            <Snap n={snapshot.manufacturers} label="Manufacturers" />
          </div>
          <hr
            className="ho-rule"
            style={{ borderColor: "var(--ho-grey-800)", marginTop: "var(--ho-sp-6)" }}
          />
          <p
            className="ho-syslabel"
            style={{ marginTop: "var(--ho-sp-4)", maxWidth: "72ch", lineHeight: 1.8 }}
          >
            {observed ? (
              <>DATA OBSERVED {observed}. </>
            ) : null}
            Every commercial fact carries an evidence source and confidence level —
            no commercial fact without evidence.
          </p>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}

function Leader({ k, v }: { k: string; v: string }) {
  return (
    <div className="ho-leader">
      <span>{k}</span>
      <span className="fill" />
      <span>{v}</span>
    </div>
  );
}

function Snap({ n, label, signal }: { n: number; label: string; signal?: boolean }) {
  return (
    <div className="snap">
      <div className={signal ? "num sig" : "num"}>{n}</div>
      <div className="lbl ho-syslabel">{label}</div>
    </div>
  );
}
