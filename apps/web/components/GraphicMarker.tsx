// GraphicMarker — the square ▪ marker and dot-matrix blocks (§5 grammar).
// Presentational only; `signal` reserves orange for live/active facts.
import type { CSSProperties } from "react";

export function GraphicMarker({
  signal = false,
  style,
}: {
  signal?: boolean;
  style?: CSSProperties;
}) {
  return (
    <span
      aria-hidden="true"
      className={signal ? "ho-marker ho-marker--signal" : "ho-marker"}
      style={style}
    />
  );
}

export function DotMatrix({
  count = 4,
  signal = false,
}: {
  count?: 4 | 6;
  signal?: boolean;
}) {
  const cls = [
    "ho-dots",
    signal ? "ho-dots--signal" : "",
    count === 6 ? "ho-dots--6" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={cls} aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <i key={i} />
      ))}
    </span>
  );
}
