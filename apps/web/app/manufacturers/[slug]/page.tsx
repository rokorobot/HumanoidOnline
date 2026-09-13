// Manufacturer detail — from /api/manufacturers/{slug}. 404 -> notFound().
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { findManufacturer } from "@/lib/api-client";
import { boolLabel, deploymentMeaning, formatDate, regionLabel } from "@/lib/format";
import type { ManufacturerSource } from "@/lib/types";
import { RobotThumb } from "@/components/RobotThumb";
import { StatusBracket } from "@/components/StatusBadge";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

// WS8.5 / R22 — one governed read shared by the page and generateMetadata via
// React cache() (per-request memoization), never an alternate data path.
const getManufacturerCached = cache(findManufacturer);

// Human labels for the profile fields a company source can support.
const FIELD_LABELS: Record<string, string> = {
  legal_name: "legal entity",
  country_region_code: "headquarters country",
  headquarters_city: "headquarters city",
  incorporation: "incorporation",
  operating_locations: "other locations",
  founded_year: "founded",
  website_url: "website",
  description: "description",
  target_markets: "target markets",
  commercial_model: "business model",
  deployment_status: "humanoid deployment",
  deployment_note: "deployment basis",
  is_public_company: "public company",
  ticker: "listing",
  parent_company: "parent",
  parent_listing: "parent listing",
  parent_relationship: "ownership",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const m = await getManufacturerCached(slug);
  if (!m) return { title: "Not found" };
  return {
    title: m.name,
    description:
      m.description ??
      `${m.name} — humanoid-robot manufacturer profile and verified platforms on HumanoidOnline.`,
  };
}

// One profile fact. UNKNOWN keeps the unknown tone; it is never a value.
function Fact({ k, v, unknown }: { k: string; v: string; unknown?: boolean }) {
  return (
    <div className="cf-row">
      <dt>{k}</dt>
      <dd style={unknown ? { color: "var(--ho-unknown)" } : undefined}>{v}</dd>
    </div>
  );
}

function SourceRow({ source: s }: { source: ManufacturerSource }) {
  const published = formatDate(s.published_at);
  const observed = formatDate(s.observed_at);
  const verified = formatDate(s.verified_at);
  const supports = s.claim_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ");
  return (
    <div className="evrow">
      <div className="subj">
        {s.source_url ? (
          <a href={s.source_url} target="_blank" rel="noopener noreferrer">
            {s.source_title ?? s.source_url} ↗
          </a>
        ) : (
          (s.source_title ?? "Untitled source")
        )}
        <br />
        <span className="stamp">{supports ? `Supports: ${supports}` : "No field claim recorded"}</span>
      </div>
      <div className="src">
        SOURCE: {s.source_type}
        <br />
        {published && <>PUBLISHED {published} · </>}OBSERVED {observed}
        <br />
        {verified ? (
          <>VERIFIED {verified} &reg;</>
        ) : s.retrieval === "AGENT_ASSISTED_RESEARCH" ? (
          <>Agent-assisted research · not human-verified</>
        ) : (
          <>Unverified claim</>
        )}
      </div>
      <div className="conf-cell stamp">{s.confidence}</div>
    </div>
  );
}

