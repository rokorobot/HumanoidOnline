# G4-4A — Catalogue-wide audit (read-only), 2026-10-04

Scope: the whole catalogue, production database, read-only. Tooling: `db/readiness_check.py`
(`integrity`, `coverage`) from DR-G4 §13 plus direct inspection of the accepted-claim and proposal
tables. **Nothing was changed by this audit.** It is the inventory that G4-4B remediates, and it is
not a completeness campaign: coverage is informational and never the objective.

## 1. Baseline (before G4-4B)

| Measure | Value |
|---|---|
| robots (stored / published) | 57 / 38 |
| integrity gate | PASS, 0 blocking |
| coverage bands (informational) | LOW 25, PARTIAL 29, GOOD 3 |
| canonical direct facts | 279 |
| canonical projected facts | 7 |
| `DETAIL_ONLY` | 160 |
| `NO_CATALOGUE_HOME` | 13 |
| `UNMAPPED_KNOWLEDGE` | 9 |
| `UNACCOUNTED_LOSS` | 0 |
| `CONFLICT` | 0 |
| `NOT_YET_REVIEWED` | 31 |
| legacy unexplained `false` values (published robots) | 8 |
| published robots without a summary | 4 |
| unpublished robots asserting `ANNOUNCED` without evidence | 19 |

A deterministic per-robot baseline (hash of the robot row plus offers, availability, specifications,
variants, images and status evidence) was recorded before any change, to prove after each batch that only
the intended robots moved.

Not defects (owner ruling): robots without a price (38), without availability (44), without deployment
evidence (54), or with UNKNOWN fields. A missing price is correct when the manufacturer has published none.

## 2. Priority 1 — the 19 unpublished `ANNOUNCED` stubs

Rule applied (frozen maturity dictionary; owner WorkOrder): `ANNOUNCED` is kept only when first-party
evidence establishes **both** that the robot was publicly revealed **and** that it is not yet available
(explicit pre-order / planned / not-for-sale wording); otherwise `UNKNOWN`. Public fame alone, shipping
hardware, business-only sales and reservations without a stated status do not establish it. No other
maturity is guessed; where the evidence points at another state the case is listed for the owner.
Evidence column: **V** = verbatim first-party fetch, **S** = a search-result summary of a first-party page
(enough to show `ANNOUNCED` is contradicted, not enough to assert another state).

| Robot | First-party finding | Disposition |
|---|---|---|
| agibot-a2 | A2 Ultra described as deployed commercially at scale, "more than 1,000 units in 2025" (S, agibot.com/products/A2) | `UNKNOWN`; candidate for a commercial state (owner) |
| astribot-s1 | product page states neither a release nor an availability (V) | `UNKNOWN` |
| booster-t1 | developer robot, RoboCup 2025 champion, store listing (S, booster.tech/booster-t1) | `UNKNOWN`; candidate commercial |
| clone-protoclone | "Protoclone" is not named; page offers "Reserve one of the first 279 Clones ever made, in its Alpha Edition." (V, clonerobotics.com/android) | `UNKNOWN`: identity not matched, reservation only |
| engineered-arts-ameca-desktop | "not yet a consumer product. All robots are available to businesses for qualified applications" (S) | `UNKNOWN`: sold to businesses |
| engineered-arts-mesmer | product presented for entertainment/museums/research; no availability statement located (S) | `UNKNOWN` |
| figure-01 | no first-party availability statement located | `UNKNOWN` |
| figure-03 | announced 9 Oct 2025, then "Ramping Figure 03 Production" and "F.03 Arrives at BMW" (S, figure.ai/news) | `UNKNOWN`: shipping evidence contradicts `ANNOUNCED` |
| fourier-intelligence-gr-1 | "officially rolled out and became the first mass-produced humanoid robot in 2023" (S, fftai.com) | `UNKNOWN`: contradicts |
| galbot-g1 | product page plus developer SDK documentation; shipping product (S) | `UNKNOWN`: contradicts |
| limx-dynamics-cl-1 | news: a test showcase, "will be progressively deployed"; no availability; the company's launched product is named Oli (S) | `UNKNOWN`; naming/identity note |
| neura-4ne-1 | "expected to be available end of 2026"; EUR 100 reservation (S, neura-robotics.com/product/4ne1-reservation) | `UNKNOWN`: same evidence class for which the owner kept the 4NE1 Mini `UNKNOWN`; one owner decision would cover both |
| pal-kangaroo | page offers "Request a quote" and a datasheet; availability not stated (V, pal-robotics.com/robot/kangaroo) | `UNKNOWN` |
| realbotix-aria | first-party site presents Aria among current products (S) | `UNKNOWN` |
| robotera-l7 | first-party site lists the product; no availability statement located (S) | `UNKNOWN` |
| robotera-star1 | same | `UNKNOWN` |
| toyota-t-hr3 | "On November 21, 2017, Toyota ... revealed T-HR3" (S, global.toyota newsroom); no availability statement | `UNKNOWN` (candidate `ANNOUNCED` or a research-prototype state: owner) |
| ubtech-walker-s2 | "UBTECH began the mass production and delivery of Walker S2" (S, ubtrobot.com) | `UNKNOWN`: contradicts |
| xiaomi-cyberone | unveiled 11 Aug 2022 (Xiaomi IR / community); first-party availability fetch timed out | `UNKNOWN` |

