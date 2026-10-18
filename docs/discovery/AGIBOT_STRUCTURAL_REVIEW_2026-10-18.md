# AgiBot (`www.agibot.com`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `agibot-official`, done before any adapter
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
| 1 | 18:47:15 | `https://www.agibot.com/robots.txt` | 404; 1872 B; sha256 `6833254d2cba…` |
| 2 | 18:48:13 | `https://www.agibot.com/` | 200; 98010 B; sha256 `632e1b48dd9d…` |
| 3 | 18:48:17 | `https://www.agibot.com/sitemap.xml` | 200; 56703 B; sha256 `1c0adf5a8dd2…` |
| 4 | 18:49:33 | `https://www.agibot.com/products/A2` | 200; 105919 B; sha256 `555bc6808812…` |
| 5 | 18:49:38 | `https://www.agibot.com/products/X2` | 200; 131334 B; sha256 `08b47879dfae…` |
| 6 | 18:49:42 | `https://www.agibot.com/products/G2` | 200; 97366 B; sha256 `19816a25e950…` |

No block, challenge or rate limit was met.

## robots.txt

`https://www.agibot.com/robots.txt` returned **404**. Under RFC 9309 that means no restrictions (the same handling as `neurarobotics.px.media`). **`robots_status` reads `ALLOWED`, with the 404 recorded.** The runner re-reads it on every run, so a future file applies immediately.

## Page structure

- Server-rendered (3–9 k characters of visible text). No JSON-LD and no `<h1>`.
- **`canonical` points to the homepage on every product page** (`/products/A2`, `/products/X2`, `/products/G2` all declare `https://www.agibot.com/`). It is **not** an identity locator. The generic canonical/redirect learning must not use it for these pages (it would collapse every product onto `/`).
- `<title>` names the model only on A2 (`AGIBOT A2-AGIBOT Innovation …`). X2 and G2 carry the generic company title. Identity must come from the URL slug (`/products/<MODEL>`) plus a visible model heading block, via a source-specific extractor (the XPENG pattern).
- **Product URL family:** `/products/<MODEL>` (`A2`, `A2_Pro`, `A2_Ultra`, `A3`, `X1`, `X2`, `G1`, `G1_MAX`, `G2`, plus non-humanoid `C5`, `D1_*`, `OmniHand_*`, `VR`, `AIDEA`). Humanoid scope (A2/A3/X2/G2…) is the owner's call per model; wheeled G2 and dexterous hands need a scope decision.
- **Sitemap is malformed and partly stale.** Of 307 `<loc>` entries, several lack the slash after the host (`https://www.agibot.comproducts/A2`, `…comhttps://digit.com.cn/`), and many use an older `/product/<id>.html` family. It must not be used as an enumeration seed.
- Store link: `store.agibot.com`, **a separate host, not registered, not covered**. Other hosts: `genie.agibot.com`, `jp.agibot.com`, `www.zhiyuan-robot.com`, `agibot-world.com`.

## Commercial language observed

"Contact sales" on X2. No price. (The "reserve" token hit is the footer "All rights reserved".)

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.agibot.com` |
| Candidate path prefixes | `/products/` (individual models listed as seeds) |
| Seeds | fixed reviewed list of `/products/<MODEL>` URLs for in-scope humanoids |
| Extractor | source-specific; canonical must be ignored; slug + visible heading |
| Blockers | owner scope decisions per model (A2/A3/X1/X2/G1/G2 humanoid? G2 wheeled?); malformed sitemap; adapter + fixtures |
