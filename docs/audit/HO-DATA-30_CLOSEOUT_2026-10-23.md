# HO-DATA-30 — Close-out of all held cells (2026-10-23)

**Status:** PROPOSED. One owner approval covers:
- the final status of all 216 remaining held cells;
- batch 6;
- the NAO caveat attribution fix.

Nothing is merged or imported yet. It applies the owner rulings ratified on 2026-10-23 (DEC-02/03/04/05/06/07/11-D9/13;
DEC-01/08/09/10/12/14 strict). It makes **no new ruling and no new research**.

**Why:** the held evidence should not be collected again and again. After this PR, every held cell has a final status:
- **PUBLISH:** the value goes to production in batch 6;
- **CLOSED-UNKNOWN:** the cell stays UNKNOWN, and the reason is recorded once in the register.

A closed cell is **not researched again**. It reopens only on:
- a new first-party manufacturer statement for that edition (for example, a reply to the outreach requests), or
- an owner change of the cited ruling.

Register: `ho-data-30/closeout_register.csv`. It lists every cell with its final status, basis, route, the value it
would get if the ruling were reversed, its reopen condition, and its source and sha256.

## 1. Result

| Final status | Cells |
|---|---|
| **PUBLISH** (batch 6) | **7** |
| **CLOSED-UNKNOWN** | **209** |
| of which routed to a separate governed process | 7 (4 XPENG IRON → G3 claim pipeline; 3 explicit `has_sdk=false` → DR-G4 §4.3 negative chain) |
| **Total held cells** | **216** |

Production after batch 6: **483 / 946 = 51.1%** core UNKNOWN (from 490); **P0 87/258 = 33.7%**; P1 396/688. The 3
NOT_APPLICABLE cells stay in the denominator and are reported separately.

## 2. Batch 6: values released by rulings already ratified

`db/catalogue/ho_data_30_batch6_expected.json`: **7 values on 5 robots**, each filled from NULL.

| Robot | Field | Value | Ruling | First-party evidence |
|---|---|---|---|---|
| honda-asimo | has_vision | true | DEC-05 (2005 New ASIMO) | 2005 release: "recognize the surrounding environment through its visual sensors" |
| honda-asimo | has_manipulation | true | DEC-05 | 2005 release: "A new function to carry objects using a cart was also added"; "ASIMO passing tray" |
| softbank-nao | hand_dof | 1 | DEC-04 + DEC-07 | NAO6 datasheet DoF table: Hand 1 (in each), consistent with the total of 25 |
| softbank-nao | runtime_minutes (P0) | 60 | DEC-04 + DEC-11/D9 | NAO6 datasheet: "60 min (Active use) 90 min (Normal use)"; 90 min stays in the caveat |
| pal-talos | hand_dof | 1 | DEC-07 | TALOS datasheet DoF table: Gripper 1 (x2); "3 fingers, 1 actuator" |
| softbank-pepper | hand_dof | 1 | DEC-07 | Pepper joint list: "LHand Left hand Open and Close" (one joint per hand) |
| fourier-intelligence-gr-2 | hand_dof | 6 | DEC-07 | GR-2 brochure table: "Basic Dexterous Hand 6 / Enhanced Dexterous Hand (Optional) 12" (read from the rendered page) |

**NAO caveat attribution fix (text only, same robot row):**
- The 11 batch-5 caveats that began "SoftBank Robotics states" now begin "Maxtronics (NAO6 publisher) states".
- The ROS caveat begins "Aldebaran's NAOqi documentation states".
- No value changes. NAO weight stays **5.5 kg**: the schema stores one decimal (`NUMERIC(6,1)`), and the caveat quotes
  the datasheet's exact "5.48 kg". Storing two decimals would be a separate schema change.

**Rehearsal 2026-10-23** (Neon branch from production, deleted after use):
- run 1: 5 robot rows updated; run 2: no-op;
- `import_preflight.py`: PASS (5 business changes, 0 unexplained);
- `import_identity_check.py`: PASS (TOUCHED = 5, 0 ADDED, 0 ID changes, dangling 25);
- `validate_catalogue.py`: G2 and MEDIA-01 OK;
- column diff: exactly the 7 cells, all NULL → value, plus `spec_caveats`;
- XPENG IRON governance tests pass.

## 3. Closed cells by basis

