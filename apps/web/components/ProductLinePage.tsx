// DR-L1 — product-line page body. Direct answer first, then the edition table.
// Server component, pure of I/O: the line is the governed `/api/product-lines/{slug}` read.
// The line states no fact of its own; every cell below comes from the edition's RobotDetail.
import Link from "next/link";

import { PriceStateCard } from "@/components/PricingState";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import {
  accessibleModes,
  priceDisplayFromHeadline,
  selectHeadline,
} from "@/lib/commercial-summary";
import { formatDate, resolveAvailabilitySummary } from "@/lib/format";
import { statusLabel } from "@/lib/labels";
import { buildLineAnswer } from "@/lib/line-answer";
import type { ProductLineDetail, RobotDetail } from "@/lib/types";

function unknownCell(text: string) {
  return <span style={{ color: "var(--ho-unknown)" }}>{text}</span>;
}

function EditionRow({ robot }: { robot: RobotDetail }) {
  const price = priceDisplayFromHeadline(selectHeadline(robot.pricing_offers ?? []));
  const avail = resolveAvailabilitySummary(accessibleModes(robot.availability_offers ?? []), "short");
  const s = robot.specs;
  return (
    <tr data-edition={robot.slug}>
      <th scope="row">
        <Link href={`/robots/${robot.slug}`}>{robot.name}</Link>
      </th>
      <td>{statusLabel(robot.commercial_status)}</td>
      <td>
        <PriceStateCard price={price} />
      </td>
      <td>{avail.isUnknown ? unknownCell(avail.label) : avail.label}</td>
      <td>{s.height_cm != null ? `${s.height_cm} cm` : unknownCell("Not published")}</td>
      <td>{s.degrees_of_freedom != null ? s.degrees_of_freedom : unknownCell("Not published")}</td>
      {/* has_sdk is already on the governed read: shown only when recorded, never inferred. */}
      <td>{s.has_sdk == null ? unknownCell("Not published") : s.has_sdk ? "Yes" : "No"}</td>
    </tr>
  );
}

export function ProductLinePage({ line }: { line: ProductLineDetail }) {
  const answer = buildLineAnswer(line.name, line.robots);
  return (
    <>
      <SystemHeader
        title={`PRODUCT LINE / ${line.slug.toUpperCase()}`}
        fields={[{ label: "EDITIONS", value: line.robots.length }]}
      />
      <div className="wrap">
        <SiteNav active="robots" />

        <div className="pagebar">
          <div>
            <SectionIndex>PRODUCT LINE</SectionIndex>
            <h1>{line.name}</h1>
          </div>
          <span className="meta">
            <Link href={`/manufacturers/${line.manufacturer.slug}`}>{line.manufacturer.name}</Link>
          </span>
        </div>

        <section className="blk" style={{ borderTop: 0 }} aria-labelledby="answer">
          <h2 id="answer">Direct answer</h2>
          <div data-testid="direct-answer">
            {answer.paragraphs.map((p, i) => (
              <p className="prose" key={i}>
                {p}
              </p>
            ))}
          </div>
          <p className="stamp" style={{ marginTop: 16 }}>
            Editions grouped by the manufacturer:{" "}
            <a href={line.source_url} rel="noopener noreferrer">
              {line.source_url}
            </a>
            {formatDate(line.observed_at) ? `, read ${formatDate(line.observed_at)}` : ""}.
            Every figure above and below belongs to the named edition; none is carried over from
            another edition.
          </p>
        </section>

        <section className="blk" style={{ marginBottom: "var(--ho-sp-7)" }} aria-labelledby="editions">
          <div className="blk-head">
            <div>
              <SectionIndex>01 — EDITIONS</SectionIndex>
              <h2 id="editions">Editions</h2>
            </div>
          </div>
          {line.robots.length > 0 ? (
            <div className="table-scroll">
              <table data-testid="edition-table">
                <caption>
                  Each row is one edition; the price shown is that edition&apos;s headline offer.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Edition</th>
                    <th scope="col">Status</th>
                    <th scope="col">Price</th>
                    <th scope="col">Availability</th>
                    <th scope="col">Height</th>
                    <th scope="col">Degrees of freedom</th>
                    <th scope="col">SDK access</th>
                  </tr>
                </thead>
                <tbody>
                  {line.robots.map((r) => (
                    <EditionRow key={r.slug} robot={r} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-state">No published editions.</p>
          )}
        </section>
      </div>
    </>
  );
}
