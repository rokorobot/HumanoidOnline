// SEO-03 — length discipline for <title> and meta description. Pure, so the same
// record always yields the same metadata.
//
// Descriptions come from catalogue text (summaries, direct answers) of any length.
// Search engines truncate past ~160 characters and treat very short ones as thin,
// so we keep whole sentences up to the limit and, when the text is too short, append
// a page-specific sentence built only from facts the page already shows.
import type { Metadata } from "next";

export const DESCRIPTION_MAX = 160;
export const DESCRIPTION_MIN = 70;
export const TITLE_MAX = 60;
// Must match the template in app/layout.tsx.
export const TITLE_SUFFIX = " — HumanoidOnline";

const squash = (s: string) => s.replace(/\s+/g, " ").trim();

function clamp(text: string): string {
  if (text.length <= DESCRIPTION_MAX) return text;
  // Whole sentences first: never cut a claim in half when a clean stop exists.
  const sentences = text.match(/[^.!?]+[.!?]+(?=\s|$)/g) ?? [];
  let out = "";
  for (const s of sentences) {
    const next = squash(out + s);
    if (next.length > DESCRIPTION_MAX) break;
    out = next;
  }
  if (out.length >= DESCRIPTION_MIN) return out;
  // One long sentence: cut at the last word boundary and mark the cut.
  const cut = text.slice(0, DESCRIPTION_MAX - 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > 0 ? cut.slice(0, space) : cut).replace(/[\s,;:—–-]+$/, "")}…`;
}

/** A 70–160 character description from `primary`, topped up with `extra` when short. */
export function fitDescription(primary: string | null | undefined, extra: string): string {
  const base = squash(primary ?? "");
  if (!base) return clamp(squash(extra));
  if (base.length >= DESCRIPTION_MIN) return clamp(base);
  const joined = /[.!?]$/.test(base) ? `${base} ${squash(extra)}` : `${base}. ${squash(extra)}`;
  return clamp(joined);
}

/** Keep the brand suffix only when the full title still fits in 60 characters. */
export function fitTitle(title: string): Metadata["title"] {
  return title.length + TITLE_SUFFIX.length <= TITLE_MAX ? title : { absolute: title };
}
