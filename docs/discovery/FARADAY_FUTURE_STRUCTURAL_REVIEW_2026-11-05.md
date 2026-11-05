# Faraday Future robotics (`robotics.ff.com`) structural review: 2026-11-05

Read-only, bounded inspection of the source `faraday-future-official` (registered in `db/discovery/source_registry.json`, PR #223), done before any adapter exists. It limits what a future adapter may assume. **It is not an adapter, enables nothing and records no eligibility decision.**

## Authority

Robert Konecny (product owner), in thread 2026-11-05: "go" on the structural-review work order offered for `limx-dynamics-official` and `faraday-future-official` (docs/28 A4, §3 step 1). Internal business decision, **not publisher consent**; `tos_status` stays `UNKNOWN`; the terms of service were not read.

Method: retrieved 2026-11-05 by an AI agent (Claude Code) with the crawler user agent `HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)`; robots.txt first, then every URL checked with `app.services.discovery.robots`; ≥ 3 s apart, 5 requests, redirects not followed, no retries. Agent observations, **not** MANUAL_BOOTSTRAP readings and not verified facts. Bodies kept locally, not committed.

Disclosure: on 2026-10-31 the same pages were read with curl and a real browser (page rendered, `/us/ff-futurist/` and `/us/futurist/`) for the catalogue; that was before and outside this review.

## Requests (5)

| Time (UTC) | URL | Result |
|---|---|---|
| 19:32:14 | `https://robotics.ff.com/robots.txt` | 200; 117 B; sha256 `0d41b7de6d13…` |
| 19:32:17 | `https://robotics.ff.com/us/sitemap.xml` | 200; 4794 B; sha256 `b98428224186…` |
| 19:32:21 | `https://robotics.ff.com/us/` | 200; 626112 B; sha256 `0abf7a9f10e9…` |
| 19:32:25 | `https://robotics.ff.com/us/ff-futurist/` | 200; 945545 B; sha256 `af1337f9ad61…` |
| 19:32:29 | `https://robotics.ff.com/us/futurist/` | 200; 465335 B; sha256 `5eedc8bbb2cb…` |

No block, challenge or rate limit was met.

## robots.txt

**200.** `User-agent: *` / `Allow: /`; sitemaps `/us/sitemap.xml` and `/sitemap.xml`. No disallow, no `Crawl-delay`. **`robots_status` reads `ALLOWED`.** The separate host `www.ff.com` has a different robots.txt (disallows `/us/media/*`, `/press/*`, `/api`, `/en/*`, `/zh-hans/*`) and is **not** covered or registered.

## Page structure

- Pages are large (0.5–0.9 MB) and the readable content is rendered client-side. The static response nonetheless **contains the page data**: product values (for example the All-New Futurist 174 cm, 89,900 and 129,900 USD) and menu data sit in embedded page configuration, plus 2 JSON-LD blocks. No `<h1>`.
- **`canonical` points to another host** (`https://www.ff.com/us/robotics/…`). It is not an identity locator; identity must come from the URL slug (`/us/ff-futurist/`, `/us/futurist/`).
- **The embedded data is not self-consistent.** On `/us/ff-futurist/` the JSON-LD offer says 34,990 USD while the menu says "From $84,990" and the rendered block "Futurist Ultra $139,990"; menu defaults list other prices. An extractor must not take JSON-LD or menu defaults as the price of a model without a rule; this review records the hazard, not a rule.
- Two Futurist generations coexist: `/us/ff-futurist/` (older, banner "Coming Soon on 6/22") and `/us/futurist/` ("FF All-New Futurist", two editions).
- Product URL family from the sitemap (`/us/…`): `ff-futurist`, `futurist`, `ff-master`, `ff-master-mini`, `ff-faber`, `fx-aegis`, `fx-aegis-mega`, `fx-aegis-hyper`, `fx-navi`, `nova`, `nova-mini`, `nova-hello`, `nova-mini-hello`; also `preorder-agreement`, `b2b-solutions`, `eai-brain`.

## Commercial language observed

"Order Now", "Preorder / Inquire", "Start From $89,900", "Coming Soon". No deposit or delivery terms were read (`/us/preorder-agreement/` not requested).

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `robotics.ff.com` |
| Candidate path prefixes | `/us/ff-futurist/`, `/us/futurist/` (humanoid scope per docs/16 §17.1) |
| Seeds | fixed reviewed list of those two URLs |
| Extractor | source-specific; slug identity (canonical ignored); parse embedded page data with an explicit rule for conflicting prices; or a rendered-page reading |
| Blockers | owner scope for other products (`ff-master*`, `fx-*`, `nova*`, `ff-faber`: not described as humanoid, not assessed); `/us/preorder-agreement/` not reviewed; no adapter or fixtures; `www.ff.com` is a separate host |
