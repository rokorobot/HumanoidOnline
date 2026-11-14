# AI Visibility Baseline — aeo-pilot-2026-11-r2 (R2)

Internal measurement record under `docs/24` as amended by `docs/29` (incl. D7). Makes no external claim.

## 1. Disclosure

| Item | Value |
|---|---|
| Window | 2026-11-14T07:15:29+00:00 → 2026-11-14T07:21:25+00:00 (UTC) |
| Registry | v2 (10 queries, `docs/29` §5) |
| Collection | treg-only (owner decision D7, 2026-10-31); no manual reference run |
| Surfaces included | `ChatGPT via treg/cloro.ai-search.chatgpt.scrape`<br>`Gemini via treg/cloro.ai-search.gemini.scrape`<br>`Google AI Mode via treg/cloro.google.serp.ai_mode`<br>`Perplexity API via treg/perplexity.web.answer.fast` |
| Surfaces excluded | ChatGPT / Gemini / Perplexity / Google AI Mode consumer UIs as seen by a human (no manual run, D7); Microsoft Copilot; Google AI Overviews (`docs/29` §4) |
| Region / language | `DE` / `en` for the three cloro surfaces; Perplexity API has no region parameter |
| Reviewer | Pending — owner (D5). Result states derived mechanically; correctness not yet scored |
| Observations | 40 — ENGINE_ERROR 1, NOT_CITED 39 |
| Observability coverage | 39 of 40 observable |
| Spend | ≈ $0.10 this run; ≈ $0.19 cumulative across R1 + R2, of the owner's $10 sweep cap (D8) |

## 2. Headline

| Metric | Value |
|---|---|
| `citation_rate` | 0 of 39 |
| `linked_source_rate` | 0 of 39 |
| `first_source_rate` | 0 of 39 |
| `correct_answer_with_citation_rate` | 0 of 39 (no `CITED` observation, so independent of the pending correctness review) |
| `citation_correctness_rate` | not reported — 0 `CITED` |
| `unattributed_use_rate` | not assessed (field `unknown` throughout) |

**HumanoidOnline was not cited, linked or mentioned in any of the 39 observable answers.** humanoidonline.com was reachable (HTTP 200) and `robots.txt` allows all crawlers on the day of the run.

## 3. By surface and by query

| Surface | CITED | Observable |
|---|---|---|
| `ChatGPT via treg/cloro.ai-search.chatgpt.scrape` | 0 | 9 |
| `Gemini via treg/cloro.ai-search.gemini.scrape` | 0 | 10 |
| `Google AI Mode via treg/cloro.google.serp.ai_mode` | 0 | 10 |
| `Perplexity API via treg/perplexity.web.answer.fast` | 0 | 10 |

| Query | Text | CITED | Observable |
|---|---|---|---|
| `COMMERCIAL-003` | Which humanoid robots can be purchased in Europe? | 0 | 3 |
| `COMMERCIAL-004` | Which humanoid robots can be purchased in North America? | 0 | 4 |
| `COMMERCIAL-005` | Which humanoid robots can be purchased in Asia? | 0 | 4 |
| `COMMERCIAL-002` | Which humanoid robots are commercially available? | 0 | 4 |
| `COMMERCIAL-001` | How much does the Unitree G1 cost? | 0 | 4 |
| `CAPABILITY-001` | Which humanoid robots have SDK access? | 0 | 4 |
| `CAPABILITY-003` | Which humanoid robots are suitable for research? | 0 | 4 |
| `COMPARE-002` | Unitree G1 vs Booster K1. | 0 | 4 |
| `ENTITY-003` | How tall is the Unitree G1? | 0 | 4 |
| `MARKET-002` | How many commercial humanoid robots exist? | 0 | 4 |

## 4. Regional resources (queries 1–3)

Post-publication baseline: Europe published 2026-10-05, North America 2026-10-23, Asia 2026-10-24 (`docs/29` §2). No pre-publication baseline exists for NA or Asia.

| Query | Surface | HumanoidOnline URL cited | Sources cited instead |
|---|---|---|---|
| `COMMERCIAL-003` | ChatGPT | none | — |
| `COMMERCIAL-003` | Gemini | none | eu.robotshop.com, rbtx.de, robotharbour.com |
| `COMMERCIAL-003` | Google | none | humanoid-scout.de, merarobotics.com, neura-robotics.com, quadruped.de, robotshop.com |
| `COMMERCIAL-003` | Perplexity | none | eu.robotshop.com, heise.de |
| `COMMERCIAL-004` | ChatGPT | none | 1x.tech, 3logic.ru, agibot.com, apptronik.com, blessthisstuff.com, booster.tech, botinfo.ai, docs.pollen-robotics.com, gongboshi-robot.com, humanoid.observer, internetofthingsnews.com, mt.co.kr, pollen-robotics.com, robostore.com, robotatta.com, robotsguide.com, shop.unitree.com, starbotusa.com, store.agibot.com, teswel.ru, thehumanoid.report, theroboticlife.com |
| `COMMERCIAL-004` | Gemini | none | keyirobot.com |
| `COMMERCIAL-004` | Google | none | robotsinternational.com, robozaps.com, shop.unitree.com, theconveyor.co |
| `COMMERCIAL-004` | Perplexity | none | humanoid.press, originofbots.com, roboticsintl.com, robotsusa.com, the-gadgeteer.com, themodelpress.com, theroboticlife.com, top3dshop.com |
| `COMMERCIAL-005` | ChatGPT | none | 3logic.ru, agibot.com, antarum.ai, asiasatellite.co, biorobot.ai, boosterobotics.com, botsales.com, engineai.com.cn, everyhumanoid.com, fftai.com, hardwaremap.com, humanoid-mart.com, humanoid.observer, humanoidvs.com, humanrobots.si, internetofthingsnews.com, offbrandhuman.com, robot-distribution.com, robotics.hellobike.com, thehumanoid.report, unitree.com |
| `COMMERCIAL-005` | Gemini | none | robotsinternational.com |
| `COMMERCIAL-005` | Google | none | globaldronehq.com, robotsasia.com, shop.unitree.com |
| `COMMERCIAL-005` | Perplexity | none | humanoid.observer, robotsasia.com, robotsinternational.com, theresarobotforthat.com |

