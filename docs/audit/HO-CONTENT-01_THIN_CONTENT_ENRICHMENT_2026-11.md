# HO-CONTENT-01 — Thin-content enrichment (2026-11-02)

Owner-approved research task (2026-11-02), separate from the SEO audit (67/100, 33 thin pages). Scope: add real, sourced text to the 8 `/use-cases/<slug>` pages and the `/manufacturers/<slug>` pages. Word count is a side effect, not a target. **Nothing was imported to production, merged or promoted.** The PR stays open for owner approval.

## 1. What changed

| File | Fields touched | Fields NOT touched |
|---|---|---|
| `db/catalogue/use_cases.json` | `description`, `typical_requirements`, `key_limitations` (all three are loaded by `db/import_catalogue.py:1040-1058`) | `typical_tasks`, slugs, names, categories |
| `db/catalogue/manufacturers.json` | `description` on 20 of 31 makers, plus one or more new `evidence` rows per maker with `claim_fields: ["description"]` | every other profile field (`deployment_status`, `deployment_note`, `commercial_model`, `target_markets`, ...), robot files, prices, availability, use-case fits |
| `scripts/measure_page_words.py` | new: counts words inside `<main>` for every use-case and manufacturer page | — |

No schema change. No new field. Each new manufacturer evidence row carries `source_url`, `source_type`, `observed_at` (2026-11-02), `confidence`, a verbatim `excerpt`, `claim_fields`, and a note with the exact supported facts and the `RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26)` statement. `verified_at` is null everywhere (AGENT_ASSISTED_RESEARCH rows are never human-verified).

Use-case rows have no evidence table (the schema has none), so the sources for every factual use-case claim are recorded in section 4 of this document.

## 2. Word counts (words inside `<main>`, `scripts/measure_page_words.py`)

Baseline = production https://humanoidonline.com on 2026-11-02. "After" = the PR's Netlify deploy preview. Catalogue text only reaches a rendered page after the DB is re-imported, and the page text comes from the database through the API, so a deploy preview shows these words only if its API points at a database that has imported this branch. The "Catalogue text words" column is the exact change to the catalogue fields (description + requirements + limitations for use cases; description for makers) and is what the import will add.

Note on the brief: it quotes 78-314 words for the use-case pages. Production measures 84-799, because the page also renders the ranked robot list and navigation. The thin ones are `home` (84), `security-inspection` (180), `warehouse-logistics` (220). Two makers, `aimoga` and `faraday-future`, are not live in production (404), so no page baseline exists for them.

### Use cases

| Page | Baseline page words | After (preview) | Catalogue text words (before → after) |
|---|---|---|---|
| `/use-cases/warehouse-logistics` | 220 | pending | 9 → 203 |
| `/use-cases/manufacturing` | 349 | pending | 8 → 203 |
| `/use-cases/research-education` | 799 | pending | 6 → 146 |
| `/use-cases/home` | 84 | pending | 4 → 208 |
| `/use-cases/events-entertainment` | 754 | pending | 7 → 69 |
| `/use-cases/retail-service` | 313 | pending | 73 → 156 |
| `/use-cases/healthcare-rehabilitation` | 278 | pending | 86 → 126 |
| `/use-cases/security-inspection` | 180 | pending | 60 → 133 |

### Manufacturers