Result: **0 retained, 19 changed to `UNKNOWN`** (all remain unpublished). Eight records show first-party
evidence of shipping or business sales, for which a commercial state is a separate owner decision.

## 3. Priority 2 — the 8 legacy unexplained `false` values

| Robot | Field | Finding | Disposition |
|---|---|---|---|
| unitree-g1 | has_manipulation | wording is preserved in `hand_type` ("fixed non-dexterous hands (non-articulating; cannot grasp)") and `hand_dof = 0`, a stated fact | boolean to `NULL`; sourced zero kept |
| unitree-g1 | has_sdk | the note paraphrases a retail listing ("denies SDK access"); no first-party negative | `NULL` |
| unitree-g1 | developer_edition | inferred from the SKU being "Basic" | `NULL` |
| unitree-g1-edu-plus-u2 | has_manipulation | wording preserved in `hand_type`; reseller listing | `NULL`; sourced zero kept |
| unitree-h2 | has_sdk, developer_edition | Unitree's table shows "/" for Secondary Development on H2 and "YES" on H2 EDU (V, unitree.com/H2): a cell value, not a negative statement | `NULL` |
| unitree-r1 | has_sdk, developer_edition | same table pattern ("/" vs "YES") plus a distributor remark | `NULL` |

No ratified negative projection exists, so none can resolve `false`; no source wording is invented.
Related faithfulness finding: the stored `secondary_development` specifications read "Not supported on this
edition (H2 EDU only)", an interpretation of "/". They are restated as the table cell values.

## 4. Priority 3 — the 4 published robots without a summary

