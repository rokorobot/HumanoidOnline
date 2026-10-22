# HO-DATA-30 — Catalogue Completeness Acceleration: feasibility, execution plan and batch 3 (2026-10-22)

**Status:**
- **Feasibility plan:** delivered.
- **Batch 3:** PROPOSED, not approved, merged or imported.
- **Decisions:** no publication, identity ruling, semantic-policy approval, source activation or production mutation is made here.

**Research basis:** standing work order `HO-DATA-STANDING 2026-10-22` (DR-D1), manufacturer sources only, read-only.

**Method:**
- Five parallel research agents covered all 43 published records and all 600 UNKNOWN cells, under one brief (`ho-data-30/research_brief.md`).
- Each agent saved the raw bodies it relied on.
- The orchestrator re-checked every proposed value against those saved bodies with a script (verbatim present, sha256 recorded) and then reviewed each one against the catalogue's governance (DR-G4, DR-C1, earlier owner decisions).

**Artefacts in `ho-data-30/`:**
- `cell_classification.csv`: all 600 cells, with class, proposed value, source URL, sha256 and verbatim.
- `retrieval_log.md`: every URL, its outcome and file hash.
- `research_brief.md`.

## 1. Verdict

**The −30 pp target (≤ 33.4%, i.e. ≥ 284 more known cells) is not achievable from the manufacturer evidence that
exists publicly today, even if every pending owner decision went the catalogue's way.**

| Scenario | Additional known cells | Core UNKNOWN |
|---|---|---|
| Today (production, `31916dd`) | — | 600 / 946 = **63.4%** |
| **Batch 3 (this PR, ready)** | **54** | 546 / 946 = **57.7%** |
| Realistic, after owner decisions on the held items (§5) | about 175–210 | about 390–425 = **41–45%** |
| Theoretical upper bound: every evidence-backed held cell becomes a known value | 54 + 222 = 276 | 324 / 946 = **34.2%** |
| Target | 284 | ≤ 316 = **33.4%** |

The theoretical bound still misses the target by 8 cells, and it assumes:
- every identity ruling, every proposed policy (D1–D12) and two new mapping rules (autonomy, developer_edition) are approved as proposed;
- every held value survives review.

The realistic shortfall is about **75–110 cells**. Almost all of them sit in fields that manufacturers do not
publish (§4, SOURCE_SILENT = 291). Closing that gap needs new evidence routes (§6), not more searching of the same
pages.

## 2. Phase 1 — catalogue-wide recovery assessment

**Matrix.**
- Recomputed from catalogue JSON at `31916dd` and from production (`robot` table, published rows): 43 robots × 22 core fields = 946 cells, **600 UNKNOWN**.
- JSON and production agree cell for cell (0 null mismatches).
- P0: 103/258 = 39.9%. P1 (16 fields): 497/688 = 72.2%.

**Booleans.** The 9 Boolean fields hold exactly **262** UNKNOWN cells, the same count as HO-DATA-02A. The held claims in
production (`candidate_claim`, `discovery_claim_proposal`) are all dated before 02A, which already mapped them.

**Classification of all 600 cells** (after research and orchestrator review):

| Class | Meaning | P0 | P1 Boolean | P1 other | Total |
|---|---|---|---|---|---|
| EVIDENCE_AVAILABLE | clean first-party evidence, in batch 3 | 0 | 45 | 9 | **54** |
| POLICY_BLOCKED | evidence exists; a semantic rule is needed (D1–D12, autonomy/developer_edition mapping, DR-G4 negatives) | 11 | 78 | 67 | **156** |
| IDENTITY_BLOCKED | evidence exists for a different or undecided edition, generation or manufacturer of record | 22 | 27 | 19 | **68** |
| CONFLICTING | first-party sources disagree, or the value contradicts existing record values | 3 | 1 | 0 | **4** |
| BLOCKED_BY_DRIFT | clean, but the scoped import would also carry known unreviewed JSON-vs-production drift (preflight STOP) | 0 | 5 | 0 | **5** |
| SOURCE_UNCONFIRMED | the host is not proven to be the manufacturer's | 0 | 2 | 0 | **2** |
| SOURCE_SILENT | the first-party documents read do not state the field (documents named per cell) | 61 | 97 | 133 | **291** |
| SOURCE_UNAVAILABLE | blocked (Tesla: HTTP 403 on every tesla.com path; not bypassed) | 4 | 7 | 6 | **17** |
| NOT_APPLICABLE | the manufacturer's own description makes the field inapplicable (Ameca: does not walk; mains-powered) | 2 | 0 | 1 | **3** |
| NOT_RESEARCHED | — | 0 | 0 | 0 | **0** |