| Page | Baseline page words | After (preview) | Catalogue description words (before → after) | Status |
|---|---|---|---|---|
| `/manufacturers/1x-technologies` | 321 | pending | 81 → 141 | enriched |
| `/manufacturers/agibot` | 247 | pending | 78 → 134 | enriched |
| `/manufacturers/agility-robotics` | 299 | pending | 83 → 148 | enriched |
| `/manufacturers/aimoga` | not live (404) | n/a | 35 → 35 | not enriched |
| `/manufacturers/apptronik` | 298 | pending | 89 → 89 | not enriched |
| `/manufacturers/astribot` | 168 | pending | 63 → 103 | enriched |
| `/manufacturers/booster-robotics` | 271 | pending | 82 → 151 | enriched |
| `/manufacturers/boston-dynamics` | 389 | pending | 85 → 85 | not enriched |
| `/manufacturers/clone-robotics` | 327 | pending | 90 → 134 | enriched |
| `/manufacturers/engineered-arts` | 336 | pending | 94 → 150 | enriched |
| `/manufacturers/faraday-future` | not live (404) | n/a | 39 → 39 | not enriched |
| `/manufacturers/figure-ai` | 333 | pending | 76 → 125 | enriched |
| `/manufacturers/fourier-intelligence` | 191 | pending | 74 → 112 | enriched |
| `/manufacturers/galbot` | 261 | pending | 82 → 150 | enriched |
| `/manufacturers/hanson-robotics` | 161 | pending | 60 → 60 | not enriched |
| `/manufacturers/honda` | 289 | pending | 92 → 147 | enriched |
| `/manufacturers/kepler-robotics` | 230 | pending | 73 → 73 | not enriched |
| `/manufacturers/limx-dynamics` | 184 | pending | 74 → 127 | enriched |
| `/manufacturers/neura-robotics` | 252 | pending | 85 → 151 | enriched |
| `/manufacturers/pal-robotics` | 204 | pending | 69 → 115 | enriched |
| `/manufacturers/rainbow-robotics` | 198 | pending | 70 → 126 | enriched |
| `/manufacturers/realbotix` | 249 | pending | 80 → 80 | not enriched |
| `/manufacturers/robotera` | 243 | pending | 77 → 77 | not enriched |
| `/manufacturers/sanctuary-ai` | 245 | pending | 70 → 93 | enriched |
| `/manufacturers/softbank-robotics` | 183 | pending | 50 → 108 | enriched |
| `/manufacturers/tesla` | 287 | pending | 73 → 73 | not enriched |
| `/manufacturers/toyota` | 279 | pending | 89 → 133 | enriched |
| `/manufacturers/ubtech-robotics` | 315 | pending | 83 → 118 | enriched |
| `/manufacturers/unitree` | 315 | pending | 73 → 108 | enriched |
| `/manufacturers/xiaomi` | 137 | pending | 42 → 42 | not enriched |
| `/manufacturers/xpeng-robotics` | 270 | pending | 74 → 74 | not enriched |

## 3. Method and retrieval caveats

- Primary sources first (maker pages, press releases, company histories, a customer/operator release). Secondary media only where marked, never as the sole basis for a maker fact.
- Pages were read with the WebFetch tool, which returns **processed page text, not raw HTML**; no page hash is available. Quotes in `excerpt` fields come from that processed text. They should be spot-checked against the live pages before promotion; this is stated in every evidence note.
- JavaScript-only pages returned only a title (Hanson Robotics, ROBOTERA, partly Galbot). `iso.org` returned 403 (Cloudflare) to both WebFetch and curl, so ISO pages were **not read directly** (see claim UC-3).
- Where a source was inconsistent with itself or with the existing profile, the conflict was preserved and listed in section 6, not resolved.

## 4. Use-case claims and sources

Every factual sentence added to a use-case page. Confidence is HumanoidOnline's own: HIGH = stated on the maker's or customer's own page; MEDIUM = secondary or partly unread source.

### warehouse-logistics
| # | Claim | Source | Conf. |
|---|---|---|---|
| WL-1 | 27 Jun 2024: Agility and GXO announced a multi-year RaaS agreement for Digit at GXO's SPANX facility near Atlanta, which they called the industry's first formal commercial humanoid deployment; it followed a late-2023 proof-of-concept pilot. | https://agilityrobotics.com/content/gxo-signs-industry-first-multi-year-agreement-with-agility-robotics (corroboration: https://investors.gxo.com/news-releases/news-release-details/gxo-signs-industry-first-multi-year-agreement-agility-robotics, seen in search only, 403 on fetch) | HIGH |
| WL-2 | Digit moves totes from cobots onto conveyors via Agility Arc, alongside existing AMRs. | same Agility release | HIGH |
| WL-3 | Workflows: tote handling, palletizing/depalletizing, machine tending, kitting and sequencing. | https://www.agilityrobotics.com/solutions | HIGH |
| UC-3 / WL-4 | ISO's new-work-item proposal says no ISO safety standard for dynamically stable industrial mobile robots was published or in development; it is now draft ISO/CD 25785-1. | NWIP text: https://www.mta.org.uk/resources/iso-np-25785-1-link-to-new-work-item-proposal/ (trade-body copy, read). "Committee Draft ISO/CD 25785-1" label: https://www.iso.org/standard/91469.html, **title seen in search results only, page unreadable** | MEDIUM |
| WL-5 | Agility: first skills target repetitive, strenuous, load-intensive work; certain safety features still in development; safety features do not eliminate all operational risk. | https://www.agilityrobotics.com/solutions | HIGH |
| WL-6 | Agility's solutions page states no payload or runtime figures; Schaeffler's plan for a significant number of humanoids across 100 plants by 2030 is the customer's aspiration. | https://www.agilityrobotics.com/solutions (absence statement and customer quote) | HIGH |

