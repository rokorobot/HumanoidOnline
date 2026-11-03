// /insights/[slug] — one editorial article (DR-I1). Prose and sources come from lib/insights.ts; every
// robot the article names is rendered live from the catalogue API, never retyped. Unknown or draft
// slugs 404 (only published insights are routable).
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CommercialTriad } from "@/components/CommercialTriad";
import { JsonLd } from "@/components/JsonLd";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { StatusBadge } from "@/components/StatusBadge";
import { SystemHeader } from "@/components/SystemHeader";
import { findRobot } from "@/lib/api-client";
import { type Block, type Inline, findInsight, insightPath } from "@/lib/insights";
import { buildInsightJsonLd } from "@/lib/jsonld";
import { absoluteUrl } from "@/lib/site";
import type { RobotDetail } from "@/lib/types";

// Live robot blocks come from the API, so render per request like /robots/[slug]
// (a build-time prerender has no API). Unknown or draft slugs 404 via findInsight.
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const insight = findInsight((await params).slug);
  if (!insight) return { title: "Not found", robots: { index: false, follow: false } };
  const url = absoluteUrl(insightPath(insight.slug));
  return {
    title: insight.title,
    description: insight.description,
    alternates: { canonical: url },
    openGraph: {
      type: "article",
      title: insight.title,
      description: insight.description,
      url,
      publishedTime: insight.publishedAt,
      modifiedTime: insight.updatedAt,
    },
  };
}

function Inlines({ content }: { content: Inline[] }) {
  return (
    <>
      {content.map((c, i) =>
        typeof c === "string" ? (
          c
        ) : c.href.startsWith("/") ? (
          <Link key={i} href={c.href}>
            {c.text}
          </Link>
        ) : (
          <a key={i} href={c.href} rel="noopener">
            {c.text}
          </a>
        ),
      )}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case "heading":
      return <h2>{block.text}</h2>;
    case "paragraph":
      return (
        <p>
          <Inlines content={block.content} />
        </p>
      );
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag>
          {block.items.map((item, i) => (
            <li key={i}>
              <Inlines content={item} />
            </li>
          ))}
        </Tag>
      );
    }
    case "table":
      return (
        <div className="table-scroll">
          <table>
            <caption>{block.caption}</caption>
            <thead>
              <tr>
                {block.head.map((h) => (
                  <th key={h} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => (
                <tr key={row[0]}>
                  {row.map((cell, i) => (i === 0 ? <th key={i} scope="row">{cell}</th> : <td key={i}>{cell}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

// Live catalogue block: status and availability straight from the governed read.
function RobotBlock({ robot }: { robot: RobotDetail }) {
  const slug = robot.slug;
  return (
    <article className="rcard" data-testid="insight-robot" data-robot={slug}>
      <p className="meta">{robot.manufacturer.name}</p>
      <h3>
        <Link href={`/robots/${slug}`}>{robot.name}</Link>
      </h3>
      <StatusBadge status={robot.commercial_status} />
      <CommercialTriad
        status={robot.commercial_status}
        availabilityOffers={robot.availability_offers}
        deploymentCount={robot.deployments.length}
        strongestConfidence={null}
      />
      <p>
        <Link href={`/robots/${slug}`}>Full record →</Link>
      </p>
    </article>
  );
}

export default async function InsightPage({ params }: { params: Promise<{ slug: string }> }) {
  const insight = findInsight((await params).slug);
  if (!insight) notFound();
  // One governed read per linked robot; a robot the API can't return is simply not shown (never guessed).
  const robots = (await Promise.all(insight.robotSlugs.map((s) => findRobot(s)))).filter(
    (r): r is RobotDetail => r !== null,
  );

  return (
    <>
      <JsonLd data={buildInsightJsonLd(insight)} />
      <SystemHeader title="INSIGHTS" fields={[{ value: "DATED · SOURCED", label: "" }]} />
      <div className="wrap" data-testid="insight-article">
        <SiteNav />
        <div className="pagebar">
          <div>
            <SectionIndex>INSIGHTS</SectionIndex>
            <h1>{insight.title}</h1>
            <p className="meta">
              Published <time dateTime={insight.publishedAt}>{insight.publishedAt}</time> · Updated{" "}
              <time dateTime={insight.updatedAt}>{insight.updatedAt}</time> · HumanoidOnline
            </p>
          </div>
        </div>
        <div className="prose">
          <p>
            <b>Short answer:</b> {insight.summary}
          </p>
          {insight.body.map((b, i) => (
            <BlockView key={i} block={b} />
          ))}

          <h2>Live catalogue records</h2>
          <p>Current status and availability, read live from the HumanoidOnline catalogue.</p>
          {robots.map((r) => (
            <RobotBlock key={r.slug} robot={r} />
          ))}

          <h2 id="sources">Sources</h2>
          <ul data-testid="insight-sources">
            {insight.sources.map((s) => (
              <li key={s.url}>
                <a href={s.url} rel="nofollow noopener">
                  {s.title}
                </a>
                , {s.publisher}, <time dateTime={s.date}>{s.date}</time>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
