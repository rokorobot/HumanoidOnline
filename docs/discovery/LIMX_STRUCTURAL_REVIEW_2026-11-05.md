# LimX Dynamics (`www.limxdynamics.com`) structural review: 2026-11-05

Read-only, bounded inspection of the source `limx-dynamics-official` (registered in `db/discovery/source_registry.json`, PR #222), done before any adapter exists. It limits what a future adapter may assume. **It is not an adapter, enables nothing and records no eligibility decision.**

## Authority

Robert Konecny (product owner), in thread 2026-11-05: "go" on the structural-review work order offered for `limx-dynamics-official` and `faraday-future-official`, as a step towards `OWNER_AUTHORIZED` monitoring (docs/28 A4, §3 step 1). That is an internal business decision, **not publisher consent**, and `tos_status` stays `UNKNOWN`. The terms of service were not read or assessed.

Method: retrieved 2026-11-05 by an AI agent (Claude Code), with the crawler's own user agent `HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)`. robots.txt was fetched first and every later URL was checked against it with the repository's own parser (`app.services.discovery.robots`). Requests were at least 3 s apart, 7 in total, redirects were recorded but not followed, nothing was retried. These are agent observations, **not** MANUAL_BOOTSTRAP readings and not verified facts (docs/16 §2.1). Response bodies were kept locally for fixtures and are not committed.

Disclosure: on 2026-10-31 the same pages (`/en/products/luna`, `/ja/news/BK000062`) were also read with an ordinary fetch tool and curl for the catalogue (values recorded in the robot files); that was before and outside this review.

## Requests (7, crawler user agent, ≥ 3 s apart, redirects not followed)

| Time (UTC) | URL | Result |
|---|---|---|
| 19:31:30 | `https://www.limxdynamics.com/robots.txt` | 200; 507 B (gzip); sha256 `6e921b9b3f09…` |
| 19:31:34 | `https://www.limxdynamics.com/sitemap.xml` | 200; 5759 B (gzip); sha256 `17349a72d8c4…` |
| 19:31:38 | `https://www.limxdynamics.com/` | 302 → `/zh` (not followed); 138 B |
| 19:31:42 | `https://www.limxdynamics.com/en/products/oli` | 200; 51721 B (gzip); sha256 `575230fbbc0d…` |
| 19:31:46 | `https://www.limxdynamics.com/en/products/luna` | 200; 51365 B (gzip); sha256 `e36410b3079c…` |
| 19:31:49 | `https://www.limxdynamics.com/en/products/oli/spec` | 200; 46551 B (gzip); sha256 `f2afdd1a0522…` |
| 19:31:53 | `https://www.limxdynamics.com/en/products/luna/spec` | 200; 45397 B (gzip); sha256 `b6b7987b4e65…` |

No block, challenge or rate limit was met.

## robots.txt

**200.** Group `*`: `Allow: /`, `Disallow: /api/`, `Disallow: /admin/`. Named groups for search and AI crawlers (including `ClaudeBot`, `GPTBot`) are all `Allow: /`; none names `HumanoidOnlineMarketBot`, so group `*` applies. Sitemaps: `/sitemap.xml`, `/sitemap-images.xml`. No `Crawl-delay`. **`robots_status` reads `ALLOWED`** for the product paths below; the runner must re-read robots.txt every run.

## Page structure

- Responses are **gzip-compressed even without `Accept-Encoding`**: the fetcher must decompress.
- `/` answers **302 to `/zh`**. Locale prefixes `/en`, `/zh`, `/ko`, `/ja` exist; use `/en/…` seeds explicitly.
- Product and spec pages are server-rendered (4–6 k characters of visible text), with a self-referential `canonical`, a descriptive `<title>`, one `<h1>`, a meta description and 6–8 JSON-LD blocks. Identity can come from the URL slug plus `<h1>`/canonical.
- Product URL family in the sitemap: `/<locale>/products/<slug>` with `/spec`, `/video`, `/download`, `/faq` children, for `tron1`, `tron2`, `oli`, `luna`, `fluxvla`; plus `/news/BK<number>`, `/documents/<id>`.
- Spec values observed (not recorded here as facts): Oli 165 cm, 31 DoF; Luna 160 cm, 27 DoF (meta descriptions).
- Prices are **not** on product pages; the Luna China price is in the news notice `/en/news/BK000062` (`/ja/news/BK000062` was read 2026-10-31).

## Commercial language observed

"Buy Now" links to `/en/order`. The order page was not requested in this review.

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.limxdynamics.com` |
| Candidate path prefixes | `/en/products/oli`, `/en/products/luna` (+ their `/spec`), `/en/news/` for launch and price notices |
| Seeds | fixed reviewed list of those URLs |
| Extractor | source-specific; gzip; JSON-LD plus visible spec table; canonical is usable here |
| Blockers | owner scope for `tron1`, `tron2`, `fluxvla` (multi-form or software, not described as humanoid); `/en/order` not reviewed; no adapter or fixtures yet; a seller (`knoxlabs.com`) is a different host and not covered |
