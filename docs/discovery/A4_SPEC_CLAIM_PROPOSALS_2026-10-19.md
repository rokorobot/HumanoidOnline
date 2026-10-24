# A4 discovery: specification claim proposals for owner review (2026-10-19)

Covers all five owner-authorized manufacturer sources. Part 1: Unitree. Part 2: Booster, AgiBot, Agility, Figure. Nothing in this document has been written to the catalogue.

**Status: PROPOSALS. Nothing has been written to the catalogue.** Each row is a verbatim value observed by the governed `unitree-robotics-official` adapter (values as re-extracted by 0.1.1) and stored as a discovery-layer `candidate_claim` (NOT_VERIFIED). Promotion needs the owner's decision on the edition mapping and the value, then the normal claim → materialize → import chain.

## Part 1: Unitree H2 / R1 / G1

### Evidence

| Candidate | Fetched (final URL) | Retrieved (UTC) | Content hash |
|---|---|---|---|
| H2 | https://www.unitree.com/H2/ | 2026-10-18 22:06:50 | `769e8027a217bcb7…` |
| R1 | https://www.unitree.com/R1/ | 2026-10-18 22:06:54 | `ef1d2c91edab5d85…` |
| G1 | https://www.unitree.com/g1/ | 2026-10-18 22:06:58 | `e1a93cd0bd136246…` |

Agent observation via the scheduled-observation workflow (owner-authorized source, A4). It is not a MANUAL_BOOTSTRAP reading. Claim IDs below are the first 8 hex characters of `candidate_claim.id` in production.

### What the 238 raw records contain

