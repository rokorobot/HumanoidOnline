// ADR-027 §8 — presentation of a Regional Research Resource.
//
// Pure rendering of the governed projection: every number, status, price and
// sentence comes from `data`; nothing is computed or authored here except
// labels. Unknown stays unknown ("Not published"); a missing offer is never
// rendered as "not available".
import Link from "next/link";

import { editorialState } from "@/lib/research-editorial";
import {
  type ResearchProjection,
  formatPriceState,
  statusLabel,
  transactionLabel,
} from "@/lib/research";
import type { ResearchRegion } from "@/lib/research";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function ResearchResource({
  data,
  preview,
  canonicalUrl,
}: {
  data: ResearchProjection;
  preview: boolean;
  canonicalUrl: string;
}) {
  const region = data.region.name;
  const kf = data.key_figures;
  const editorial = editorialState(data.region.slug as ResearchRegion, data.snapshot_date, preview);

  return (
    <article className="research-resource" data-region={data.region.slug}>
      {preview && (
        <p role="note" data-testid="preview-banner">
          <strong>Preview — not published.</strong> This resource is not public, is excluded from
          the sitemap and is marked noindex.
        </p>
      )}

      <h1>Which humanoid robots are available in {region}?</h1>
      <p>
        Snapshot <time dateTime={data.snapshot_date}>{data.snapshot_date}</time>. Generated from the
        HumanoidOnline catalogue; evidence must be dated within {data.freshness_days} days of the
        snapshot to count.
      </p>

      <section aria-labelledby="answer">
        <h2 id="answer">Direct answer</h2>
        <p data-testid="direct-answer">{data.direct_answer}</p>
      </section>

      <section aria-labelledby="figures">
        <h2 id="figures">Key figures</h2>
        <table>
          <caption>Counts at the snapshot date</caption>
          <tbody>
            <tr><th scope="row">Published humanoid robots (population)</th><td>{kf.published_population}</td></tr>
            <tr><th scope="row">With a confirmed {region} offer</th><td>{kf.robots_with_confirmed_offer}</td></tr>
            <tr><th scope="row">Manufacturers with a confirmed {region} offer</th><td>{kf.manufacturers_with_confirmed_offer}</td></tr>
            <tr><th scope="row">With no confirmed {region} offer on file</th><td>{kf.robots_without_confirmed_offer}</td></tr>
            <tr><th scope="row">Purchasable robots (each counted once, best status)</th><td>{kf.purchase_robots}</td></tr>
            {kf.purchase_by_best_status
              .filter((s) => s.robots > 0)
              .map((s) => (
                <tr key={s.status}><th scope="row">&nbsp;&nbsp;{statusLabel(s.status)}</th><td>{s.robots}</td></tr>
              ))}
            <tr><th scope="row">Purchasable robots with a published purchase price</th><td>{kf.purchase_robots_with_published_price}</td></tr>
            <tr><th scope="row">Purchasable robots with price on request</th><td>{kf.purchase_robots_price_on_request}</td></tr>
            <tr><th scope="row">Purchasable robots with price not published</th><td>{kf.purchase_robots_price_not_published}</td></tr>
            {kf.robots_by_other_transaction.map((t) => (
              <tr key={t.transaction_type}>
                <th scope="row">With a confirmed {transactionLabel(t.transaction_type).toLowerCase()} offer</th>
                <td>{t.robots}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="offers">
        <h2 id="offers">Confirmed offers in {region}</h2>
        {data.offers.length === 0 ? (
          <p>No confirmed {region} offer is on file for any published humanoid robot.</p>
        ) : (
          <table data-testid="offers-table">
            <caption>One row per robot, seller, country and transaction type</caption>
            <thead>
              <tr>
                <th scope="col">Robot</th>
                <th scope="col">Manufacturer</th>
                <th scope="col">Transaction</th>
                <th scope="col">Status</th>
                <th scope="col">Seller</th>
                <th scope="col">Country</th>
                <th scope="col">Price</th>
                <th scope="col">Evidence date</th>
                <th scope="col">Confidence</th>
                <th scope="col">Sources</th>
              </tr>
            </thead>
            <tbody>
              {data.offers.map((o) => (
                <tr key={`${o.robot_slug}|${o.provider_slug}|${o.region_code}|${o.transaction_type}`}>
                  <th scope="row"><Link href={`/robots/${o.robot_slug}`}>{o.robot_name}</Link></th>
                  <td>{o.manufacturer_name}</td>
                  <td>{transactionLabel(o.transaction_type)}</td>
                  <td>{statusLabel(o.availability_status)}</td>
                  <td>{o.provider_slug ?? "Seller not recorded"}{o.provider_type ? ` (${o.provider_type.toLowerCase()})` : ""}</td>
                  <td>{o.region_code}</td>
                  <td>
                    {o.prices.map((p, i) => (
                      <span key={i} data-price-kind={p.kind}>
                        {i > 0 && <br />}
                        {formatPriceState(p)}
                        {p.kind === "PUBLISHED" && p.price_basis ? <small> ({p.price_basis})</small> : null}
                      </span>
                    ))}
                  </td>
                  <td><time dateTime={o.evidence_date}>{o.evidence_date}</time></td>
                  <td>{o.confidence}{o.human_verified ? "" : " · no human verification recorded"}</td>
                  <td>
                    {o.source_urls.map((u, i) => (
                      <span key={u}>{i > 0 && ", "}<a href={u} rel="nofollow noopener">{host(u)}</a></span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {data.no_confirmed_offer.length > 0 && (
        <section aria-labelledby="none">
          <h2 id="none">No confirmed {region} offer on file</h2>
          <p>
            This lists robots for which HumanoidOnline holds no qualifying {region} evidence. It
            does not mean they are unavailable in {region}.
          </p>
          {data.no_confirmed_offer.map((g) => (
            <div key={g.reason} data-group={g.reason}>
              <h3>{g.label} ({g.robots.length})</h3>
              <ul>
                {g.robots.map((r) => (
                  <li key={r.slug}><Link href={`/robots/${r.slug}`}>{r.name}</Link></li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {editorial.show && (
        <section aria-labelledby="context" data-testid="editorial">
          <h2 id="context">Reading this resource</h2>
          {editorial.draft && <p role="note"><strong>DRAFT — editorial text not yet reviewed.</strong></p>}
          {editorial.outdated && <p role="note">This context was last reviewed more than 180 days before the snapshot and may be outdated.</p>}
          {editorial.fragment.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
          {editorial.fragment.reviewed_at && (
            <p><small>Reviewed {editorial.fragment.reviewed_at}.</small></p>
          )}
        </section>
      )}

      <section aria-labelledby="method">
        <h2 id="method">Methodology</h2>
        <dl>
          {Object.entries(data.methodology).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="faq">
        <h2 id="faq">Frequently asked questions</h2>
        {data.faq.map((f) => (
          <div key={f.question}>
            <h3>{f.question}</h3>
            <p>{f.answer}</p>
          </div>
        ))}
      </section>

      <section aria-labelledby="cite">
        <h2 id="cite">Cite this resource</h2>
        <p>
          HumanoidOnline, “Which humanoid robots are available in {region}?”, snapshot{" "}
          {data.snapshot_date}. <a href={canonicalUrl}>{canonicalUrl}</a>. Machine-readable:{" "}
          <a href={`${canonicalUrl}.json`}>JSON</a>.
        </p>
      </section>

      {preview && data.readiness && (
        <section aria-labelledby="readiness" data-testid="readiness">
          <h2 id="readiness">Publication readiness (review only)</h2>
          <p>
            Gate {data.readiness.gate_passes ? "passes" : "fails"}: {data.readiness.qualifying_robots} robots
            (minimum {data.readiness.min_robots}) from {data.readiness.qualifying_manufacturers} manufacturers
            (minimum {data.readiness.min_manufacturers}).
            {data.readiness.failures.length > 0 && ` ${data.readiness.failures.join("; ")}.`}
          </p>
        </section>
      )}
    </article>
  );
}
