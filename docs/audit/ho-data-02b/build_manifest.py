"""HO-DATA-02B enrichment manifest. Writes CSV + prints recoverability totals. No I/O beyond the output file.

usage: python build_manifest.py <out.csv>
"""
import collections, csv, sys

WO = "AGENT_ASSISTED_RESEARCH; work order 'HO-DATA-02B 2026-10-22' (docs/26 R5); retrieved by Claude Opus 5.5 + Sonnet research agents; not human-verified"
A4 = "A4 discovery claim (production candidate_claim / discovery_claim_proposal)"
D = "2026-10-22"

# Source captures (sha256 prefix of the body retrieved 2026-10-22).
SRC = {
    "a2u_en": ("https://www.agibot.com/products/A2_Ultra", "MANUFACTURER_PAGE", "AgiBot", "1b596c3d3c3a11fa"),
    "a2u_jp": ("https://agibot.com/jp/products/A2_Ultra", "MANUFACTURER_PAGE", "AgiBot", "a1984883aecaa036"),
    "a2u_store": ("https://store.agibot.com/products/a2-ultra.json", "MANUFACTURER_STORE", "AgiBot", "agent-relayed"),
    "t1": ("https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/specifications/", "MANUFACTURER_DOC", "Booster Robotics", "f30c459c972c497f"),
    "galbot": ("http://www.galbot.com/g1/", "MANUFACTURER_PAGE", "Galbot", "4f3b10993e3cdb1d"),
    "ws2_en": ("https://www.ubtrobot.com/en/humanoid/products/walker-s2", "MANUFACTURER_PAGE", "UBTECH", "aee635e54335ad39"),
    "ws2_cn": ("https://www.ubtrobot.com/cn/humanoid/products/walker-s2", "MANUFACTURER_PAGE", "UBTECH", "7ab544e5285c6eb4"),
    "ws2_img": ("https://owebsite-cdn.ubtrobot.com/resources/image/2025/07/24/701244770754629.png", "MANUFACTURER_PAGE", "UBTECH", "d5dc2a359465139d"),
    "nao_pdf": ("https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf", "MANUFACTURER_DOC", "Maxtronics Robotics SAS", "d452b3e2ca0cd0e6"),
    "nao_page": ("https://maxtronics.com/nao6/", "MANUFACTURER_PAGE", "Maxtronics Robotics SAS", "20ec1d3c8590c0b1"),
    "kaist_plus": ("https://breakthroughs.kaist.ac.kr/sub02/view/id/289", "ORIGINATING_LAB", "KAIST (not the manufacturer)", "agent-relayed"),
    "kaist_2013": ("https://news.kaist.ac.kr/newsen/html/news/?mode=V&mng_no=4010", "ORIGINATING_LAB", "KAIST (not the manufacturer)", "agent-relayed"),
    "r1_page": ("https://www.unitree.com/R1", "MANUFACTURER_PAGE", "Unitree", "0dad7acfd9c1f093"),
    "r1_shop": ("https://shop.unitree.com/products/unitree-r1", "MANUFACTURER_STORE", "Unitree", "0628b7c8ad5a3a30"),
    "neura_res": ("https://neura-robotics.com/product/4ne1-mini-reservation", "MANUFACTURER_PAGE", "NEURA Robotics", "c75543d69a8a79e6"),
    "t2": ("https://www.booster.tech/booster-t2", "MANUFACTURER_PAGE", "Booster Robotics", "agent-relayed"),
    "digit5": ("https://www.agilityrobotics.com/solutions/digit-5", "MANUFACTURER_PAGE", "Agility Robotics", "agent-relayed"),
    "none": ("", "", "", ""),
}

TIER = {"height_cm": "P0", "weight_kg": "P0", "payload_kg": "P0", "runtime_minutes": "P0", "walk_speed_ms": "P0",
        "degrees_of_freedom": "P0"}