export default async function ManufacturerDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const m = await getManufacturerCached(slug);
  if (!m) notFound();

  const headquarters = [m.headquarters_city, regionLabel(m.country)].filter(Boolean).join(" · ");
  const publicCo = boolLabel(m.is_public_company);
  const deployment = m.deployment_status && m.deployment_status !== "UNKNOWN" ? m.deployment_status : null;
  const meaning = deploymentMeaning(deployment);

  return (
    <>
      <SystemHeader
        title={`MANUFACTURER / ${m.slug.toUpperCase()}`}
        fields={[
          { label: "PUBLISHED MODELS", value: m.published_robot_count },
          { label: "TRACKED MODELS", value: m.tracked_robot_count },
          ...(m.country ? [{ label: "HQ", value: m.country }] : []),
        ]}
      />
      <div className="wrap">
        <SiteNav active="manufacturers" />

        <div className="pagebar">
          <div>
            <SectionIndex>MANUFACTURER RECORD</SectionIndex>
            <h1 style={{ fontFamily: "var(--ho-font-display-serif)", textTransform: "none", fontWeight: 500 }}>
              {m.name}
            </h1>
          </div>
          {m.website_url && (
            <a className="ho-chip" href={m.website_url} target="_blank" rel="noopener noreferrer">
              WEBSITE ↗
            </a>
          )}
        </div>

        <section className="blk" style={{ borderTop: 0 }}>
          <div className="two-col">
            <div>
              <p className="prose">
                {m.description ?? "No description on record."}
              </p>
              {m.legal_name && (
                <p className="stamp" style={{ marginTop: 16 }}>
                  Legal entity: {m.legal_name}
                </p>
              )}
              {m.target_markets.length > 0 && (
                <>
                  <p className="stamp" style={{ marginTop: 16 }}>
                    Target markets
                  </p>
                  <div className="taglist mfr-markets">
                    {m.target_markets.map((t) => (
                      <span className="ho-chip" key={t}>
                        {t.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
            <div>
              <dl className="mfr-facts">
                <Fact k="Headquarters" v={headquarters || "UNKNOWN"} unknown={!headquarters} />
                <Fact k="Incorporation" v={m.incorporation ?? "UNKNOWN"} unknown={!m.incorporation} />
                <Fact
                  k="Other locations"
                  v={m.operating_locations.length > 0 ? m.operating_locations.join("; ") : "NOT RECORDED"}
                  unknown={m.operating_locations.length === 0}
                />
                <Fact
                  k="Founded"
                  v={m.founded_year != null ? String(m.founded_year) : "UNKNOWN"}
                  unknown={m.founded_year == null}
                />
                <Fact k="Business model" v={m.commercial_model ?? "UNKNOWN"} unknown={!m.commercial_model} />
                <Fact k="Humanoid deployment" v={deployment ?? "UNKNOWN"} unknown={!deployment} />
                <Fact
                  k="Public company"
                  v={m.is_public_company && m.ticker ? `${publicCo.label} · ${m.ticker}` : publicCo.label}
                  unknown={publicCo.unknown}
                />
                {m.parent_company && (
                  <Fact
                    k="Parent"
                    v={m.parent_listing ? `${m.parent_company} · ${m.parent_listing}` : m.parent_company}
                  />
                )}
              </dl>
              {(meaning || m.deployment_note) && (
                <p className="stamp mfr-deployment" style={{ marginTop: 12 }}>
                  {meaning && <>Humanoid deployment {deployment}: {meaning}. </>}
                  {m.deployment_note && <>Basis: {m.deployment_note}</>}
                </p>
              )}
              {m.parent_relationship && (
                <p className="stamp mfr-ownership" style={{ marginTop: 8 }}>
                  Ownership: {m.parent_relationship}
                </p>
              )}
            </div>
          </div>
        </section>

        <section className="blk">
          <div className="blk-head">
            <div>
              <SectionIndex>01 — PUBLISHED MODELS</SectionIndex>
              <h2>Robots</h2>
            </div>
            <SystemLabel>
              {m.published_robot_count} PUBLISHED · {m.tracked_robot_count} TRACKED
            </SystemLabel>
          </div>
          {m.robots.length > 0 ? (
            <div className="fit-list">
              {m.robots.map((r) => (
                <div className="fit-row" key={r.slug}>
                  <div className="fit-lead">
                    <RobotThumb slug={r.slug} name={r.name} image={r.primary_image} />
                    <div className="fit-name">
                      <Link className="name" href={`/robots/${r.slug}`}>
                        {r.name}
                      </Link>
                    </div>
                  </div>
                  <StatusBracket status={r.commercial_status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">No published models for this manufacturer.</p>
          )}
        </section>

        {m.providers.length > 0 && (
          <section className="blk">
            <div className="blk-head">
              <div>
                <SectionIndex>02 — PROVIDERS</SectionIndex>
                <h2>Commercial providers</h2>
              </div>
            </div>
            <div className="taglist">
              {m.providers.map((p) => (
                <span className="ho-chip" key={p.slug}>
                  {p.name} · {p.type}
                </span>
              ))}
            </div>
          </section>
        )}

        {m.deployments.length > 0 && (
          <section className="blk">
            <div className="blk-head">
              <div>
                <SectionIndex>03 — DEPLOYMENTS</SectionIndex>
                <h2>Field deployments</h2>
              </div>
            </div>
            <div className="matrix">
              <div className="mrow head">
                <span>Robot</span>
                <span>Customer</span>
                <span>Region</span>
              </div>
              {m.deployments.map((d, i) => (
                <div className="mrow" key={i}>
                  <span>{d.robot_slug}</span>
                  <span>{d.customer_name ?? "Undisclosed"}</span>
                  <span className={d.region ? "" : "na"}>{d.region ?? "—"}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="blk" id="company-sources" style={{ marginBottom: "var(--ho-sp-7)" }}>
          <div className="blk-head">
            <div>
              <SectionIndex>04 — COMPANY SOURCES</SectionIndex>
              <h2>Where the profile comes from</h2>
            </div>
            <SystemLabel>{m.sources.length} SOURCES</SystemLabel>
          </div>
          {m.sources.length > 0 ? (
            <div className="ev">
              {m.sources.map((s, i) => (
                <SourceRow source={s} key={i} />
              ))}
            </div>
          ) : (
            <p className="empty-state">No company-level sources on record.</p>
          )}
        </section>
      </div>
    </>
  );
}
