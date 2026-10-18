# Booster Robotics (`www.booster.tech`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `booster-robotics-official`, done before any adapter
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
| 1 | 18:47:10 | `https://www.booster.tech/robots.txt` | 200; 76 B; sha256 `f69e8c0401a4…` |
| 2 | 18:48:05 | `https://www.booster.tech/` | 302 → `/?target=en` (not followed); 242 B; sha256 `315d782474c6…` |
| 3 | 18:48:10 | `https://www.booster.tech/sitemap-index.xml` | 200; 187 B; sha256 `364d6ecd40ce…` |
| 4 | 18:49:26 | `https://www.booster.tech/?target=en` | 200; 120533 B; sha256 `45a8e0532ba4…` |
| 5 | 18:49:31 | `https://www.booster.tech/sitemap-0.xml` | 200; 7666 B; sha256 `7af7498db2e1…` |
| 6 | 18:50:28 | `https://www.booster.tech/booster-t2/` | 302 → `/booster-t2/?target=en` (not followed); 242 B; sha256 `315d782474c6…` |
| 7 | 18:50:32 | `https://www.booster.tech/booster-k1/` | 302 → `/booster-k1/?target=en` (not followed); 242 B; sha256 `315d782474c6…` |
| 8 | 18:50:35 | `https://www.booster.tech/store/` | 302 → `/store/?target=en` (not followed); 242 B; sha256 `315d782474c6…` |
| 9 | 18:50:44 | `https://www.booster.tech/booster-t2/?target=en` | 200; 160680 B; sha256 `5dd473678c3b…` |

No block, challenge or rate limit was met.

## robots.txt

`User-agent: *` / `Allow: /` / `Sitemap: https://www.booster.tech/sitemap-index.xml`. No group names our token and there is no crawl-delay. **`robots_status` honestly reads `ALLOWED`.**

## Page structure

- **Every English page 302-redirects to the same path with `?target=en`** (`/` → `/?target=en`, `/booster-t2/` → `/booster-t2/?target=en`), on the same host. Seeds must be the `?target=en` URLs. The adapter's URL normalization must keep this query parameter, or treat the 302 as a same-resource redirect. Either way a fixture test is required.
- Static Astro site (`_astro` assets), fully server-rendered: the T2 page has about 11 k characters of visible text.
- **JSON-LD `Product` on the T2 page**: `name: "Booster T2"`, `brand: Booster Robotics`, `url: https://www.booster.tech/booster-t2/`, matching `canonical` and `<h1>Booster T2</h1>`. Identity has three agreeing locators, the cleanest of the six sources. **There is no `offers` block**, so no price or availability is machine-stated.
- **Sitemap** (`sitemap-index.xml` → `sitemap-0.xml`, 34 URLs): English `/booster-t2/`, `/booster-k1/`, `/education/`, `/news/`, `/store/` and `/cn/` copies. **No T1 page exists in the sitemap.** The catalogue's T1 cannot be monitored from this site as listed.
- "Buy now" links go to `/store?key=t2&target=en` and `/store?key=k1&target=en` (same host). The store page was not fetched beyond its 302. Whether it states prices, and whether it is a reviewed path, is a separate review step. `agentstore.booster.tech`, `docs.`, `studio.` and `support.` are other hosts.

## Commercial language observed

"Buy now" call-to-action only. No price on the pages fetched. The homepage `$` is a funding-round headline (`Raises Nearly $150M`), not a price. An adapter must never read it as one (a fixture test with this body is required).

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.booster.tech` |
| Candidate path prefixes | `/booster-t2/`, `/booster-k1/` (identity); `/store` only after its own review |
| Seeds | `/booster-t2/?target=en`, `/booster-k1/?target=en` (K1 body not fetched yet; the request cap was reached) |
| Extractor | generic JSON-LD `Product` path works for identity (name + canonical + h1 agree) |
| Blockers | query-string handling in normalization; K1 page fixture; store page review; T1 absent from site |