Of the 235 held cells (POLICY, IDENTITY, CONFLICTING, DRIFT, UNCONFIRMED), **222 carry a first-party quote**. Thirty-one of
those are P0.

## 3. Batch 3 — the largest justified clean batch

**Scope:** 54 values on 17 published robots, each filled from NULL. No P0 cell qualified: every P0 candidate was
identity-, policy- or conflict-blocked (§5).

**Mapping rules applied** (part of what the owner approves):
- A Boolean is set `true` only where the manufacturer states the capability **in words** for this product:
  - has_vision: cameras or vision sensors;
  - has_manipulation: grasping or manipulation;
  - has_sdk: an SDK;
  - has_api: a programming API;
  - ros_support: ROS/ROS 2;
  - simulation_support: an official simulation model or support (URDF/MJCF, Isaac, MuJoCo, Gazebo);
  - has_teleoperation: teleoperation or operator remote control, including a manufacturer handheld controller or VR kit, recorded in the caveat;
  - has_language_ui: spoken or natural-language conversation stated in words, not just a microphone or "LLM support".
- **No `false` is written.** Explicit negatives (Unitree "Only the EDU version supports secondary development") follow the DR-G4 §4.3 chain and are held.
- mobility is set only from a stated locomotion type. hand_type only from a named standard end effector. Numeric fields only as stated, or by pure unit conversion.

**Expected production change:** `import_catalogue.py` scoped to the 17 slugs in
`db/catalogue/ho_data_30_batch3_expected.json` → **17 robot rows CHANGED**, nothing else.

**Rehearsal 2026-10-22** (Neon branch from production, deleted after use):
- run 1: robot 17 updated; run 2: no-op;
- `import_preflight.py` with the manifest: PASS (17 business changes, 0 unexplained);
- `import_identity_check.py`: PASS (TOUCHED = the 17 robots, 0 ID_CHANGED, 0 ADDED, dangling audit targets 25);
- `validate_catalogue.py`: G2 and MEDIA-01 OK;
- column diff: exactly the 54 intended cells changed, all NULL → value, plus `spec_caveats`/`updated_at`.

The first two rehearsals, which still included `unitree-h1` and `unitree-h2-edu`, were **stopped by preflight**:
- importing `unitree-h1` would add 2 shop evidence rows from the 2026-09-26 freshness pass;
- importing `unitree-h2-edu` would rewrite the alza-cz provider description.

Both are known drift that needs its own review. Those robots' 5 clean cells are therefore held as BLOCKED_BY_DRIFT.

**Projected after batch 3:** core UNKNOWN 546/946 = **57.7%** (−5.7 pp); P0 103/258 = 39.9% (unchanged); P1
443/688 = **64.4%** (from 72.2%).

