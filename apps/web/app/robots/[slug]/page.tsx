// Robot detail /robots/[slug] — identity header experimental, data disciplined.
// The key proof: three INDEPENDENT dimensions; all six price states incl.
// QUOTE_ONLY ≠ UNKNOWN; specs with explicit UNKNOWN; evidence drill-down with
// real source/dates/confidence/link. 404 -> notFound(). All facts from the API.
import Link from "next/link";

import { getRobot, listRegions } from "@/lib/api-client";
import {
  formatDate,
  maturityIndex,
  MATURITY_LADDER,
  modeLabel,
} from "@/lib/format";
import type {
  Deployment,
  Evidence,
  PricingOffer,
  RobotDetail,
} from "@/lib/types";
import { AvailabilityMatrix } from "@/components/AvailabilityState";
import { CommercialTriad } from "@/components/CommercialTriad";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { deriveModelCode } from "@/components/RobotCard";
import { EvidenceStamp } from "@/components/EvidenceStamp";
import { GraphicMarker } from "@/components/GraphicMarker";
import { RequestAvailabilityButton } from "@/components/RequestAvailabilityButton";
import { MachineCode } from "@/components/MachineCode";
import { PriceStateLong } from "@/components/PricingState";
import { SpecRow } from "@/components/DataCell";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter } from "@/components/SiteNav";
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
        subject: `Price — ${modeLabel(p.transaction_type)}${p.region ? ` · ${p.region}` : ""} · ${p.price_type}`,
        subjectCode: "SUBJECT: PRICING_OFFER",
        evidence: p.evidence,
      });
  }
  for (const a of robot.availability_offers) {
    if (a.evidence)
      rows.push({
        subject: `Availability — ${modeLabel(a.transaction_type)}${a.region ? ` · ${a.region}` : ""} · ${a.availability_status}`,
        subjectCode: "SUBJECT: AVAILABILITY_OFFER",
        evidence: a.evidence,
      });
  }
  for (const d of robot.deployments) {
    if (d.evidence)
      rows.push({
        subject: `Deployment — ${d.customer_name ?? "Undisclosed customer"}`,
        subjectCode: "SUBJECT: DEPLOYMENT",
        evidence: d.evidence,
      });
  }
  return rows;
}

