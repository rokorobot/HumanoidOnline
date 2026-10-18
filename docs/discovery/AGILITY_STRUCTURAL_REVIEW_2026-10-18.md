# Agility Robotics (`www.agilityrobotics.com`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `agility-robotics-official`, done before any adapter
was written. It limits what a future adapter may assume. **It is not an adapter, enables
nothing and records no eligibility decision.**

## Authority

Robert Konecny (product owner), review follow-up to PR #162 (2026-10-18): "six separate,
bounded structural reviews … Inspect applicable robots.txt rules and candidate source pages,
respect technical blocks and applicable restrictions, and produce documented findings for
adapter implementation. Do not perform unrestricted crawling." It rests on the 2026-10-18
owner instruction adding the source to the discovery monitoring programme (docs/28 A4,
`OWNER_AUTHORIZED`). That is an internal business decision, **not publisher consent**, and
`tos_status` stays `UNKNOWN`. The terms of service were not read or assessed.

Method: retrieved 2026-10-18 by an AI agent (Claude Code), with the crawler's own user agent
`HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)` and no other
identity. robots.txt was fetched first and every later URL was checked against it with the
repository's own parser (`app.services.discovery.robots`) before being requested. Requests
were at least 3 s apart, capped at 10 per host, redirects were recorded but not followed,
and nothing was retried. These are agent observations, **not** MANUAL_BOOTSTRAP readings and
not verified facts (docs/16 §2.1). Response bodies were retained locally for adapter fixtures
and are not committed here.

## Requests (6, crawler user agent `HumanoidOnlineMarketBot/0.1`, ≥ 3 s apart, redirects not followed)

| # | Time (UTC) | URL | Result |
|---|---|---|---|
| 1 | 18:47:19 | `https://www.agilityrobotics.com/robots.txt` | 200; 52 B; sha256 `a7c5087772d1…` |
| 2 | 18:48:18 | `https://www.agilityrobotics.com/` | 200; 157131 B; sha256 `26d6f85a1a2c…` |
| 3 | 18:48:21 | `https://www.agilityrobotics.com/sitemap.xml` | 200; 26500 B; sha256 `8ba1f79743f6…` |
| 4 | 18:49:43 | `https://www.agilityrobotics.com/solutions/digit-5` | 200; 332462 B; sha256 `920237e2a1b9…` |
| 5 | 18:49:46 | `https://www.agilityrobotics.com/solutions/digit/spec-sheet` | 200; 124212 B; sha256 `ad348b084834…` |
| 6 | 18:49:49 | `https://www.agilityrobotics.com/press` | 200; 125386 B; sha256 `a8ad075cce20…` |

Served through Cloudflare. No block, challenge or rate limit was met for our agent.

## robots.txt

The file contains only `Sitemap: https://www.agilityrobotics.com/sitemap.xml`. With no user-agent groups, nothing is disallowed. **`robots_status` reads `ALLOWED`.**

## Page structure

- Server-rendered (Webflow-style markup). Good locators: `<title>`, `<h1>`, `og:title` and a self-referencing `canonical` on every page fetched. No JSON-LD.
- **Product page:** `/solutions/digit-5`, title `Digit 5 | Agility`, h1 `Digit 5: Safety designed to unlock scale`, about 28 k characters of text.
- **`/solutions/digit/spec-sheet` has only ~0.9 k characters of visible text** (heading plus links to `/sales`). The specification content is not in the HTML: it is a form-gated or script-delivered download. An adapter cannot read specs from it, and we do not submit forms (LIVE.3 spirit).
- **Sitemap** (145 URLs, served as `application/rss+xml`): `/solutions/digit-5`, `/solutions/digit/*`, press articles under `/content/<slug>` (e.g. `/content/digit-deployed-at-gxo-in-historic-humanoid-raas-agreement`), `/press`. The `/content/` family is a usable **announcement** pattern for deployment/maturity signals.

## Commercial language observed

No price anywhere. "Contact sales" / "Deploy Digit" route to `/sales` (a form). The only `$` amounts are in executive biographies (`$1.5B …`), which a fixture test must keep from ever becoming a price. Deployment statements in press articles are **editorial/press claims**. They become deployment proposals for human review, never verified deployments.

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.agilityrobotics.com` |
| Candidate path prefixes | `/solutions/digit-5` (product), `/content/` (announcements), `/press` (index) |
| Seeds | `/solutions/digit-5`; announcements from `/press` or the sitemap's `/content/` entries (bounded) |
| Extractor | generic `<h1>`/title identity works; announcements need the announcement pattern |
| Blockers | spec sheet not machine-readable; `Digit` vs `Digit 5` identity/edition decision for the owner; adapter + fixtures |