### manufacturing
| # | Claim | Source | Conf. |
|---|---|---|---|
| MF-1 | Figure 02 at BMW Spartanburg: 11 months, 10-hour shifts Mon-Fri, loaded sheet-metal parts onto a welding fixture on an active line; 1,250+ hours, 90,000+ parts, contributed to 30,000+ X3 vehicles. | https://www.figure.ai/news/production-at-bmw | HIGH |
| MF-2 | Targets (not results): 84 s cycle, 37 s loading, >99% placement per shift, 5 mm tolerance, zero pauses/resets; feeds six-axis welding robots. | same | HIGH |
| MF-3 | Forearm was the top hardware failure point; removed distribution board and dynamic cabling for Figure 03. | same | HIGH |
| MF-4 | Apptronik Apollo is in a commercial pilot agreement with Mercedes-Benz; engagement terms not stated. | https://www.prnewswire.com/news-releases/apptronik-and-mercedes-benz-enter-commercial-agreement-that-will-pilot-apptroniks-apollo-humanoid-robot-in-mercedes-benz-manufacturing-facilities-302089972.html (already recorded in `apptronik-apollo.json`); terms: existing `apptronik` deployment_note | HIGH |
| MF-5 | UBTECH began Walker S2 mass production and delivery in Nov 2025, orders above 800 million yuan. | https://www.prnewswire.com/news-releases/ubtech-humanoid-robot-walker-s2-begins-mass-production-and-delivery-with-orders-exceeding-800-million-yuan-302616924.html (already recorded on `ubtech-robotics`) | HIGH |

### research-education
| # | Claim | Source | Conf. |
|---|---|---|---|
| RE-1 | Unitree lists secondary development for G1 EDU, not base G1; EDU adds 23-43 DOF (vs 23), higher arm payload, optional hand/waist upgrades; arm payload about 2 kg (G1) / 3 kg (EDU), varying with posture; about 2 h battery. | https://www.unitree.com/g1 | HIGH |
| RE-2 | Booster: team from Tsinghua robot control lab and RoboCup team; 700+ deliveries to 200+ customers (Nov 2025); 38 teams on Booster robots at RoboCup 2026. | https://www.booster.tech/about-us (38 teams also in existing `booster-robotics` evidence) | HIGH |
| RE-3 | Booster Studio: IDE for agent development, simulation, deployment to physical robots. | https://www.booster.tech/about-us | HIGH |

### home
| # | Claim | Source | Conf. |
|---|---|---|---|
| HM-1 | 1X says NEO folds laundry, organizes shelves, tidies, opens doors, fetches items, turns off lights; chores can be scheduled. | https://www.1x.tech/discover/neo-home-robot | HIGH |
| HM-2 | Delivery planned primarily in the US in 2026, other markets from 2027. | same | HIGH |
| HM-3 | Figure states Figure 03 is designed for the home. | https://www.figure.ai/news/introducing-figure-03 (already recorded in `figure-03.json`) | HIGH |
| HM-4 | Head-to-toe soft body; gentle actuation "uniquely safe and compliant around people"; 5 ft 6 in, 66 lb, 4 h battery, 55 lb carry, 18 lb arm payload. | https://www.1x.tech/discover/neo-home-robot (safety wording); https://www.1x.tech/neo (specifications) | HIGH |
| HM-5 | NEO works autonomously by default; a 1X Expert can remotely supervise at scheduled times; grows in abilities with each software update. | https://www.1x.tech/neo ; discover page | HIGH |
| HM-6 | CEO told Road to VR (30 Oct 2025): "most of the things in your home autonomously" when it ships; quality will "vary and will improve drastically quite fast as we get data". | https://roadtovr.com/helper-robot-neo-vr-telepresence/ (secondary, quote read on page) | MEDIUM |