| Robot | Field | Proposed | Verbatim (first-party) | Source |
|---|---|---|---|---|
| agibot-a2-ultra | hand_dof | 6 | Single Hand DOF 6-DOF Dexterous Hand | https://www.agibot.com/products/A2_Ultra |
| agibot-a2-ultra | hand_type | 6-DoF dexterous hand | Single Hand DOF 6-DOF Dexterous Hand | https://www.agibot.com/products/A2_Ultra |
| agibot-a2-ultra | has_api | True | we provide two forms of relatively simple and general interfaces for secondary development: HTTP JSON RPC a… | https://open.agibot.com/docs/en/aimdk/a2/v2_1/dev_guide/03-second_develop_interface_overview |
| agibot-a2-ultra | has_language_ui | True | 物体認識,バイリンガル対話,レスポンスがいい. | https://www.agibot.com/jp/products/A2_Ultra |
| agibot-a2-ultra | has_manipulation | True | Dexterous Hand Delivery Capability Grasping weight (palm down): <3kg | https://open.agibot.com/docs/en/aimdk/a2/v2_1/dev_guide/01-a2_overview |
| agibot-a2-ultra | has_sdk | True | Released the A2 Ultra Development Guide (v2.1)  /  AimDK-A2-Ultra-V2.1-0603 | https://open.agibot.com/docs/en/aimdk/a2/v2_1/dev_guide |
| agibot-a2-ultra | has_teleoperation | True | VR Teleoperation Kit  /  (Compatible only with AGIBOT A2 Ultra and AGIBOT A2 Lite)  /  Real-time Motion Map… | https://www.agibot.com/products/VR |
| agibot-a2-ultra | has_vision | True | RGB-D Camera Equipped | https://www.agibot.com/products/A2_Ultra |
| agibot-a2-ultra | mobility | BIPEDAL | Anthropomorphic walking | https://www.agibot.com/products/A2_Ultra |
| agibot-a2-ultra | ros_support | True | The machine defaults to ROS2 Humble with Fastdds | https://open.agibot.com/docs/en/aimdk/a2/v2_1/dev_guide/03-second_develop_interface_overview |
| agibot-a2-ultra | simulation_support | True | We provide a mujoco-based simulation system for the A2 robot | https://open.agibot.com/docs/en/aimdk/a2/v2_1/dev_guide/08-motion_control_simulation |
| booster-k1-educational | has_teleoperation | True | Handheld remote controller: Available  /  Handheld Controller. Responsive and easy to use. Use the thumbsti… | https://www.booster.tech/booster-k1 |
| booster-k1-geek | has_teleoperation | True | Handheld remote controller: Available  /  Handheld Controller. Responsive and easy to use. Use the thumbsti… | https://www.booster.tech/booster-k1 |
| booster-k1-professional | has_teleoperation | True | Handheld remote controller: Available  /  Handheld Controller. Responsive and easy to use. Use the thumbsti… | https://www.booster.tech/booster-k1 |
| booster-t1 | has_api | True | 并下发模式切换、速度控制、关节控制、动作、轨迹和音频播放等指令 | https://docs.booster.tech/zh-CN/docs/developer-guide/booster-os-python-sdk/sdk-overview/ |
| booster-t1 | has_language_ui | True | Hi Chat ：支持语音对话 | https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/overview/ |
| booster-t1 | has_sdk | True | 机型 Booster K1 / T1 / T2 | https://docs.booster.tech/zh-CN/docs/developer-guide/booster-os-python-sdk/sdk-overview/ |
| booster-t1 | has_teleoperation | True | 开机后等待约 1 分钟，机器人播放提示音，即可被遥控。 | https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/quick-start/ |
| booster-t1 | has_vision | True | 深度相机、麦克风阵列、扬声器都在头部。 | https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/overview/ |
| booster-t1 | mobility | BIPEDAL | 单侧腿（6 个自由度）  /  全向行走 ：支持前向、后向、侧向行走，以及旋转和复合行走。 | https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/overview/ |
| booster-t1 | ros_support | True | ROS 2 节点与 Booster Robotics SDK 应用可以和 Booster 系统服务 互通 | https://docs.booster.tech/zh-CN/docs/developer-guide/cpp/sdk-overview/ |
| booster-t1 | simulation_support | True | T1 (23 DoF)  /  23 自由度布局：头部 2、双臂各 4、腰部 1、双腿各 6 个关节。  /  robots/T1/T1_23dof.urdf | https://docs.booster.tech/zh-CN/docs/developer-guide/open-source/booster-assets/ |
| booster-t2-education | has_language_ui | True | Hi Chat 语音交互 智能对话交互 Agent，可灵活切换多种趣味人设 | https://docs.booster.tech/zh-CN/docs/product-manual/t2/getting-started/overview/ |
| booster-t2-education | has_teleoperation | True | Handheld Remote Controller: Available | https://www.booster.tech/booster-t2 |
| booster-t2-professional | has_language_ui | True | Hi Chat 语音交互 智能对话交互 Agent，可灵活切换多种趣味人设 | https://docs.booster.tech/zh-CN/docs/product-manual/t2/getting-started/overview/ |
| booster-t2-professional | has_teleoperation | True | Handheld Remote Controller: Available | https://www.booster.tech/booster-t2 |
| boston-dynamics-atlas-electric | has_teleoperation | True | The robot can be controlled in three different ways: autonomous mode, teleoperated, or by using a tablet st… | https://bostondynamics.com/blog/boston-dynamics-unveils-new-atlas-robot-to-revolutionize-industry/ |
| boston-dynamics-atlas-electric | has_vision | True | Tactile and 360° camera view | https://bostondynamics.com/products/atlas/ |
| engineered-arts-ameca | hand_dof | 4 | 8 degrees of freedom in the hands, 4 left, 4 right | https://docs.engineeredarts.co.uk/guide/reference/hardware/mesmer_full_size_gen2 |
| engineered-arts-ameca | has_api | True | "controlAPI":"REST, WebSocket, Python & Node.js SDKs" | https://engineeredarts.com/assets/index-DwBa69-D.js |
| engineered-arts-ameca | has_sdk | True | "controlAPI":"REST, WebSocket, Python & Node.js SDKs" | https://engineeredarts.com/assets/index-DwBa69-D.js |
| figure-03 | battery_wh | 2300 | 2.3 kWh enables 5 hours of run time at peak performance | https://www.figure.ai/news/f-03-battery-development |
| figure-03 | has_language_ui | True | To make it easier to communicate naturally with the robot, Figure 03 features an upgraded audio hardware sy… | https://www.figure.ai/news/introducing-figure-03 |
| figure-03 | has_vision | True | Figure 03 introduces a next-generation vision system engineered for high-frequency visuomotor control. Its … | https://www.figure.ai/news/introducing-figure-03 |
| fourier-intelligence-gr-2 | battery_wh | 950 | Battery Capacity ≈ 950 Wh | https://www.fftai.com/pdf/en/gr2.pdf |
| fourier-intelligence-gr-2 | has_api | True | through intuitive APIs | https://www.fftai.com/pdf/en/gr2.pdf |
| fourier-intelligence-gr-2 | has_manipulation | True | including torso rotation, grasping, walking, and getting up from the ground | https://www.fftai.com/pdf/en/gr2.pdf |
| fourier-intelligence-gr-2 | has_teleoperation | True | Teleoperation Real-time Remote Control Systems (Pico/VisionPro) | https://www.fftai.com/pdf/en/gr2.pdf |
| fourier-intelligence-gr-2 | has_vision | True | Camera Stereo Camera | https://www.fftai.com/pdf/en/gr2.pdf |
| fourier-intelligence-gr-2 | simulation_support | True | The platform supports frameworks such as NVIDIA Isaac Lab, ROS, and Mujoco. | https://www.fftai.com/pdf/en/gr2.pdf |
| galbot-g1 | has_language_ui | True | 对话自然流畅，动作精准配合 | https://www.galbot.com/g1 |
| galbot-g1 | has_manipulation | True | 快速准确地完成取货与交付  /  单臂 5 kg | https://www.galbot.com/g1 |
| galbot-g1 | has_vision | True | 头部 双目相机 ×1 | https://www.galbot.com/g1 |
| galbot-g1 | mobility | WHEELED | 底盘形式 4 轮全向移动底盘 | https://www.galbot.com/g1 |
| pal-reem-c | has_teleoperation | True | Speed your research with extra software: from Whole-Body Control to navigation, HRI skills or teleoperation. | https://pal-robotics.com/robot/reem-c/ |
| pal-reem-c | simulation_support | True | Simulation model available at: http:// wiki.ros.org/Robots/REEM-C | https://pal-robotics.com/robot/reem-c/ |
| pal-talos | has_teleoperation | True | Speed your research with extra software: from Whole-Body Control to navigation, HRI skills or teleoperation. | https://pal-robotics.com/robot/talos/ |
| pal-talos | has_vision | True | RGB 1280x720 at 30 fps | https://pal-robotics.com/wp-content/uploads/2025/09/TALOS-DataSheet-1.pdf |
| pal-talos | simulation_support | True | Gazebo simulation and URDF model | https://pal-robotics.com/wp-content/uploads/2025/09/TALOS-DataSheet-1.pdf |
| softbank-pepper | has_language_ui | True | starts making conversation | https://us.softbankrobotics.com/pepper |
| ubtech-walker-s2 | has_manipulation | True | achieving ground-reaching flexibility and extended-reach manipulation | https://www.ubtrobot.com/en/humanoid/products/WalkerS2 |
| ubtech-walker-s2 | has_vision | True | The pure RGB binocular stereo vision solution is built in Walker S2's head. | https://www.ubtrobot.com/en/humanoid/products/WalkerS2 |
| unitree-h2 | hand_type | Rubber hand (factory standard) | 1、How to remove the factory-standard rubber hand supplied with Model H2 \| Removal Instructions for Standar… | https://doc-cdn.unitree.com/25/1553/en/25_1553_en |
| unitree-h2 | simulation_support | True | URDF files for different versions of the H2 robot have been uploaded to Unitree's public GitHub repository. | https://doc-cdn.unitree.com/25/1264/en/25_1264_en |