| Closure basis | Cells | of which a value exists if the ruling were reversed | Examples |
|---|---|---|---|
| DEC-01 strict (autonomy wording not mapped) | 30 | 2 | boston-dynamics-atlas-electric autonomy=SUPERVISED_AUTONOMY; figure-03 autonomy=TASK_AUTONOMOUS |
| DEC-02 (only records that are themselves a developer/research platform) | 27 | 0 |  |
| DEC-10 strict (label is not fingertip span / shoulder-to-tip reach) | 24 | 12 | agibot-a2-ultra arm_span_cm=140.1; agility-digit reach_cm=167.6; fourier-intelligence-gr-2 reach_cm=152.0 |
| DEC-07 (standard end effector only) | 23 | 7 | booster-t2-education has_manipulation=True; booster-t2-professional has_manipulation=True; figure-03 has_manipulation=True |
| DEC-06 identity (Kepler K1/K2, Sophia/Sophia Utility, Apollo/Apollo 2, Digit/Digit 5, Atlas hand generation, Figure 02) | 22 | 9 | apptronik-apollo has_teleoperation=True; boston-dynamics-atlas-electric hand_dof=13; hanson-sophia has_api=True |
| DEC-12 strict (DR-G4 §4.3 negatives; base-edition scope) | 14 | 3 | unitree-g1 has_sdk=False; unitree-h2 has_sdk=False; unitree-r1 has_sdk=False |
| unsupported wording / internal use | 12 | 2 | hanson-sophia payload_kg=0.5; rainbow-hubo mobility=BIPEDAL |
| DR-G4 variant scope (4NE1 Mini Standard/Pro) | 9 | 5 | 4ne1-mini hand_dof=12; 4ne1-mini has_language_ui=True; 4ne1-mini has_sdk=True |
| DEC-08 strict (no spoken conversation stated) | 8 | 0 |  |
| DEC-09 strict (no V×Ah or DoF summing) | 7 | 4 | booster-t1 battery_wh=504.0; booster-t2-education battery_wh=480.0; booster-t2-professional battery_wh=480.0 |
| unsupported wording | 7 | 1 | pal-reem-c has_vision=True |
| DEC-03 (R1 EDU: family-invariant values only) | 5 | 4 | unitree-r1-edu-u3 weight_kg=29.0; unitree-r1-edu-u4 weight_kg=29.0; unitree-r1-edu-u5 weight_kg=29.0 |
| DEC-05 (2005 New ASIMO) — value belongs to another generation or is unstated for 2005 | 4 | 3 | honda-asimo hand_dof=13; honda-asimo hand_type=multi-fingered hand with tac; honda-asimo runtime_minutes=40 |
| XPENG IRON governance pin (owner decisions 2026-10-03) | 4 | 4 | xpeng-iron hand_type=Dexterous hand (22-DoF per p; xpeng-iron has_language_ui=True; xpeng-iron has_manipulation=True |
| unsupported | 4 | 3 | 1x-neo degrees_of_freedom=75; agility-digit runtime_minutes=90; figure-02 battery_wh=2300 |
| DEC-11 (numeric policy) | 3 | 1 | ubtech-walker-s2 payload_kg=15 |
| D2 (not a walking speed) | 2 | 2 | 4ne1-mini walk_speed_ms=1.28; galbot-g1 walk_speed_ms=1.5 |
| DEC-14 strict (first-party EN/JP conflict) | 2 | 0 |  |
| D10 (height-adjustable) | 1 | 1 | galbot-g1 height_cm=173.0 |
| DEC-04 (NAO6) — evidence insufficient | 1 | 1 | softbank-nao has_manipulation=True |
| **Total CLOSED-UNKNOWN** | **209** | **64** | |

**Choosing to reverse a ruling:** 64 closed cells carry a value that a different ruling would publish. Each is listed
with its value in the register's `value_if_ruling_reversed` column. Reversing a ruling is a new owner decision and would
produce a new exact batch. The largest groups, and why they were not published:
- **Unitree "Arm Span ≈ 0.45 m":** physically not a fingertip span.
- **V×Ah energy:** arithmetic on nominal ratings.
- **Kepler K2 values on a record with K1 height and weight:** an identity error, not a data gap.
- **Sophia hand values from a CAD design repository:** a design file, not a product specification.

## 4. What remains to raise completeness

- **Manufacturer answers** are now the main route. Outreach wave 1 (`ho-data-30/outreach-wave1/`, 188 cells, not sent)
  includes several closed cells, because a direct manufacturer statement is their reopen condition.
- **Feasibility after batch 6:** ≤ 33.4% needs 167 more values, about 46% usable answers across the 363-cell answerable
  pool (wave 1 + wave 2).
- **XPENG IRON (4 cells):** eligible for promotion through the G3 claim pipeline; separate owner act.
