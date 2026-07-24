// One deterministic match result. Renders the integer score, the exact six-part
// score_breakdown (each value is the criterion's weighted contribution in points,
// summing to the score), the concrete reasons, and any warnings — every number
// reproducible from score_breakdown (frozen contract §7.5).
import Link from "next/link";

import type { MatchItem } from "@/lib/types";

const CRITERIA: [string, string][] = [
  ["use_case_fit", "Use-case fit"],
  ["commercial_availability", "Commercial"],
  ["technical_fit", "Technical"],
  ["geographic_fit", "Geography"],
  ["budget_fit", "Budget"],
  ["deployment_readiness", "Deployment"],
];

export function MatchCard({ match }: { match: MatchItem }) {
  const b = match.score_breakdown;
  return (
    <article className="mr-card" data-slug={match.robot.slug}>
      <div className="mr-top">
        <div className="mr-cat">{match.category.replace(/_/g, " ")}</div>
        <div className="mr-lock">
          <Link className="mr-name" href={`/robots/${match.robot.slug}`}>
            {match.robot.name}
          </Link>
          <span className="mr-mfr">{match.robot.manufacturer}</span>
        </div>
        <div className="mr-score">
          <span className="num">{match.score}</span>
          <span className="u">MATCH</span>
        </div>
      </div>

      <div className="mr-body">
        <div className="mr-breakdown" aria-label="Score breakdown">
          {CRITERIA.map(([k, label]) => {
            const v = b[k] ?? 0;
            const w = Math.max(0, Math.min(100, v));
            return (
              <div className="mr-bk" key={k}>
                <span className="k">{label}</span>
                <span className="bar" aria-hidden="true">
                  <i style={{ width: `${w}%` }} />
                </span>
                <span className={v > 0 ? "val" : "val unk"}>{v.toFixed(1)}</span>
              </div>
            );
          })}
        </div>

        <div className="mr-expl">
          <ul className="mr-reasons">
            {match.reasons.map((r, i) => (
              <li key={i}>
                <span className="mk">✓</span> {r}
              </li>
            ))}
          </ul>
          {match.warnings.length > 0 && (
            <ul className="mr-warns">
              {match.warnings.map((w, i) => (
                <li key={i}>
                  <span className="mk">⚠</span> {w}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mr-foot">
        <Link className="btn" href={`/robots/${match.robot.slug}`}>
          Robot detail →
        </Link>
      </div>
    </article>
  );
}
