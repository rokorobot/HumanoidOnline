# HO-DATA-02A — Missing Data Opportunity Analysis (2026-10-22)

**Type:** read-only analysis. No catalogue file, production row, source, or publication state was changed.
**Catalogue basis:** `origin/main` @ `4f992c9` (after PR #187). The published set was checked and is identical to production (43 robots).
**Held-evidence basis:** read-only SELECTs against production (`candidate_claim`, `discovery_candidate`,
`discovery_claim_proposal`, `discovery_source`, `fetched_page`), run 2026-10-22 on a read-only connection with `SET TRANSACTION READ ONLY`.
**Not done:** no manufacturer page, datasheet or new host was fetched. Stage 2 research is outside this task.

Files: `ho-data-02a/gap_matrix.csv` (robot × field: KNOWN or gap class), `ho-data-02a/gap_cells.csv`
(one row per UNKNOWN cell, with class and basis), `ho-data-02a/gap_matrix.py` (reproduces both from the catalogue
plus the claim export).

---

## 1. Counting rule

- **Population:** the 43 published robot records (`is_published: true`). The 18 unpublished records are out of
  scope; 7 of them are empty stubs.
- **Fields:** the 22 core spec fields that the robot detail page renders (`apps/web/app/robots/[slug]/page.tsx:549-576`).
  A cell is UNKNOWN when its catalogue value is `null`. `false` and `0` count as known (for example, G1 `hand_dof 0`).
- **Denominator:** every field counts for every robot, 946 cells in total. Nothing is reclassified as "not applicable".
- Extended specs, commercial status, deployments and capabilities are reported separately (§3) and are not part of the 946.

## 2. Baseline

| Scope | UNKNOWN | Rate |
|---|---|---|
| **All 22 core fields** | 619 / 946 | **65.4%** |
| P0 (height, weight, payload, runtime, walk speed, DoF) | 119 / 258 | **46.1%** |
| P1 technical (battery Wh, mobility, hand type/DoF, vision, SDK, API, ROS, simulation, dev edition, language UI) | 317 / 473 | 67.0% |
| P1 capability (autonomy, manipulation, teleoperation) | 100 / 129 | 77.5% |
| P2 (arm span, reach) | 83 / 86 | 96.5% |

The reported "50%+" is confirmed, and the real figure is higher: **65.4%**. Of the 619 gaps, 262 are boolean fields.

**Per field (UNKNOWN of 43):** height 9 · weight 14 · payload 27 · runtime 17 · **walk speed 32** · DoF 20 ·
battery Wh 40 · mobility 11 · hand type 36 · hand DoF 34 · vision 19 · SDK 26 · API 30 · ROS 32 · simulation 29 ·
dev edition 34 · language UI 26 · autonomy 34 · manipulation 27 · teleoperation 39 · **arm span 43** · reach 40.

**Seven published robots have no core spec at all (22/22 UNKNOWN):** `agibot-a2-ultra`, `booster-t1`, `galbot-g1`,
`ubtech-walker-s2` (all four COMMERCIAL), `softbank-nao`, `softbank-pepper` and `rainbow-hubo`. Together they hold
154 cells (25% of all gaps) and 42 P0 cells (35% of P0 gaps).

## 3. Outside the 22 core fields

- **Extended specs** (sensors, compute, connectivity, battery pack, torque): only 17 of 43 published robots have
  any. By key: `compute_base` 12, `cameras` 15, `connectivity` 12, `battery_pack` 5, `lidar` 3.
- **Actuation**, a P1 item in the brief, has no spec key in `spec_definitions.json`. Unitree claims such as "Joint
  motor" and "Joint output bearing" are already captured, but there is nowhere to store them in the catalogue.
- **Maturity:** 12 of 43 robots have `commercial_status` UNKNOWN. These are already listed as owner decisions in
  `G4-4A_CATALOGUE_AUDIT_2026-10-04.md` and are not re-audited here. 40 of 43 have no deployment row, and 26 have no
  capability row.

## 4. Gap classes

Each UNKNOWN cell gets exactly one class. The classes are tested in the order shown.

| Class | Meaning | Cells | P0 | Boolean |
|---|---|---|---|---|
| `HELD_DIRECT` | Production already holds a manufacturer claim that states this field. | 2 | 0 | 2 |
| `HELD_DECISION` | Production holds a claim, but an owner semantic or identity ruling is needed first (§6). | 24 | 9 | 5 |
| `FETCHED_NOT_EXTRACTED` | An authorized source has fetched the product page, but no claims were extracted for this robot. | 22 | 6 | 9 |
| `SOURCE_SILENT` | `specs_note` records that the checked primary source does not state this field. | 121 | 19 | 32 |
| `CRAWLED_PAGE_SILENT` | An authorized source crawled this record's own product page, and no claim on it states this field. | 111 | 15 | 60 |
| `SOURCE_PREFIX_EXTENSION` | The manufacturer has an enabled owner-authorized source, but this product page is outside its authorized path prefixes. | 51 | 14 | 20 |
| `RESEARCH_NEVER_STARTED` | `specs_note` is still the placeholder "Specifications not yet verified." No spec research is recorded. | 66 | 18 | 27 |
| `RESEARCH` | There is no held evidence and no recorded source check for this field. | 222 | 38 | 107 |

**The distinction the brief asks for:**

- **Already captured but not used: 48 cells (7.8%).** These are the HELD and FETCHED classes. Authorized sources
  have crawled the spec pages of 21 of the 43 published records (counting edition records that share a page). For Unitree, Booster, Figure 03 and 4NE1 Mini, nearly everything it states
  about the core fields has already been promoted. **The bottleneck is how much evidence we collect, not how we use it.**
- **Checked, and the source is silent: 232 cells (37.5%).** These are the two SILENT classes. Here "the manufacturer
  does not disclose it" is plausible, but only for the page we checked. Manuals, datasheets and developer docs have
  not been checked. Today the `SOURCE_SILENT` reasoning exists only as free text in `specs_note`.
- **Not checked: 339 cells (54.8%).** These are `RESEARCH`, `RESEARCH_NEVER_STARTED` and
  `SOURCE_PREFIX_EXTENSION`. This is where the brief's main opportunity lies: values that may already be published
  that our system has not looked for. 51 of these cells belong to manufacturers we have already authorized.

## 5. Ranked enrichment backlog

The batches are ranked by likely recovered P0 cells relative to acquisition and governance cost. Each batch is
grouped the way crawl and promotion actually run, by source or manufacturer, and every batch goes through the
existing governed promotion workflow. **Upper bound** means the value if every cell in the batch resolves. It is
not a forecast. The batches add up to all 619 cells and all 119 P0 cells.

| # | Batch | Robots | Cells (P0), upper bound | What it needs | Boundary |
|---|---|---|---|---|---|
| **1** | **Unlock held claims** | 4ne1-mini (SDK and ROS: DIRECT); booster-t2 ×2; unitree-g1, h2, h2-edu, r1, r1-edu-u1 and u3–u6; agility-digit | **26 (9)** | Owner rulings D1–D8 (§6), then routine promotion PRs. No new access. | Owner ruling, then promotion |
| **2** | **AgiBot A2 extraction** | agibot-a2-ultra (COMMERCIAL, 22/22 UNKNOWN) | **22 (6)** | `/products/A2` has already been fetched under the owner-authorized `agibot-official` source, but all 70 AgiBot claims are for X2. Needs an A2 extractor, then edition scoping (A2 vs A2 Ultra vs A2 Lite). | Stage 3 build authorization |
| **3** | **Prefix extension on authorized manufacturers** | booster-t1 (22), unitree-h1 (11), figure-02 (18; discontinued, so its page may be gone) | **51 (14)** | The owner adds `/booster-t1`, `/H1` and a Figure 02 path to the existing A4 authorizations. Then crawl, then promote. | Owner A4 authorization |
| **4** | **Never-researched platforms with a long public history** | softbank-nao, softbank-pepper, rainbow-hubo | **66 (18)** | A Stage 2 research work order (docs/26 A3 R5). These platforms have shipped for years, so manufacturer technical documentation probably exists. This pass did not verify that. | Research work order |
| **5** | **Commercial robots with no source** | ubtech-walker-s2, galbot-g1 (22 each), engineered-arts-ameca (17) | **61 (17)** | Stage 2 research. These are candidates for new A4 sources if the owner chooses. | Research work order; A4 onboarding is a separate decision |
| **6** | **Deeper first-party documents for checked-silent fields** | 12 Unitree records, 5 Booster, 2 PAL, xpeng-iron, figure-03, 4ne1-mini, agility-digit, 1x-neo, apptronik-apollo | **232 (34)** | User manuals, developer docs and datasheets beyond the product page (for walk speed, ROS/simulation, battery Wh, booleans). Most of these are on new hosts, so each one needs a new-source decision. Lower yield: some values will be genuinely undisclosed, and recording that is progress in knowledge, not in coverage. | Research work order / new source |
| **7** | **Unchecked fields on other published robots** | honda-asimo, tesla-optimus, 1x-eve, hanson-sophia, ubtech-walker-s1, kepler-k2-forerunner, fourier-gr-2, sanctuary-phoenix, boston-dynamics-atlas-electric, apptronik-apollo, 1x-neo | **161 (21)** | Stage 2 research. Yield will be uneven: several of these manufacturers disclose little. | Research work order |

**Edition scope applies to every batch.** A gap is a (record, field, edition) slot. The Unitree G1, H2 and R1 pages
give one value per edition column. An "R1 EDU" column value does not fill `unitree-r1-edu-u3`, and a parent value is
never copied to an edition (see D6).

**Note on the two HELD_DIRECT cells:** `has_sdk` and `ros_support` are rendered through the G4 resolver
(`ResolvedRow`). Promotion writes the robot column, and the resolver derives what is displayed on read
(`apps/api/app/services/resolved_facts.py`). 4NE1 Mini has Standard and Pro variants, so the promotion PR should
confirm that the datasheet statement covers both variants before it writes a product-level value.

## 6. Owner rulings that unlock held evidence (Batch 1)

| ID | Question | Held claim | Cells |
|---|---|---|---|
| D1 | May a value be **derived from stated components**? For example, `battery_wh` = stated voltage × stated capacity, or DoF = the sum of stated per-limb DoF. Precedents point both ways: the G1 promotion summed per-limb rows into `joint_breakdown`, while the H1 note refused to infer a DoF total. | Booster T2: "48 V, 10 Ah" | 2 |
| D2 | May a stated **maximum** speed fill `walk_speed_ms`, or does it belong only in the extended `max_speed` key? This also decides much of the 32/43 walk-speed gap in future crawls. | 4NE1 Mini: "Max. 4.6 km/h" | 1 |
| D3 | Should `payload_kg` take a dual-arm or a per-arm figure? The G1 precedent used the arm maximum load. The T2 note currently keeps the value UNKNOWN because distributors disagree. | Booster T2: "Maximum Dual-Arm Payload 10 kg*" | 2 |
| D4 | Does the G1 precedent (mic array + speaker + two-way interaction → `has_language_ui` true) extend to "Large-Model Support: Supported" plus a mic array and speaker? | Booster T2 | 2 |
| D5 | How should `hand_type` read when the end effector is optional ("standard, gripper, or dexterous hand")? | Booster T2 ×2, Unitree H2 EDU | 3 |
| D6 | Edition scope: may a generic "EDU" column value (weight "About 29kg", DoF "26-40") fill a U-edition record, or only a value stated for that edition? | Unitree R1 EDU U1, U3–U6 | 5 |
| D7 | Is "Digit 5" the catalogue's `agility-digit`? And is "Reach 2.2m" an arm reach (the schema's meaning) or a vertical reach? | Agility Digit 5 (NEW_ENTITY) | 2 |
| D8 | Is Unitree's "/" in an edition column a first-party statement of absence ("not offered / not fitted")? Or is it silence? It appears on every Unitree crawl. | G1 "Secondary Development: /"; H2 and R1 "Secondary Development: /", "Dexterous Hand: /" | 7 |

