// ADR-027 §8 — presentation of a Regional Research Resource.
//
// Pure rendering of the governed projection: every number, status, price and
// sentence comes from `data`; nothing is computed or authored here except
// labels and the §8 section split. Unknown stays unknown ("Not published"); a
// missing offer is never rendered as "not available".
//
// Fixed section order (ADR-027 §8): direct answer, key figures, offers that are
// available/limited, waitlist/preorder/quote-only offers (kept apart from
// AVAILABLE), global-only robots (region unconfirmed), robots with no confirmed
// offer, deployments (use, not purchasability), editorial context, methodology,
// FAQ, citation. "What changed" is omitted: no reproducible delta exists yet.
import Link from "next/link";

import { editorialSourceLabel, editorialState } from "@/lib/research-editorial";
import {
  type ResearchOffer,
  type ResearchProjection,
  type ResearchRegion,
  formatPriceState,
  statusLabel,
  transactionLabel,
} from "@/lib/research";

// AVAILABLE (and constrained-but-orderable LIMITED) stay apart from offers that
// are waitlist, preorder or contact/quote-gated.
const DIRECT_STATUSES = new Set(["AVAILABLE", "LIMITED"]);

function sourceLabel(url: string): string {
  try {
    const u = new URL(url);
    const label = `${u.hostname.replace(/^www\./, "")}${u.pathname === "/" ? "" : u.pathname}`;
    return label.length > 44 ? `${label.slice(0, 43)}\u2026` : label;
  } catch {
    return url;
  }
}

// Sources are separate links, one per line, so they stay readable in a narrow column.
const robotLabel = (r: { name: string; manufacturer_name: string }) =>
  `${r.name} (${r.manufacturer_name})`;

function Sources({ urls }: { urls: string[] }) {
  return (
    <>
      {urls.map((u) => (
        <span key={u} className="src">
          <a href={u} rel="nofollow noopener">{sourceLabel(u)}</a>
        </span>
      ))}
    </>
  );
}

// A short basis ("incl VAT") stays inline, because it decides whether two prices are
// comparable. A long one is kept in full behind a disclosure so rows stay compact.
function PriceBasis({ text }: { text: string }) {
  if (text.length <= 60) return <small>{text}</small>;
  return (
    <details>
      <summary>Price basis</summary>
      <small>{text}</small>
    </details>
  );
}

