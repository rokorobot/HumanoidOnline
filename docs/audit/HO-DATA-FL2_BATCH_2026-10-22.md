# HO-DATA Fast Lane — Batch 2: evidence package (2026-10-22)

**Status:** PROPOSED. Not approved, merged or imported. Approval of this exact batch covers merge, rehearsal, scoped
production import and verification (`docs/decisions/DR-D1_HO_DATA_FAST_LANE_AND_STANDING_RESEARCH_AUTHORIZATION.md` §2).

**Research basis:** standing work order `HO-DATA-STANDING 2026-10-22` (DR-D1 §1), manufacturer sources only,
read-only. Every value below was seen in the raw retrieved body (curl or Python urllib) and not taken from a
summarizing tool. WebSearch results were used only to locate first-party URLs. No login, block or access control was
bypassed. Nothing was written to production or to any discovery source.

**Baseline:** production after batch 1 (`6a725da`): P0 UNKNOWN 107/258 = 41.5%; core UNKNOWN 607/946 = 64.2%.

## 1. Clean batch (proposed for import)

Three published robot records; each value is filled from NULL. `spec_caveats` quote the manufacturer, and
`specs_note` carries the SPECIFICATIONS and RETRIEVAL statements.

| Robot (edition) | Field | Tier | Current | Proposed | Verbatim source text | Source (sha256 prefix) |
|---|---|---|---|---|---|---|
| `1x-neo` (NEO) | walk_speed_ms | P0 | UNKNOWN | 1.4 | `Walking speed 1.4 m/s` (beside `Max run speed 6.2 m/s`) | https://www.1x.tech/neo (721f1a7a63b54c93) |
| `1x-neo` (NEO) | battery_wh | P1 | UNKNOWN | 842 | `Battery Capacity 842 Wh` | same |
| `pal-talos` (TALOS) | degrees_of_freedom | P0 | UNKNOWN | 32 | `32 DEGREES OF FREEDOM (DoF)`: legs 6 (x2), arms 7 (x2), gripper 1 (x2), waist 2, neck 2 | PAL datasheet https://pal-robotics.com/wp-content/uploads/2025/09/TALOS-DataSheet-1.pdf (7e32fb98db39e48b), linked from https://pal-robotics.com/robot/talos/ |
| `pal-talos` (TALOS) | battery_wh | P1 | UNKNOWN | 1080 | `Nominal energy 1080 Wh` | same datasheet |
| `engineered-arts-ameca` (Ameca, generation 2.6) | weight_kg | P0 | UNKNOWN | 62 | `"model":"Ameca" … "generation":"2.6 (2024)" … "weight":"137.7 lbs \| 62 kg"` | Engineered Arts site asset https://www.engineeredarts.com/assets/index-DwBa69-D.js (e33505fc9f503e50), which serves the spec table of https://www.engineeredarts.com/robot/ameca/ |
| `engineered-arts-ameca` | degrees_of_freedom | P0 | UNKNOWN | 61 | `"totalDoF":"61 Degrees of Freedom (DoF)"`. Confirmed by the user docs: `Ameca … has 61 degrees of freedom` (27 face, 5 neck, 8 shoulders, 10 arms, 8 hands, 3 torso) | same asset; https://docs.engineeredarts.co.uk/guide/reference/hardware/mesmer_full_size_gen2 (d77e5143e202f7fe) |
| `engineered-arts-ameca` | arm_span_cm | P1 | UNKNOWN | 180 | `"armSpan":"70.9 in \| 1800 mm"` (unit conversion mm→cm) | same asset |

**Consistency checks against existing values.** TALOS datasheet height 175 cm, weight 95 kg, payload 6 kg and
"1.5h walking" all match the record. Ameca's `1870 mm` matches the owner-ratified 187 cm. The NEO page is the same
body as the HO-DATA-02C capture.

**Edition notes.**
- The Ameca values are stated for the current generation 2.6 (2024). The record is the single Ameca product record,
  and the caveat names the generation.
- TALOS has one edition.
- NEO is the single published NEO record.

**Expected production change** (`db/catalogue/ho_data_fast_lane_batch2_expected.json`): `import_catalogue.py --only
1x-neo --only pal-talos --only engineered-arts-ameca` → 3 robot rows CHANGED. No other table changes.

**Rehearsal (2026-10-22, Neon branch from production at LSN 0/F43B4A0, deleted after use):**
- run 1: robot 3 updated, everything else unchanged; run 2: no-op;
- `import_preflight.py` with the manifest: PASS (3 business changes, 0 unexplained);
- `import_identity_check.py`: PASS (TOUCHED = only the 3 robots, 0 ID_CHANGED, dangling audit targets 25);
- `validate_catalogue.py`: G2 and MEDIA-01 OK;
- column diff: exactly the 7 values above, plus `spec_caveats`.

**Projected completeness:** P0 UNKNOWN 107 → **103/258 = 39.9%** (measured on the rehearsal branch). Core UNKNOWN
607 → **600/946 = 63.4%**.

## 2. Held for owner decision (not in the clean batch)

### 2.1 Identity and edition

