# HO-DATA-30 — Owner ratification package, batch 5 and outreach wave 1 (2026-10-23)

**Status:** PROPOSED. Nothing is ratified, merged, imported or sent. Each owner ruling, the batch and each outreach
message is a separate owner act.

**Basis:** evidence already gathered under `HO-DATA-STANDING 2026-10-22` (DR-D1). This step adds no new research.

**Metric:** fixed 946-cell denominator (43 published robots × 22 core fields).
- Production at `c658560`: **526 UNKNOWN = 55.6%**; P0 101/258 = 39.1%.
- Target ≤ 316 (33.4%) → **210 more known values**.
- The three NOT_APPLICABLE cells (Ameca) stay in the denominator and are reported separately.

## 1. What the 252 held cells can deliver

All 252 held cells are reviewed:
- 227 remaining from the Phase 1 decision package: 235, minus the 2 Galbot cells and 5 drift cells now live, minus
  Walker S1 vision, now live;
- 25 new Phase 2 holds.

Per-cell file: `ho-data-30/ratification_cells.csv`. It gives each cell's tier, decision, the value released under the
recommended and the alternative ruling, verbatim, source and sha256. Every (robot, field) cell appears once, so no
projection double-counts.

| Tier | Meaning | Cells |
|---|---|---|
| **A** | High confidence, edition-specific: one narrow owner ruling releases a stated value for this exact record | 1 |
| **B** | Uncertain mapping: a semantic rule decides the value (autonomy, developer edition, end effectors, language UI, derivations, label semantics, numeric policies, explicit negatives) | 142 |
| **C** | Manufacturer-generation or identity conflict: the value is stated, but for a product whose identity with the record must be ruled (NAO6, R1 EDU configurations, ASIMO generation, Next-Gen IRON, Kepler K1/K2, Sophia Utility, Apollo 2, Atlas hand). Once the identity is ruled, the value itself is certain | 54 |
| **D** | Unsupported: no usable value under any proposed ruling (weak or future-tense wording, internal-only simulation, other generation, variant-scoped 4NE1 Mini facts, ranges) | 55 |

**Projected release, without double counting:**
- **Recommended rulings:** **40 cells (13 P0)**: 1 tier A, 35 tier C, 4 tier B.
- **Alternative rulings only:** a further **27 cells (9 P0)**.
- **Never released by a ruling:** 185 cells (tier D, plus the tier B/C cells whose recommended outcome is UNKNOWN).

| Decision | Cells | A | B | C | D | Released if recommended (P0) | Extra only if alternative (P0) | Robots |
|---|---|---|---|---|---|---|---|---|
| DEC-01 | 30 | 0 | 30 | 0 | 0 | 0 (0) | 2 (0) | 30 |
| DEC-02 | 29 | 0 | 29 | 0 | 0 | 2 (0) | 0 (0) | 29 |
| DEC-03 | 23 | 0 | 0 | 22 | 1 | 18 (6) | 4 (4) | 6 |
| DEC-04 | 12 | 0 | 0 | 11 | 1 | 11 (3) | 0 (0) | 1 |
| DEC-04+DEC-07 | 1 | 0 | 1 | 0 | 0 | 0 (0) | 1 (0) | 1 |
| DEC-04+DEC-11 | 1 | 0 | 1 | 0 | 0 | 0 (0) | 1 (1) | 1 |
| DEC-05 | 8 | 0 | 0 | 7 | 1 | 2 (2) | 1 (1) | 1 |
| DEC-06 | 26 | 0 | 0 | 12 | 14 | 4 (0) | 8 (0) | 6 |
| DEC-07 | 27 | 0 | 27 | 0 | 0 | 1 (0) | 3 (0) | 18 |
| DEC-08 | 8 | 0 | 8 | 0 | 0 | 0 (0) | 0 (0) | 8 |
| DEC-09 | 7 | 0 | 4 | 0 | 3 | 0 (0) | 4 (0) | 7 |
| DEC-10 | 24 | 0 | 24 | 0 | 0 | 0 (0) | 0 (0) | 16 |
| DEC-11 | 3 | 0 | 0 | 0 | 3 | 0 (0) | 0 (0) | 3 |
| DEC-11/D10 | 1 | 0 | 1 | 0 | 0 | 0 (0) | 1 (1) | 1 |
| DEC-11/D2 | 2 | 0 | 2 | 0 | 0 | 0 (0) | 2 (2) | 2 |
| DEC-11/D9 | 1 | 0 | 1 | 0 | 0 | 1 (1) | 0 (0) | 1 |
| DEC-12 | 14 | 0 | 14 | 0 | 0 | 0 (0) | 0 (0) | 3 |
| DEC-13 | 1 | 1 | 0 | 0 | 0 | 1 (1) | 0 (0) | 1 |
| DEC-14 | 2 | 0 | 0 | 2 | 0 | 0 (0) | 0 (0) | 1 |
| DEC-16 | 9 | 0 | 0 | 0 | 9 | 0 (0) | 0 (0) | 1 |
| DEC-18 | 7 | 0 | 0 | 0 | 7 | 0 (0) | 0 (0) | 6 |
| NEW-P2 | 12 | 0 | 0 | 0 | 12 | 0 (0) | 0 (0) | 10 |
| — | 4 | 0 | 0 | 0 | 4 | 0 (0) | 0 (0) | 4 |
| **Total** | **252** | **1** | **142** | **54** | **55** | **40 (13)** | **27 (9)** | |

