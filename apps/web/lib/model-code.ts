// Presentation helper kept out of components/RobotCard.tsx so pages that only need the
// model token (robot detail, compare) do not pull the card's client components in.
// Derive a short machine model token from the canonical slug (presentational —
// derived from a real identifier, not a fabricated fact).
export function deriveModelCode(slug: string, mfrSlug: string): string {
  let token = slug;
  if (mfrSlug && slug.startsWith(`${mfrSlug}-`)) {
    token = slug.slice(mfrSlug.length + 1);
  } else if (slug.includes("-")) {
    token = slug.split("-").slice(1).join("-");
  }
  return token.replace(/-/g, " ").toUpperCase();
}

