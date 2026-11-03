# DR-I1 — `/insights` editorial section

**Status:** APPROVED — 2026-11-03, Robert Konecny (product owner), in thread. A scope change under AGENTS.md rule 1.
**Related:** AGENTS.md rules 1, 6, 7; docs/23 §17; ADR-027 §2 (`/research` is generated from catalogue data and stays so).

## 1. Decision

HumanoidOnline gets a new on-site editorial section, `/insights`: an index plus one page per article. The first article is `agility-digit-5-europe-2027`, converted from the draft `marketing/drafts/agility-digit-5-europe-2027.md` (deleted; the article is its new home). The owner chose **not** to publish the article off-site.

## 2. Constraints

- **Web-only static content.** Articles are typed TypeScript in `apps/web/lib/insights.ts`. No backend, schema or catalogue change; no new npm or Python dependency; no Markdown library.
- **Facts rule.** Every article lists its sources (title, publisher, URL, date). Live catalogue facts (commercial status, specs, availability) for robots named in an article are not retyped: each linked robot is rendered from the existing API. Prose may state dated manufacturer statements with their source.
- **Drafts never leak.** A `draft` article does not render, is not in the index, the sitemap or `llms.txt`, and its URL is a 404.
- **Navigation.** Linked from the footer only. The main header navigation is unchanged.
- Existing layout, design tokens, JSON-LD helpers, sitemap and `llms.txt` are reused.
