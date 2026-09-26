# NEURA Robotics — structural review (read-only)

- **Date:** 2026-09-26, 09:30–09:33 UTC
- **Scope:** owner-authorized structural inspection only (docs/16 §12.1). No product crawl, no adapter run, no production write.
- **User agent:** `HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)`, sent on every request, with requests at least 3 s apart.
- **Owner ToS decision:** `ALLOWED`, by Robert Konecny from his own reading (DR-A4). It is recorded through `discovery source review` at registration, not in code.

## Requests (7 in total)

| # | URL | Status | Notes |
|---|---|---|---|
| 1 | https://neura-robotics.com/robots.txt | 200 | `User-agent: *` · `Allow: /` · `Crawl-delay:3` · `Sitemap: …/sitemap_index.xml` |
| 2 | https://neura-robotics.com/sitemap_index.xml | 200 | Yoast index listing `post-`, `page-`, `product-` and `product_cat-` sitemaps |
| 3 | https://neura-robotics.com/product-sitemap.xml | 200 | 8 page URLs: `/shop/` and `/de/shop/`, 3 English `/product/*-reservation/`, 3 German `/de/produkt/*` |
| 4 | https://neura-robotics.com/shop/ | 301 → `https://neura-robotics.com` | `x-redirect-by: redirection`; there is no shop index |
| 5 | https://neura-robotics.com/product/4ne1-reservation/ | 200 | ~393 KB HTML; server-rendered |
| 6 | https://neura-robotics.com/products/4ne1/ | 200 | ~343 KB HTML; server-rendered |
| 7 | https://neura-robotics.com/news/ | 200 | "News & Press Releases" index |

Not requested: the homepage, `page-sitemap.xml`, `post-sitemap.xml`, any other product page, any article, and the WordPress REST API. A link to `/wp-json/wp/v2/product/35501` is present on the pages.

## robots.txt for our user agent

No group names `HumanoidOnlineMarketBot`, so the `*` group applies: `Allow: /`. **Crawl-delay is 3 s**, so the fetcher uses max(3, 2) = 3 s. The block list of AI-training crawlers recorded in the July 2026 assessment (docs/16 §23.1) is no longer present.

## Structure

- **Host:** `neura-robotics.com`. The platform is WordPress with Elementor, WooCommerce and Yoast, behind Cloudflare.
- **Product-page families (English):**
  - `/products/<slug>/` holds the official robot pages. The site nav links `4ne1`, `mipa`, `maira`, `lara` and `mav`; only 4NE1 is titled a humanoid on the page inspected.
  - `/product/<slug>-reservation/` holds the reservation pages: `4ne1`, `4ne1-mini`, `mipa` and `quadruped`. `4ne1-mini` is linked from the 4NE1 reservation page but **missing from the product sitemap**.
  - German copies (`/de/produkt/…`) are excluded.
- **Estimated targets behind the proposed seeds:** about 8–9 (5 robot pages plus 3–4 reservation pages). The 50-page cap is far above this.
- **HTTP-only:** viable. The visible content (~6–7k characters per page) is in the HTML response, and no client-side framework was detected.

## JSON-LD

Each page carries one Yoast graph containing `WebPage`, `BreadcrumbList`, `WebSite`, `Organization` and, on product pages, `ImageObject`.

- **Absent:** `Product`, `Offer`, price, currency, availability, model, and any structured properties.
- The breadcrumb's last item names the reservation, e.g. "4NE1 Reservation".
- The `<title>` names the product, e.g. "Reserve 4NE1: …" and "Humanoid Robot 4NE1 for Work and Life | …".

What the pages expose **only as visible text**:
- On the robot page: labelled specifications such as "Payload (kg)", "Height (cm)", "speed (km/h)" and "Weight (kg)".
- On the reservation page: a **tiered estimated unit price**, excluding taxes and shipping, by quantity band; a **refundable per-unit reservation fee** credited toward the purchase; and an **expected-availability** statement for a named generation ("Gen 3.5").

## Newsroom

`/news/` is a usable index page, and its site-wide nav is how the `/products/` pages are found. However, its article links are **root-level slugs** (`/<slug>/`), the same shape as ordinary pages, and its dated links (`/2026/06/10/` and similar) are day archives. With the current config design (one set of URL patterns shared by all seeds), there is **no deterministic announcement pattern**, so announcement monitoring is disabled for NEURA. A future option is a per-seed pattern that treats `post-sitemap.xml` entries as announcements.

## Adapter configuration (what changed)

`sources/neura_robotics.py` moves from 0.1.0 to 0.2.0:
- `allowed_path_prefixes`: `/products/`, `/product/`, `/product-sitemap.xml`, `/news/`
- `seed_urls`: `https://neura-robotics.com/product-sitemap.xml` and `https://neura-robotics.com/news` (normalized)
- `product_path_pattern`: `/products/[a-z0-9-]+` or `/product/[a-z0-9-]+-reservation` (full match on the normalized path)
- `announcement_path_pattern`: none
- `property_map`: empty
- `quote_phrases`: none observed
- `structural_review`: points to this document
- **`blocked_reason`**: set, so the runner refuses NEURA with `ADAPTER_BLOCKED`, whatever the source's approval state.

## Why it stays blocked, and the owner decisions needed

The generic extractor (JSON-LD `Product`, else `<h1>`) is **unsafe** for NEURA:
- **Robot pages:** the `<h1>` is a marketing tagline, so the fallback would create a candidate *named after a slogan*.
- **Reservation pages:** there's no `<h1>` and no `Product`, so they produce `NOTHING_FOUND`.

Running NEURA needs a NEURA-specific deterministic HTML extractor, a separate change for approval, plus these decisions:
1. **Identity source:** the breadcrumb last item, a `<title>` pattern ("Reserve (?P<name>…):"), or both. Plus the variant question: the reservation names a *generation* ("4NE1 Gen 3.5").
2. **Catalogue identity:** the catalogue robot is named **`4NE-1`**, but the site writes **`4NE1`**. These do not normalize to each other, so without a **confirmed alias** in `db/discovery/identity_aliases.json` the resolver would report `NEW_ENTITY`. No alias was added.
3. **Estimated price tiers:** record them as `price_type=ESTIMATED`, one signal per quantity band (tier in `note`), excluding tax and shipping?
4. **Reservation fee:** it is a refundable **deposit** and must never be recorded as a price (docs/16 §6.2). Should it be recorded at all, and as what?
5. **Obtainability of a reservation:** `WAITLIST` ("place in the delivery queue") or `PREORDER`, or no signal?
6. **Labelled specs** ("Payload (kg) 10-100"): record ranges verbatim as claims, with a mapping for units such as cm → m?
7. **Scope noise:** `/products/` also contains non-humanoid robots (MAiRA, LARA, MAV). Should the pattern stay generic, so new humanoids are detected, with humans rejecting the rest, or be restricted?
8. **Trailing slash:** the normalized target URL has no trailing slash, and WordPress 301s to the slash form, which costs one extra redirect request per target. A later fix would fetch the as-linked URL while keeping the normalized form as `external_ref`.

## Still uncertain

- Whether the homepage would be a better seed than `/news/` (not requested).
- Whether `/products/mipa/` and the other robot pages share the 4NE1 template (only one robot page was inspected).
- Whether the WordPress REST API (`/wp-json/wp/v2/product/…`) exposes structured fields (not requested; using it would be a separate decision).