export default async function RobotDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [robot, countries] = await Promise.all([
    getRobot(slug),
    listRegions({ type: "COUNTRY" }),
  ]);

  const code = deriveModelCode(robot.slug, robot.manufacturer.slug);
  const conf = strongestConfidence(robot);
  const evidenceRows = collectEvidence(robot);
  const mfrCountry = robot.manufacturer.country;
  const ladderIdx = maturityIndex(robot.commercial_status);
  const discontinued = robot.commercial_status === "DISCONTINUED";
  const s = robot.specs;

  const evidenceStatusField = conf
    ? { label: "EVIDENCE STATUS:", value: conf, emphasis: conf === "VERIFIED" || conf === "HIGH" }
    : { label: "EVIDENCE STATUS:", value: "NONE ON RECORD" };

  return (
    <>
      <SystemHeader
        title={`ROBOT RECORD / ${robot.slug.toUpperCase()}`}
        fields={[evidenceStatusField]}
      />

      {/* DARK IDENTITY HEADER */}
      <div className="idhead ho-dark ho-scan">
        <div className="in">
          <div className="topbar">
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
            <div className="seg">
              UNIT / <b>{robot.slug.toUpperCase()}</b>
            </div>
            <div className="seg">{robot.summary ? "HUMANOID PLATFORM" : "HUMANOID"}</div>
            <div className="seg">
              STATUS — <b>{robot.commercial_status}</b>
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
          </div>
        </div>
      </div>

      <div className="wrap">
        {/* SUMMARY + ACTIONS */}
        <div className="summary-row">
          <p>{robot.summary ?? robot.description ?? "No description on record."}</p>
          <div className="actions">
            <Link className="btn" href={`/compare?ids=${robot.slug}`}>
              <GraphicMarker /> Compare +
            </Link>
            <RequestAvailabilityButton
              robotSlug={robot.slug}
              robotName={robot.name}
              countries={countries}
            />
          </div>
        </div>

        {/* THE THREE DIMENSIONS */}
        <section className="blk">
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
                  <span className="k">commercial_status</span>
                  <span className="s">{robot.commercial_status}</span>
                </div>
                <div>
                  <SystemLabel as="div">Maturity ladder</SystemLabel>
                  <div
                    className="ladder"
                    title={MATURITY_LADDER.join(" → ")}
                    style={{ marginTop: 8 }}
                    role="img"
                    aria-label={`Maturity: ${robot.commercial_status}`}
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
                    <span style={{ color: "var(--ho-text-faint)" }}>
                      ANNOUNCED ▸ RAAS_DEPLOYMENT ▸ DISCONTINUED
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
            <article className="dim">
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
                  Predicate <code>commercially_accessible</code> = is_current AND
                  status ∉ {"{"}NOT_AVAILABLE, DISCONTINUED{"}"}. Absence of a row =
                  unknown, not NOT_AVAILABLE.
                </p>
              </div>
            </article>

            {/* DIM 3 — evidence */}
            <article className="dim">
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
                  <span className="k">deployments</span>
                  <span className="s">
                    {robot.deployments.length}
                    {conf && <span className="mono">· {conf}</span>}
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
        <section className="blk">
          <div className="blk-head">
            <div>
              <SectionIndex>02 — PRICING</SectionIndex>
              <h2>Price is never one column</h2>
            </div>
            <SystemLabel>
              transaction_type × price_type × billing × region × provider
            </SystemLabel>
          </div>

          <div className="ptable">
            <div className="prow head">
              <div>Mode</div>
              <div>Region</div>
              <div>Provider</div>
              <div>Price</div>
              <div>Evidence</div>
            </div>
            {robot.pricing_offers.length > 0 ? (
              robot.pricing_offers.map((p, i) => (
                <PricingRow key={i} offer={p} />
              ))
            ) : (
              <div className="prow">
                <div className="val unknown" style={{ textTransform: "none" }}>
                  —
                </div>
                <div className="val unknown" style={{ textTransform: "none" }}>
                  —
                </div>
                <div className="val unknown" style={{ textTransform: "none" }}>
                  —
                </div>
                <div>
                  <PriceStateLong price={null} />
                </div>
                <div className="stamp" style={{ color: "var(--ho-text-faint)" }}>
                  — absence claims nothing —
                </div>
              </div>
            )}
          </div>
        </section>

        {/* SPECIFICATIONS */}
        <section className="blk">
          <div className="blk-head">
            <div>
              <SectionIndex>03 — SPECIFICATIONS</SectionIndex>
              <h2>Physical / intelligence / developer</h2>
            </div>
            <SystemLabel>NULL = UNKNOWN, NEVER 0 OR FALSE</SystemLabel>
          </div>
          <div className="specgrid">
            <div className="spectbl">
              <h3>Physical</h3>
              <SpecRow label="Height" value={s.height_cm} unit="cm" />
              <SpecRow label="Weight" value={s.weight_kg} unit="kg" />
              <SpecRow label="Payload" value={s.payload_kg} unit="kg" />
              <SpecRow label="Walk speed" value={s.walk_speed_ms} unit="m/s" />
              <SpecRow label="Runtime" value={s.runtime_minutes} unit="min" />
              <SpecRow label="Battery" value={s.battery_wh} unit="Wh" />
              <SpecRow label="Mobility" value={s.mobility} />
              <SpecRow label="DOF" value={s.degrees_of_freedom} />
            </div>
            <div className="spectbl">
              <h3>Intelligence</h3>
              <SpecRow label="Autonomy" value={s.autonomy} />
              <SpecRow label="Manipulation" value={s.has_manipulation} />
              <SpecRow label="Teleoperation" value={s.has_teleoperation} />
              <SpecRow label="Vision" value={s.has_vision} />
              <SpecRow label="Language UI" value={s.has_language_ui} />
              <SpecRow label="Hand type" value={s.hand_type} />
              <SpecRow label="Hand DOF" value={s.hand_dof} />
            </div>
            <div className="spectbl">
              <h3>Developer</h3>
              <SpecRow label="SDK" value={s.has_sdk} />
              <SpecRow label="API" value={s.has_api} />
              <SpecRow label="ROS support" value={s.ros_support} />
              <SpecRow label="Developer edition" value={s.developer_edition} />
              <SpecRow label="Simulation support" value={s.simulation_support} />
              <SpecRow label="Announced" value={robot.announced_year} />
            </div>
          </div>

          {robot.extended_specs.length > 0 && (
            <div className="specgrid" style={{ marginTop: "var(--ho-sp-6)" }}>
              <div className="spectbl">
                <h3>Extended specifications</h3>
                {robot.extended_specs.map((x, i) => (
                  <SpecRow key={i} label={x.label} value={x.value} unit={x.unit} />
                ))}
              </div>
            </div>
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
        <section className="blk">
          <div className="blk-head">
            <div>
              <SectionIndex>04 — EVIDENCE &amp; PROVENANCE</SectionIndex>
              <h2>No commercial fact without evidence</h2>
            </div>
            <SystemLabel>EvidenceStamp + ConfidenceIndicator</SystemLabel>
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
              Availability requests are captured as demand intelligence. No
              checkout, no payment — commercial transaction workflows are later
              phases, driven by availability_offer rows without redesign.
            </p>
          </div>
          <RequestAvailabilityButton
            robotSlug={robot.slug}
            robotName={robot.name}
            countries={countries}
          />
        </div>
      </div>
      <SiteFooter />
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

function PricingRow({ offer }: { offer: PricingOffer }) {
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
      <div>{modeLabel(offer.transaction_type)}</div>
      <div className={offer.region ? "" : "val unknown"} style={{ textTransform: "none" }}>
        {offer.region ?? "—"}
      </div>
      <div className={offer.provider ? "" : "val unknown"} style={{ textTransform: "none" }}>
        {offer.provider ?? "—"}
      </div>
      <div>
        <PriceStateLong price={price} />
      </div>
      <div className="stamp">
        {offer.evidence ? (
          <>
            {offer.evidence.confidence}
            {offer.evidence.verified_at
              ? ` · ${formatDate(offer.evidence.verified_at)}`
              : ""}
            <br />
            SOURCE: {offer.evidence.source_type}
          </>
        ) : (
          <span style={{ color: "var(--ho-text-faint)" }}>— no evidence —</span>
        )}
      </div>
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
            style={
              d.evidence?.confidence === "VERIFIED"
                ? { color: "var(--ho-verified)" }
                : undefined
            }
          >
            {d.evidence?.confidence ?? "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
