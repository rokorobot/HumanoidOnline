// CompareBar — sticky tray showing the current compare selection built from the
// catalogue `compare` URL param. Links to /compare?ids=... (2–4 required).
import Link from "next/link";

export function CompareBar({ slugs }: { slugs: string[] }) {
  if (slugs.length === 0) return null;
  const ready = slugs.length >= 2 && slugs.length <= 4;
  return (
    <div
      style={{
        position: "sticky",
        bottom: 0,
        zIndex: 5,
        background: "var(--ho-ink)",
        color: "var(--ho-paper-ink)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "12px 20px",
        flexWrap: "wrap",
        borderTop: "var(--ho-rule-med) solid var(--ho-signal)",
      }}
    >
      <span className="ho-syslabel" style={{ color: "var(--ho-paper-ink)" }}>
        COMPARE SELECTION: {slugs.length} / 4 — {slugs.join(" · ")}
      </span>
      {ready ? (
        // Emergency Compare Traffic Containment — this link's target is the
        // live compare selection, which changes on every toggle and is never
        // guaranteed to have been requested before. Default viewport prefetch
        // would trigger a full (currently unbatched) compare backend
        // computation merely from this bar scrolling into view, before the
        // user ever clicks it.
        <Link
          className="btn btn--signal"
          href={`/compare?ids=${slugs.join(",")}`}
          prefetch={false}
        >
          Open comparison →
        </Link>
      ) : (
        <span className="ho-syslabel" style={{ color: "var(--ho-grey-400)" }}>
          SELECT AT LEAST 2 TO COMPARE
        </span>
      )}
    </div>
  );
}
