// Compare-selection carry-over (UX-01 / P0-D, extended by UX-02C).
//
// The compare selection lives in the URL only:
//   /robots?compare=a,b          catalogue tray
//   /robots/<slug>?compare=a,b   robot detail (carried; the page itself never reads it on the server)
//   /compare?ids=a,b             comparison
// Server HTML hrefs stay PLAIN (`/compare`, `/robots`, `/robots/<slug>`) - crawl containment: no
// selection-carrying anchor is ever emitted. At CLICK time the link reads the current URL and,
// when it holds a selection, navigates to the equivalent URL on the target surface. No store,
// no cookie, no localStorage - the URL remains the single source.

export const MAX_COMPARE = 4;
const SLUG = /^[a-z0-9][a-z0-9-]{0,80}$/;
const DETAIL = /^\/robots\/([a-z0-9][a-z0-9-]*)$/;

/** Parse a comma-separated slug list: trimmed, validated, de-duplicated, at most MAX_COMPARE. */
export function parseSlugs(raw: string | null | undefined): string[] {
  const out: string[] = [];
  for (const part of (raw ?? "").split(",")) {
    const s = part.trim();
    if (SLUG.test(s) && !out.includes(s)) out.push(s);
    if (out.length === MAX_COMPARE) break;
  }
  return out;
}

/** The selection a page's URL currently carries (empty when none / not a carrying surface). */
export function selectionFromLocation(pathname: string, search: string): string[] {
  const params = new URLSearchParams(search);
  if (pathname === "/compare") return parseSlugs(params.get("ids"));
  if (pathname === "/robots" || DETAIL.test(pathname)) return parseSlugs(params.get("compare"));
  return [];
}

/** Add or remove a slug in a selection (adding is a no-op once MAX_COMPARE is reached). */
export function toggleSlug(selection: string[], slug: string): string[] {
  if (selection.includes(slug)) return selection.filter((s) => s !== slug);
  return selection.length >= MAX_COMPARE ? selection : [...selection, slug];
}

/**
 * Where a click on the nav/card link `href` should go given the current location, or
 * null to use the link's own href unchanged.
 */
export function resolveNavTarget(href: string, pathname: string, search: string): string | null {
  const selection = selectionFromLocation(pathname, search);
  if (selection.length === 0) return null;
  const list = selection.join(",");
  if (href === "/compare") {
    return pathname === "/compare" ? `/compare${search}` : `/compare?ids=${list}`; // on /compare: keep its state
  }
  if (href === "/robots") return `/robots?compare=${list}`;
  const detail = DETAIL.exec(href);
  if (detail) return `/robots/${detail[1]}?compare=${list}`;
  return null;
}