# recoverability:
#   CLEAN            stated for this exact edition, label matches the field, at most a unit conversion; consistent with ratified precedent
#   IF_POLICY        recoverable only if the named PROPOSED policy is approved
#   IDENTITY_BLOCKED needs an owner identity / source-eligibility decision first
#   CONFLICT         first-party sources disagree; owner picks or it stays UNKNOWN
#   NOT_RECOVERABLE  not stated / blocked / excluded by the conservative policy (the status column says which)
# verification: RAW_VERIFIED (orchestrator re-fetched and saw the value) | AGENT_RELAYED (research agent via fetch summariser) | HELD (production claim)
R = []


def row(rank, slug, name, edition, field, value, unit, conv, label, excerpt, src, status, verification, recov, policies="", note="", basis=WO):
    url, kind, publisher, h = SRC[src]
    R.append(dict(rank=rank, robot_slug=slug, record_name=name, edition_as_stated=edition, field=field,
                  tier=TIER.get(field, "P1/P2"), proposed_value=value, unit=unit, conversion=conv,
                  label_as_printed=label, verbatim_excerpt=excerpt, source_url=url, source_kind=kind,
                  publisher=publisher, retrieved_at=D if src != "none" else "", content_sha256_16=h,
                  evidence_status=status, verification=verification, recoverability=recov,
                  policies_required=policies, note=note, retrieval_basis=basis if src != "none" else ""))


