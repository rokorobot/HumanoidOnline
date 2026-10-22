# HO-DATA-02B — Evidence Recovery and P0 Enrichment: Research Plan and Backlog (2026-10-22)

**Status:** plan and evidence backlog only. **Nothing here is approved, promoted, imported or published.**
No catalogue file, production row, source authorization or publication state was changed.

**Baseline:** HO-DATA-02A @ `4f992c9`. P0 UNKNOWN = 119/258 = **46.1%**. Target: below 30% (≤77 UNKNOWN), i.e. ≥42 P0 cells must be resolved.

**Retrieval basis:** owner AGENT_ASSISTED_RESEARCH work order **"HO-DATA-02B 2026-10-22"** (docs/26 R5), confirmed in
chat on 2026-10-22. Scope: public first-party material for the seven 22/22 robots and the Batch 1 held-claim robots.
All of it is read-only. Evidence is labelled AGENT_ASSISTED_RESEARCH, never VERIFIED and never MANUAL_BOOTSTRAP.
One scope extension, made by the orchestrator: KAIST pages (originating lab, not the manufacturer) were read for
HUBO and are flagged under D11. GitHub (`github.com/BoosterRobotics`) and the UBTECH image CDN were read as
manufacturer-controlled hosts. WebSearch surfaced third-party snippets; these were used only as leads.
No A4 source or path prefix was added. No login, CAPTCHA or block was bypassed. RobotShop was not used.

**Files:**
- `ho-data-02b/enrichment_manifest.csv`: 87 rows, one per (record, field), with the exact edition label, proposed
  value, unit, verbatim label and excerpt, source URL, publisher, retrieval date, content hash, verification status and recoverability.
- `ho-data-02b/build_manifest.py`: regenerates the CSV and the totals.

---

## 1. Result in one table

P0 cells in scope: 42 on the seven 22/22 robots, plus 10 Batch 1 cells (52 in total). They resolve as follows:

| Recoverability | P0 cells | Meaning |
|---|---|---|
| **CLEAN** | **12** | Stated for the exact edition, the label matches the field, at most a unit conversion, consistent with ratified precedent, and **raw-verified** by re-fetch. |
| IF_POLICY | 4 | Recoverable only if the named *proposed* policy (§3) is approved. |
| IDENTITY_BLOCKED | 7 | The value is first-party for a specific generation, but the owner must decide record identity or source eligibility (NAO→NAO6; HUBO generation; KAIST). |
| CONFLICT | 2 | Two first-party pages disagree for the same edition (A2 Ultra EN vs JP). The conflict is preserved. |
| NOT_RECOVERABLE | 27 | Checked and not stated (10), blocked (6), or stated ambiguously and excluded by the conservative policies (11). |

**Effect on P0 UNKNOWN (baseline 119):**

| If the owner approves… | P0 UNKNOWN | Rate |
|---|---|---|
| CLEAN rows only | 107 | **41.5%** |
| + the policies those rows need (D2, D9, D10, D12) | 103 | 39.9% |
| + the identity decisions (NAO6, HUBO generation + KAIST) | 96 | 37.2% |
| + conflict rulings (A2 Ultra) | 94 | 36.4% |

**The <30% target is not reachable from this scope.** Even the best case leaves at least 17 cells short. The 12
CLEAN cells are the actual, evidence-backed recovery. 02A's upper bound for this scope assumed 51 P0 cells; the
actual figure is 12–25. Most of the shortfall comes from values the manufacturers do not publish on any page we
could reach (Walker S2, HUBO, Pepper), not from extraction failures. §6 sets out where the remaining ≥17–30 cells
would have to come from.

## 2. The seven 22/22 robots, starting with the four COMMERCIAL ones

