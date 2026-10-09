// Robot detail /robots/[slug] — identity header experimental, data disciplined.
// The key proof: three INDEPENDENT dimensions; all six price states incl.
// QUOTE_ONLY ≠ UNKNOWN; specs with explicit UNKNOWN; evidence drill-down with
// real source/dates/confidence/link. 404 -> notFound(). All facts from the API.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { findManufacturer, findRobot, listRegions } from "@/lib/api-client";
import { providerLabel, providerNamesFrom, type ProviderNames } from "@/lib/providers";
import { buildRobotJsonLd } from "@/lib/jsonld";
import { absoluteUrl } from "@/lib/site";
import {
  accessibleModes,
  commercialSummary,
  priceDisplayFromHeadline,
  selectHeadline,
} from "@/lib/commercial-summary";
import {
  enumLabel,
  availabilityLabel,
  autonomyLabel,
  confidenceLabel,
  mobilityLabel,
  priceTypeLabel,
  sourceTypeLabel,
  statusLabel,
} from "@/lib/labels";
import {
  formatDate,
  maturityIndex,
  MATURITY_LADDER,
  modeLabel,
} from "@/lib/format";
import type {
  Deployment,
  Evidence,
  ExtendedSpec,
  PricingOffer,
  RobotDetail,
} from "@/lib/types";
import { DetailComparisonLink } from "@/components/DetailComparisonLink";
import { AvailabilityMatrix } from "@/components/AvailabilityState";
import { CitationFacts } from "@/components/CitationFacts";
import { CommercialTriad } from "@/components/CommercialTriad";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { deriveModelCode } from "@/lib/model-code";
import { EvidenceStamp } from "@/components/EvidenceStamp";
import { GraphicMarker } from "@/components/GraphicMarker";
import { RequestAvailabilityButton } from "@/components/RequestAvailabilityButton";
import { RobotGallery } from "@/components/RobotGallery";
import { MachineCode } from "@/components/MachineCode";
import { PriceStateLong } from "@/components/PricingState";
import { SpecRow, SpecValue } from "@/components/DataCell";
import { ResolvedFactCell } from "@/components/ResolvedFactCell";
import { factsByProperty, hasScopedKnowledge } from "@/lib/resolved-facts";
import type { ResolvedFact } from "@/lib/types";
import { SectionIndex } from "@/components/SectionIndex";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

const CONF_RANK: Record<string, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  VERIFIED: 4,
};

function strongestConfidence(robot: RobotDetail): string | null {
  const all: Evidence[] = [
    ...robot.pricing_offers.map((p) => p.evidence).filter(Boolean),
    ...robot.availability_offers.map((a) => a.evidence).filter(Boolean),
    ...robot.deployments.map((d) => d.evidence).filter(Boolean),
  ] as Evidence[];
  if (all.length === 0) return null;
  let best: string | null = null;
  let bestRank = 0;
  for (const e of all) {
    const rank = CONF_RANK[e.confidence] ?? 0;
    // VERIFIED only counts as verified when verified_at is present.
    const effective =
      e.confidence === "VERIFIED" && !e.verified_at ? "HIGH" : e.confidence;
    const effRank = CONF_RANK[effective] ?? rank;
    if (effRank > bestRank) {
      bestRank = effRank;
      best = effective;
    }
  }
  return best;
}

interface EvidenceRow {
  subject: string;
  subjectCode: string;
  evidence: Evidence;
}