# ---- 1. agibot-a2-ultra (COMMERCIAL) -------------------------------------------------------------
s, n = "agibot-a2-ultra", "A2 Ultra"
row(1, s, n, "A2 Ultra", "height_cm", 169, "cm", "", "Height", "Height|169cm (A2 Ultra column)", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN", note="JP page agrees (身長 169cm).")
row(1, s, n, "A2 Ultra", "weight_kg", 69, "kg", "", "Weight", "Weight|≈69kg", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN", note="Approximate (≈) -> caveat. JP ≈69kg agrees; store JSON weight 69.0 kg (agent-relayed).")
row(1, s, n, "A2 Ultra", "degrees_of_freedom", 40, "DoF", "", "Total DOF", "Total DOF|40", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN", note="JP label 主動自由度 (active DoF) 40. Do not sum sub-rows.")
row(1, s, n, "A2 Ultra", "runtime_minutes", 90, "min", "1.5 h -> 90 min", "Battery Life", "Battery Life|Standing : 3h,|Walking : 1.5h+", "a2u_en", "STATED_AMBIGUOUS", "RAW_VERIFIED", "IF_POLICY", "D9", "Two modes; walking is a lower bound ('1.5h+'); JP 歩行 約1.5h. D9 takes the walking mode with both modes in a caveat.")
row(1, s, n, "A2 Ultra", "walk_speed_ms", "", "m/s", "", "Speed", "EN: Speed|Max 1.2m/s  vs  JP: 速度|最大0.8m/s, 通常使用≤0.6m/s", "a2u_en", "CONFLICT", "RAW_VERIFIED", "CONFLICT", "D2", "EN and JP first-party pages disagree for the same edition (1.2 vs 0.8 max). Conflict preserved; stays UNKNOWN until the owner rules.")
row(1, s, n, "A2 Ultra", "payload_kg", "", "kg", "", "Max Arm Load / 片腕最大負荷", "EN: Max Arm Load|≈2kg  vs  JP: 片腕最大負荷|約3kg", "a2u_en", "CONFLICT", "RAW_VERIFIED", "CONFLICT", "D3", "EN ≈2 kg (per-arm not stated) vs JP single-arm ≈3 kg. Conflict preserved.")
row(1, s, n, "A2 Ultra", "hand_dof", 6, "DoF", "", "Single Hand DOF", "Single Hand DOF|6-DOF Dexterous Hand", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN", note="Listed in the A2 Ultra spec table as the model's hand (Lite '/'), not as an option; precedent: G1 Basic hand fields from the model's own spec listing.")
row(1, s, n, "A2 Ultra", "hand_type", "6-DoF dexterous hand", "", "", "Single Hand DOF", "6-DOF Dexterous Hand", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN", note="As above.")
row(1, s, n, "A2 Ultra", "has_vision", True, "", "", "Perception System", "RGB-D Camera|Equipped", "a2u_en", "STATED", "RAW_VERIFIED", "CLEAN")
row(1, s, n, "A2 Ultra", "battery_wh", "", "Wh", "", "Battery Capacity", "Battery Capacity|14.4Ah", "a2u_en", "CHECKED_NOT_STATED", "RAW_VERIFIED", "NOT_RECOVERABLE", "D1", "Only Ah stated; no voltage or Wh. No derivation.")

# ---- 2. booster-t1 (COMMERCIAL) ----------------------------------------------------------------
s, n = "booster-t1", "T1"
row(2, s, n, "T1 (Basic and Standard share the table)", "height_cm", 118, "cm", "1.18 m -> 118 cm", "高（站直）", "高（站直）|1.18m", "t1", "STATED", "RAW_VERIFIED", "CLEAN", note="Editions differ only in compute (基础版/标准版); D6 satisfied.")
row(2, s, n, "T1", "weight_kg", 30, "kg", "", "重量", "重量|约 30kg", "t1", "STATED", "RAW_VERIFIED", "CLEAN", note="约 = approximately -> caveat.")
row(2, s, n, "T1", "degrees_of_freedom", 23, "DoF", "", "全身自由度", "全身自由度|23", "t1", "STATED", "RAW_VERIFIED", "CLEAN", note="Arm '4（可拓展）' (expandable); a 29-DoF 7-DoF-arm layout appears in BoosterRobotics/booster_assets README (agent-relayed) -> caveat.")
row(2, s, n, "T1", "walk_speed_ms", 1.0, "m/s", "", "行走速度", "行走速度|1m/s", "t1", "STATED", "RAW_VERIFIED", "CLEAN")
row(2, s, n, "T1", "runtime_minutes", 120, "min", "2 h -> 120 min", "续航", "续航|2h", "t1", "STATED", "RAW_VERIFIED", "CLEAN", note="Conditions not stated -> caveat.")
row(2, s, n, "T1", "payload_kg", "", "kg", "", "", "(no payload row in the specification table)", "t1", "CHECKED_NOT_STATED", "RAW_VERIFIED", "NOT_RECOVERABLE", note="Other T1 manual chapters not read; research lead.")
row(2, s, n, "T1", "battery_wh", "", "Wh", "", "容量", "容量|48V 10.5Ah", "t1", "STATED_AMBIGUOUS", "RAW_VERIFIED", "NOT_RECOVERABLE", "D1", "V and Ah only; no derivation.")
row(2, s, n, "T1", "has_vision", True, "", "", "传感器 相机", "相机|深度相机", "t1", "STATED", "RAW_VERIFIED", "CLEAN")

# ---- 3. galbot-g1 (COMMERCIAL) -----------------------------------------------------------------
s, n = "galbot-g1", "G1"
row(3, s, n, "G1", "weight_kg", 92.5, "kg", "", "机身重量", "机身重量|92.5 kg", "galbot", "STATED", "RAW_VERIFIED", "CLEAN")
row(3, s, n, "G1", "payload_kg", 5, "kg", "", "负载能力（腕部中心）单臂", "负载能力（腕部中心）|单臂 5 kg|合计 10 kg", "galbot", "STATED", "RAW_VERIFIED", "CLEAN", note="Stated per-arm value; ratified precedent: G1 payload_kg 2.0 is a stated per-arm maximum. 10 kg combined -> max_dual_arm_load_kg.")
row(3, s, n, "G1", "degrees_of_freedom", 21, "DoF", "", "自由度（不含底盘和末端执行器）", "自由度（不含底盘和末端执行器）|合计 21", "galbot", "STATED", "RAW_VERIFIED", "CLEAN", note="Excludes chassis and end effectors (4NE1 Mini 'base unit only' precedent) -> caveat.")
row(3, s, n, "G1", "runtime_minutes", 480, "min", "8 h -> 480 min", "续航与充电 / 工作时长", "续航与充电|工作时长 8 小时", "galbot", "STATED", "RAW_VERIFIED", "CLEAN", note="Sits under the 续航与充电 (battery endurance & charging) heading next to 适配器充电 3.5 小时: an endurance figure, unlike 4NE1 Mini 'Operating Time 24/7'. Duty cycle not stated -> caveat (Figure 03 'Runtime 5HR' precedent).")
row(3, s, n, "G1", "height_cm", 173, "cm", "1730 mm -> 173 cm", "整机高度（最高）", "整机高度（最高）|1730 mm|腿部升降高度差|650 mm", "galbot", "STATED_AMBIGUOUS", "RAW_VERIFIED", "IF_POLICY", "D10", "Maximum height of a height-adjustable robot (650 mm lift range).")
row(3, s, n, "G1", "walk_speed_ms", 1.5, "m/s", "", "最大速度", "底盘形式|4 轮全向移动底盘 ... 最大速度|1.5 m/s", "galbot", "STATED_AMBIGUOUS", "RAW_VERIFIED", "IF_POLICY", "D2", "Wheeled-base maximum speed; D2 must cover wheeled locomotion and 'max'.")
row(3, s, n, "G1", "mobility", "WHEELED", "", "", "底盘形式", "底盘形式|4 轮全向移动底盘", "galbot", "STATED", "RAW_VERIFIED", "CLEAN")
row(3, s, n, "G1", "has_vision", True, "", "", "感知 头部", "头部|双目相机 ×1", "galbot", "STATED", "RAW_VERIFIED", "CLEAN")
row(3, s, n, "G1", "has_language_ui", True, "", "", "拟人交互", "对话自然流畅", "galbot", "STATED", "RAW_VERIFIED", "IF_POLICY", "D4", "Marketing statement of natural dialogue + 2x linear 4-mic arrays.")
row(3, s, n, "G1", "hand_type", "", "", "", "末端执行器", "末端执行器|可在灵巧手、吸盘和夹爪之间更换", "galbot", "STATED_AMBIGUOUS", "RAW_VERIFIED", "NOT_RECOVERABLE", "D5", "Interchangeable; no standard fit stated -> dexterous_hand_option text only.")
row(3, s, n, "G1", "reach_cm", "", "cm", "", "手臂长（肩部中心到腕部中心）", "手臂长（肩部中心到腕部中心）|710 mm", "galbot", "STATED_AMBIGUOUS", "RAW_VERIFIED", "NOT_RECOVERABLE", note="Shoulder-to-wrist excludes the hand; not reach_cm -> limb_lengths_mm text.")

# ---- 4. ubtech-walker-s2 (COMMERCIAL) ----------------------------------------------------------
s, n = "ubtech-walker-s2", "Walker S2"
for f in ("height_cm", "weight_kg", "walk_speed_ms", "degrees_of_freedom"):
    row(4, s, n, "Walker S2", f, "", "", "", "", "(not stated on EN or CN product page; spec image is a hardware-features diagram)", "ws2_cn", "CHECKED_NOT_STATED", "RAW_VERIFIED", "NOT_RECOVERABLE", note="Research lead: UBTECH launch release / brochure on ubtrobot.com news.")
row(4, s, n, "Walker S2", "payload_kg", "", "kg", "", "负载 负重行走", "负载|负重行走 >15kg ; EN: Walker S2 can lift 15kg payload", "ws2_cn", "STATED_AMBIGUOUS", "RAW_VERIFIED", "NOT_RECOVERABLE", "D3", "Load-carrying walk / whole-body lift, lower bound -> not an arm payload under D3.")
row(4, s, n, "Walker S2", "runtime_minutes", "", "min", "", "续航 持续作业", "续航|持续作业 ≥4小时", "ws2_cn", "STATED_AMBIGUOUS", "RAW_VERIFIED", "NOT_RECOVERABLE", "D9", "Continuous operation lower bound on a robot with autonomous battery swap / dual-battery mode: not battery runtime.")
row(4, s, n, "Walker S2", "has_vision", True, "", "", "hardware diagram", "RGB Camera*2 ; RGBD Camera*1 ; Fish-eye Camera*2", "ws2_img", "STATED", "RAW_VERIFIED", "CLEAN")
row(4, s, n, "Walker S2", "hand_type", "dexterous hands", "", "", "hardware diagram", "Dexterous Hands*2", "ws2_img", "STATED", "RAW_VERIFIED", "IF_POLICY", "D5", "Shown as fitted on the product diagram; standard-fit not stated in words.")

# ---- 5. softbank-nao (identity: generic 'NAO' record vs NAO6 published by Maxtronics) ----------
s, n = "softbank-nao", "NAO"
row(5, s, n, "NAO6 (MODEL: H25600)", "height_cm", 57.4, "cm", "574 mm -> 57.4 cm", "Robot size (HxDxW)", "574x311x275 mm / 22.6x12.2x10.8 in", "nao_pdf", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6", "Page says 'Standing 58 cm tall' (rounded). Requires owner: generic NAO record = NAO6; publisher Maxtronics vs catalogue manufacturer SoftBank.")
row(5, s, n, "NAO6", "weight_kg", 5.48, "kg", "", "Robot weight", "5.48 kg / 12.08 lbs", "nao_pdf", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6")
row(5, s, n, "NAO6", "degrees_of_freedom", 25, "DoF", "", "(page text)", "Standing 58 cm tall with 25 degrees of freedom", "nao_page", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6", "Datasheet prints only a per-segment breakdown; the total comes from the page.")
row(5, s, n, "NAO6", "runtime_minutes", 60, "min", "", "Run time", "60 min (Active use) / 90 min (Normal use)", "nao_pdf", "STATED_AMBIGUOUS", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6,D9", "D9 takes the active-use value; 90 min in caveat.")
row(5, s, n, "NAO6", "payload_kg", "", "kg", "", "", "(no payload in datasheet or page)", "nao_pdf", "CHECKED_NOT_STATED", "RAW_VERIFIED", "NOT_RECOVERABLE")
row(5, s, n, "NAO6", "walk_speed_ms", "", "m/s", "", "", "(no walking speed in datasheet or page)", "nao_pdf", "CHECKED_NOT_STATED", "RAW_VERIFIED", "NOT_RECOVERABLE")
row(5, s, n, "NAO6", "battery_wh", 62.5, "Wh", "", "Energy", "62.5 Wh", "nao_pdf", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6")
row(5, s, n, "NAO6", "has_sdk", True, "", "", "SDK", "Software development kit for creating and controlling applications on NAO. Includes APIs and libraries (Python, C++)", "nao_pdf", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6")
row(5, s, n, "NAO6", "simulation_support", True, "", "", "SDK", "visual programming tools, simulation environment, and development documentation", "nao_pdf", "STATED", "RAW_VERIFIED", "IDENTITY_BLOCKED", "D6")
row(5, s, n, "NAO6", "has_language_ui", True, "", "", "LANGUAGES", "Text to speech & Automatic speech Recognition: ...", "nao_pdf", "STATED", "AGENT_RELAYED", "IDENTITY_BLOCKED", "D6,D4")
row(5, s, n, "NAO6", "hand_dof", 1, "DoF per hand", "", "Hand (in each)", "Hand (in each) 1", "nao_pdf", "STATED", "AGENT_RELAYED", "IDENTITY_BLOCKED", "D6")

# ---- 6. softbank-pepper ------------------------------------------------------------------------
s, n = "softbank-pepper", "Pepper"
for f in TIER:
    row(6, s, n, "Pepper (unversioned)", f, "", "", "", "", "doc.aldebaran.com ECONNRESET on every attempt; maxtronics.com and us.softbankrobotics.com Pepper pages state no specs", "none", "BLOCKED", "AGENT_RELAYED", "NOT_RECOVERABLE", note="Retry doc.aldebaran.com from another route or owner capture; Maxtronics says it no longer supports Pepper.")

# ---- 7. rainbow-hubo ---------------------------------------------------------------------------
s, n = "rainbow-hubo", "HUBO"
row(7, s, n, "DRC-HUBO+", "height_cm", 173, "cm", "", "Its height", "Its height is 173cm, and its weight is 82kg.", "kaist_plus", "STATED", "AGENT_RELAYED", "IDENTITY_BLOCKED", "D6,D11", "Rainbow presents HUBO as heritage only, no specs. KAIST is the originating lab, not the manufacturer; generation must be chosen.")
row(7, s, n, "DRC-HUBO+", "weight_kg", 82, "kg", "", "its weight", "Its height is 173cm, and its weight is 82kg.", "kaist_plus", "STATED", "AGENT_RELAYED", "IDENTITY_BLOCKED", "D6,D11")
row(7, s, n, "DRC-HUBO+", "degrees_of_freedom", 32, "DoF", "", "DOF", "DRC-HUBO+ has 32 DOF (degree of freedom)", "kaist_plus", "STATED", "AGENT_RELAYED", "IDENTITY_BLOCKED", "D6,D11", "DRC-HUBO (2013) stated 34 DoF / 4.7 ft / 120 lbs on news.kaist.ac.kr: a different configuration.")
for f in ("payload_kg", "runtime_minutes", "walk_speed_ms"):
    row(7, s, n, "any HUBO generation", f, "", "", "", "", "(not stated by Rainbow Robotics or the KAIST pages read)", "none", "CHECKED_NOT_STATED", "AGENT_RELAYED", "NOT_RECOVERABLE")

# ---- Batch 1 held claims, reassessed -------------------------------------------------------------
row(8, "4ne1-mini", "4NE1 Mini", "Standard and Pro", "has_sdk", True, "", "", "Interfaces", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync", "neura_res", "STATED", "RAW_VERIFIED + HELD", "CLEAN", note="Stated for BOTH variants -> product-level value valid. Datasheet's C++ SDK is Pro-only on the reservation page (conflict irrelevant to the boolean).")
row(8, "4ne1-mini", "4NE1 Mini", "Standard and Pro", "ros_support", True, "", "", "Interfaces", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync", "neura_res", "STATED", "RAW_VERIFIED + HELD", "CLEAN")
row(8, "4ne1-mini", "4NE1 Mini", "datasheet (edition-agnostic)", "walk_speed_ms", "", "m/s", "", "Speed", "Speed Max. 4.6 km/h 2.9 mph", "none", "STATED_AMBIGUOUS", "HELD", "NOT_RECOVERABLE", "D2", "Stays in extended max_speed: mobility UNKNOWN, no locomotion label.", basis=A4)
row(8, "unitree-r1", "R1", "R1 column (AIR, R1, EDU all print the same)", "payload_kg", 2, "kg", "", "Maximum Torque of Arm Joint【1】", "Maximum Torque of Arm Joint【1】|About 2kg ... [1] The maximum load of the arm varies greatly under different arm extension postures.", "r1_page", "STATED_AMBIGUOUS", "RAW_VERIFIED + HELD", "IF_POLICY", "D12,D3", "Torque label with a mass value; footnote describes arm load. Already held in production (3 claims, one per edition column) but unmapped: 02A should have classed this cell HELD_DECISION. Not propagated to R1 EDU U1–U6 (D6).")
row(8, "unitree-r1", "R1", "R1 (and R1 AIR)", "has_sdk", False, "", "", "store note", "Please Note: Only the EDU version supports secondary development.", "r1_shop", "STATED", "RAW_VERIFIED", "CLEAN", note="Explicit first-party negative for non-EDU R1 (not derived from '/').")
for slug in ("booster-t2-education", "booster-t2-professional"):
    row(8, slug, "T2", "T2 Education / Professional", "payload_kg", "", "kg", "", "Maximum Dual-Arm Payload", "10 kg* — *The maximum arm payload varies significantly depending on arm posture.", "t2", "STATED_AMBIGUOUS", "AGENT_RELAYED + HELD", "NOT_RECOVERABLE", "D3", "Combined, posture-dependent; already in max_dual_arm_load_kg.")
    row(8, slug, "T2", "T2", "battery_wh", "", "Wh", "", "Battery Rating", "48 V, 10 Ah", "t2", "STATED_AMBIGUOUS", "AGENT_RELAYED + HELD", "NOT_RECOVERABLE", "D1")
    row(8, slug, "T2", "T2", "has_language_ui", "", "", "", "Audio Module / Large-Model Support", "Microphone array + speaker; Large-Model Support: Supported", "t2", "STATED_AMBIGUOUS", "HELD", "NOT_RECOVERABLE", "D4", "Lead: T2 manual voice-interaction chapter (unread).", basis=A4)
    row(8, slug, "T2", "T2", "hand_type", "", "", "", "End Effector (Optional)", "standard, gripper, or dexterous hand", "t2", "STATED_AMBIGUOUS", "AGENT_RELAYED + HELD", "NOT_RECOVERABLE", "D5")
row(8, "unitree-h2-edu", "H2 EDU", "H2 EDU", "hand_type", "", "", "", "Dexterous Hand", "Dexterous Hand (Multiple Model Options)", "none", "STATED_AMBIGUOUS", "HELD", "NOT_RECOVERABLE", "D5", basis=A4)
row(8, "unitree-r1-edu-u1", "R1 EDU U1", "R1 EDU (generic column)", "degrees_of_freedom", "", "DoF", "", "Degree of Freedom(Total Joints)", "26-40", "none", "STATED_AMBIGUOUS", "HELD", "NOT_RECOVERABLE", "D6", "No per-U-edition value on unitree.com or shop.unitree.com; U1–U6 are distributor (reichelt) configurations.", basis=A4)
for i in range(3, 7):
    row(8, f"unitree-r1-edu-u{i}", f"R1 EDU U{i}", "R1 EDU (generic column)", "weight_kg", "", "kg", "", "Weight (With Battery)", "About 29kg", "none", "STATED_AMBIGUOUS", "HELD", "NOT_RECOVERABLE", "D6", "Generic EDU column; hand fit-out differs per U-edition.", basis=A4)
for f, ex in (("reach_cm", "Reach* 2.2m/7.2ft"), ("runtime_minutes", "Work/Shift* 20HRS/24HRS")):
    row(8, "agility-digit", "Digit", "Digit 5", f, "", "", "", f.split("_")[0], ex + " — *preliminary estimates ... pre-production hardware", "digit5", "STATED_AMBIGUOUS", "AGENT_RELAYED + HELD", "NOT_RECOVERABLE", "D7", "Digit 5 is 'in development'; identity unresolved; specs are preliminary estimates.")
for slug, f in (("unitree-g1", "has_sdk"), ("unitree-h2", "has_sdk"), ("unitree-h2", "hand_type"), ("unitree-h2", "hand_dof"), ("unitree-r1", "hand_type"), ("unitree-r1", "hand_dof")):
    row(8, slug, slug, "base column", f, "", "", "", "Secondary Development / Dexterous Hand", "/", "none", "CHECKED_NOT_STATED", "HELD", "NOT_RECOVERABLE", "D8", "'/' is not defined anywhere on unitree.com/g1, /H2, /R1 -> not a stated negative.", basis=A4)

out = sys.argv[1]
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, list(R[0])); w.writeheader(); w.writerows(R)

p0 = [r for r in R if r["tier"] == "P0"]
print("rows", len(R), "P0 rows", len(p0))
print("P0 by recoverability:", dict(collections.Counter(r["recoverability"] for r in p0)))
print("P1 by recoverability:", dict(collections.Counter(r["recoverability"] for r in R if r["tier"] != "P0")))
for k in ("CLEAN", "IF_POLICY", "IDENTITY_BLOCKED", "CONFLICT"):
    print(k, sorted((r["robot_slug"], r["field"]) for r in p0 if r["recoverability"] == k))