D1, D2, D3 and D8 are policy rulings that will come up in every future crawl. Deciding them once also fixes the
rules that Stage 3 extraction will need.

## 7. Structural findings (PROPOSE ONLY)

1. **`arm_span_cm` is 0/43.** Manufacturers label single-arm reach as "arm span" (documented in the G1 note), so this
   field is unlikely ever to fill. It stays in the denominator as the brief requires, but on its own it adds 4.5
   points to the overall rate.
2. **Booleans are 42% of all gaps.** G4-4 correctly removed unsupported negatives. Booleans now close only from
   explicit first-party statements, which manufacturers rarely make, and D8 is the first systematic source of them.
   Whether the overall target is met depends mainly on booleans.
3. **The reason a value is UNKNOWN is not structured.** The brief's key distinction (undisclosed vs not yet found)
   exists only as free text in `specs_note`, and this analysis had to encode it by hand. A per-cell gap reason in the
   robot file, recording the checked source and date, would make the distinction measurable on every run. That
   would be a catalogue-format change for owner review, not a new evidence system.
4. **There is no spec key for actuation**, so this P1 item in the brief has nowhere to go.
5. **Discovery fetches only allowlisted product pages.** Today's authorized paths reach the spec pages of 21 of the
   43 published records. Turning discovery into a catalogue-completion engine is mostly a matter of widening what is
   fetched (Batches 2, 3 and 6). The extraction and promotion machinery already works.

