# Unitree Robotics (`www.unitree.com`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `unitree-robotics-official`, done before any adapter
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

## Requests (9, crawler user agent `HumanoidOnlineMarketBot/0.1`, ≥ 3 s apart, redirects not followed)

| # | Time (UTC) | URL | Result |
|---|---|---|---|
| 1 | 18:47:03 | `https://www.unitree.com/robots.txt` | 200; 70 B; sha256 `38154ea005f8…` |
| 2 | 18:48:01 | `https://www.unitree.com/` | 200; 69971 B; sha256 `530dbc16e723…` |
| 3 | 18:48:04 | `https://www.unitree.com/sitemap.xml` | 200; 8239 B; sha256 `f655644f0da1…` |
| 4 | 18:49:14 | `https://www.unitree.com/H2` | 302 → `/H2/` (not followed); 0 B; sha256 `e3b0c44298fc…` |
| 5 | 18:49:18 | `https://www.unitree.com/R1` | 302 → `/R1/` (not followed); 0 B; sha256 `e3b0c44298fc…` |
| 6 | 18:49:22 | `https://www.unitree.com/g1` | 302 → `/g1/` (not followed); 0 B; sha256 `e3b0c44298fc…` |
| 7 | 18:50:21 | `https://www.unitree.com/H2/` | 200; 58872 B; sha256 `2cffdcf67575…` |
| 8 | 18:50:24 | `https://www.unitree.com/R1/` | 200; 68878 B; sha256 `5b45881e6f65…` |
| 9 | 18:50:27 | `https://www.unitree.com/g1/` | 200; 67371 B; sha256 `9f7106b7bd92…` |

No block, challenge or rate limit was met.

## robots.txt

`User-agent:*` / `Disallow:` (empty, so everything is allowed) / `Sitemap:https://www.unitree.com/sitemap.xml`. The file starts with a UTF-8 BOM. No group names our token and there is no crawl-delay. **`robots_status` honestly reads `ALLOWED`.** Adapter note: the parser must tolerate the BOM. A test with these exact bytes is required.

## Page structure

- **Server-rendered Nuxt** (`__NUXT__` present). The product pages carry 6–7 k characters of visible text in the raw HTML, so no JS execution is needed.
- **Product URL family:** root-level slugs, `/H2/`, `/R1/`, `/g1/` (case varies by model; the homepage also links `/G1-D`, `/H2-D`, `/H2plus`, `/R1-7a`, `/R1-D`, `/G1pl`, `/h1`). The slash-less form answers **302 to the trailing-slash form on the same host** (the NEURA redirect shape). Seeds must be the trailing-slash URLs.
- **Sitemap is not usable for enumeration.** It lists 59 URLs, all under `/cn/` (Chinese site). None of the English product pages is in it. Seeds must therefore be a fixed, reviewed list, as for XPENG.
- **Identity locators:** no `<h1>`, no `canonical`, no JSON-LD. `og:title` is a site-wide Chinese boilerplate (`宇树科技—…`). `<title>` names the model (`Unitree H2 Destiny Awakening | Unitree Robotics`, `Unitree R1 | Unitree Robotics`), but the G1 title is an SEO string (`Humanoid robot G1_Humanoid Robot Functions_Humanoid Robot Price | …`). Identity therefore needs **URL slug + `<title>` model token agreement**, with a source-specific extractor. The generic `<h1>` and JSON-LD rules cannot be used.
- **Variants on one page:** the parameter table lists several editions per page (H2 / H2 EDU; R1 AIR / R1 / R1 EDU; G1 editions). Mapping an edition to a catalogue robot or variant (e.g. `unitree-h2` vs `unitree-h2-edu`, `unitree-r1-edu-u*`) is an **identity decision for the owner**. It is never fuzzy-matched.

## Commercial language observed (not interpreted; owner semantics needed)

- `Price（Tax and Shipping cost excluded）` table rows such as `H2 $29,900`, `H2 EDU Contact Sales`, `R1 AIR $4,900`, `R1 $5,900`, `R1 EDU Contact Sales`. The G1 page says `Price from $13.5K` and `US $13.5K`.
- These are manufacturer-published USD prices **excluding tax and shipping**, on a global site. They are not EU prices or retail offers, and they do not state availability. `from $…` is a starting price for the cheapest edition. `Contact Sales` is a quote route (ON_REQUEST semantics only for that edition), never a price. **Which `price_type` these map to, if any, is an owner decision (new semantic, condition 4).** Until then an adapter emits them as proposals at most, and they stay UNKNOWN in the catalogue.
- Store links point to `https://unistore.unitree.com` (**a separate host, not registered, not covered**) and `/booking` (Store/Cooperate).

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.unitree.com` only (`unistore.`, `support.`, `eai.` … are other hosts) |
| Candidate path prefixes | `/H2/`, `/R1/`, `/g1/` (+ the other model slugs once reviewed individually) |
| Seeds | fixed reviewed list of trailing-slash product URLs; no link-following needed |
| Extractor | source-specific, identity-only first: slug + `<title>` model token; editions listed, never resolved automatically |
| Blockers | owner decisions on edition→robot mapping and on the USD tax-excluded price semantics; adapter + offline fixtures from these bodies |