- **15 commercial/meta records**: edition lists, per-edition prices, terms, 'from'. Prices match the catalogue already (H2 $29,900, R1 $5,900, G1 $13.5K, from Unitree's store). **R1 AIR $4,900** is the only new price, and it has no catalogue robot.
- **80 already in the catalogue** (same value, reformatted), mostly H2/R1, whose records were built from these tables on 2026-09-11.
- **60 trivial cells** (√ / - / footnote marks).
- **20 R1 AIR cells**: an edition with no catalogue robot.
- **63 absent cells**, which reduce to the distinct facts below. Several are duplicates across editions, or already present in other words (e.g. H2's 120/360 N·m torque, 75.6 V).

### Proposed additions (deduplicated)

| # | Target robot | Proposed key | Page edition | Verbatim value | Value | Claim |
|---|---|---|---|---|---|---|
| 1 | unitree-g1 (catalogue name 'G1 Basic') | `standing_dimensions_mm` | G1 | 1320x450x200mm | HIGH | `23bac6c6` |
| 2 | unitree-g1 (catalogue name 'G1 Basic') | `folded_dimensions_mm` | G1 | 690x450x300mm | HIGH | `2a9f41cb` |
| 3 | unitree-g1 (catalogue name 'G1 Basic') | `limb_lengths_mm` | G1 | 0.6M | MEDIUM | `171dcd90` |
| 4 | unitree-g1 (catalogue name 'G1 Basic') | `knee_joint_torque_nm` | G1 | 90N.m | HIGH | `e7c4a0a8` |
| 5 | unitree-g1 (catalogue name 'G1 Basic') | `joint_ranges` | G1 | Waist joint：Z±155° Knee joint：0~165° Hip joint：P±154°、R-30~+170°、Y±158° | MEDIUM | `b5825557` |
| 6 | unitree-g1 (catalogue name 'G1 Basic') | `sensors` | G1 | Depth Camera+3D LiDAR | HIGH | `6219f138` |
| 7 | unitree-g1 (catalogue name 'G1 Basic') | `battery_pack` | G1 | 13 string lithium battery | MEDIUM | `1436deb3` |
| 8 | unitree-g1 (catalogue name 'G1 Basic') | `charger` | G1 | 54V 5A | MEDIUM | `100959de` |
| 9 | unitree-g1 (catalogue name 'G1 Basic') | `joint_encoders` | G1 | Dual encoder | LOW | `ebee1db0` |
| 10 | unitree-g1 (catalogue name 'G1 Basic') | `manufacturer_warranty_months` | G1 | 8 months | HIGH | `6654f6b8` |
| 11 | unitree-g1-edu-plus-u2 (EDU line; see caveat) | `degrees_of_freedom_range` | G1 EDU | 23 - 43 | MEDIUM | `161df981` |
| 12 | unitree-g1-edu-plus-u2 (EDU line; see caveat) | `hand_options` | G1 EDU | 7（Optional Force control of three-fingered hand）+2(Optional 2 additional wrist degrees of freedom) *Three-fingered dexterous hand Dex3-1 Parameter: The thumb has 3 active degrees of freedom; the index finger has 2 active degrees of freedom; the middle finger has 2 active degrees of freedom. **Dex3-1 can optionally be installed with tactile sensor arrays | MEDIUM | `a3d30a4d` |
| 13 | unitree-g1-edu-plus-u2 (EDU line; see caveat) | `manufacturer_warranty_months` | G1 EDU | 18 months | HIGH | `d6080853` |
| 14 | unitree-g1-edu-plus-u2 (EDU line; see caveat) | `compute_ai` | G1 EDU | Multiple brands and models available such as Orin, etc. | LOW | `fabbeef4` |
| 15 | unitree-r1 + unitree-r1-edu-u1…u6 | `joint_ranges` | R1 | Waist Joint：Y±150° R±30° Knee Joint：-10°~+139° Hip Joint：Y:±157° P:-168° ~+146° R:-60° ~+100° | MEDIUM | `eae74a85` |
| 16 | unitree-r1 + unitree-r1-edu-u1…u6 | `joint_output_bearing` | R1 | Crossed roller bearings, Double Hook Ball Bearings | LOW | `9dc4980f` |
| 17 | unitree-h2 + unitree-h2-edu | `materials` | H2 | Aircraft-Grade Aluminum + Titanium Alloy + High-Strength Engineering Plastics | LOW | `13956ccc` |
| 18 | unitree-h2 + unitree-h2-edu | `joint_output_bearing` | H2 | Industrial grade crossed roller bearings (high precision, high load capacity) | LOW | `191e71d1` |

### Owner decisions required

1. **Edition mapping.** Stage E exact-matched the page models to `unitree-h2`, `unitree-r1` and `unitree-g1`, but each page has several editions. The page's 'G1' column is the base edition, catalogued as **'G1 Basic'**. The **'G1 EDU'** column describes the whole EDU line (23–43 DoF, optional hands), while the catalogue holds one configuration, `G1 EDU Plus (U2)` (29 DoF, fixed hands). Rows 11–14 therefore must not be applied to U2 as-is. **'R1 EDU'** spans the catalogue's six U1–U6 configurations.
2. **R1 AIR (new edition).** A new unpublished robot record, or out of scope? Its page values (verbatim): Height, Width and Thickness（Stand） = 1230x357x190mm; Weight (With Battery) = About 27kg; Degree of Freedom(Total Joints) = 20; Single Leg Degrees of Freedom = 6; Single Arm Degrees of Freedom = 4; Basic Computing Power = 8-Core High-Performance Processor; Camera = Monocular camera; Microphone Array = 4-Mic Array; Battery Life = About 1h; Warranty Period【3】 = 6 Months; price $4,900 (tax and shipping excluded).
3. **Source label anomalies (kept verbatim, not corrected):** R1 AIR's row 'Maximum Torque of Arm Joint【1】' states 'About 2kg' (a mass, not a torque). The values '0.6M' (G1 limb length) and 'About 35kg+' (G1 EDU weight) are as written.
4. **Low-value rows** (LOW): accept as extended specs, or ignore?

Unitree prices: the page adds no new price to existing robots. The price-semantics question (USD, tax and shipping excluded) is unchanged and already reflected in the catalogue's `unitree-store` GLOBAL offers.

## Part 2: Booster, AgiBot, Agility, Figure (adapters v0.2.0, observed 2026-10-18)

The v0.1.0 adapters were identity-only by design, so the approved pages' specification blocks were
not read. v0.2.0 (PR #167, merged) records them verbatim. One bounded observation per source
re-extracted the cached bodies: **225 new claims** (Booster T2 64, K1 81; AgiBot X2 70; Agility
Digit 5 4; Figure 03 6). AgiBot A2's page has no specification table, so it has none.

| Page | Fetched | Retrieved (UTC) | Content hash |
|---|---|---|---|
| products/A2 | https://www.agibot.com/products/A2 | 2026-10-18 22:48:57 | `c7e09dc956f13ed9…` |
| products/X2 | https://www.agibot.com/products/X2 | 2026-10-18 22:48:59 | `62c5ee252367186c…` |
| solutions/digit-5 | https://www.agilityrobotics.com/solutions/digit-5 | 2026-10-18 22:14:49 | `82160494b118eed3…` |
| booster-k1?target=en | https://www.booster.tech/booster-k1?target=en | 2026-10-18 22:11:18 | `1cc79de28eca6cf7…` |
| booster-t2?target=en | https://www.booster.tech/booster-t2?target=en | 2026-10-18 22:11:16 | `6d0e4303d3d50238…` |
| figure | https://www.figure.ai/figure | 2026-10-18 22:52:47 | `46db86658974d4bb…` |

### Conflicts with the current catalogue (owner decision needed)

| Robot | Catalogue | Official page (verbatim, claim) |
|---|---|---|
| booster-k1-geek / -educational / -professional | walk_speed 0.4 m/s | Walking Speed 2 m/s (`89e5d72c`), same for all three editions |
| booster-k1-geek | runtime 30 min | Battery life 20 min (walking at 1.1 m/s) (`c6f067a5`) |
| booster-k1-educational / -professional | runtime 80 min | Battery life 1 h 10 min (walking at 1.1 m/s) (`a55b65de`) |
| agility-digit ("Digit") | payload 16 kg | Digit 5: Payload* 23kg/50lbs (`9fc92033`). Likely a **different generation**: an identity decision, not a correction |

### New facts with a catalogue home (proposals)

| Target robot | Proposed key | Verbatim value (claim) |
|---|---|---|
| booster-k1-geek | compute_ai | 48 TOPS (dense) AI computing power (`72ddb0f3`) |
| booster-k1-educational | compute_ai | 117 TOPS AI computing power (`17628e19`) |
| booster-k1-professional | compute_ai | 200 TOPS AI computing power (`96b2a532`) |
| booster-k1-* | peak_joint_torque_nm | 60 N·m (`af6fdd75`) |
| booster-k1-geek | manufacturer_warranty | 3 months (extended warranty available) (`4b9741f9`) |
| booster-k1-educational / -professional | manufacturer_warranty | 1 year (extended warranty available) (`942966bc`) |
| booster-t2-education | compute_ai | High-performance ARM processor, 375 TOPS AI computing power (`5681e6bb`) |
| booster-t2-professional | compute_ai | Jetson Thor T5000, 2070 TFLOPS AI computing power (`e13fcd8f`) |
| booster-t2-* | manufacturer_warranty | 1 year; extended warranty available (`1b74fb91`) |
| booster-t2-* | end_effector_options | standard, gripper, or dexterous hand. (`223cae62`) |
| figure-03 (unpublished, no specs today) | height | 5'8" (`48923025`) |
| figure-03 | payload | 20KG (`b4da6ae2`) |
| figure-03 | weight | 61KG (`bd4d27ae`) |
| figure-03 | runtime | 5HR (`c3258260`) |
| figure-03 | walk speed | 1.2M/S (`6e17a216`) |
| Digit 5 (identity decision first) | reach / duty | Reach* 2.2m/7.2ft (`388e2e44`); Work/Shift* 20HRS/24HRS (`76deefad`); Run to charge ratio* 10:1 (`78a91389`) |

Booster also states connectivity, IMU, camera, ports, buttons, safety and voice-prompt rows (LOW value; all kept as claims).

### AgiBot X2: no catalogue robot (identity decision)

The catalogue has only `agibot-a2-lite` and `agibot-a2-ultra`. The X2 page states two editions, **X2** and **X2 Ultra**, with 35 rows each. For example:
- Weight Approx.35kg (`4b5e8992`) vs Approx.39kg (`2af51fb5`);
- Total DoF 25 (`7f702bad`) vs 30 (`126dc465`);
- Battery Approx.500Wh (`df42554b`);
- Operating time At 0.5 m/s walking Approx. 2 hours (`b2b18036`);
- Compute RK3588 ×2 (`aab9d7af`);
- 3D LiDAR Not equipped (`7ce7d49e`) vs Equipped (`34d1e2e1`).

Decide whether X2 / X2 Ultra become new unpublished robot records. **Source label anomaly:** AgiBot's own table labels the operating-temperature row "Excluding end effector" (-10℃ to 40℃ (`1d45b3b3`)). It is kept verbatim and not relabelled.

### Remaining gaps

- **No prices** on Booster, AgiBot, Agility or Figure pages. Booster "Buy now" leads to `/store`, which is not reviewed, and AgiBot's store is on another host.
- **AgiBot A2:** the page has no specification table; its specs are in images.
- **Agility:** the spec sheet is form-gated, so only the four headline stats exist.
- **Figure:** only the stat block; no editions, prices or deployments on `/figure`.
- **Alza.cz:** still blocked (robots.txt 403).
