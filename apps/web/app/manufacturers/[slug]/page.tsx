// Manufacturer detail — from /api/manufacturers/{slug}. 404 -> notFound().
import Link from "next/link";

import { getManufacturer } from "@/lib/api-client";
import { regionLabel } from "@/lib/format";
import { StatusBracket } from "@/components/StatusBadge";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

export default async function ManufacturerDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const m = await getManufacturer(slug);

  return (
    <>
      <SystemHeader
        title={`MANUFACTURER / ${m.slug.toUpperCase()}`}
        fields={[
          { label: "ROBOTS", value: m.robots.length },
          ...(m.country ? [{ label: "REGION", value: m.country }] : []),
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
                  {m.is_public_company && m.ticker ? ` · ${m.ticker}` : ""}
                </p>
              )}
            </div>
            <div>
              <div className="ho-leader"><span>REGION</span><span className="fill" /><span style={m.country ? undefined : { color: "var(--ho-unknown)" }}>{regionLabel(m.country) ?? "UNKNOWN"}</span></div>
              <div className="ho-leader"><span>FOUNDED</span><span className="fill" /><span style={m.founded_year ? undefined : { color: "var(--ho-unknown)" }}>{m.founded_year ?? "UNKNOWN"}</span></div>
              <div className="ho-leader"><span>MODEL</span><span className="fill" /><span style={m.commercial_model ? undefined : { color: "var(--ho-unknown)" }}>{m.commercial_model ?? "UNKNOWN"}</span></div>
              <div className="ho-leader"><span>DEPLOY</span><span className="fill" /><span style={m.deployment_status ? undefined : { color: "var(--ho-unknown)" }}>{m.deployment_status ?? "UNKNOWN"}</span></div>
              <div className="ho-leader"><span>PUBLIC CO.</span><span className="fill" /><span>{m.is_public_company ? "YES" : "NO"}</span></div>
            </div>
          </div>
        </section>

        <section className="blk">
          <div className="blk-head">
            <div>
              <SectionIndex>01 — PORTFOLIO</SectionIndex>
              <h2>Robots</h2>
            </div>
            <SystemLabel>{m.robots.length} PUBLISHED</SystemLabel>
          </div>
          {m.robots.length > 0 ? (
            <div className="fit-list">
              {m.robots.map((r) => (
                <div className="fit-row" key={r.slug}>
                  <div className="fit-name">
                    <Link className="name" href={`/robots/${r.slug}`}>
                      {r.name}
                    </Link>
                  </div>
                  <StatusBracket status={r.commercial_status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">No published robots for this manufacturer.</p>
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
          <section className="blk" style={{ marginBottom: "var(--ho-sp-7)" }}>
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
      </div>
      <SiteFooter />
    </>
  );
}
