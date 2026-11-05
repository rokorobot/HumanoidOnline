// DR-UI2 — home "Obtainable now" board (dark hero register). One row per
// commercially accessible robot from the list read: obtainable modes (canonical
// available_modes), the headline price WITH its seller, region and terms (same
// offer row as the amount), and maturity. Per-offer status and evidence live on
// the robot page's offer board; this row claims nothing beyond the list data.
import Link from "next/link";

import { PriceStateCard } from "@/components/PricingState";
import { StatusBracket } from "@/components/StatusBadge";
import { modeLabel } from "@/lib/format";
import type { RobotListItem } from "@/lib/types";

export function HomeOfferBoard({
  robots,
  tabs,
}: {
  robots: RobotListItem[];
  tabs: { mode: string; label: string; count: number }[];
}) {
  return (
    <div className="home-board">
      <ul className="home-board__tabs" aria-label="Obtainable as">
        {tabs.map((t) => (
          <li key={t.mode}>
            <Link href={`/robots?transaction_type=${t.mode}&view=board`}>
              {t.label} <span className="n">{t.count}</span>
            </Link>
          </li>
        ))}
      </ul>
      {robots.length > 0 ? (
        <div className="home-board__scroll" tabIndex={0} role="group" aria-label="Obtainable now">
          <table>
            <thead>
              <tr>
                <th scope="col">Robot</th>
                <th scope="col">Obtainable as</th>
                <th scope="col">Headline price</th>
                <th scope="col">Maturity</th>
                <th scope="col">
                  <span className="sr-only">Detail</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {robots.map((r) => (
                <tr key={r.slug}>
                  <td>
                    <div className="hb-robot">
                      <span className="hb-thumb" aria-hidden="true">
                        {r.primary_image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={r.primary_image.image_url} alt="" loading="lazy" />
                        ) : null}
                      </span>
                      <span>
                        <Link className="hb-name" href={`/robots/${r.slug}`}>
                          {r.name}
                        </Link>
                        <span className="hb-mfr">{r.manufacturer.name}</span>
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className="cb-modes">
                      {r.available_modes.map((m) => (
                        <span key={m} className="ob-flap" data-enum={m}>
                          {modeLabel(m)}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td>
                    <PriceStateCard price={r.price_display} />
                  </td>
                  <td>
                    <StatusBracket status={r.commercial_status} />
                  </td>
                  <td>
                    <Link className="hb-go" href={`/robots/${r.slug}#pricing`} aria-label={`${r.name}: offers`}>
                      Offers →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-state">No robots currently expose a commercially-accessible offer.</p>
      )}
      <div className="home-board__foot">
        <span>Each price shows its seller, market and terms. Status and evidence per offer are on each robot page.</span>
        <Link href="/robots?view=board">Open the catalogue board →</Link>
      </div>
    </div>
  );
}