## 8. Measurement and the proposed target

Proposed metric: **known cells / 946** across the published set, reported by tier and by gap class, with the mix of
classes tracked too. A cell that moves from `RESEARCH` to a SILENT class is progress in knowledge, but not in
coverage. The two must not be mixed.

Reality check on "<30% UNKNOWN":

- **Overall <30%** needs ≤283 UNKNOWN cells, so ≥336 must be resolved. Batches 1–5 have a combined upper bound of
  226 cells, which would still leave ≥393 UNKNOWN (≥41.5%). The overall target cannot be reached without Batches 6–7
  and substantial boolean resolution.
- **P0 <30%** needs ≤77 UNKNOWN P0 cells, so ≥42 must be resolved. Batches 1–5 have a combined P0 upper bound of 64.
  **This target is reachable** if about two thirds of them resolve.

Recommendation: adopt **P0 <30%** as the first milestone and keep **overall <30%** as the HO-DATA-02 goal. Report
both against this baseline (65.4% / 46.1% @ `4f992c9`).

## 9. Recommended next step (PROPOSE ONLY)

Start with Batch 1. It needs only owner rulings D1–D8 and uses evidence already in production, and the same rulings
set the semantics that Stage 3 extraction needs. Next would be Batch 2 (the A2 extractor, under an existing
authorization) and the Batch 3 prefix authorizations. This document does not authorize any of them.
