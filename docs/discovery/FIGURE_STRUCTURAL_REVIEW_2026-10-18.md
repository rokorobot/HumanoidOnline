# Figure AI (`www.figure.ai`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `figure-ai-official`, done before any adapter
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
| 1 | 18:47:23 | `https://www.figure.ai/robots.txt` | 200; 61 B; sha256 `c0aeed8d990e…` |
| 2 | 18:48:22 | `https://www.figure.ai/` | 200; 39169 B; sha256 `007b6ee32c01…` |
| 3 | 18:48:25 | `https://www.figure.ai/sitemap.xml` | 200; 4384 B; sha256 `b8ff72471d48…` |
| 4 | 18:49:50 | `https://www.figure.ai/figure` | 200; 42044 B; sha256 `009e2458240b…` |
| 5 | 18:49:54 | `https://www.figure.ai/news` | 200; 56065 B; sha256 `b4c32dd9c577…` |
| 6 | 18:49:57 | `https://www.figure.ai/news/ramping-figure-03-production` | 200; 54944 B; sha256 `0ad005febf57…` |

Served by Vercel. No block, challenge or rate limit was met.

## robots.txt

`User-agent: *` / `Disallow: /index-privacy-policy` / `Disallow: /info`. Neither path is needed, and no group names our token. **`robots_status` reads `ALLOWED`.** Adapter path prefixes must not include `/info`.

## Page structure

- Next.js (`__NEXT_DATA__`). **No `canonical` on any page fetched**, and no JSON-LD.
- **Product page `/figure`:** title `Figure 03 | Figure`, first `<h1>` `FIGURE 03`. Only ~1.4 k characters of visible text are server-rendered: it is a media-heavy page with **no specification table** in the HTML.
- **News:** `/news` (index, h1s are article titles) and `/news/<slug>` articles (e.g. `/news/ramping-figure-03-production`, ~8.6 k characters, title = h1 = headline). The sitemap (36 URLs) lists all news slugs. Usable as an **announcement** pattern (`/news/<slug>`).
- Model naming varies across pages: `Figure 03` / `FIGURE 03` / `F.03` style, plus older `F.02` (`/news/f-02-decommission`). Generation identity (Figure 01 / 02 / 03) is an owner identity decision, and any alias needs the alias register.

## Commercial language observed

None. No price, no availability, no order route. The `$` on `/news` is article text. Deployment statements (e.g. BMW production) are press claims, kept as proposals for review.

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.figure.ai` |
| Candidate path prefixes | `/figure` (product), `/news/` (announcements); never `/info`, `/index-privacy-policy` |
| Seeds | `/figure`, `/news` |
| Extractor | `<title>` + `<h1>` agree on the product page; no canonical, so slug/title agreement only |
| Blockers | generation naming/alias decision (03 vs F.03 vs FIGURE 03); thin product page (identity and announcements only); adapter + fixtures |
