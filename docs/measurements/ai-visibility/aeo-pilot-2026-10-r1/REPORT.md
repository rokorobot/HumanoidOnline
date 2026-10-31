# AI Visibility Baseline — aeo-pilot-2026-10-r1 (R1)

Internal measurement record under `docs/24` as amended by `docs/29` (incl. D7). Makes no external claim.

## 1. Disclosure

| Item | Value |
|---|---|
| Window | 2026-10-31T03:11:37+00:00 → 2026-10-31T03:16:55+00:00 (UTC) |
| Registry | v2 (10 queries, `docs/29` §5) |
| Collection | treg-only (owner decision D7, 2026-10-31); no manual reference run |
| Surfaces included | `ChatGPT via treg/cloro.ai-search.chatgpt.scrape`<br>`Gemini via treg/cloro.ai-search.gemini.scrape`<br>`Google AI Mode via treg/cloro.google.serp.ai_mode`<br>`Perplexity API via treg/perplexity.web.answer.fast` |
| Surfaces excluded | ChatGPT / Gemini / Perplexity / Google AI Mode consumer UIs as seen by a human (no manual run, D7); Microsoft Copilot; Google AI Overviews (`docs/29` §4) |
| Region / language | `DE` / `en` for the three cloro surfaces; Perplexity API has no region parameter |
| Reviewer | Pending — owner (D5). Result states derived mechanically; correctness not yet scored |
| Observations | 40 — NOT_CITED 40 |
| Observability coverage | 40 of 40 observable |
| Spend | ≈ $0.09 of the $2 R1 + R2 authorization |

## 2. Headline

| Metric | Value |
|---|---|
| `citation_rate` | 0 of 40 |
| `linked_source_rate` | 0 of 40 |
| `first_source_rate` | 0 of 40 |
| `correct_answer_with_citation_rate` | 0 of 40 (no `CITED` observation, so independent of the pending correctness review) |
| `citation_correctness_rate` | not reported — 0 `CITED` |
| `unattributed_use_rate` | not assessed (field `unknown` throughout) |

**HumanoidOnline was not cited, linked or mentioned in any of the 40 answers.** humanoidonline.com was reachable (HTTP 200) and `robots.txt` allows all crawlers on the day of the run.

## 3. By surface and by query

| Surface | CITED | Observable |
|---|---|---|
| `ChatGPT via treg/cloro.ai-search.chatgpt.scrape` | 0 | 10 |
| `Gemini via treg/cloro.ai-search.gemini.scrape` | 0 | 10 |
| `Google AI Mode via treg/cloro.google.serp.ai_mode` | 0 | 10 |
| `Perplexity API via treg/perplexity.web.answer.fast` | 0 | 10 |

| Query | Text | CITED | Observable |
|---|---|---|---|
| `COMMERCIAL-003` | Which humanoid robots can be purchased in Europe? | 0 | 4 |
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
| `COMMERCIAL-003` | ChatGPT | none | agibot.com, australiasatellite.com, booster.tech, core77.com, elektor.de, embodiedglobal.com, engineeredarts.com, eu.robotshop.com, funduinoshop.com, latinsatelital.com, neura-robotics.com, rbtx.com, rbtx.pt, reichelt.com, reichelt.de, robob2b.ru, robostore.com, robot-distribution.com, roboter-zentrale.de, sonnyrobotics.com, terra-robotics.com, toneart-shop.de |
| `COMMERCIAL-003` | Gemini | none | rbtx.de, robotautotrader.com |
| `COMMERCIAL-003` | Google | none | 1x.tech, merarobotics.com, pollen-robotics.com, robotshop.com |
| `COMMERCIAL-003` | Perplexity | none | eu.robotshop.com |
| `COMMERCIAL-004` | ChatGPT | none | 1x.tech, agibot.com, aiwiki.ai, booster.tech, botinfo.ai, botsales.com, core77.com, dobot-robots.com, engineai.com.cn, fftai.com, funduinoshop.com, humanoid.press, humanoidapplications.com, humanoza.com, mt.co.kr, novaverum.com, offbrandhuman.com, robopilots.ai, robostore.com, roboticaguide.com, robotsforthat.com, speedydrone.ca, unitree.com, usrobotstore.com, zmprobots.com |
| `COMMERCIAL-004` | Gemini | none | antonrobots.com, robotsinternational.com |
| `COMMERCIAL-004` | Google | none | keyirobot.com, robotshop.com, theresarobotforthat.com |
| `COMMERCIAL-004` | Perplexity | none | forbes.com, humanoza.com, robotsinternational.com, robotsusa.com, shop.unitree.com, themodelpress.com |
| `COMMERCIAL-005` | ChatGPT | none | asiasatellite.co, booster.tech, botland.store, botsales.com, en.engineai.com.cn, engineai.com.cn, gongboshi-robot.com, hai.stanford.edu, humanoid.observer, humanoid.press, keplerbot.com, omg.rocks, robolupa.com, robopear.com, robostore.com, robot-distribution.com, robotsinternational.com, shop.unitree.com, store.agibot.com |
| `COMMERCIAL-005` | Gemini | none | robostore.com, top3dshop.com |
| `COMMERCIAL-005` | Google | none | humanoid.guide, robotsinternational.com, shop.unitree.com, youtube.com |
| `COMMERCIAL-005` | Perplexity | none | accio.com, eu.36kr.com, robotsasia.com, robotsinternational.com, robotsmiddleeast.com |