### Recommended rulings (each is a separate yes/no)

| ID | Recommended ruling | Releases |
|---|---|---|
| DEC-13 | Accept Unitree's R1 SDK guide "Max Arm Payload … Approx. 2kg" (same in every R1 column) for R1. This supersedes the 2026-09-11 hold | 1 (P0) |
| DEC-03 | The six R1 EDU U1–U6 records are R1 EDU configurations. Release **only values Unitree states identically for every R1 edition or for the R1 family**: payload 2 kg, ROS 2, teleoperation. Weight (27 vs 29 kg by column), DoF (a range) and arm span stay UNKNOWN | 18 (6 P0) |
| DEC-04 | `softbank-nao` is NAO6, and NAO6 documentation published by Maxtronics/Aldebaran counts as first-party. The manufacturer of record does not change | 11 (3 P0) |
| DEC-05 | `honda-asimo` is the **2005 New ASIMO**: Honda's 2005 release states 130 cm and 54 kg, matching the record. Releases DoF 34 and walking 2.7 km/h. The 2004-only runtime and the 2011 values are not used | 2 (2 P0) |
| DEC-06 | `xpeng-iron` is the Next-Gen IRON (the record's DoF 76/21 matches XPENG's Sept 2026 release). Releases mobility, manipulation, conversation and dexterous hand, with no hand DoF (first-party sources say 21 vs 22). Kepler, Sophia, Apollo and Atlas items stay held | 4 |
| DEC-11 (D9) | Multi-mode runtime: take the walking-mode figure, with the qualifier in a caveat (A2 Ultra "Walking: 1.5h+" → 90 min) | 1 (P0) |
| DEC-07 (D5) | `hand_type` = the standard shipped end effector only (GR-2: basic dexterous hand); optional hands are not used | 1 |
| DEC-02 | `developer_edition` = true only where the manufacturer describes the record itself as a developer or research platform (Booster T1 "development platform for developers", REEM-C "a research platform") | 2 |
| DEC-01, 08, 09, 10, 12, 14 | Keep strict (UNKNOWN): marketing autonomy wording, speech-only language claims, V×Ah arithmetic, non-standard "arm span"/segment labels, negatives outside the DR-G4 §4.3 chain, and the A2 Ultra EN/JP conflict | 0 |

**Alternatives worth an explicit choice** (they add cells but carry the stated risk):

| Alternative | Cells added | Risk |
|---|---|---|
| V×Ah → Wh for Booster T1/T2 and Galbot | 4 | arithmetic on nominal values |
| Autonomy levels for Atlas and Figure 03 | 2 | interpretive enum levels |
| Galbot wheeled speed and maximum height | 2 | not walking speed; height-adjustable robot |
| 4NE1 Mini "Speed Max." | 1 | no locomotion label |
| Full EDU-column propagation for R1 EDU weight | 4 | weight differs by column (27 vs 29 kg) |
| ASIMO 2011 generation | adds runtime 40 min | **changes** weight 54 → 48 |

## 2. Batch 5: the maximum clean batch that can follow the recommended rulings

`db/catalogue/ho_data_30_batch5_expected.json`: **40 values on 14 robots**, each filled from NULL. Each caveat names its
decision ID and quotes the manufacturer.

The JSON in this PR already carries the values. **Merging and importing require ratification of the listed decisions
plus approval of this exact batch.** If any decision is rejected, its cells are removed and the batch is regenerated
and re-rehearsed for a new exact approval.

