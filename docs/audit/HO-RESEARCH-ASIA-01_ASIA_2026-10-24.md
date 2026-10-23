# HO-RESEARCH-ASIA-01 — Asia Regional Research Resource: implementation, evidence and readiness

**Date:** 2026-10-24 · **Branch:** `feat/research-asia` (from `main` d6a1b6e, which holds the published Europe and North America resources)
**Status:** DRAFT PR. Nothing is merged, imported, flagged or published. `RESEARCH_PUBLISHED_REGIONS=europe,north-america` is unchanged on both environments.

## 1. What this branch does

The Asia resource reuses the ADR-027 machinery that serves Europe and North America; nothing about those two pages is redesigned.

| Layer | Change |
|---|---|
| Geography | `db/catalogue/regions.json`: new `ASIA` CONTINENT, with 50 direct children: 49 of the 50 UN M49 142 codes, plus `TW`. Only `region.parent_id` changes (§3). |
| API | `REGION_SLUGS["asia"] = "ASIA"`. Same read model, projection, 5-robot / 3-manufacturer gate and evidence-age rule (no 90-day window). |
| Web | `asia` joins `RESEARCH_REGIONS`, with `asia/page.tsx` and `asia.json/route.ts` through the shared `ResearchRegionPage` / `research-json`. Signed noindex preview: the form lists Asia. A DRAFT editorial fragment (`reviewed_at: null`, one UN M49 citation, no figures). |
| Publication | Closed by default. The sitemap, `llms.txt`, hub link and navigation follow the existing flag logic, so Asia stays absent under the current production flag (tested). |
| Data | The proposed Fast Lane batch ASIA-01 (§5) and its manifest `db/catalogue/ho_research_asia01_expected.json`. **Not imported.** |

Every Asia figure, table row, price, FAQ answer and JSON-LD node comes from the one governed projection. The editorial fragment holds only geography and interpretation (tested: no digit, currency or robot name).

## 2. Baseline (read-only, 2026-10-24, from the attached audit; re-derived locally)

Production has 43 published robots and no `ASIA`/`APAC` grouping. Published robots have 0 Asia-coded offers, prices or deployments (all 50 M49 codes plus `TW` were checked). The gate fails at 0/0.

This branch's projection over the **current main catalogue files**, without the batch, is also 0 robots / 0 manufacturers. This is the explicit closed, zero-offer state; it is pinned by `test_zero_offer_state_is_explicit_and_fails_the_gate`.

## 3. Geography decisions (owner review required)