| Robot | P0 CLEAN | Also recoverable | Not recoverable | Source(s) | Notes |
|---|---|---|---|---|---|
| **agibot-a2-ultra** | height 169 cm · weight 69 kg · DoF 40 | runtime 90 min (D9) · speed and payload in CONFLICT | — | agibot.com/products/A2_Ultra (EN) and /jp/ | EN "Speed Max 1.2m/s" and "Max Arm Load ≈2kg" vs JP "最大0.8m/s, 通常使用≤0.6m/s" and "片腕最大負荷 約3kg". P1 CLEAN: hand DoF 6, hand type, vision. Battery is 14.4 Ah only, so no Wh value. |
| **booster-t1** | height 118 cm · weight 30 kg · DoF 23 · walk speed 1.0 m/s · runtime 120 min | — | payload (not in the specification table) | docs.booster.tech T1 product manual, 规格参数 | The T1 page is not on booster.tech marketing; the manual is first-party. Basic and Standard differ only in compute. The 23 DoF row carries the note "4（可拓展）" (expandable). |
| **galbot-g1** | weight 92.5 kg · payload 5 kg per arm · DoF 21 · runtime 480 min | height 173 cm (D10, max of a 650 mm lift range) · speed 1.5 m/s (D2, wheeled) | — | galbot.com/g1 (Chinese spec table) | DoF excludes chassis and end effectors (caveat). Combined arm load of 10 kg goes to `max_dual_arm_load_kg`. P1: mobility WHEELED and vision CLEAN; language UI depends on D4. |
| **ubtech-walker-s2** | — | — | height, weight, speed, DoF (not stated) · payload "负重行走 >15kg" (whole-body, D3) · runtime "持续作业 ≥4小时" (battery swap, D9) | ubtrobot.com EN + CN product pages and the spec image | The "Specifications" image is a hardware-features diagram, not a parameter table. P1: vision CLEAN; hand type depends on D5. |
| softbank-nao | — | height 57.4 · weight 5.48 · DoF 25 · runtime 60 (all IDENTITY) | payload, walk speed (not stated) | Maxtronics NAO6 datasheet (H25600, 2026-06) + maxtronics.com/nao6 | The record is a generic "NAO" attributed to SoftBank. The current first-party publisher is Maxtronics Robotics SAS (aldebaran.com redirects there). P1: 62.5 Wh, SDK, simulation and language UI are all stated. |
| softbank-pepper | — | — | all 6 (BLOCKED) | — | doc.aldebaran.com resets every connection. Maxtronics states no Pepper specs and no longer supports Pepper. SoftBank Robotics America's page has no specs. |
| rainbow-hubo | — | height 173 · weight 82 · DoF 32 for DRC-HUBO+ (IDENTITY + source eligibility) | payload, runtime, speed (not stated) | KAIST pages (originating lab) | Rainbow Robotics presents HUBO only as heritage, with no specs and no current HUBO product. |

## 3. Proposed semantic policies (PROPOSED — none is owner-approved)

These are the most conservative readings that are consistent with existing precedent. A row that depends on a
policy is marked IF_POLICY and is **not** counted as recovered.