### events-entertainment
| # | Claim | Source | Conf. |
|---|---|---|---|
| EV-1 | Ameca: rent / quote / demo; conference, expo, keynote and R&D uses; 70+ languages; 2 x 8 MP cameras; 61 actuated movements; 1,870 mm; 62 kg; Tritium platform with browser Python scripting. | https://engineeredarts.com/robot/ameca/ | HIGH |

### retail-service
| # | Claim | Source | Conf. |
|---|---|---|---|
| RS-1 | Galbot G1 (wheeled, two arms) operates in Galaxy Space Capsule units at 170+ sites in 40+ cities. | http://www.galbot.com/g1/ (already recorded in `galbot-g1.json`) | HIGH |
| RS-2 | July 2025: nearly 10 Beijing stores, one-day deployment, 100-store target for the year. | https://www.therobotreport.com/galbot-picks-up-153m-commercialize-g1-semi-humanoid/ (secondary; company statements) | MEDIUM |
| RS-3 | Pepper launched June 2014; Guinness recognition Feb 2026 as first mass-produced humanoid. | https://www.softbankrobotics.com/profile/ | HIGH |

### healthcare-rehabilitation
| # | Claim | Source | Conf. |
|---|---|---|---|
| HC-1 | Fourier began in 2015 in medical rehabilitation robotics; exoskeletons help patients with neurological impairments stand and walk; GR-3 (Aug 2025) designed for social and assistive companionship. | https://www.wipo.int/en/web/ip-advantage/w/stories/fourier-healthcare-robots-with-humanoid-designs (WIPO's account of the company) | MEDIUM |

### security-inspection
| # | Claim | Source | Conf. |
|---|---|---|---|
| SI-1 | Spot: autonomous inspections; inspections in energized, radioactive or otherwise hazardous areas; IP54; 14 kg payload; 90 min average runtime. | https://bostondynamics.com/products/spot/ | HIGH |
| SI-2 | Atlas: IP67. | https://bostondynamics.com/products/atlas/ (already recorded in `boston-dynamics-atlas-electric.json` `specs_note`) | HIGH |
| SI-3 | Kepler positions Forerunner K2 for high-risk operations. | https://www.prnewswire.com/news-releases/kepler-debuts-forerunner-k2-humanoid-robot-accelerating-commercial-deployment-302281546.html (already recorded on `kepler-robotics`) | HIGH |
| SI-4 | Unitree lists power inspection among its applications. | https://www.unitree.com/about | HIGH |

## 5. Manufacturer claims and sources

Each row is a new `evidence` row in `manufacturers.json` (same URL, `observed_at` 2026-11-02, `claim_fields: ["description"]`). The exact supported facts are in each row's `note`.

