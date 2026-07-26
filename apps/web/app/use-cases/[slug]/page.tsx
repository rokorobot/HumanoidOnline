// Use-case detail — from /api/use-cases/{slug}. 404 -> notFound().
// suitable_robots ordered by fit_score desc (from the API).
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { findUseCase } from "@/lib/api-client";
import { StatusBracket } from "@/components/StatusBadge";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

export const dynamic = "force-dynamic";

// WS8.5 / R22 — one governed read shared by the page and generateMetadata via
// React cache() (per-request memoization), never an alternate data path.
const getUseCaseCached = cache(findUseCase);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const u = await getUseCaseCached(slug);
  if (!u) return { title: "Not found" };
  return {
    title: u.name,
    description:
      u.description ??
      `Humanoid robots suited to ${u.name}, ranked by fit on HumanoidOnline.`,
  };
}

export default async function UseCaseDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const u = await getUseCaseCached(slug);
  if (!u) notFound();

  return (
    <>
      <SystemHeader
        title={`USE CASE / ${u.slug.toUpperCase()}`}
        fields={[
          { label: "SUITABLE", value: u.suitable_robots.length },
          ...(u.category ? [{ label: "CATEGORY", value: u.category }] : []),
        ]}
      />
      <div className="wrap">
        <SiteNav active="use-cases" />

        <div className="pagebar">
          <div>
            <SectionIndex>USE-CASE RECORD</SectionIndex>
            <h1>{u.name}</h1>
          </div>
          {u.category && <span className="meta">{u.category}</span>}
        </div>

        <section className="blk" style={{ borderTop: 0 }}>
          <p className="prose">{u.description ?? "No description on record."}</p>
          {u.typical_requirements && (
            <p className="stamp" style={{ marginTop: 16 }}>
              Typical requirements: {u.typical_requirements}
            </p>
          )}
          {u.key_limitations && (
            <p className="stamp" style={{ marginTop: 8 }}>
              Key limitations: {u.key_limitations}
            </p>
          )}
          {u.typical_tasks && u.typical_tasks.length > 0 && (
            <div className="taglist">
              {u.typical_tasks.map((t, i) => (
                <span className="ho-chip" key={i}>
                  {t}
                </span>
              ))}
            </div>
          )}
        </section>

        <section className="blk" style={{ marginBottom: "var(--ho-sp-7)" }}>
          <div className="blk-head">
            <div>
              <SectionIndex>01 — SUITABLE ROBOTS</SectionIndex>
              <h2>Ranked by fit</h2>
            </div>
            <SystemLabel>ORDERED BY FIT_SCORE — DESC</SystemLabel>
          </div>
          {u.suitable_robots.length > 0 ? (
            <div className="fit-list">
              {u.suitable_robots.map((r) => (
                <div className="fit-row" key={r.slug}>
                  <div className="fit-name">
                    <Link className="name" href={`/robots/${r.slug}`}>
                      {r.name}
                    </Link>
                    {r.commercial_readiness && (
                      <StatusBracket status={r.commercial_readiness} />
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    {r.limitations && (
                      <span className="stamp" style={{ maxWidth: "40ch" }}>
                        {r.limitations}
                      </span>
                    )}
                    <span className="fit-score">
                      {r.fit_score != null ? (
                        `FIT ${(r.fit_score * 100).toFixed(0)}%`
                      ) : (
                        <span style={{ color: "var(--ho-unknown)" }}>FIT UNKNOWN</span>
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">No suitable robots recorded for this use case.</p>
          )}
        </section>
      </div>
    </>
  );
}