| Decision | Robot | Field | Value | Source |
|---|---|---|---|---|
| DEC-02 | booster-t1 | developer_edition | True | https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/overview/ |
| DEC-02 | pal-reem-c | developer_edition | True | https://pal-robotics.com/robot/reem-c/ |
| DEC-03 | unitree-r1-edu-u1 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u1 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u1 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-03 | unitree-r1-edu-u2 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u2 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u2 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-03 | unitree-r1-edu-u3 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u3 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u3 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-03 | unitree-r1-edu-u4 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u4 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u4 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-03 | unitree-r1-edu-u5 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u5 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u5 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-03 | unitree-r1-edu-u6 | has_teleoperation | True | https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/main/README.md |
| DEC-03 | unitree-r1-edu-u6 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |
| DEC-03 | unitree-r1-edu-u6 | ros_support | True | https://doc-cdn.unitree.com/27/1164/en/27_1164_en |
| DEC-04 | softbank-nao | battery_wh | 62.5 | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | degrees_of_freedom | 25 | https://maxtronics.com/en/nao6/ |
| DEC-04 | softbank-nao | has_api | True | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | has_language_ui | True | https://maxtronics.com/en/nao-robot-user-guide/ |
| DEC-04 | softbank-nao | has_sdk | True | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | has_vision | True | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | height_cm | 57.4 | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | mobility | BIPEDAL | https://maxtronics.com/wp-content/uploads/nao6_userguide_en_maxtronic_web-1-1.pdf |
| DEC-04 | softbank-nao | ros_support | True | http://doc.aldebaran.com/2-5/dev/ros/index_ros.html |
| DEC-04 | softbank-nao | simulation_support | True | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-04 | softbank-nao | weight_kg | 5.48 | https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf |
| DEC-05 | honda-asimo | degrees_of_freedom | 34 | https://global.honda/en/newsroom/news/2005/c051213-asimo-eng.html |
| DEC-05 | honda-asimo | walk_speed_ms | 0.75 | https://global.honda/en/newsroom/news/2005/c051213-asimo-eng.html |
| DEC-06 | xpeng-iron | hand_type | Dexterous hand | https://www.xpeng.com/technology/ai_robot_iron |
| DEC-06 | xpeng-iron | has_language_ui | True | https://www.xpeng.com/news/019a56f54fe99a2a0a8d8a0282e402b7 |
| DEC-06 | xpeng-iron | has_manipulation | True | https://www.xpeng.com/technology/ai_robot_iron |
| DEC-06 | xpeng-iron | mobility | BIPEDAL | https://www.xpeng.com/technology/ai_robot_iron |
| DEC-07 | fourier-intelligence-gr-2 | hand_type | Basic dexterous hand | https://www.fftai.com/pdf/en/gr2.pdf |
| DEC-11/D9 | agibot-a2-ultra | runtime_minutes | 90 | https://www.agibot.com/products/A2_Ultra |
| DEC-13 | unitree-r1 | payload_kg | 2.0 | https://doc-cdn.unitree.com/27/1135/en/27_1135_en |

**Rehearsal 2026-10-23** (Neon branch from production, deleted after use):
- run 1: 14 robot rows updated; run 2: no-op;
- `import_preflight.py`: PASS (14 business changes, 0 unexplained);
- `import_identity_check.py`: PASS (TOUCHED = 14, 0 ADDED, 0 ID changes, dangling 25);
- `validate_catalogue.py`: G2 and MEDIA-01 OK;
- column diff: exactly the 40 cells, all NULL → value.

**Projected: core UNKNOWN 486/946 = 51.4%; P0 88/258 = 34.1%.**

## 3. Outreach wave 1 (drafts, not sent)

`ho-data-30/outreach-wave1/` covers Unitree, Booster, UBTECH, 1X, Aldebaran/SoftBank (Pepper) with Maxtronics (NAO6),
and PAL.

**Refinements over the Phase 2 drafts:**
- one table per robot edition;
- a precise definition for every field: rated walking speed (not peak), fingertip arm span, per-arm payload, Wh of the
  standard pack, and the standard (not optional) end effector;
- the public text already found, quoted where it falls short;
- edition-mapping questions (Unitree U-configurations, Pepper hardware version);
- explicit source requirements: a company address or a public document on the manufacturer's domain, naming the
  product and edition, and dated.

Cells released by batch 5 and rule-only fields are not asked.

| Manufacturer | Cells | P0 |
|---|---|---|
| Unitree | 61 | 13 |
| Booster | 42 | 6 |
| UBTECH | 31 | 9 |
| 1X | 21 | 4 |
| Aldebaran/SoftBank + Maxtronics | 18 | 7 |
| PAL | 15 | 1 |
| **Wave 1** | **188** | **40** |

## 4. Feasibility of ≤ 33.4% (recalculated)

The answerable pool is every UNKNOWN cell that a direct manufacturer statement could close: **363 cells** across 22
manufacturers. It consists of:
- 262 source-silent or blocked cells;
- 101 held cells whose only blocker is the form of the public statement (Wh not stated, a non-standard span label, an
  optional hand, an unlabelled speed, and so on).

Rule-only fields (autonomy, developer edition), identity-blocked values and released cells are excluded.

| Starting point | Core UNKNOWN | Still needed for ≤ 316 | Required usable answers from the 363-cell pool | Wave 1 (188 cells) alone |
|---|---|---|---|---|
| Today | 526 (55.6%) | 210 | 57.9% | insufficient (210 > 188) |
| After batch 5 (recommended rulings) | 486 (51.4%) | **170** | **46.8%** | would need 90.4% |
| After batch 5 + every alternative ruling | 459 (48.5%) | 143 | 40.5% (of 353) | would need 76.1% |

**Conclusion:** ≤ 33.4% is reachable only with all three of:
1. the recommended rulings (batch 5);
2. outreach to essentially every manufacturer: wave 1 plus a wave 2 covering 175 cells (Figure, Rainbow, NEURA, a Tesla
   capture, XPENG, Apptronik, Hanson, Agility, Sanctuary, Boston Dynamics, Galbot, Honda, Engineered Arts, Kepler,
   AgiBot, Fourier);
3. usable answers for at least ~47% of all requested cells (about 170 cells).

Unsolicited specification requests are usually answered at far lower rates. Unless several large manufacturers answer
in full, the realistic outcome stays about 38–45%. No value will be estimated to close the gap.