| ID | Proposed rule | Precedent / conflict |
|---|---|---|
| **D1 Derived values** | A core column takes a value as stated, or after a pure unit conversion (kWh→Wh, km/h→m/s, h→min, mm→cm), and the conversion is recorded in `spec_caveats`. No arithmetic across separately stated quantities: no V × Ah, no summing per-limb DoF, no dividing a combined load. | Follows H2 972 Wh (from kWh), the T2 note, the H1 note and Figure 03's 5'8" conversion. **Affects:** T2/T1/A2 Ultra/Galbot battery Wh stay UNKNOWN. NAO6's 62.5 Wh is stated directly. |
| **D2 Speed** | `walk_speed_ms` takes a manufacturer **locomotion** speed ("walking speed", "moving speed", or "speed" in a mobility table), including "max" or "up to", with the qualifier recorded in a caveat. A speed with no locomotion context goes to `max_speed`. If `mobility` is UNKNOWN, an unlabelled speed is not mapped. **Owner question inside D2:** does a wheeled base's maximum speed count? | Follows K1 (up to 2 m/s), Figure 03 ("Speed") and H1 ("max moving speed 3.3"). 4NE1 Mini stays out. Galbot depends on the wheeled question. |
| **D3 Payload** | Per-arm or unqualified payload, with a caveat. Never divide a combined or posture-dependent dual-arm figure, and never use a whole-body carry figure. When both rated and peak are stated, take rated. | Follows G1 (arm max load), H2 (rated 7 / peak 15) and the T2 note. **Excludes:** T2 combined 10 kg* and Walker S2 "负重行走 >15kg". |
| **D4 Language UI** | True only when spoken or natural-language interaction is stated in words. Microphones, speakers, alert voice prompts and "large-model support" do not count. | Follows the G1 listen-and-respond precedent. |
| **D5 Hand type** | Records the end effector that ships as standard for this edition. Options go to `dexterous_hand_option` / `hand_module`. | Follows G1 Basic and 4NE1 Mini. Excludes T2, H2 EDU and Galbot (interchangeable). |
| **D6 Edition scope** | A value fills a record only when it is stated for that edition, or explicitly for all editions. It is never propagated from a generic column or name, and ranges are never stored in INT columns. | Follows G1 Basic. **Excludes:** R1 EDU U1–U6, and NAO/HUBO until identity is decided. |
| **D7 Identity first** | NEW_ENTITY claims (Digit 5) do not attach to an existing record. Preliminary or "in development" specifications are not current values. | Follows the Stage E workflow. |
| **D8 Unitree "/"** | "/" is not a stated negative. Unitree defines it nowhere on the G1, H2 or R1 pages (checked). A negative needs words. | **Found:** shop.unitree.com R1 says "Only the EDU version supports secondary development" → `unitree-r1.has_sdk = false` (CLEAN, P1). |
| **D9 Runtime with several modes** *(new)* | When several modes are stated, take the **walking/active** mode, record the others in a caveat, and keep a lower bound ("1.5h+", "≥4h") as stated with a caveat. "Continuous operation" on a robot that swaps batteries is not battery runtime. | Follows K1 ("1 h 10 min walking") and T2 ("continuous walking 2h"). Affects A2 Ultra 90 min, NAO6 60 min (90 in caveat) and Walker S2 (excluded). |
| **D10 Variable geometry** *(new)* | For a height-adjustable robot, `height_cm` takes the manufacturer's stated **maximum** overall height, with the lift range in a caveat. Alternative: leave it UNKNOWN. | No precedent. Affects Galbot G1. |
| **D11 Originating-lab sources** *(new)* | A university or lab that built a robot is **not** first-party for a commercial manufacturer record unless the owner rules otherwise. Proposed: not eligible for core columns. | No precedent. Affects HUBO (KAIST). |
| **D12 Mislabelled rows** *(new)* | When a manufacturer row's label contradicts its unit (a "torque" label with a kg value) but its footnote names the quantity, the value may be used only with the verbatim label in a caveat. Proposed default: not used until the owner rules. | No precedent. Affects R1 "Maximum Torque of Arm Joint【1】 About 2kg", whose footnote is about arm load. |

## 4. Batch 1 held claims, reassessed for edition applicability