| Maker | New facts (summary) | Source |
|---|---|---|
| 1x-technologies | NEO autonomous by default; scheduled remote 1X Expert; 5 ft 6 in, 66 lb, 4 h battery; delivery plan US 2026 / other markets 2027 | https://www.1x.tech/neo, https://www.1x.tech/discover/neo-home-robot |
| agibot | production milestones 1,000 / 10,000 / 20,000th robot; A1 (Aug 2023), A2 (Aug 2024); company-claimed "routine operation at an industrial site" (Jul 2025) | https://www.agibot.com/about_Zhiyuan |
| agility-robotics | GXO RaaS agreement 27 Jun 2024, SPANX pilot, tasks, Arc, workflows, safety wording | https://agilityrobotics.com/content/gxo-signs-industry-first-multi-year-agreement-with-agility-robotics, https://www.agilityrobotics.com/solutions (the latter is cited inside the note, not as a separate row) |
| astribot | founded end-2022; vision; product names with no specs/prices/dates | https://www.astribot.com/ |
| booster-robotics | founded Jun 2023 by CEO Cheng Hao; RoboCup 2025 and 2026 results; K1 Oct 2025; Booster Studio | https://www.booster.tech/about-us |
| clone-robotics | musculotendon Myofiber units; water and electricity; GPU at the edge; reservation page gives no terms | https://clonerobotics.com/android/ |
| engineered-arts | rent/quote/demo; uses; Ameca specs; Tritium | https://engineeredarts.com/robot/ameca/ |
| figure-ai | 10-hour shifts, 1,250+ h, 90,000+ parts, forearm failure point | https://www.figure.ai/news/production-at-bmw |
| fourier-intelligence | GR series three generations; GR-3 care-setting use; no regulatory approval mentioned | https://www.wipo.int/en/web/ip-advantage/w/stories/fourier-healthcare-robots-with-humanoid-designs |
| galbot | RMB 1.1 bn (~US$153M) round Jul 2025, ~US$335M total; one-day deployment; 5,000 goods types; pharmacies; own-site wording on scaled operation | https://www.therobotreport.com/galbot-picks-up-153m-commercialize-g1-semi-humanoid/ (MEDIUM), http://www.galbot.com/about/ |
| honda | 25+ years bipedal R&D; ASIMO 7,907 km; collision-absorption tech; Narita guide-robot test | https://global.honda/en/robotics/asimo/ |
| limx-dynamics | Series B Feb 2026; pre-IPO Jul 2026; SAIC MoU Jul 2025; FluxVLA open-sourced Apr 2026 | https://www.limxdynamics.com/en/about |
| neura-robotics | CEO/founder David Reger; Series A / B / C figures; team size (both figures); 8 locations | https://neura-robotics.com/about-us/ |
| pal-robotics | REEM-A 2005; first EU project 2014, 60+ since; TIAGo Pro 2023; Kangaroo Pro for sale 2025 | https://pal-robotics.com/timeline/ |
| rainbow-robotics | started 2011 from HUBO; product series; no prices/stock | https://www.rainbow-robotics.com/ |
| sanctuary-ai | Physical AI built for multi-embodiment; no customers named | https://sanctuary.ai/ |
| softbank-robotics | Pepper developer sales 2015, PARLOR 2019, Guinness 2026; JPY 14.5 bn each from Alibaba and Foxconn (2015) | https://www.softbankrobotics.com/profile/ |
| toyota | T-HR3 design team, servo partners, exhibition dates | https://global.toyota/en/newsroom/corporate/19841525.html |
| ubtech-robotics | 3,112 patents (Jun 2026); 9880.HK from 29 Dec 2023; Walker S training in automotive factories | https://www.ubtrobot.com/en/about/company-profile |
| unitree | product line inventory | https://www.unitree.com/about |

## 6. Left out, and why

**Makers not enriched (no honest, primary, fetchable source this session):**

| Maker | Reason |
|---|---|
| aimoga, faraday-future | Not live in production (404). One thin source each; nothing further found. Enrichment would only add unverified secondary claims. |
| xiaomi | Only secondary coverage (TechCrunch and others) found for CyberOne specifications; no Xiaomi page. Specification figures also conflict across sources (search results disagreed on weight). Left alone. |
| hanson-robotics | hansonrobotics.com is JavaScript-only (returned a title); only Wikipedia is on record. |
| robotera | robotera.com is JavaScript-only; only the existing trade-press source. |
| apptronik, boston-dynamics, kepler-robotics, realbotix, tesla, xpeng-robotics | Already source-dense; the new facts found were either commercial facts outside this task (see below) or no better than the existing ones. Apptronik's Mercedes release URL returned 404; the kepler-robot.com host did not resolve. |

**Facts found but deliberately not used:**