| Record | Finding | Decision needed | Yield if decided |
|---|---|---|---|
| `honda-asimo` | Honda publishes several generations, each with different specifications. The record's 130 cm / 54 kg matches the **2004** "next-generation" ASIMO and the **2005** New ASIMO. 2004 release: `Normal walking speed: 2.5km/h`, `Continuous operating time: 1hour`, `Total 34 degrees of freedom` (global.honda/en/newsroom/news/2004/c041215-asimo-eng.html, e2f04a47c03e4da7). 2005 release: `Normal walking speed: 2.7km/hour`, `Height: 130cm`, `Weight: 54kg`, `Total 34 degrees of freedom` (…/2005/c051213-asimo-eng.html, eb1d0a169ec2c86e). Honda's current **About ASIMO** page states the final (November 2011) model: `Height 130 cm`, `Weight 48 kg (decreased 6 kg from previous model)`, `Maximum speed 9 km/hour`, `Operating time 40 minutes (walking)`, `Total 57 degrees of freedom` (global.honda/en/ASIMO/about/, 90a6c5d467c81a64). | Which generation does the record represent? (a) 2005: DoF 34 and walk 0.75 m/s (2.7 km/h); the 2005 release states no runtime, and the 2004 one-hour figure belongs to the previous model. (b) 2011 final model: DoF 57 and runtime 40 min, and weight would change 54 → 48, a correction of an existing value. 2011 states only a maximum (running) speed, which falls under D2. | 2–3 P0 |
| `softbank-pepper`, `softbank-nao` | Aldebaran knowledge-base URLs now redirect to maxtronics.com. The Pepper technical-specifications article redirects to a marketing page with no specifications. | 02B §7.2(a) identity / manufacturer of record. Pepper specs need a reachable first-party page. | up to 12 P0 |
| `apptronik-apollo` | apptronik.com/apollo returns 404; the live product is Apollo 2 (02C). | Is the record Apollo or Apollo 2? | 2 P0 |
| `xpeng-iron`, `rainbow-hubo`, `unitree-r1-edu-u1…u6` | Unchanged from 02B §7.2: generation, originating-lab (D11) and distributor-edition (D6) questions. | As in 02B. | — |

### 2.2 Depends on an unapproved policy (D1–D12) or a first-party conflict

| Record | Field | Stated | Policy |
|---|---|---|---|
| `galbot-g1` | height_cm / walk_speed_ms | `整机高度（最高）1730 mm`; `最大速度 1.5 m/s` (wheeled base) | D10 / D2 |
| `agibot-a2-ultra` | walk_speed_ms, payload_kg | EN `Max 1.2m/s`, `≈2kg` vs JP `最大0.8m/s`, `約3kg` | first-party conflict |
| `agibot-a2-ultra` | runtime_minutes | `Standing : 3h, Walking : 1.5h+` | D9 |
| `4ne1-mini` | walk_speed_ms | `Speed Max. 4.6 km/h` with no locomotion label | D2 |
| `booster-t2-*` | payload_kg | posture-dependent combined arm payload | D3 |
| `unitree-r1` | payload_kg | `Maximum Torque of Arm Joint【1】 About 2kg` | D12 + D3 |
| `1x-neo` | degrees_of_freedom | per-part rows only (hands 22×2, arms 7×2, neck 3, spine 2, legs 6×2), no total | D1 (no summing) |
| `unitree-h1` | degrees_of_freedom | per-limb only | D1 |

### 2.3 Not applicable (owner question: count as N/A or keep in the denominator?)

The HO-DATA-02A rule keeps every cell in the denominator, so these cells stay UNKNOWN in the metric.

| Record | Field | Reason |
|---|---|---|
| `engineered-arts-ameca` | walk_speed_ms | Ameca does not walk (record mobility STATIONARY) |
| `engineered-arts-ameca` | runtime_minutes | mains "Robot Power Supply"; no battery is stated |

## 3. Checked and not stated (2026-10-22, documents named)

| Record | Fields | Documents read |
|---|---|---|
| `unitree-h1` | payload, runtime, total DoF | unitree.com/h1 (only `Battery capacity: 864Wh`, `Moving speed of 3.3m/s`) |
| `booster-k1-*` ×3 | payload | booster.tech/booster-k1 (DoF 22, `walking speeds of up to 2 m/s`, `up to 70 minutes of walking runtime`; no load figure) |
| `pal-talos` | walk_speed_ms | product page and datasheet |
| `boston-dynamics-atlas-electric` | walk_speed_ms | bostondynamics.com/products/atlas/ and the 2026 launch post (states `Battery Life 4 hours`, 50/30 kg capacities, 56 DoF; no speed) |
| `engineered-arts-ameca` | payload | site spec table and user docs |

## 4. Source unavailable

| Record | Fields | What happened |
|---|---|---|
| `figure-02` | 6 P0 | figure.ai/figure-02 returns 404; archive use is not authorized (DR-D1 §1) |
| `unitree-*` walk speed ×11 | walk_speed_ms | support.unitree.com returns a 768-byte script shell. Search shows the official G1 manual is image-only. A distributor copy states about 2 m/s, but third-party copies are excluded. |
| `hanson-sophia` | 3 P0 | hansonrobotics.com/sophia/ returns a 1 KB shell with no specifications |
| `1x-eve` | 4 P0 | 1x.tech/eve has no specification fields in its page data |
| `softbank-pepper` | 6 P0 | see §2.1 |

## 5. Path to P0 < 30% (≤ 77 UNKNOWN)

After this batch, 103 remain, so 26 more are needed. The largest blocks are owner decisions, not research:

- the Unitree walk speed ×11, which needs a first-party manual route or a third-party-copy policy;
- Pepper/NAO identity (12);
- ASIMO generation (2–3);
- D2/D9/D10 rulings (about 4);
- Figure 02 archive use (6).

Research alone, within the standing scope, is unlikely to close the gap.