## 5. By URL

| Target URL | Cited in |
|---|---|
| `/research/humanoid-availability/europe` | 0 of 4 (COMMERCIAL-003) |
| `/research/humanoid-availability/north-america` | 0 of 4 (COMMERCIAL-004) |
| `/research/humanoid-availability/asia` | 0 of 4 (COMMERCIAL-005) |
| any HumanoidOnline URL | 0 of 40 |

## 6. Competitor sources

`competitor_citation_frequency`, top 25 domains, each as answers citing it of 40 observable answers.

| Domain | Answers |
|---|---|
| unitree.com | 12 of 40 |
| shop.unitree.com | 8 of 40 |
| robotsinternational.com | 7 of 40 |
| booster.tech | 6 of 40 |
| robostore.com | 6 of 40 |
| blog.robozaps.com | 5 of 40 |
| core77.com | 4 of 40 |
| eu.robotshop.com | 4 of 40 |
| usrobotstore.com | 4 of 40 |
| humanoid.guide | 4 of 40 |
| agibot.com | 3 of 40 |
| roboter-zentrale.de | 3 of 40 |
| toneart-shop.de | 3 of 40 |
| 1x.tech | 3 of 40 |
| robotshop.com | 3 of 40 |
| aiwiki.ai | 3 of 40 |
| engineai.com.cn | 3 of 40 |
| fftai.com | 3 of 40 |
| humanoza.com | 3 of 40 |
| theresarobotforthat.com | 3 of 40 |
| hai.stanford.edu | 3 of 40 |
| humanoid.observer | 3 of 40 |
| deploy.report | 3 of 40 |
| robotsguide.com | 3 of 40 |
| roboticscenter.ai | 3 of 40 |

Directory/aggregator sites comparable to HumanoidOnline that *were* cited include humanoid.guide, humanoza.com, blog.robozaps.com, humanoid.observer, deploy.report, robotsguide.com and humanoid.press.

## 7. Repeatability

Pending R2 (5–9 days after R1, `docs/29` §6.1: 2026-11-05 to 2026-11-09).

## 8. Catalogue findings

Pending owner correctness review. Raw answers are in `evidence/` for that review.

## 9. Deviations from `docs/29` §6

- **Collector:** treg-only, agent-run on owner instruction (D7); no manual run, no human-view reference.
- **Region:** `DE`, not the expected `CZ` — cloro's ChatGPT endpoint refuses `CZ`; `DE` used on all three cloro surfaces for consistency. Perplexity API takes no region.
- **Perplexity surface:** Perplexity's Agent API (`fast` preset, 1 step, ≤ 512 output tokens), not the Perplexity web app; treg offers no scrape of the web app. Not comparable with a human Perplexity web observation.
- **Session / authentication:** provider-run sessions; authentication and personalization recorded as `unknown`.
- **Evidence:** raw API response JSON per observation (with SHA-256 in `notes`), not screenshots. cloro's hosted HTML renders were not requested.
- **Review:** result states derived mechanically from returned source URLs and answer text (`humanoidonline` / `humanoid.company`); `reviewed_by` and correctness are blank until the owner reviews.
- **Retry:** `COMMERCIAL-001` × Gemini timed out once upstream (HTTP 502, not charged) and succeeded on immediate retry; the retry is the recorded observation.