## 4. Where the remaining UNKNOWNs sit

SOURCE_SILENT (291) by field: arm_span 32, reach 26, battery_wh 25, walk_speed 23, hand_dof 22, hand_type 19,
ros_support 18, has_api 15, simulation_support 14, payload 13, has_teleoperation 13, has_sdk 13, DoF 9, runtime 8, others ≤ 8.

These are the fields manufacturers rarely publish as text: arm span and reach, battery energy (often only V and Ah),
walking speed, hand detail, and the developer-interface flags of consumer or closed products.

## 5. Owner decisions that unlock evidence-backed cells (separate from batch 3)

| Decision | Evidence-backed cells | Examples |
|---|---|---|
| **autonomy mapping rule** (new) | 28 | Atlas "works autonomously with minimal supervision"; Figure 03 "all autonomously" |
| **Identity: R1 EDU U1–U6** (do Unitree's R1/R1 EDU statements apply to the distributor U editions?) | 29 | ROS 2, teleoperation, payload 2 kg, arm span, weight 29 kg |
| **D5 end effector / optional hands** | about 24 | T2, Galbot, GR-2 hand options; H2 EDU dexterous hand options |
| **developer_edition mapping rule** (new) | 19 | Unitree EDU editions; K1/T2 "Education/Professional" tiers |
| **Label semantics** (Unitree "Arm Span 0.45 m", arm-segment lengths as reach, GR-2 "Arm Reach 1520 mm") | 14 | G1, R1, GR-2, Galbot |
| **D4 language UI** | 12 | REEM-C "speaks over 30 languages", 4NE1 Mini "Natural Language Interaction" |
| **Identity: NAO** (SoftBank vs Maxtronics, NAO6) | 11 | height 57.4 cm, weight 5.48 kg, 25 DoF, 62.5 Wh, SDK/API |
| **D1 derivation** (V×Ah, per-part DoF sums) | 9 | T1 48 V × 10.5 Ah; NEO and H1 per-part DoF |
| **Identity: ASIMO generation** | 6 | 2004/2005: DoF 34, runtime 60 min, walk 2.5/2.7 km/h |
| **D9 runtime modes; D2 speed; D3 payload; D10 height** | 15 | A2 Ultra 1.5 h+ walking; Galbot 1.5 m/s wheeled; T2 dual-arm 10 kg; Galbot 1730 mm max |
| **Identity: XPENG generation, Kepler K1/K2 record, Sophia vs "Sophia Utility"** | 18 | IRON 82/22 vs 76/21 DoF; K2 52 DoF vs record's K1 height and weight |
| **DR-G4 §4.3 explicit negatives** (register "Only the EDU version supports secondary development" → has_sdk=false) | 3+ | H2, R1 (G1 conflicts with existing true flags) |
| **Earlier owner decisions to revisit** | 1+ | R1 payload: the owner held it UNKNOWN on 2026-09-11 over the mislabelled row; Unitree's R1 SDK guide now labels it "Max Arm Payload … Approx. 2kg" |
| **Drift reconciliation** (H1 shop evidence rows; alza-cz provider description) | 5 | H1 has_api and teleoperation; H2 EDU simulation, API and teleoperation |
| **A2 Ultra EN vs JP conflict** | 2 | speed 1.2 vs 0.8 m/s; arm load ≈2 vs 約3 kg |

The realistic range in §1 assumes that about 55–70% of these cells survive the owner's rulings.

## 6. Closing the shortfall: proposed routes (each needs an owner decision)

1. **Targeted manufacturer data requests.** A short standard request listing the exact UNKNOWN fields per edition,
   sent by the owner to the manufacturers with the most silent cells. The answers become owner-attributed evidence.

   | Manufacturer | Silent cells |
   |---|---|
   | Unitree | 33, plus walking speed for 11 records |
   | UBTECH | 32 |
   | Booster | 30 |
   | SoftBank/Aldebaran | 29 |
   | 1X | 22 |
   | Rainbow | 22 |
   | Figure | 21 |
   | Hanson | 11 |
   | Agility | 10 |
   | Apptronik | 10 |

   Expected yield: unknown. It is the only route to the arm span, reach, battery and hand fields.
2. **Image-only first-party spec tables.** UBTECH Walker S1/S2, Kepler K2 version sheet, AgiBot workspace and the
   Boston Dynamics spec sheet. These would need a policy for reading a manufacturer-hosted image or PDF, with a recorded
   capture.
3. **Owner capture for blocked hosts.** Tesla's site returns 403 to automated requests (17 cells); this needs a
   browser capture by the owner.
4. **Third-party copies of manufacturer documents.** The Unitree G1 manual and the UBTECH brochure exist only on
   reseller hosts. They would need a byte-identity and origin policy. The proposed default remains no.
5. **Applicability ruling.** Decide whether NOT_APPLICABLE cells (for example the Ameca walking speed) leave the
   applicability-adjusted denominator. They never leave the fixed 946-cell metric.

## 7. Phase 5 — measurement

| Metric | Now | After batch 3 |
|---|---|---|
| Core UNKNOWN, fixed denominator (946) | 600 = 63.4% | 546 = **57.7%** |
| P0 UNKNOWN (258) | 103 = 39.9% | 103 = 39.9% |
| P1 UNKNOWN (688) | 497 = 72.2% | 443 = **64.4%** |
| Applicability-adjusted: known / applicable (943; 3 N/A cells shown separately) | 346 / 943 = 36.7% known | 400 / 943 = **42.4% known** |

**Waterfall by manufacturer** (UNKNOWN cells today → batch 3 → held with first-party evidence → silent → unavailable / N/A):

| Manufacturer | UNKNOWN | Batch 3 | Held, evidence-backed | Held, no evidence | Silent | Unavailable | N/A |
|---|---|---|---|---|---|---|---|
| Booster | 69 | 15 | 24 | 0 | 30 | 0 | 0 |
| AgiBot | 19 | 11 | 5 | 0 | 3 | 0 | 0 |
| Fourier | 13 | 6 | 6 | 0 | 1 | 0 | 0 |
| PAL | 23 | 5 | 7 | 0 | 11 | 0 | 0 |
| Galbot | 18 | 4 | 9 | 0 | 5 | 0 | 0 |
| Figure | 34 | 3 | 3 | 7 | 21 | 0 | 0 |
| Engineered Arts | 14 | 3 | 3 | 0 | 5 | 0 | 3 |
| Unitree | 122 | 2 | 87 | 0 | 33 | 0 | 0 |
| UBTECH | 38 | 2 | 4 | 0 | 32 | 0 | 0 |
| Boston Dynamics | 14 | 2 | 4 | 1 | 7 | 0 | 0 |
| SoftBank/Aldebaran | 44 | 1 | 14 | 0 | 29 | 0 | 0 |
| 1X | 25 | 0 | 1 | 2 | 22 | 0 | 0 |
| Rainbow | 22 | 0 | 0 | 0 | 22 | 0 | 0 |
| XPENG | 20 | 0 | 8 | 0 | 12 | 0 | 0 |
| Honda | 19 | 0 | 9 | 0 | 10 | 0 | 0 |
| Tesla | 17 | 0 | 0 | 0 | 0 | 17 | 0 |
| NEURA | 17 | 0 | 11 | 0 | 6 | 0 | 0 |
| Hanson | 17 | 0 | 6 | 0 | 11 | 0 | 0 |
| Kepler | 16 | 0 | 12 | 0 | 4 | 0 | 0 |
| Agility | 14 | 0 | 3 | 1 | 10 | 0 | 0 |
| Apptronik | 14 | 0 | 3 | 1 | 10 | 0 | 0 |
| Sanctuary | 11 | 0 | 3 | 1 | 7 | 0 | 0 |
| **Total** | **600** | **54** | **222** | **13** | **291** | **17** | **3** |

## 8. Execution plan from here

1. **Batch 3** (this PR): one owner approval, then rehearsal, guarded import and verification as in DR-D1.
2. **Decision round 1** (§5): autonomy and developer_edition mapping rules; R1 EDU U-edition identity; NAO identity;
   D5; label semantics. Each approved rule turns its held cells into a Fast Lane batch using evidence already
   captured, with no new research.
3. **Drift reconciliation** for H1 and alza-cz. This releases 5 cells.
4. **Data-request round** (§6.1) and the image or capture policies (§6.2–6.3).
5. Re-measure after each step against the fixed 946-cell denominator.