`honda-asimo`, `rainbow-hubo`, `softbank-nao`, `softbank-pepper`. First-party facts read: Honda's press
release of 20 Nov 2000 ("a new small, lightweight humanoid robot named ASIMO that employs Honda's new
robotic walking technology"); Rainbow Robotics' About page ("Our journey began with 'HUBO,' Korea's first
humanoid robot"); the NAO6 page ("a proven humanoid robot designed to interact naturally with people in
education, research, healthcare and elderly environments"); SoftBank Robotics America's Pepper page
("Pepper is a robot designed for people"). Note: NAO and Pepper are now offered by Maxtronics / Aldebaran,
so the catalogue's manufacturer attribution for them may be stale (owner/identity review, not changed here).

## 5. Priority 4 — `UNMAPPED_KNOWLEDGE` (9) triage

All nine are `dexterous_hand_option` descriptions of one edition each (booster-t2-education,
booster-t2-professional, unitree-h2, unitree-h2-edu, unitree-r1, unitree-r1-edu-u3..u6). Class **B —
`DETAIL_ONLY` is sufficient**: each is valuable edition detail kept verbatim with provenance. A recurring
pattern worth an owner decision (class **A candidate**, not mapped here): wording that states hands are
*present* (for example "Two Dex3-1 three-finger hands", "Two Revo 2 Basic five-finger hands") could project
`has_manipulation = true` exactly as "12 DoF dexterous hands" does for the Mini; those four are reseller
claims. "Not specified for this edition" (H2, R1) is a paraphrase of "/" and projects nothing.

## 6. Priority 5 — pending proposals (31) triage

All 31 are CURRENT (none superseded or stale). They never block publication.

| Robot | Kinds | Priority |
|---|---|---|
| xpeng-iron | LAUNCH_PLAN, MASS_PRODUCTION_PLAN x2, DEPLOYMENT_PLAN, DEPLOYMENT_STATE, MANUFACTURING_STATE x2, SDK_PLAN | HIGH: they bear on IRON's maturity and developer information (owner semantics) |
| xpeng-iron | APPLICATIONS x5, SENSING, MORPHOLOGY x5, AI_ARCHITECTURE | MEDIUM: useful enrichment, no normalized home |
| xpeng-iron | GENERATION_HISTORY x3, GENERATION_LABEL, SHOULDER_DOF, SYSTEM_DOF_2024, MANUFACTURING_METRIC | LOW: historical / detail |
| 4ne1-mini | DATASHEET_REFERENCE | HIGH: the datasheet likely holds physical specifications (an extraction task, not a proposal) |
| 4ne1-mini | INTEGRATION x2, DESIGN_CAVEAT | MEDIUM / LOW |

## 7. Enrichment opportunities (reported, not executed)

* 4NE1 Mini datasheet: physical specifications (height, weight, payload, runtime) from a first-party PDF.
* Robots whose first-party pages state shipping or delivery: a commercial state is available as an owner
  decision for agibot-a2, booster-t1, fourier-intelligence-gr-1, galbot-g1, ubtech-walker-s2, figure-03.
* Buyer fields (payload, runtime, battery) remain UNKNOWN across most robots; adding them needs per-robot
  first-party reading and is queued, not performed.

## 8. Owner-level semantic decisions surfaced

1. Negative projections (none ratified): for example `Secondary Development` "/" versus "YES".
2. Whether availability statements ("expected end of 2026") justify `ANNOUNCED` (4NE1, 4NE1 Mini).
3. A projection for "hands present" tokens (class A candidate above).
4. Commercial states for robots whose first-party pages show shipping.
5. NAO / Pepper manufacturer attribution (Maxtronics / Aldebaran versus SoftBank Robotics).

## 9. G4-4B result (2026-10-04): before / after

Remediation PRs: #119 (stubs), #120 (legacy `false`), #121 (summaries); each applied to production with a
scoped import and checked against a per-robot before/after snapshot (only the intended robots changed;
no publication change; no price, offer, availability, variant, image or claim change; no NULL became
false or 0).

| Measure | Before | After |
|---|---|---|
| robots stored / published | 57 / 38 | 57 / 38 |
| integrity blockers | 0 | 0 |
| coverage bands LOW / PARTIAL / GOOD (informational) | 25 / 29 / 3 | 25 / 30 / 2 |
| canonical direct | 279 | 274 |
| canonical projected | 7 | 7 |
| `DETAIL_ONLY` | 160 | 160 |
| `NO_CATALOGUE_HOME` | 13 | 13 |
| `UNMAPPED_KNOWLEDGE` | 9 | 9 |
| `UNACCOUNTED_LOSS` | 0 | 0 |
| `NOT_YET_REVIEWED` | 31 | 31 |
| `CONFLICT` | 0 | 0 |
| legacy unexplained `false` | 8 | 0 |
| published robots without a summary | 4 | 0 |
| unpublished robots asserting unsupported `ANNOUNCED` | 19 | 0 |
| legacy baseline entries | 12 | 0 |

Notes. *Canonical direct* fell by five because three robots' unsupported `false` values and the same
number of other booleans became UNKNOWN: a deliberate trade of a count for truthfulness. The G1 Basic
moved from the GOOD to the PARTIAL band for the same reason; coverage is informational and is not the
objective. `NO_SDK_EVIDENCE` rose from 36 to 39 for the same three records. The 19 stubs now read
`UNKNOWN`; seven of them had also been missing the manufacturer's `official_url`, which the scoped import
supplied from the committed catalogue.

Remaining coverage gaps (no price for 38, no availability for 44, no deployment evidence for 54, UNKNOWN
buyer fields, 9 triaged hand-option descriptions and the pending proposals) are accepted normal
incompleteness or queued enrichment, not publication barriers.