function collectEvidence(robot: RobotDetail): EvidenceRow[] {
  const rows: EvidenceRow[] = [];
  for (const p of robot.pricing_offers) {
    if (p.evidence)
      rows.push({
        subject: `Price — ${modeLabel(p.transaction_type)}${p.variant ? ` · ${p.variant}` : ""}${p.region ? ` · ${p.region}` : ""} · ${priceTypeLabel(p.price_type)}`,
        subjectCode: "Subject: pricing offer",
        evidence: p.evidence,
      });
  }
  for (const a of robot.availability_offers) {
    if (a.evidence)
      rows.push({
        subject: `Availability — ${modeLabel(a.transaction_type)}${a.variant ? ` · ${a.variant}` : ""}${a.region ? ` · ${a.region}` : ""} · ${availabilityLabel(a.availability_status)}`,
        subjectCode: "Subject: availability offer",
        evidence: a.evidence,
      });
  }
  for (const d of robot.deployments) {
    if (d.evidence)
      rows.push({
        subject: `Deployment — ${d.customer_name ?? "Undisclosed customer"}`,
        subjectCode: "Subject: deployment",
        evidence: d.evidence,
      });
  }
  return rows;
}

// WS8.5 / R22 — one governed read shared by the page and generateMetadata via
// React cache() (per-request memoization), never an alternate data path.
const getRobotCached = cache(findRobot);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const robot = await getRobotCached(slug);
  if (!robot) return { title: "Not found" };
  // AI Citation Layer v0.1 / CID-04 + CIT-E — one unambiguous canonical URL per
  // record, from the SAME authoritative origin resolver every other machine
  // surface uses (lib/site.ts). Never a hard-coded production hostname: on a
  // staging/preview deploy `siteUrl()` resolves that environment's own origin
  // (or throws), so a preview can never publish production canonicals.
  //
  // The description deliberately makes NO price/availability claim: this page
  // renders those as independent, evidence-gated dimensions that may be absent
  // entirely, and metadata must not assert what the record may not contain
  // (docs/23 §10, CIT-K).
  const canonical = absoluteUrl(`/robots/${robot.slug}`);
  return {
    title: `${robot.name} by ${robot.manufacturer.name} — Specs, Status & Evidence`,
    description:
      robot.summary ??
      `${robot.name} by ${robot.manufacturer.name} — capabilities, commercial status and evidence on HumanoidOnline.`,
    alternates: { canonical },
  };
}