| Held claim | Finding (first-party, 2026-10-22) | Result |
|---|---|---|
| 4NE1 Mini `has_sdk`, `ros_support` (HELD_DIRECT) | The reservation page lists "Python SDK, ROS 2 interface" for **both** Standard and Pro. The datasheet is edition-agnostic. The C++ SDK is Pro-only on the reservation page but listed generally on the datasheet; that conflict does not affect the boolean. | **Confirmed CLEAN** for the product (P1, 2 cells) |
| 4NE1 Mini walk speed | Datasheet "Speed Max. 4.6 km/h 2.9 mph", with no locomotion label, and mobility is UNKNOWN | Stays in `max_speed` (D2) |
| Booster T2 ×2 payload / battery Wh / language UI / hand type | Footnote "*The maximum arm payload varies significantly depending on arm posture"; "48 V, 10 Ah" with no Wh; voice prompts only; end effector optional | All four stay UNKNOWN (D3, D1, D4, D5). Lead: the T2 manual's voice-interaction chapter |
| R1 EDU U1 DoF; U3–U6 weight | No per-U-edition values on unitree.com/R1 or shop.unitree.com, which lists only "R1 Air / R1 / R1 EDU". U1–U6 are distributor (reichelt) configurations. | Stay UNKNOWN (D6). **Identity note:** these six records have no Unitree-named edition. |
| Digit 5 reach / runtime | "*preliminary estimates … pre-production hardware"; "Digit 5 is in development"; "our fifth generation humanoid" | Stay UNKNOWN (D7). Not current values. |
| Unitree "/" (G1, H2, R1) | Not defined anywhere on the three pages | Not a negative (D8). Separately, R1 `has_sdk = false` is stated in words. |
| *(new)* R1 payload | unitree.com/R1: "Maximum Torque of Arm Joint【1】 About 2kg" in all three columns; [1] = arm load. **Already held in production** as three claims (one per edition column) but never mapped, so 02A mis-classed this cell as CRAWLED_PAGE_SILENT. Stage 3 lesson: "captured, unmapped", not "extractor missed it". | IF_POLICY (D12 + D3), R1 record only |

## 5. Distinguishing why a value is UNKNOWN

Every manifest row carries `evidence_status`, using the distinctions the brief asks for:

| Status | Meaning | P0 rows |
|---|---|---|
| `STATED` / `STATED_AMBIGUOUS` / `CONFLICT` | The manufacturer publishes something for this field. It is usable now, after a ruling, or not at all under the conservative policies. | 36 (18 / 16 / 2) |
| `CHECKED_NOT_STATED` | **Verified undisclosed on the documents read.** The documents are named in the row. This is not a claim that the manufacturer never published it. | 10 |
| `BLOCKED` | **Unsuccessful retrieval** (Pepper: doc.aldebaran.com resets every connection) | 6 |
| *(not in manifest)* | **Research never performed.** The 67 remaining P0 cells outside this work order (§6). | — |

"Verified undisclosed" is scoped to the documents listed. Walker S2, for example, is undisclosed on UBTECH's EN and CN
product pages; a UBTECH brochure could still state it.

## 6. Source-by-source plan for the remaining P0 gaps (next work order — PROPOSE ONLY)

The remaining 67 P0 cells are outside this work order. Ranked by expected first-party disclosure × cells. "Basis"
is what the owner would need to authorize. No A4 change is needed for agent-assisted research.

