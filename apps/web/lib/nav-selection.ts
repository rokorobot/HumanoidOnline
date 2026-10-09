// Header-nav selection carry-over (UX-01 / P0-D).
//
// The compare selection lives in the URL only: `/robots?compare=a,b` (catalogue
// tray) and `/compare?ids=a,b` (comparison). The header nav links stay plain
// `href="/compare"` / `href="/robots"` in the server HTML (crawl-containment: no
// selection-carrying anchors are ever emitted). At CLICK time the nav reads the
// current URL and, when it holds a selection, navigates to the equivalent URL on
// the other surface. No store, no cookie - the URL remains the single source.

function splitSlugs(raw: string | null): string[] {
  return (raw ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Where a click on the nav link `href` should go given the current location, or
 * null to use the link's own href unchanged.
 */
export function resolveNavTarget(
  href: string,
  pathname: string,
  search: string,
): string | null {
  const params = new URLSearchParams(search);
  if (href === "/compare") {
    if (pathname === "/compare") return `/compare${search}`; // already there: keep its state
    if (pathname === "/robots") {
      const slugs = splitSlugs(params.get("compare"));
      if (slugs.length > 0) return `/compare?ids=${slugs.join(",")}`;
    }
    return null;
  }
  if (href === "/robots") {
    const slugs =
      pathname === "/compare"
        ? splitSlugs(params.get("ids"))
        : pathname === "/robots"
          ? splitSlugs(params.get("compare"))
          : [];
    if (slugs.length > 0) return `/robots?compare=${slugs.join(",")}`;
    return null;
  }
  return null;
}