- **Realbotix Echo reservation** (US$199, 225 tabletop and 25 full-body units shipping 2027, from https://realbotix.com/about): a price and availability fact. Out of scope (no price/availability changes). Needs a robot record and owner decision; it also contradicts `commercial_model` ("custom-built via enquiry").
- **Galbot "scaled commercial rollout"** wording: kept as company wording in the description only. `deployment_status` and `deployment_note` unchanged; whether it supports COMMERCIAL is an owner call.
- **AgiBot** "certifications in China, US and Europe" (May 2025) and "highest international safety standards" (Jul 2026): the certification bodies are not named; not repeated. The `deployment_note` still says no humanoid deployment status is established and was left as is.
- **1X privacy/Expert data handling:** the 1X pages fetched do not describe it; privacy-policy text was not read. Press coverage of "Expert Mode" safeguards is secondary and one-sided, so none is asserted. The home page states only what 1X itself says.
- **Use-case limitations for events-entertainment and research-education beyond Unitree's own figures:** none sourceable without editorial judgement.
- **`typical_tasks`:** unchanged; they are editorial labels with no source.
- **Existing editorial sentences that have no source** (e.g. retail "return on investment is often novelty-driven", security "quadrupeds and wheeled robots currently dominate") were not touched. Flagged here as unsourced; a follow-up could source or soften them.
- **ISO 13482** (personal-care robots) would belong in `home`, `healthcare-rehabilitation` and `retail-service` requirements. `iso.org` was unreadable, so it is not cited.

## 7. Conflicts and follow-ups (non-blocking)

1. **LimX TRON 1:** profile says "(2024)"; LimX's about page (the profile's own source) timelines TRON 1 to October 2023. Not changed here.
2. **NEURA founding year:** profile 2019 (intro); the same page's timeline says December 2020. Team size also differs on the page (1,500+ vs 1,400+); both reported.
3. **AgiBot latest count:** the page now shows 20,000 robots (Sep 2026). The existing `deployment_note` still cites the 15,000th (Jun 2026). Left unchanged.
4. **Galbot, AgiBot, Sanctuary** `deployment_status` is NULL; the new own-site wording may justify a status review.
5. **Citation precision:** use-case fact UC-3 (ISO/CD 25785-1 label) rests on a search-result title. Re-check when `iso.org` is reachable.
6. **Evidence note provenance:** new rows cite the research work order as 'HO-CONTENT-01 thin-content enrichment' (2026-11-02). The existing rows quote a named owner; the owner should confirm the wording.

## 8. Proposals (NOT implemented: no schema or UI change)

1. **`use_case_source` table** (use_case_id, source_url, source_type, observed_at, confidence, excerpt, claim): use-case text is editorial and currently has nowhere to keep evidence, so sources live only in documents like this one (AGENTS rules 6/7 spirit). Highest-value addition.
2. **Structured manufacturer `milestones` / `funding_rounds`**: dated company events (production counts, funding) are now prose. A structured form would let the page show them as a sourced table, stay fresh, and avoid stale sentences (see AgiBot above).
3. **Use-case page sections**: "Deployments on record" (from `deployment` rows, which exist) and "Standards and safety" (e.g. ISO 25785-1) rendered from data rather than prose. Deployment rows already exist for a few robots and are the strongest honest content for thin pages.
4. **Manufacturer product list**: the pages already list robots; a "Products the maker lists that we do not catalogue" field would carry the quadrupeds, arms and software the profile prose currently mentions.

## 9. Verification

Run on Ubuntu with PostgreSQL 15 (CI uses 16; installed because docker is unavailable):

| Command | Result |
|---|---|
| `uv run db/bootstrap.py && db/import_catalogue.py && db/validate_catalogue.py && db/readiness_check.py integrity` (fresh DB, no seed) | all exit 0; G2 OK; integrity gate PASS (73 robots, 0 blocking) |
| `cd apps/api && uv sync && uv run ruff check .` | All checks passed |
| `uv run pytest` (against a **seeded** DB, as CI does with `bootstrap.py --seed`) | {{API}} |
| `cd apps/web && npm ci && npx vitest run` | 52 files, 732 tests passed |
| CI on the PR | {{CI}} |

Note: pytest against a DB where the catalogue was imported (not seeded) fails `test_agent_projection.py::test_price_display_meaning_is_preserved` (expects the seed's 16000, finds 13500). That is environment, not this change: CI seeds, it does not import, for the API job.
