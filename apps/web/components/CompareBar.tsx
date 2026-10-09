// CompareBar — sticky tray showing the current compare selection built from the
// catalogue `compare` URL param. Navigates to /compare?ids=... (2–4 required).
import { nameFromSlug } from "@/lib/labels";
import { CompareLink } from "./CompareLink";

// `names` maps slug -> display name for robots on the current page. A selected robot
// that is not on the (filtered) page falls back to a de-slugged Title Case name -
// the raw slug is never shown.
export function CompareBar({
  slugs,
  names = {},
}: {
  slugs: string[];
  names?: Record<string, string>;
}) {
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
        Compare selection: {slugs.length} / 4 — {slugs.map((s) => names[s] ?? nameFromSlug(s)).join(" · ")}
      </span>
      {ready ? (
        // Emergency Compare Crawl Containment (v0.2) — a real <a href> here
        // survives a link-parsing crawler regardless of Next's prefetch
        // setting (see components/CompareLink.tsx). This bar's target changes
        // on every toggle and is never guaranteed to have been requested
        // before, so it must only become a request on an explicit click.
        <CompareLink className="btn btn--signal" href={`/compare?ids=${slugs.join(",")}`}>
          Open comparison →
        </CompareLink>
      ) : (
        <span className="ho-syslabel" style={{ color: "var(--ho-grey-400)" }}>
          Select at least 2 to compare
        </span>
      )}
    </div>
  );
}