UN M49 Asia 142 lists 50 country/area codes ([UNSD M49 overview](https://unstats.un.org/unsd/methodology/m49/overview/)): Central Asia 143 (5), Eastern Asia 030 (7), South-eastern Asia 035 (11), Southern Asia 034 (9) and Western Asia 145 (18). All 50 already exist in `regions.json`. Before this change, 49 had no parent and `CY` sat under `EU`.

**D1 — Cyprus (implemented: disclosed v0.1 exclusion, 49/50).** The region tree is single-parent, and `CY` → `EU` → `EUROPE` feeds the EU pricing-hierarchy view, matching, lead routing and the live Europe resource. Two safe options:
- **(a) exclusion (chosen):** Cyprus stays in Europe only. This changes nothing that is live. The Asia methodology and editorial state the exception.
- **(b) a research-only membership overlay** in the read model (Asia = descendants + `CY`). That is M49-faithful 50/50, but it touches the read model shared by two live resources. It makes the generated text "every region beneath it in the catalogue hierarchy" untrue for Asia only, and it makes Europe and Asia overlap.

A proper multi-membership model would be a schema change, its own reviewed work. Recommendation: keep (a) for v0.1. Pinned by `test_cyprus_stays_in_the_eu_and_europe_and_out_of_asia` and `test_a_cyprus_offer_counts_for_europe_not_asia`.

**D2 — Taiwan (implemented: included as a commercial-market member).** `TW` is an ISO 3166-1 row that the catalogue uses as a separate commercial destination; M49 does not list it as a separate Asia entry. It is a direct child of `ASIA`; it is not reparented under `CN`. The editorial says it is included as a market and that "that is not a claim that M49 lists it as a separate entry". The alternative is to exclude `TW`, in which case a seller offer for Taiwan would count nowhere. Pinned by `test_taiwan_is_a_commercial_member_but_not_reparented_under_china`.

**Fixed rules (from the order):** `RU` stays under `EUROPE`. `APAC` is not modelled and is not a synonym for Asia: the API and preview form both refuse `apac`. `GLOBAL` is never a member. Nothing in the catalogue references `ASIA` directly (tested), so the ancestor walks in matching, lead routing and `commercial_offer` behave as before; the same argument applied to `NORTH_AMERICA`.

**Prerequisite for a production preview:** a governed **full** import of `regions.json`. Until then the API returns 404 for Asia even with a token (tested). A scoped `--only` run would not reparent the 50 members.

## 4. Evidence matrix

Every retrieval happened on 2026-10-24 under this work order (agent-assisted research, docs/26 R5). Agent readings are `MEDIUM`/`HIGH`, `verified_at` is NULL, and none is attributed to the owner. Raw bodies are kept in the session scratchpad; their sha256 is recorded below and in each evidence row's note.

### 4.1 Confirmed (in the batch)

| Robot (canonical slug) | Edition evidenced | Country | Seller (provider) | Seller type / authorization | Tx | Status (seller wording) | Price as published | Confidence |
|---|---|---|---|---|---|---|---|---|
| `unitree-g1` | "G1" column (23 DoF, no secondary development) = G1 Basic | CN | Unitree China (`unitree-cn`) | Manufacturer (direct) | PURCHASE | ON_REQUEST ("本预约定购是一种意向性定购": an intent order, confirmed by Unitree) | CNY 85,000 including tax (售价（含税）) | price HIGH · offer MEDIUM |
| `unitree-r1` | "R1" column (between R1 AIR and R1 EDU) | CN | `unitree-cn` | Manufacturer | PURCHASE | ON_REQUEST | CNY 39,900 including tax | HIGH · MEDIUM |
| `unitree-h2` | "H2" column (base edition; H2 EDU = contact sales) | CN | `unitree-cn` | Manufacturer | PURCHASE | ON_REQUEST | CNY 199,000 including tax | HIGH · MEDIUM |
| `unitree-g1` | "G1 Basic" configuration | JP | GMO AI & Robotics (`gmo-air`) | Distributor; **self-declared** Unitree 国内正規代理店 (agreement 2026-06-19) | PURCHASE | ON_REQUEST (add to cart → "お見積もりへ") | not published | MEDIUM |
| `unitree-g1-edu-plus-u2` | "G1 Edu Plus" (29 DoF, 100 TOPS dock) | JP | `gmo-air` | as above | PURCHASE | ON_REQUEST | not published | MEDIUM (U2 label: D5) |
| `unitree-r1` | "R1 Basic" (26 DoF) | JP | `gmo-air` | as above | PURCHASE | ON_REQUEST | not published | MEDIUM |
| `unitree-h2` | "H2-Basic" (i5, SDK closed) | JP | `gmo-air` | as above | PURCHASE | ON_REQUEST | not published | MEDIUM |
| `unitree-h2-edu` | "H2 EDU Standard" (i5 + i7) | JP | `gmo-air` | as above | PURCHASE | ON_REQUEST | not published | MEDIUM |
| `booster-k1-professional` | BOOSTER-K1-PRO, "Booster K1 Professional", Jetson AGX Orin 32GB | JP | Switch Science (`switch-science`) | Third-party retailer; handles Booster products since 2026-04-16; not stated to be authorized | PURCHASE | ON_REQUEST (special order "取寄商品", paid in the cart, delivery usually 2–3 months) | JPY 3,148,200 including tax | MEDIUM |
| `softbank-pepper` (variant `for-home-2`) | "Pepper for Home 2.0" (home model) | JP | TENT Inc. store on Kauriru (`tent-pepper-rental`) | Rental provider, linked from SoftBank's own Pepper page | **RENTAL** | AVAILABLE ("今すぐ月額レンタルする"; delivery-date calendar) | FROM JPY 43,780 / month including tax (1-year plan; month-to-month plan JPY 76,780) | MEDIUM |

**Deployment (separate dataset):** `ubtech-walker-s2`, CN, Hitachi (China) Ltd., status pilot (on-site testing at a Hitachi Elevator workshop). Source: [UBTECH news, 2026-07-13](https://www.ubtrobot.com/en/about/news/826577556529221). MEDIUM, because the exact site and city are not named. Start date and unit count are NULL. It produces no offer.

**Projection with the batch** (real catalogue files, snapshot 2026-10-24):
- **Asia: 7 robots / 3 manufacturers (Unitree, SoftBank Robotics, Booster Robotics). The gate PASSES.**
- Groups reconcile 7 + 36 = 43.
- 6 robots are purchasable, all on request; 4 have a published purchase price, 2 do not. 1 robot is rental-only (Pepper).
- 1 deployment.
- Europe stays at 10/3 and North America at 5/5; both are unchanged (tested).

### 4.2 Retrieval log (body sha256)

| URL | Method | sha256 |
|---|---|---|
| https://www.unitree.com/cn/g1/ | curl, browser UA | `38f25a20f44a40004bbe1b21234a5fcfc5b650cf428b4af1455e657d5e2f555f` |
| https://www.unitree.com/cn/R1 | curl | `7b124a43abde252b25596e6c137570e8b3801900ef59354ed4c080427fd98ec4` |
| https://www.unitree.com/cn/H2 | curl | `aaf0fafdc3ebd8919cbcb949928261ac389575681278e8ed21a7c058bce3ffb8` |
| https://www.unitree.com/cn/h1 | curl (no price; not used) | `5b900eca93b8fd6a5db036ff74ca3ba151480797bab8be9cd2a30bf1c90ddae6` |
| https://www.unitree.com/cn/booking | curl | `5b5b469f52f799000e13178b2edb5166de73bad0ec285bd5c337b70d0e66e138` |
| https://english.beijing.gov.cn/…/202605/t20260507_4639802.html | curl | `6257fddf0e5911a0d3634b43e11c06fa1882414a22e285b3e8d23094fc8336b2` |
| https://english.beijing.gov.cn/…/202601/t20260107_4406681.html | curl (JD MALL store; not used: it does not name a G1 edition) | `1c0ab9a0df7c22be5984e3702e7cdfe7d1ce7119200415cdcea0583815b2bb9a` |
| https://gmo-humanoid.shop/ | curl ("Unitree 国内正規代理店") | `69591467fa233e086b26b549fba7d81c5190cf1c16c5c3f42f22f80b80f8dc57` |
| https://gmo-humanoid.shop/unitree/g1/ | curl | `c5a06cd021c3391dad8e2e55b5206aece41615b98be7a96a92cbfaddb369d15c` |
| https://gmo-humanoid.shop/unitree/r1/ | curl | `72d4e93208d2551186b864a0971edeec066cbc4506038b31409912095e268d23` |
| https://gmo-humanoid.shop/unitree/h2/ | curl | `c7e69a0841032eda6c45fc69dd3935a72e92608e97f1b544efbad77ffc91b08d` |
| https://ai-robotics.gmo/news/article/g1-plus/ | curl (agreement date, quotation wording) | `df10d25949efec29f8893c786350aa72051f32bba15224637aea261035978ab4` |
| https://www.switch-science.com/products/10851 | curl | `057869dbdbde596b103812b731ded2d79898211675aae51c0c16529aa1dc89dc` |
| https://prtimes.jp/main/html/rd/p/000000239.000064534.html | WebFetch (processed text; start date 2026-04-16) | n/a |
| https://www.softbank.jp/robot/consumer/buy/ | curl | `7caae18720431455f90b4659ff63bf6cb70fbf81cb59e628ae3dcf7968671b92` |
| https://kauriru.com/pepper/items/12835, /pepper/operation_informations/about | built-in browser (rendered text); the raw body is a client-rendered shell, identical for every URL | shell `b41e1bdc90d4872e245aa69ff71fb1e17d08ef5d55b576f3b73df79a22d5285b` |
| https://www.ubtrobot.com/en/about/news/826577556529221 | curl | `43306307ee513099ec3cfb6d9998daf298fa4bbc5d31d85b3d94853ea5425874` |
| https://www.ubtrobot.com/en/about/company-profile | curl (mass production statement; not an offer) | `b592c9d13c9ccfca16e0bd87444630f01ddf2d0749e8dbfa7c2f7ed91d85f519` |
| https://store.agibot.com/products/a2-ultra | curl | `f40c2b1b12ed02913277e51480195ccbab46cb7f09943f3f95d74327ff6179ec` |
| https://www.booster.tech/cn/store?key=k1&target=cn, /cn/booster-k1 | built-in browser | (client-rendered) |

### 4.3 Potential (not in the batch — evidence gap stated)

| Lead | Why it is not in the batch |
|---|---|
| Booster K1 Educational / Professional, CN (booster.tech/cn K1 page names 教育版 and 专业版; purchase-inquiry form; 400-865-2028) | The inquiry form is the worldwide form (country selector) localized in Chinese, and it names no edition. That is closer to a GLOBAL route than a CN offer. Owner decision D6. |
| RobotShop Japan, Booster K1 Professional ("On Demand", ¥3,269,750 per a search snippet) | WebFetch returned HTTP 429 on every attempt; RobotShop is never opened in the browser pane. It would add no robot (K1 Professional already qualifies in JP). |
| GMO: R1 Edu Standard (40 TOPS) / R1 Edu Smart (100 TOPS) | Probably `unitree-r1-edu-u1` (reichelt "EDU-Standardausführung", 40 TOPS), but GMO does not use Unitree's U-codes. Left out to avoid a misidentified SKU (D5). |
| GMO: G1+, G1-D, H2 Plus, H2-D, R1-A | Not published catalogue records. |
| Unitree China: G1 EDU, H2 EDU, R1 EDU ("联系销售") | The edition tier is not pinned to a catalogue U-configuration. |
| Unitree Tmall/JD flagship listings; JD index `jd.com/jiage/652a0a34fbe95a8fcc8.html` | Tmall needs a Taobao login and JD a login/verification; we do not get around those walls. The JD index page lists unrelated toy products, not the G1 EDU U2 SKU. |
| D.I.S.R "Robno Renta" G1 rental (JP), GMO G1 rental (¥100,000/day, press) | Secondary reporting only; no first-party rental page was captured. |
| UBTECH Walker S2 CN purchase route | UBTECH publicizes tenders and volume contracts, not a buyer-facing contact-sales page for Walker S2 in China. RobotShop lists Walker S2 "On Demand" (US storefront, not Asia). |

### 4.4 Rejected

| Lead | Reason |
|---|---|
| `agibot-a2-ultra`, CN (store.agibot.com) | A worldwide store with a country field and shipping "$500-$3000". Headquarters in Shanghai is not CN availability, so this is GLOBAL at most. |
| `agibot-x2`, `agibot-x2-ultra` | Unpublished; they never enter the population or structured data (tested). |
| `softbank-pepper` PURCHASE, JP | SoftBank: "Pepper(一般販売モデル)の販売は終了しました。" No purchase offer is recorded. A CONFIRMED_NOT_OBTAINABLE purchase row could follow (D7). |
| `unitree-r1`, Beijing government 2026-05 article | R1 was only expected for demonstrations: a future demo, not an order route. |
| Galbot G1, Fourier GR-2, NAO (JP), Rainbow HUBO (KR), Singapore / India / Gulf sellers | No country-specific seller page found in this pass. HUBO has no evidence of current sale. |

## 5. HO-DATA Fast Lane batch ASIA-01 (proposed; NOT imported)

**Manifest:** `db/catalogue/ho_research_asia01_expected.json`, written from the intended change set. It has 83 entries covering 92 business rows:
- `ASIA` added, 50 regions changed
- 4 providers, 1 variant
- 10 availability offers, 5 pricing offers, 1 deployment
- 20 evidence rows

**Local rehearsal** (throwaway Postgres 16 in Docker, port 55439; no Neon branch was needed for this order):

1. `before_main` = schema + full import of main d6a1b6e. This is production's catalogue state: NA-02 and the X2 records were imported from it.
2. `after_asia` = a clone of that database, then a **full** import of this branch: region 1 added / 50 updated; provider +4; variant +1; pricing +5; availability +10; deployment +1; evidence +20.
3. `import_preflight.py --manifest …`: **PASS**, 92 business changes, all accounted for.
4. `import_identity_check.py`: **PASS**, 0 touched and 0 dangling audit targets.
5. Second import of the same JSON: no-op (0 business changes).
6. `validate_catalogue.py`: G2 OK and MEDIA-01 OK.

**Before → after (projection):**

| Region | Before | After | Gate |
|---|---|---|---|
| Asia | 0 / 0 (no hierarchy in production → 404) | 7 / 3 | FAILS → PASSES |
| Europe | 10 / 3 | 10 / 3 | unchanged |
| North America | 5 / 5 | 5 / 5 | unchanged |

**Production import (only after explicit owner approval):** a Neon safety branch, then a rehearsal branch from production, then a full `import_catalogue.py` and preflight against this manifest, then identity, then production. That makes the Asia preview possible; it does **not** publish Asia.

## 6. Owner decisions

| # | Decision | Default in this branch |
|---|---|---|
| D1 | Cyprus: v0.1 exclusion vs a research-only overlay | Exclusion (49/50, disclosed) |
| D2 | Taiwan as a commercial-market member of Asia | Included, neutral wording |
| D3 | Approve batch ASIA-01 (the 10 offers, 5 prices, 1 deployment) and the governed full import | Not imported |
| D4 | Register providers `unitree-cn`, `gmo-air` (self-declared authorized distributor), `switch-science`, `tent-pepper-rental` | Proposed |
| D5 | GMO "G1 Edu Plus" ↔ `unitree-g1-edu-plus-u2` (U2 label not on the page). If rejected, drop that one offer: Asia is still 6/3 and the gate still passes | Included, MEDIUM |
| D6 | Booster CN inquiry route: treat as GLOBAL (default) or as a CN on-request offer for K1 Educational/Professional | Not included |
| D7 | Record SoftBank's "Pepper (general sale model) sales ended" as a JP purchase CONFIRMED_NOT_OBTAINABLE row | Not recorded |
| D8 | Review the Asia DRAFT editorial (`reviewed_at`) | DRAFT, preview only |
| D9 | Publication: add `asia` to `RESEARCH_PUBLISHED_REGIONS` on the Vercel API and on Netlify | **Not authorized.** Flag stays `europe,north-america` |
| D10 | ADR-027 §4 wording for Asia (UN M49 142 minus CY plus TW) | Recorded here; docs/27 is not edited |

## 7. Launch readiness

- **Code:** ready (tests in §8).
- **Data:** the batch rehearses cleanly and passes the gate at 7/3. Production has none of it yet.
- **Preview in production** needs D3 (and the full import that adds `ASIA`) and `RESEARCH_PREVIEW_TOKEN`, which is already set for NA.
- **Publication** needs D8 (optional; the editorial stays hidden without it) and D9.

Risks recorded:
- Every purchase route is on request. No Asia offer is "available" for purchase; only the Pepper rental is.
- Japan dominates: 7 of the 10 offers are Japanese (3 sellers), against 1 Chinese manufacturer channel.
- Coverage of Korea, India, Singapore and the Gulf is still zero.