export default async function RobotDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [robot, countries] = await Promise.all([
    getRobotCached(slug),
    listRegions({ type: "COUNTRY" }),
  ]);
  if (!robot) notFound();

  // UX-02B: the maker's own providers are the only authoritative seller names the API returns.
  // A failed read must not break the page: sellers then fall back to their identifier.
  const providerNames: ProviderNames = providerNamesFrom(
    await findManufacturer(robot.manufacturer.slug)
      .then((m) => m?.providers)
      .catch(() => undefined),
  );

  const code = deriveModelCode(robot.slug, robot.manufacturer.slug);
  const conf = strongestConfidence(robot);
  const evidenceRows = collectEvidence(robot);
  const mfrCountry = robot.manufacturer.country;
  const ladderIdx = maturityIndex(robot.commercial_status);
  const discontinued = robot.commercial_status === "DISCONTINUED";
  const s = robot.specs;
  const heroSummary = commercialSummary(
    priceDisplayFromHeadline(selectHeadline(robot.pricing_offers)),
    accessibleModes(robot.availability_offers),
  );

  // A caveat EXPLAINS a spec — most often why it is UNKNOWN, or that sources
  // disagree. It never supplies a value: the row still renders whatever the
  // record holds (usually the UNKNOWN state), with the explanation beneath it.
  const caveats = new Map(robot.spec_caveats.map((c) => [c.field, c.text]));

  // G4: scoped facts are resolved once, by the API. UNKNOWN here means no accepted canonical
  // knowledge at product or variant scope; nothing is re-derived in the web layer.
  const resolved = factsByProperty(robot.resolved_facts);

  const evidenceStatusField = conf
    ? { label: "EVIDENCE STATUS:", value: conf, emphasis: conf === "VERIFIED" || conf === "HIGH" }
    : { label: "EVIDENCE STATUS:", value: "NONE ON RECORD" };

  // AGENT-01: machine projection of the SAME governed read (Product + Organization
  // JSON-LD). Semantic parity with the HTML below; UNKNOWN specs omitted, not faked.
  const jsonLd = buildRobotJsonLd(robot);

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <SystemHeader
        title={`ROBOT RECORD / ${robot.slug.toUpperCase()}`}
        fields={[evidenceStatusField]}
      />

      {/* DARK IDENTITY HEADER */}
      <div className="idhead ho-dark ho-scan">
        <div className="in">
          {/* Minimal return path (WS8.4). Robot detail deliberately does NOT
              repeat the primary SiteNav (intentional UI-D1 variance) — but a
              record page still needs an obvious escape to home/catalogue. Two
              links, NOT wrapped in <nav>, so no navigation landmark is added and
              the no-SiteNav variance is preserved exactly. */}
          <p className="idcrumb">
            <Link href="/" aria-label="HumanoidOnline home">
              HumanoidOnline
            </Link>
            <span aria-hidden="true">/</span>
            <Link href="/robots">Robot Catalogue</Link>
          </p>
          <div className="topbar">
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
            <div className="seg">
              UNIT / <b>{robot.slug.toUpperCase()}</b>
            </div>
            <div className="seg">{robot.summary ? "HUMANOID PLATFORM" : "HUMANOID"}</div>
            <div className="seg">
              STATUS — <b>{statusLabel(robot.commercial_status)}</b>
            </div>
            <div className="seg">
              {robot.manufacturer.name}
              {mfrCountry ? ` · ${mfrCountry}` : ""}
            </div>
            <div className="corner">
              <span className="ho-reg-box">&reg;</span>
            </div>
          </div>

          <div className="idbody">
            <div className="idside l">
              <span className="ho-vertical">
                RECORD: {robot.slug.toUpperCase()}
              </span>
            </div>
            <div className="idside r">
              <span className="ho-vertical">
                {robot.manufacturer.name.toUpperCase()}
                {mfrCountry ? ` / ${mfrCountry}` : ""}
              </span>
            </div>

            <div className="id-kicker">
              <SectionIndex>ROBOT RECORD — 3 INDEPENDENT DIMENSIONS</SectionIndex>
              <span className="ho-capsule">
                <span className="ho-marker ho-marker--signal" aria-hidden="true" />{" "}
                <Link href={`/manufacturers/${robot.manufacturer.slug}`}>
                  {robot.manufacturer.name.toUpperCase()}
                </Link>
              </span>
            </div>

            <div className="id-grid">
              <div>
                <div className="lockup-big">
                  <h1 className="name">{robot.name}</h1>
                  <div className="code-rules">
                    <span className="r1" />
                    <span className="r2" />
                    <span className="r3" />
                    <span className="mc">
                      {code && code !== robot.name.toUpperCase()
                        ? `${robot.name.toUpperCase()} / ${code}`
                        : robot.name.toUpperCase()}
                    </span>
                  </div>
                </div>
              </div>
              <div className="schematic">
                <svg viewBox="0 0 220 200" role="img" aria-label={`Schematic of ${robot.name}`}>
                  <g fill="none" stroke="#9C968A" strokeWidth="1.4">
                    <circle cx="110" cy="34" r="15" />
                    <line x1="110" y1="49" x2="110" y2="70" />
                    <rect x="86" y="70" width="48" height="52" />
                    <line x1="86" y1="86" x2="52" y2="110" />
                    <line x1="52" y1="110" x2="56" y2="140" />
                    <line x1="134" y1="86" x2="168" y2="110" />
                    <line x1="168" y1="110" x2="164" y2="140" />
                    <line x1="98" y1="122" x2="90" y2="160" />
                    <line x1="90" y1="160" x2="94" y2="192" />
                    <line x1="122" y1="122" x2="130" y2="160" />
                    <line x1="130" y1="160" x2="126" y2="192" />
                  </g>
                  <g fill="#FF4A00">
                    <rect x="105" y="29" width="10" height="4" />
                  </g>
                </svg>
                <span className="cap ho-syslabel">FIG. 01 — GEOMETRY (SCHEMATIC)</span>
              </div>
            </div>

            <div className="dims-strip">
              <CommercialTriadInline robot={robot} conf={conf} />
            </div>
            {/* Same one-line summary as the catalogue card and compare matrix,
                on its own full-width row beneath the three status boxes. */}
            <p className="csum csum--hero">{heroSummary.line}</p>
          </div>
        </div>
      </div>

      <div className="wrap">
        {/* MEDIA-01 — verified identity imagery (or honest IMAGE_UNAVAILABLE) */}
        <RobotGallery robotName={robot.name} images={robot.images} />

        {/* SUMMARY + ACTIONS */}
        <div className="summary-row" id="robot-summary">
          <p>{robot.summary ?? robot.description ?? "No description on record."}</p>
          <div className="actions">
            {/* The maker's own page for this model. Rendered only when the
                record holds one — never guessed from the manufacturer site. */}
            {robot.official_url && (
              <a
                className="btn"
                href={robot.official_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <GraphicMarker /> Official product page ↗
              </a>
            )}
            <DetailComparisonLink slug={robot.slug} name={robot.name} href={`/compare?ids=${robot.slug}`} />
            <RequestAvailabilityButton
              robotSlug={robot.slug}
              robotName={robot.name}
              countries={countries}
            />
          </div>
        </div>

        {/* CANONICAL FACTS — AI Citation Layer v0.1 / CID-02.
            A concise restatement of facts already rendered further down this
            same page (specs, identity, maturity), grouped for extraction.
            Adds no fact, queries nothing, and asserts no evidence — see
            components/CitationFacts.tsx. */}
        <section className="blk" id="canonical-facts">
          <div className="blk-head">
            <div>
              <SectionIndex>00 — CANONICAL FACTS</SectionIndex>
              <h2>Record summary</h2>
            </div>
            <SystemLabel>
              PROJECTION OF THIS RECORD — UNKNOWN VALUES OMITTED, NEVER INFERRED
            </SystemLabel>
          </div>
          <CitationFacts robot={robot} />
        </section>

        {/* THE THREE DIMENSIONS */}
        <section className="blk" id="commercial-status">
          <div className="blk-head">
            <div>
              <SectionIndex>01 — THE THREE DIMENSIONS</SectionIndex>
              <h2>Maturity ≠ obtainability ≠ evidence</h2>
            </div>
            <SystemLabel>
              RENDERED INDEPENDENTLY — NEVER COLLAPSED INTO ONE &quot;AVAILABLE&quot; FLAG
            </SystemLabel>
          </div>

          <div className="dims">
            {/* DIM 1 — maturity */}
            <article className="dim">
              <div className="dtop">
                <span className="num">1</span>
                <span className="t">
                  Commercial
                  <br />
                  maturity
                </span>
              </div>
              <div className="dbody">
                <div className={`ho-pair ${discontinued ? "is-unknown" : "is-signal"}`}>
                  <span className="k">Commercial status</span>
                  <span className="s" data-enum={robot.commercial_status}>
                    {statusLabel(robot.commercial_status)}
                  </span>
                </div>
                <div>
                  <SystemLabel as="div">Maturity ladder</SystemLabel>
                  <div
                    className="ladder"
                    style={{ marginTop: 8 }}
                    role="img"
                    aria-label={`Maturity: ${statusLabel(robot.commercial_status)}`}
                  >
                    {MATURITY_LADDER.map((_, i) => (
                      <i
                        key={i}
                        className={
                          i === ladderIdx ? "cur" : i < ladderIdx ? "on" : ""
                        }
                      />
                    ))}
                  </div>
                  <SystemLabel
                    as="div"
                    className=""
                  >
                    <span className="faint">
                      Announced ▸ Robot-as-a-service ▸ Discontinued
                    </span>
                  </SystemLabel>
                </div>
                <p className="stamp">
                  Platform maturity only. Says how far the product has progressed —
                  not whether you can obtain it.
                </p>
              </div>
            </article>

            {/* DIM 2 — obtainability */}
            <article className="dim" id="availability">
              <div className="dtop">
                <span className="num">2</span>
                <span className="t">
                  Obtainability
                  <br />
                  mode × region
                </span>
              </div>
              <div className="dbody">
                <AvailabilityMatrix offers={robot.availability_offers} />
                <p className="stamp">
                  Shows where this robot can currently be obtained. No offer on
                  record means availability is unknown, which is not the same as ruled out.
                </p>
              </div>
            </article>

            {/* DIM 3 — evidence */}
            <article className="dim" id="deployments">
              <div className="dtop">
                <span className="num">3</span>
                <span className="t">
                  Deployment
                  <br />
                  evidence
                </span>
              </div>
              <div className="dbody">
                <div className={`ho-pair ${conf === "VERIFIED" ? "is-verified" : ""}`}>
                  <span className="k">Deployments</span>
                  <span className="s">
                    {robot.deployments.length}
                    {conf && (
                      <span className="mono">· {confidenceLabel(conf)}</span>
                    )}
                  </span>
                </div>
                {robot.deployments.length > 0 ? (
                  <DeploymentMatrix deployments={robot.deployments} />
                ) : (
                  <p className="stamp">No deployments on record.</p>
                )}
              </div>
            </article>
          </div>
        </section>

        {/* PRICING */}
        <section className="blk" id="pricing">
          <div className="blk-head">
            <div>
              <SectionIndex>02 — PRICING</SectionIndex>
              <h2>Price is never one column</h2>
            </div>
            <SystemLabel>
              Mode, price type, billing, region and seller
            </SystemLabel>
          </div>

          {/* WS8.4 / R17: horizontally-scrollable on narrow viewports, so it is
              keyboard-focusable (WCAG 2.1.1) with a named region. */}
          <div className="ptable" tabIndex={0} role="group" aria-label="Specifications table">
            <div className="prow head">
              <div>Mode</div>
              <div>Region</div>
              <div>Provider</div>
              <div>Price</div>
              <div>Evidence</div>
            </div>
            {robot.pricing_offers.length > 0 ? (
              robot.pricing_offers.map((p, i) => (
                <PricingRow key={i} offer={p} names={providerNames} />
              ))
            ) : (
              <div className="prow">
                <div className="val unknown tt-none">
                  —
                </div>
                <div className="val unknown tt-none">
                  —
                </div>
                <div className="val unknown tt-none">
                  —
                </div>
                <div>
                  <PriceStateLong price={null} />
                </div>
                <div className="stamp faint">
                  — absence claims nothing —
                </div>
              </div>
            )}
          </div>
        </section>

        {/* SPECIFICATIONS */}
        <section className="blk" id="specifications">
          <div className="blk-head">
            <div>
              <SectionIndex>03 — SPECIFICATIONS</SectionIndex>
              <h2>Physical / intelligence / developer</h2>
            </div>
            <SystemLabel>Unconfirmed values show as unknown, never zero or no</SystemLabel>
          </div>
          <div className="specgrid">
            <div className="spectbl">
              <h3>Physical</h3>
              <SpecRow label="Height" value={s.height_cm} unit="cm" note={caveats.get("height_cm")} />
              <SpecRow label="Weight" value={s.weight_kg} unit="kg" note={caveats.get("weight_kg")} />
              <SpecRow label="Arm span" value={s.arm_span_cm} unit="cm" note={caveats.get("arm_span_cm")} />
              <SpecRow label="Reach" value={s.reach_cm} unit="cm" note={caveats.get("reach_cm")} />
              <SpecRow label="Payload" value={s.payload_kg} unit="kg" note={caveats.get("payload_kg")} />
              <SpecRow label="Walk speed" value={s.walk_speed_ms} unit="m/s" note={caveats.get("walk_speed_ms")} />
              <SpecRow label="Runtime" value={s.runtime_minutes} unit="min" note={caveats.get("runtime_minutes")} />
              <SpecRow label="Battery" value={s.battery_wh} unit="Wh" note={caveats.get("battery_wh")} />
              <SpecRow label="Mobility" value={s.mobility ? mobilityLabel(s.mobility) : s.mobility} rawEnum={s.mobility} note={caveats.get("mobility")} />
              <SpecRow label="DOF" value={s.degrees_of_freedom} note={caveats.get("degrees_of_freedom")} />
            </div>
            <div className="spectbl">
              <h3>Intelligence</h3>
              <SpecRow label="Autonomy" value={s.autonomy ? autonomyLabel(s.autonomy) : s.autonomy} rawEnum={s.autonomy} note={caveats.get("autonomy")} />
              <ResolvedRow label="Manipulation" value={s.has_manipulation} fact={resolved.has_manipulation} note={caveats.get("has_manipulation")} />
              <ResolvedRow label="Teleoperation" value={s.has_teleoperation} fact={resolved.has_teleoperation} note={caveats.get("has_teleoperation")} />
              <SpecRow label="Vision" value={s.has_vision} note={caveats.get("has_vision")} />
              <SpecRow label="Language UI" value={s.has_language_ui} note={caveats.get("has_language_ui")} />
              <SpecRow label="Hand type" value={s.hand_type} note={caveats.get("hand_type")} />
              <SpecRow label="Hand DOF" value={s.hand_dof} note={caveats.get("hand_dof")} />
            </div>
            <div className="spectbl">
              <h3>Developer</h3>
              <ResolvedRow label="SDK" value={s.has_sdk} fact={resolved.has_sdk} note={caveats.get("has_sdk")} />
              <SpecRow label="API" value={s.has_api} note={caveats.get("has_api")} />
              <ResolvedRow label="ROS support" value={s.ros_support} fact={resolved.ros_support} note={caveats.get("ros_support")} />
              <SpecRow label="Developer edition" value={s.developer_edition} note={caveats.get("developer_edition")} />
              <SpecRow label="Simulation support" value={s.simulation_support} note={caveats.get("simulation_support")} />
              <SpecRow label="Announced" value={robot.announced_year} />
            </div>
          </div>

          {robot.extended_specs.length > 0 && (
            <>
              <div className="specgrid" style={{ marginTop: "var(--ho-sp-6)" }}>
                {groupExtendedSpecs(robot.extended_specs).map(([category, rows]) => (
                  <div className="spectbl" key={category}>
                    <h3>{enumLabel("capability_category", category)}</h3>
                    {rows.map((x) => (
                      <ExtendedSpecRow key={`${x.key}:${x.variant_slug ?? ""}`} spec={x} />
                    ))}
                  </div>
                ))}
              </div>
              <p className="stamp" style={{ marginTop: "var(--ho-sp-4)" }}>
                Each extended specification carries its own source and the edition
                it was stated for. <b>PRODUCT LINE</b> means the figure was published
                for the model family, not measured on this edition;{" "}
                <b>RESELLER CLAIM</b> means a distributor stated it, not the
                manufacturer.
              </p>
            </>
          )}

          {robot.capabilities.length > 0 && (
            <div style={{ marginTop: "var(--ho-sp-6)" }}>
              <SystemLabel as="div">Capabilities</SystemLabel>
              <div className="specgrid" style={{ marginTop: 12 }}>
                <div className="spectbl">
                  <h3>Capability support (yes / no / unknown)</h3>
                  {robot.capabilities.map((c) => (
                    <SpecRow key={c.slug} label={c.name} value={c.supported} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>

        {/* EVIDENCE / PROVENANCE */}
        <section className="blk" id="evidence">
          <div className="blk-head">
            <div>
              <SectionIndex>04 — EVIDENCE &amp; PROVENANCE</SectionIndex>
              <h2>No commercial fact without evidence</h2>
            </div>
            <SystemLabel>Source, dates and confidence for every commercial fact</SystemLabel>
          </div>
          {evidenceRows.length > 0 ? (
            <div className="ev">
              {evidenceRows.map((r, i) => (
                <div className="evrow" key={i}>
                  <div className="subj">
                    {r.subject}
                    <br />
                    <MachineCode>{r.subjectCode}</MachineCode>
                  </div>
                  <div>
                    <EvidenceStamp evidence={r.evidence} />
                  </div>
                  <div className="conf-cell">
                    <ConfidenceIndicator
                      level={r.evidence.confidence}
                      verifiedAt={r.evidence.verified_at}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">
              No evidence rows attached to this record&apos;s commercial facts.
            </p>
          )}
        </section>

        {/* COMMERCIAL ACTION PANEL */}
        <div className="action-panel">
          <div>
            <SectionIndex>COMMERCIAL ACTION</SectionIndex>
            <p className="note">
              Availability requests are recorded as interest. There is no checkout
              or payment on HumanoidOnline.
            </p>
          </div>
          <RequestAvailabilityButton
            robotSlug={robot.slug}
            robotName={robot.name}
            countries={countries}
          />
        </div>
      </div>
    </>
  );
}

function CommercialTriadInline({
  robot,
  conf,
}: {
  robot: RobotDetail;
  conf: string | null;
}) {
  return (
    <CommercialTriad
      status={robot.commercial_status}
      availabilityOffers={robot.availability_offers}
      deploymentCount={robot.deployments.length}
      strongestConfidence={conf}
    />
  );
}

function PricingRow({ offer, names }: { offer: PricingOffer; names: ProviderNames }) {
  const price = {
    type: offer.price_type,
    amount: offer.price,
    amount_min: offer.price_min,
    amount_max: offer.price_max,
    currency: offer.currency,
    billing_period: offer.billing_period,
  };
  return (
    <div className="prow">
      <div>
        {modeLabel(offer.transaction_type)}
        {/* A variant-scoped price names its configuration, so Standard and Pro are never
            read as two prices for one thing. */}
        {offer.variant && (
          <span className="ho-syslabel d-blk">
            {offer.variant} configuration
          </span>
        )}
      </div>
      <div className={offer.region ? "tt-none" : "val unknown tt-none"}>
        {offer.region ?? "—"}
      </div>
      <div
        className={offer.provider ? "tt-none" : "val unknown tt-none"}
        {...(offer.provider && (offer.provider_name || names[offer.provider]) ? { "data-provider": offer.provider } : {})}
      >
        {offer.provider ? providerLabel(offer.provider, names, offer.provider_name).text : "—"}
      </div>
      <div>
        <PriceStateLong price={price} />
        {/* The terms this price is quoted on. They belong to THIS offer row and
            are rendered with it, so one seller's number is never read under
            another seller's terms. */}
        {offer.price_basis && (
          <span className="ho-syslabel d-blk">
            {offer.price_basis}
          </span>
        )}
        {offer.shipping_terms && (
          <span className="ho-syslabel d-blk">
            {offer.shipping_terms}
          </span>
        )}
        {offer.package_contents && (
          <span className="ho-syslabel d-blk">
            Includes: {offer.package_contents}
          </span>
        )}
        {offer.warranty_terms && (
          <span className="ho-syslabel d-blk">
            Warranty (this seller): {offer.warranty_terms}
          </span>
        )}
        {offer.order_status_note && (
          <span className="ho-syslabel d-blk">
            {offer.order_status_note}
          </span>
        )}
        {/* Only an explicit FALSE is a warning. null means the edition match was
            never assessed, and silence is the honest rendering of that. */}
        {offer.edition_confirmed === false && (
          <span className="ho-syslabel d-blk">
            ⚠ {offer.edition_note ?? "This listing is not confirmed to be this edition."}
          </span>
        )}
      </div>
      <div className="stamp">
        {offer.evidence ? (
          <>
            <span data-enum={offer.evidence.confidence}>
              {confidenceLabel(offer.evidence.confidence)}
            </span>
            {offer.evidence.verified_at
              ? ` · ${formatDate(offer.evidence.verified_at)}`
              : ""}
            <br />
            SOURCE:{" "}
            <span data-enum={offer.evidence.source_type}>
              {sourceTypeLabel(offer.evidence.source_type)}
            </span>
          </>
        ) : (
          <span className="faint">— no evidence —</span>
        )}
      </div>
    </div>
  );
}

// Stable grouping for the extended table: categories in first-appearance order
// (the API already sorts the rows), so the page cannot reorder itself between
// renders. No fact is computed here — only which heading a row sits under.
function groupExtendedSpecs(specs: ExtendedSpec[]): [string, ExtendedSpec[]][] {
  const groups = new Map<string, ExtendedSpec[]>();
  for (const spec of specs) {
    const key = spec.category || "Other";
    const bucket = groups.get(key);
    if (bucket) bucket.push(spec);
    else groups.set(key, [spec]);
  }
  return [...groups.entries()];
}

// A row for a capability resolved by the API (G4). A plain product value renders exactly as
// before; a scoped resolution (uniform / varies / partial / conflict) renders its words; and a
// truly UNKNOWN property keeps the ordinary UNKNOWN. Nothing is inferred here.
function ResolvedRow({
  label,
  value,
  fact,
  note,
}: {
  label: string;
  value: number | string | boolean | null | undefined;
  fact: ResolvedFact | undefined;
  note?: string | null;
}) {
  if (!hasScopedKnowledge(fact)) return <SpecRow label={label} value={value} note={note} />;
  return (
    <div className="srow">
      <span className="k">{label}</span>
      <span className="d-blk">
        <ResolvedFactCell fact={fact} />
        {note && (
          <span className="ho-syslabel d-blk">
            {note}
          </span>
        )}
      </span>
    </div>
  );
}

// An extended spec has no evidence row of its own, so its attribution travels
// with the value and is rendered WITH it — a number whose source is a click away
// is a number presented as ours.
function ExtendedSpecRow({ spec }: { spec: ExtendedSpec }) {
  const qualifiers: string[] = [];
  if (spec.source_kind === "RESELLER_CLAIM") qualifiers.push("RESELLER CLAIM");
  if (spec.edition_scope === "PRODUCT_LINE") qualifiers.push("PRODUCT LINE");
  if (spec.edition_scope === "PLATFORM") qualifiers.push("PLATFORM");

  const attribution = [
    spec.source_label,
    qualifiers.length ? qualifiers.join(" · ") : null,
    spec.observed_at ? `observed ${formatDate(spec.observed_at)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="srow">
      <span className="k">
        {spec.label}
        {spec.variant && (
          <span className="ho-syslabel d-blk">
            {spec.variant} configuration
          </span>
        )}
      </span>
      <span className="d-blk">
        <SpecValue value={spec.value} unit={spec.unit} />
        {attribution && (
          <span className="ho-syslabel d-blk">
            {spec.source_url ? (
              <a href={spec.source_url} target="_blank" rel="noopener noreferrer">
                {attribution} ↗
              </a>
            ) : (
              attribution
            )}
          </span>
        )}
      </span>
    </div>
  );
}

function DeploymentMatrix({ deployments }: { deployments: Deployment[] }) {
  return (
    <div className="matrix">
      <div className="mrow head">
        <span>Customer</span>
        <span>Use case</span>
        <span>Conf.</span>
      </div>
      {deployments.map((d, i) => (
        <div className="mrow" key={i}>
          <span>{d.customer_name ?? "Undisclosed"}</span>
          <span className={d.use_case ? "" : "na"}>{d.use_case ?? "—"}</span>
          <span
            data-enum={d.evidence?.confidence}
            style={
              d.evidence?.confidence === "VERIFIED"
                ? { color: "var(--ho-verified)" }
                : undefined
            }
          >
            {d.evidence ? confidenceLabel(d.evidence.confidence) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