| # | Records (P0 cells) | First-party documents to retrieve | Expected yield | Basis |
|---|---|---|---|---|
| 1 | honda-asimo (4) | global.honda ASIMO specification page / Honda press kit | High: Honda published full ASIMO specs | Work order |
| 2 | booster-k1 ×3 (payload, 3) | docs.booster.tech K1 product manual, specifications page (same system as T1) | Medium. T1's table had no payload, so K1 may not either. | Work order |
| 3 | unitree-h1 (payload, runtime, DoF: 3) | unitree.com/H1 spec table, H1 user manual | Medium. DoF is per-limb only (D1). | Work order (A4 prefix not needed for agent research) |
| 4 | Unitree walk speed ×11 (G1, G1 EDU U2, H2, H2 EDU, R1, R1 EDU U1–U6) | Unitree Document Center / support.unitree.com manuals | Uncertain; product pages are silent. U-editions are still subject to D6. | Work order (new host) |
| 5 | figure-02 (6) | figure.ai F.02 page/news (discontinued; the page may be gone; archive only if gone) | Medium–low | Work order |
| 6 | engineered-arts-ameca (5) | engineeredarts.co.uk Ameca datasheet | Some fields probably do not apply (Ameca does not walk). They stay in the denominator. | Work order |
| 7 | xpeng-iron (5) | XPENG IRON launch materials | Low until the generation question (2024 vs Next-Gen) is decided | Work order + identity |
| 8 | 1x-eve (4), 1x-neo (2), apptronik-apollo (2), agility-digit (2), pal-talos (2), ubtech-walker-s1 (3), ubtech-walker-s2 (4: brochure/news) | Manufacturer product pages, datasheets and press kits | Mixed | Work order |
| 9 | tesla-optimus (4), hanson-sophia (3), boston-dynamics-atlas-electric (1), figure-03 DoF (1) | Manufacturer pages | Low: historically undisclosed | Work order |
| 10 | softbank-pepper (6) | doc.aldebaran.com technical pages | High if reachable. Needs a different network route or an owner-supplied capture (no circumvention). | Owner action |
| — | R1 EDU payload ×6 | — | Blocked by D6 unless Unitree states per-edition values | — |

Even with rows 1–4 and 6 succeeding, reaching ≤77 depends on rows 4 and 5. **The target is plausible but not
demonstrated.** The next work order should start with rows 1–3 (cheap, high confidence) and re-measure before
committing to rows 4–9.

## 7. Owner decisions required before any implementation

1. **Policies D1–D12** (§3). Approve, amend or reject each one.
2. **Identity:**
   - (a) Does `softbank-nao` represent NAO6? Who is the manufacturer of record: SoftBank, or Maxtronics as the current publisher? This is a catalogue data change, not a schema change.
   - (b) Which `rainbow-hubo` generation does the record represent, and is the record in scope at all, given that Rainbow no longer offers HUBO?
   - (c) Provenance of the R1 EDU U1–U6 records (distributor-defined editions).
3. **Conflict:** which A2 Ultra page governs speed and payload (EN or JP), or leave both UNKNOWN with the conflict recorded.
4. **Promotion:** each CLEAN row still goes through the existing governed path. That path is: catalogue JSON change (specs + `spec_caveats` + `specs_note` RETRIEVAL statement), then the promotion record in `db/catalogue/promotions/`, then PR, then owner approval, then import. Publication is unchanged.

## 8. Schema changes (identified separately)

**None is required for any manifest row.** Every proposed value fits an existing `robot` column, `spec_caveats` or an
existing `spec_definitions` key. Datasheets, manuals and store pages map to the existing `source_type` values
`MANUFACTURER_SITE` and `MANUFACTURER_STORE`.

Optional proposals, each needing owner approval as its own reviewed change:

- **S1:** a structured per-field gap reason (CHECKED_NOT_STATED / BLOCKED / NOT_RESEARCHED, plus documents and date).
  This would make §5 measurable on every run. It needs a schema or catalogue-format decision.
- **S2:** a spec key for actuation (`spec_definitions.json`, catalogue data, not `schema.sql`).
- **S3:** if D10 is rejected, a min/max height representation for variable-geometry robots (a schema change). Not recommended now.

## 9. Verification notes

- Every CLEAN row was **re-fetched raw by the orchestrator**: the value was seen in the response body, and the
  content sha256 prefix is in the CSV.
- Rows marked `AGENT_RELAYED` came through a research agent's page summariser and were not raw-confirmed. They are
  KAIST (HUBO), the A2 Ultra store JSON, the T2 and Digit 5 footnotes, and the NAO6 language list and hand DoF. No
  CLEAN row depends on them, and they must be re-fetched before any promotion.
- `ho-data-02b/retrieval_log.md` lists every URL fetched in this work order, with its outcome, who fetched it and
  the content hash where one was recorded.
- Third-party pages (Wikipedia, resellers, RoboCup team sheets) were used only as leads, never as values.