## 5. By URL

| Target URL | Cited in |
|---|---|
| `/research/humanoid-availability/europe` | 0 of 3 (COMMERCIAL-003; ChatGPT `ENGINE_ERROR`) |
| `/research/humanoid-availability/north-america` | 0 of 4 (COMMERCIAL-004) |
| `/research/humanoid-availability/asia` | 0 of 4 (COMMERCIAL-005) |
| any HumanoidOnline URL | 0 of 39 |

## 6. Competitor sources

`competitor_citation_frequency`, top 25 domains, each as answers citing it of 39 observable answers.

| Domain | Answers |
|---|---|
| blog.robozaps.com | 10 of 39 |
| unitree.com | 9 of 39 |
| roboticscenter.ai | 8 of 39 |
| shop.unitree.com | 7 of 39 |
| robostore.com | 4 of 39 |
| thehumanoid.report | 4 of 39 |
| robotsinternational.com | 4 of 39 |
| github.com | 4 of 39 |
| support.unitree.com | 4 of 39 |
| quadruped.de | 3 of 39 |
| booster.tech | 3 of 39 |
| humanoid.observer | 3 of 39 |
| globaldronehq.com | 3 of 39 |
| webuildhumanoids.com | 3 of 39 |
| joybuy.de | 3 of 39 |
| humanoidversus.com | 3 of 39 |
| eu.robotshop.com | 2 of 39 |
| merarobotics.com | 2 of 39 |
| robotshop.com | 2 of 39 |
| 1x.tech | 2 of 39 |
| 3logic.ru | 2 of 39 |
| agibot.com | 2 of 39 |
| apptronik.com | 2 of 39 |
| botinfo.ai | 2 of 39 |
| internetofthingsnews.com | 2 of 39 |

Directory/aggregator sites comparable to HumanoidOnline that *were* cited in R2 include blog.robozaps.com, humanoid.observer, humanoid.press, humanoza.com, deploy.report and robotsguide.com.

## 7. Repeatability

Stability per surface against R1 (`aeo-pilot-2026-10-r1`), `docs/29` §6.1: pairs with the same result state in both runs, of pairs observable in both. Excluded pairs are counted as coverage.

| Surface | Same state R1 → R2 | Excluded pairs |
|---|---|---|
| `ChatGPT via treg/cloro.ai-search.chatgpt.scrape` | 9 of 9 | 1 (COMMERCIAL-003: R2 `ENGINE_ERROR`) |
| `Gemini via treg/cloro.ai-search.gemini.scrape` | 10 of 10 | 0 |
| `Google AI Mode via treg/cloro.google.serp.ai_mode` | 10 of 10 | 0 |
| `Perplexity API via treg/perplexity.web.answer.fast` | 10 of 10 | 0 |

The finding is stable: HumanoidOnline was `NOT_CITED` on every observable pair in both runs. Changes between the runs, none of which affects that finding:

- 2026-10-31: crawl-duplicate `noindex`/canonical policy (#217), IndexNow (#218), Bing Webmaster Tools.
- 2026-10-31: robot page titles (#224) and the five `/lines/*` product-line pages (#226, #227).

Fourteen days is short for indexing and citation effects, so R2 is not evidence that those changes failed. Among comparable directories, blog.robozaps.com was cited in 10 of 39 answers (5 of 40 in R1).

## 8. Catalogue findings

Pending owner correctness review. Raw answers are in `evidence/` for that review.

## 9. Deviations from `docs/29` §6

- **Collector:** treg-only, agent-run on owner instruction (D7); no manual run, no human-view reference.
- **Region:** `DE`, not the expected `CZ` — cloro's ChatGPT endpoint refuses `CZ`; `DE` used on all three cloro surfaces for consistency. Perplexity API takes no region.
- **Perplexity surface:** Perplexity's Agent API (`fast` preset, 1 step, ≤ 512 output tokens), not the Perplexity web app; treg offers no scrape of the web app. Not comparable with a human Perplexity web observation.
- **Session / authentication:** provider-run sessions; authentication and personalization recorded as `unknown`.
- **Evidence:** raw API response JSON per observation (with SHA-256 in `notes`), not screenshots. cloro's hosted HTML renders were not requested.
- **Review:** result states derived mechanically from returned source URLs and answer text (`humanoidonline` / `humanoid.company`); `reviewed_by` and correctness are blank until the owner reviews.
- **Retry:** `COMMERCIAL-002` × ChatGPT and `COMMERCIAL-003` × ChatGPT timed out upstream (HTTP 502, not charged). Both were retried once. COMMERCIAL-002 succeeded and is recorded. COMMERCIAL-003 timed out again and is recorded as `ENGINE_ERROR`, excluded from denominators.
- **Cadence:** sweeps run every 14 days (owner request, D8). R2 is 14 days after R1, outside the `docs/29` §6.1 5–9 day window.