function OfferTable({
  offers,
  testId,
  caption,
}: {
  offers: ResearchOffer[];
  testId: string;
  caption: string;
}) {
  return (
    <div className="table-scroll">
    <table data-testid={testId}>
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Robot</th>
          <th scope="col">Manufacturer</th>
          <th scope="col">Transaction</th>
          <th scope="col">Status</th>
          <th scope="col">Seller</th>
          <th scope="col">Region</th>
          <th scope="col">Price</th>
          <th scope="col">Evidence date</th>
          <th scope="col">Confidence</th>
          <th scope="col">Sources</th>
        </tr>
      </thead>
      <tbody>
        {offers.map((o) => (
          <tr key={`${o.robot_slug}|${o.provider_slug}|${o.region_code}|${o.transaction_type}`}>
            <th scope="row"><Link href={`/robots/${o.robot_slug}`}>{o.robot_name}</Link></th>
            <td><Link href={`/manufacturers/${o.manufacturer_slug}`}>{o.manufacturer_name}</Link></td>
            <td>{transactionLabel(o.transaction_type)}</td>
            <td>{statusLabel(o.availability_status)}</td>
            <td>
              {o.provider_slug ?? "Seller not recorded"}
              {o.provider_type ? ` (${o.provider_type.toLowerCase()})` : ""}
            </td>
            <td>{o.region_code}</td>
            <td>
              {o.prices.map((p, i) => (
                <span key={i} data-price-kind={p.kind}>
                  {i > 0 && <br />}
                  {formatPriceState(p)}
                  {p.kind === "PUBLISHED" && p.price_basis ? <PriceBasis text={p.price_basis} /> : null}
                </span>
              ))}
            </td>
            <td><time dateTime={o.evidence_date}>{o.evidence_date}</time></td>
            <td>{o.confidence}{o.human_verified ? "" : " · no human verification recorded"}</td>
            <td><Sources urls={o.source_urls} /></td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
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
  const direct = data.offers.filter((o) => DIRECT_STATUSES.has(o.availability_status));
  const gated = data.offers.filter((o) => !DIRECT_STATUSES.has(o.availability_status));
  const globalOnly = data.no_confirmed_offer.find((g) => g.reason === "GLOBAL_ONLY");
  const otherGroups = data.no_confirmed_offer.filter((g) => g.reason !== "GLOBAL_ONLY");

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

      {data.publication_health.status === "LIMITED_EVIDENCE" && (
        <div role="note" data-testid="limited-evidence-warning">
          <p>
            <strong>Limited current evidence.</strong> This resource remains published, but the
            current evidence on file no longer meets HumanoidOnline’s normal publication threshold.
            Stale offers are excluded from current availability figures.
          </p>
          {data.publication_health.reasons.length > 0 && (
            <ul>
              {data.publication_health.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <section aria-labelledby="answer">
        <h2 id="answer">Direct answer</h2>
        <p data-testid="direct-answer">{data.direct_answer}</p>
      </section>

      <section aria-labelledby="figures">
        <h2 id="figures">Key figures</h2>
        <div className="table-scroll table-scroll--narrow">
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
        </div>
      </section>

      <section aria-labelledby="offers">
        <h2 id="offers">Confirmed offers in {region}: available or limited</h2>
        {direct.length === 0 ? (
          <p data-testid="offers-available-empty">
            No offer with an available or limited status is on file for {region}.
          </p>
        ) : (
          <OfferTable
            offers={direct}
            testId="offers-available-table"
            caption="One row per robot, seller, region and transaction type"
          />
        )}
      </section>

      <section aria-labelledby="gated">
        <h2 id="gated">Waitlist, preorder and quote-only offers in {region}</h2>
        <p>
          These offers are confirmed on file but cannot be ordered directly: the buyer joins a
          waitlist, preorders, or must request a quote or contact the seller.
        </p>
        {gated.length === 0 ? (
          <p data-testid="offers-gated-empty">
            No waitlist, preorder or quote-only offer is on file for {region}.
          </p>
        ) : (
          <OfferTable
            offers={gated}
            testId="offers-gated-table"
            caption="One row per robot, seller, region and transaction type"
          />
        )}
      </section>

      {globalOnly && (
        <section aria-labelledby="global" data-testid="global-only">
          <h2 id="global">Global availability, region unconfirmed</h2>
          <p>
            These robots have only a global (or region-unspecific) offer on file. That is not
            evidence of availability in {region}, so they are not counted above.
          </p>
          <ul>
            {globalOnly.robots.map((r) => (
              <li key={r.slug}><Link href={`/robots/${r.slug}`}>{robotLabel(r)}</Link></li>
            ))}
          </ul>
        </section>
      )}

      {otherGroups.length > 0 && (
        <section aria-labelledby="none">
          <h2 id="none">No confirmed {region} offer on file</h2>
          <p>
            This lists robots for which HumanoidOnline holds no qualifying {region} evidence. It
            does not mean they are unavailable in {region}.
          </p>
          {otherGroups.map((g) => (
            <div key={g.reason} data-group={g.reason}>
              <h3>{g.label} ({g.robots.length})</h3>
              <ul>
                {g.robots.map((r) => (
                  <li key={r.slug}><Link href={`/robots/${r.slug}`}>{robotLabel(r)}</Link></li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      <section aria-labelledby="deployments" data-testid="deployments">
        <h2 id="deployments">Deployments in {region}</h2>
        <p>
          Deployment evidence shows that a robot has been used in {region}. It does not show that
          the robot can be purchased there.
        </p>
        {data.deployments.length === 0 ? (
          <p data-testid="deployments-empty">
            No evidenced deployment in {region} is on file for a published humanoid robot.
          </p>
        ) : (
          <div className="table-scroll">
          <table data-testid="deployments-table">
            <caption>Evidenced deployments, shown regardless of age</caption>
            <thead>
              <tr>
                <th scope="col">Robot</th>
                <th scope="col">Manufacturer</th>
                <th scope="col">Customer</th>
                <th scope="col">Region</th>
                <th scope="col">Status</th>
                <th scope="col">Units</th>
                <th scope="col">Started</th>
                <th scope="col">Evidence date</th>
                <th scope="col">Confidence</th>
                <th scope="col">Sources</th>
              </tr>
            </thead>
            <tbody>
              {data.deployments.map((d, i) => (
                <tr key={`${d.robot_slug}|${d.region_code}|${d.customer_name}|${i}`}>
                  <th scope="row"><Link href={`/robots/${d.robot_slug}`}>{d.robot_name}</Link></th>
                  <td><Link href={`/manufacturers/${d.manufacturer_slug}`}>{d.manufacturer_name}</Link></td>
                  <td>{d.customer_name ?? "Undisclosed"}</td>
                  <td>{d.region_code}</td>
                  <td>{d.status ?? "Not stated"}</td>
                  <td>{d.unit_count ?? "Not stated"}</td>
                  <td>{d.started_on ?? "Not stated"}</td>
                  <td><time dateTime={d.evidence_date}>{d.evidence_date}</time></td>
                  <td>{d.confidence}{d.human_verified ? "" : " · no human verification recorded"}</td>
                  <td><Sources urls={d.source_urls} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {editorial.show && (
        <section aria-labelledby="context" data-testid="editorial">
          <h2 id="context">Reading this resource</h2>
          {editorial.draft && <p role="note"><strong>DRAFT — editorial text not yet reviewed.</strong></p>}
          {editorial.outdated && <p role="note">This context was last reviewed more than 180 days before the snapshot and may be outdated.</p>}
          {editorial.fragment.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
          {editorial.fragment.sources.length > 0 && (
            <p data-testid="editorial-source">
              <small>
                Source:{" "}
                <a href={editorial.fragment.sources[0]} rel="noopener">
                  {editorialSourceLabel(editorial.fragment.sources[0])}
                </a>
              </small>
            </p>
          )}
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
