# Use-case enrichment review — proposal record (2026-10-08)

Owner WorkOrder of 2026-10-08, steps 1 to 3: audit all published robots against the five use cases, propose
evidence-supported `use_case_fit` rows, and prepare a coverage check. **Everything here is a proposal for owner
review.** Nothing was imported, published, merged or deployed, and no external research was performed: every
association rests on text already recorded in the robot's own catalogue file.

| Measure | Before (`origin/main` @ 0e7e690) | After (this branch) |
|---|---|---|
| Published robots | 42 | 42 |
| Commercially accessible (canonical predicate) | 16 | 16 |
| Robots with at least one use case | 8 | 23 |
| Use-case rows | 9 | 24 |
| Commercially accessible robots with a use case | 6 of 16 | 13 of 16 |
| Other published robots with a use case | 2 of 26 | 10 of 26 |
| Rows on unpublished robots | 0 | 0 |

15 rows are added. No existing row is changed. Three commercially accessible robots stay uncovered, each
for a stated reason (section 5). The target of 16 of 16 is **not** met, because meeting it would have required
forcing a robot into a category its recorded evidence does not support.

## 1. Rules applied

**Evidence criterion.** A robot receives a fit row only when a source recorded in an evidence row of its own file
(commercial-status, offer or deployment evidence) either names the use case or states an enabling capability
for it, with the supporting text quoted or attributed in the file. A summary line with no recorded source does
not qualify, however plausible. Each new note cites the source URL, and a test checks that the URL is already a
recorded source of that robot.

**Score rubric.** A numeric score is given only when the source positions the robot for the use case. Otherwise
the row carries NULL, meaning associated but not rated.

| Band | Research & Education | Manufacturing, Warehouse & Logistics |
|---|---|---|
| 0.85 | Positioned for it, with SDK, ROS and simulation all documented (existing: G1 EDU Plus) | Purpose-built, with a recorded production deployment (existing: Digit) |
| 0.80 | Positioned for it, with secondary development and ROS or simulation documented, possibly qualified by the source | — |
| 0.75 | Positioned for it, with secondary development documented; ROS and simulation not established | — |
| 0.70 | First-party developer or research positioning; specifications not verified (existing: H1) | Stated positioning with a recorded pilot or completed deployment (existing: Apollo, Figure 02) |
| 0.60 | — | First-party positioning and stated delivery; no deployment row, specifications not verified |
| NULL | A source names the use case or an enabling capability, but does not position this edition for it | Same |

**Readiness.** `commercial_readiness` equals the robot's own `commercial_status` when the use case is the product's
stated positioning, and is NULL otherwise. It never exceeds the robot's status and is never set for a robot whose
status is UNKNOWN. A fit score states suitability. It does not state deployment readiness or obtainability.

**Confidence.** The JSON `confidence` key is a reviewer aid. The importer does not store it.

## 2. Safeguard findings

- **NULL scores and matching.** `repository.load_candidates` passes the fit score for the requirement's use case
  to the engine. A NULL score and a missing row both arrive as `None`, and `engine._use_case` then returns the
  neutral 0.5 sub-score with the warning "use-case fit for X is unverified". `is_primary`, `commercial_readiness`,
  `notes` and `limitations` are never read by the engine. A NULL-score row therefore cannot move any match rank.
  It only adds the robot to the use-case page, listed after every scored robot, and to the `robot_count` beside
  it. `test_use_case_fit_safeguards.py` proves this against the database.
- **Numeric scores and matching.** Use-case fit carries 25 of 100 base weight. A score above 0.5 raises a robot
  for that use case, a score below 0.5 lowers it, and a score of 0.6 or more adds a reason line.
- **The 16.** All 16 published robots with an availability offer satisfy the canonical predicate
  (`is_current` and `condition = NEW` and status not NOT_AVAILABLE or DISCONTINUED). Computed from the files and
  confirmed through `robot_commercial_snapshot.is_obtainable` on a fresh import of this branch: 16. No
  discrepancy. `unitree-r1-edu-u5` has one retired offer and qualifies on its other, current offer.
- **Published-only API.** `/api/use-cases` counts and `/api/use-cases/{slug}` rows are filtered on
  `robot.is_published`. No test covered this for the use-case endpoints; one is added. No unpublished robot
  receives a fit in this change, and a test holds that.
- **Figure 02.** Its Manufacturing row is accurate history: readiness DISCONTINUED, a recorded BMW deployment.
  Matching already hard-excludes discontinued robots. On the use-case page it ties Apollo at 0.70 and can list
  first. That is a presentation matter for the profile and page work (step 4), not a data defect. Row unchanged.
- **Schema.** No change needed. `use_case_fit.fit_score` is nullable and the pages already render an unrated row.

## 3. Proposed additions

| Robot | Use case | Score | Confidence | Readiness | Recorded source | Rationale |
|---|---|---|---|---|---|---|
| `booster-k1-educational` | research-education | 0.80 | MEDIUM | COMMERCIAL | [eu.robotshop.com](https://eu.robotshop.com/collections/booster-robotics) | Explicit education positioning + SDK + ROS2 + simulation, each qualified by the source; third-party source. |
| `booster-k1-professional` | research-education | 0.80 | MEDIUM | COMMERCIAL | [eu.robotshop.com](https://eu.robotshop.com/collections/booster-robotics) | Explicit research positioning + SDK + ROS2 + simulation, each qualified by the source; third-party source. |
| `booster-k1-geek` | research-education | NULL | LOW | NULL | [eu.robotshop.com](https://eu.robotshop.com/collections/booster-robotics) | Enabling developer capabilities are sourced; positioning for this configuration is not. Not rated. |
| `booster-t2-professional` | research-education | 0.80 | MEDIUM | COMMERCIAL | [booster.tech](https://www.booster.tech/booster-t2), [docs.booster.tech](https://docs.booster.tech/docs/product-manual/t2/getting-started/specifications/) | Manufacturer positions it as a development platform + SDK + ROS2 + simulation (MEDIUM in the record). |
| `booster-t2-education` | research-education | 0.80 | MEDIUM | COMMERCIAL | [booster.tech](https://www.booster.tech/booster-t2), [docs.booster.tech](https://docs.booster.tech/docs/product-manual/t2/getting-started/specifications/) | Education edition by name + development-platform positioning + SDK + ROS2 + simulation. |
| `booster-t1` | research-education | 0.70 | LOW | COMMERCIAL | [booster.tech](https://www.booster.tech/booster-t1/) | Explicit first-party developer positioning; no verified specifications or developer interfaces. Same band as Unitree H1. |
| `unitree-h2-edu` | research-education | 0.75 | MEDIUM | LIMITED_COMMERCIAL | [unitree.com](https://www.unitree.com/H2), [reichelt.com](https://www.reichelt.com/de/en/shop/product/h2_edu_standard_-_humanoid_research_robot-418482) | EDU edition + manufacturer-stated secondary development; ROS and simulation not established. |
| `unitree-r1-edu-u1` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-r1-edu-u2` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-r1-edu-u3` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-r1-edu-u4` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-r1-edu-u5` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-r1-edu-u6` | research-education | 0.80 | MEDIUM | COMMERCIAL | [unitree.com](https://www.unitree.com/R1) | EDU edition by name + manufacturer-stated secondary development + simulation support; ROS not established. |
| `unitree-h2` | research-education | NULL | LOW | NULL | [reichelt.com](https://www.reichelt.com/de/en/shop/product/h2_basic_-_humanoid_research_robot-418424), [unitree.com](https://www.unitree.com/H2) | A recorded source names the use case, but the enabling capability is stated only for the EDU edition. Not rated. |
| `ubtech-walker-s2` | manufacturing | 0.60 | MEDIUM | COMMERCIAL | [prnewswire.com](https://www.prnewswire.com/news-releases/ubtech-humanoid-robot-walker-s2-begins-mass-production-and-delivery-with-orders-exceeding-800-million-yuan-302616924.html) | First-party industrial positioning + stated delivery; no deployment row and no verified specifications, so below the Apollo/Figure 02 band (0.70), which rests on recorded deployments. |

The full note and limitation text for each row is in the robot's JSON file.

## 4. Existing rows audited

| Robot | Use case | Score | Readiness | Finding |
|---|---|---|---|---|
| `1x-neo` | home | 0.60 | EARLY_ACCESS | Consistent. Unchanged. |
| `agility-digit` | warehouse-logistics | 0.85 | RAAS_DEPLOYMENT | Consistent with the recorded GXO deployment. Unchanged. |
| `apptronik-apollo` | manufacturing | 0.70 | PILOT | Consistent with the recorded Mercedes-Benz pilot. The summary also mentions logistics partners, but no source is recorded, so no Warehouse & Logistics row is added. |
| `engineered-arts-ameca` | events-entertainment | 0.80 | COMMERCIAL | Consistent. The summary's mention of research has no recorded source, so no Research & Education row is added. |
| `figure-02` | manufacturing | 0.70 | DISCONTINUED | Accurate history; see section 2. Unchanged. |
| `unitree-g1-edu-plus-u2` | research-education | 0.85 | COMMERCIAL | Consistent. Unchanged. |
| `unitree-g1-edu-plus-u2` | events-entertainment | 0.50 | COMMERCIAL | Consistent. Unchanged. |
| `unitree-g1` | research-education | 0.75 | COMMERCIAL | **Inconsistent with its own record.** See decision D1. Unchanged pending that decision. |
| `unitree-h1` | research-education | 0.70 | COMMERCIAL | Consistent (SDK, ROS and simulation recorded). Unchanged. |

Every existing readiness value equals the robot's current commercial status. No stale readiness was found.

## 5. Owner decisions

**D1. Re-rate G1 Basic for Research & Education (0.75 to NULL).** The existing note reads "Low price point and
SDK/ROS support make G1 a common research/education platform". The same record states that the base G1 "does
not offer secondary development (SDK) access", which belongs to the EDU tier, and `has_sdk` is not set. ROS and
simulation support are recorded for the G1 platform. Under the rubric the base edition is unrated, the same
treatment proposed for the H2 base edition. This reverses an earlier editorial score on a live, accessible robot,
so it is **not applied** here. Proposed text, if accepted: score NULL, readiness NULL, note stating the missing
secondary development, limitation pointing to the G1 EDU records.

**D2. 4NE1 Mini.** The evidence supports an unrated Research & Education row (section 7). The file is a
governed-promotion record, and `test_catalogue_stub_adopts_existing_robot.py` pins it to carry no use-case row.
Adding one means amending that pin. Not applied.

**D3. AgiBot A2 Ultra and Unitree R1.** No recorded source supports any of the five use cases. Closing either
gap needs new first-party evidence, which is outside this WorkOrder.

**D4. New use-case categories.** Not implemented. Candidates, with the evidence behind each:

| Candidate category | Robots | Evidence on file |
|---|---|---|
| Retail and service | `galbot-g1`, `xpeng-iron`, `softbank-pepper` | Galbot: sourced, in operation. XPENG: sourced, planned. Pepper: quoted in summary, no evidence row. |
| Healthcare and rehabilitation | `softbank-nao`, `softbank-pepper`, `fourier-intelligence-gr-2` | Summary text only. |
| Security and inspection | `1x-eve`, `kepler-k2-forerunner` | Summary text only. |

Only Retail and service has a sourced, operating example today. One robot does not make a useful page.

**D5. Enforcement.** Two checks are prepared (section 8). The database check reports on every run and blocks
only with a flag that no workflow passes. The file-level test does run in CI once this merges: it fails when a
published, commercially accessible robot has no use case and is not on the reviewed gap list.

## 6. Coverage matrix — all 42 published robots

Accessible = satisfies the canonical commercial-accessibility predicate.

| Robot | Status | Accessible | Use cases after this change | Change |
|---|---|---|---|---|
| `1x-eve` | UNKNOWN | no | none | gap |
| `1x-neo` | EARLY_ACCESS | yes | home 0.60 | existing |
| `4ne1-mini` | UNKNOWN | yes | none | gap |
| `agibot-a2-ultra` | COMMERCIAL | yes | none | gap |
| `agility-digit` | RAAS_DEPLOYMENT | yes | warehouse-logistics 0.85 | existing |
| `apptronik-apollo` | PILOT | no | manufacturing 0.70 | existing |
| `booster-k1-educational` | COMMERCIAL | yes | research-education 0.80 | added |
| `booster-k1-geek` | COMMERCIAL | yes | research-education NULL | added |
| `booster-k1-professional` | COMMERCIAL | yes | research-education 0.80 | added |
| `booster-t1` | COMMERCIAL | no | research-education 0.70 | added |
| `booster-t2-education` | COMMERCIAL | no | research-education 0.80 | added |
| `booster-t2-professional` | COMMERCIAL | yes | research-education 0.80 | added |
| `boston-dynamics-atlas-electric` | UNKNOWN | no | none | gap |
| `engineered-arts-ameca` | COMMERCIAL | yes | events-entertainment 0.80 | existing |
| `figure-02` | DISCONTINUED | no | manufacturing 0.70 | existing |
| `fourier-intelligence-gr-2` | PROTOTYPE | no | none | gap |
| `galbot-g1` | COMMERCIAL | no | none | gap |
| `hanson-sophia` | UNKNOWN | no | none | gap |
| `honda-asimo` | UNKNOWN | no | none | gap |
| `kepler-k2-forerunner` | PROTOTYPE | no | none | gap |
| `pal-reem-c` | UNKNOWN | no | none | gap |
| `pal-talos` | UNKNOWN | no | none | gap |
| `rainbow-hubo` | UNKNOWN | no | none | gap |
| `sanctuary-phoenix` | PROTOTYPE | no | none | gap |
| `softbank-nao` | UNKNOWN | no | none | gap |
| `softbank-pepper` | UNKNOWN | no | none | gap |
| `tesla-optimus` | UNKNOWN | no | none | gap |
| `ubtech-walker-s1` | UNKNOWN | no | none | gap |
| `ubtech-walker-s2` | COMMERCIAL | no | manufacturing 0.60 | added |
| `unitree-g1-edu-plus-u2` | COMMERCIAL | yes | research-education 0.85, events-entertainment 0.50 | existing |
| `unitree-g1` | COMMERCIAL | yes | research-education 0.75 | existing |
| `unitree-h1` | COMMERCIAL | yes | research-education 0.70 | existing |
| `unitree-h2-edu` | LIMITED_COMMERCIAL | yes | research-education 0.75 | added |
| `unitree-h2` | LIMITED_COMMERCIAL | no | research-education NULL | added |
| `unitree-r1-edu-u1` | COMMERCIAL | no | research-education 0.80 | added |
| `unitree-r1-edu-u2` | COMMERCIAL | no | research-education 0.80 | added |
| `unitree-r1-edu-u3` | COMMERCIAL | no | research-education 0.80 | added |
| `unitree-r1-edu-u4` | COMMERCIAL | yes | research-education 0.80 | added |
| `unitree-r1-edu-u5` | COMMERCIAL | yes | research-education 0.80 | added |
| `unitree-r1-edu-u6` | COMMERCIAL | no | research-education 0.80 | added |
| `unitree-r1` | COMMERCIAL | yes | none | gap |
| `xpeng-iron` | ANNOUNCED | no | none | gap |

## 7. Robots left without a use case

| Robot | Accessible | Candidate | What the file holds | What would close it |
|---|---|---|---|---|
| `agibot-a2-ultra` | yes | — | Recorded sources state deployment scale ("over a thousand units", "over 20 leading enterprises") and a rental and quote path. None names a sector or application. A rental listing is not a use case. | A first-party A2 Ultra page naming its applications. |
| `unitree-r1` | yes | — | Recorded sources state price, stock and specifications. Unitree's table shows no secondary development for this edition. Nothing positions it for any application. | A first-party statement of intended use for the non-EDU R1. |
| `4ne1-mini` | yes | research-education (unrated) | NEURA's product page lists a Python SDK and ROS 2 interface for both configurations, and a C++ SDK, digital twin access and Neura Gym training readiness for the Pro. The file is a governed-promotion record pinned by `test_catalogue_stub_adopts_existing_robot.py` to carry no use-case row. | Owner decision D2. |
| `1x-eve` | no | warehouse-logistics; new: security | Summary only: "Wheeled humanoid for security and logistics tasks." No evidence row. | One sourced first-party excerpt. |
| `boston-dynamics-atlas-electric` | no | manufacturing | Summary only: "All-electric Atlas developed with automotive partners." No evidence row. | One sourced first-party excerpt. |
| `fourier-intelligence-gr-2` | no | research-education; new: healthcare and rehabilitation | Summary only: "Research/rehabilitation humanoid sold to institutions." The one evidence row is a third-party page with no excerpt. | A Fourier excerpt stating the intended application. |
| `galbot-g1` | no | new: retail and service | Sourced, first-party: Galbot states G1 operates in its Galaxy Space Capsule retail units at more than 170 sites in over 40 cities. Retail operation fits none of the five current use cases. | Owner decision D4. |
| `hanson-sophia` | no | events-entertainment; research-education | Summary only: "Expressive research and entertainment humanoid". Specifications come from a third-party guide; no evidence row. | One sourced first-party excerpt. |
| `honda-asimo` | no | — | Historical platform. No recorded source names an application. | None sought; a historical record. |
| `kepler-k2-forerunner` | no | manufacturing; warehouse-logistics | Summary only: "Industrial/commercial humanoid for manufacturing, logistics and hazardous environments". The one evidence row is a third-party page with no excerpt. | A Kepler excerpt stating the intended application. |
| `pal-reem-c` | no | research-education | SDK and ROS support are recorded from PAL's REEM-C page and owner-ratified, but only in `specs_note`. No evidence row; the "research platform" wording is summary only. | One evidence row quoting PAL's positioning. |
| `pal-talos` | no | research-education | SDK, ROS support and a developer edition are recorded from PAL's TALOS page and owner-ratified, but only in `specs_note`. No evidence row; the "research humanoid" wording is summary only. | One evidence row quoting PAL's positioning. |
| `rainbow-hubo` | no | — | No recorded source names an application. | A first-party excerpt. |
| `sanctuary-phoenix` | no | — | Summary only: "Dexterity-focused humanoid trained through teleoperation." No application is named. | A first-party excerpt. |
| `softbank-nao` | no | research-education; new: healthcare | The summary quotes the current maker: "designed to interact naturally with people in education, research, healthcare and elderly environments". No evidence row carries the quote. | Record the quoted page as an evidence row. |
| `softbank-pepper` | no | research-education; new: retail and service | The summary quotes SoftBank Robotics America listing "retail, banking, education, hospitality and healthcare applications". No evidence row carries the quote. | Record the quoted page as an evidence row. |
| `tesla-optimus` | no | manufacturing | Summary only: "General-purpose humanoid program; internal factory use first." No evidence row. | One sourced first-party excerpt. |
| `ubtech-walker-s1` | no | manufacturing | Summary only: "Industrial humanoid piloted in Chinese EV factories." No evidence row. | One sourced first-party excerpt. |
| `xpeng-iron` | no | new: retail and service | Sourced, first-party: XPENG states "initial commercial-scenario rollouts beginning in XPENG's own stores and campuses". Planned, not delivered; status ANNOUNCED. | Owner decision D4. |

## 8. Checks prepared

- `apps/api/tests/test_catalogue_use_case_fits.py` (no database): fit shape against the schema, readiness never
  above the robot's status, deployments agree with fits, cited sources are recorded sources, no fit on an
  unpublished robot, and coverage of accessible robots against the reviewed gap list.
- `apps/api/tests/test_use_case_fit_safeguards.py` (database): the use-case API excludes an unpublished robot
  from page and count, and a NULL-score row leaves every matching input identical.
- `db/validate_catalogue.py`: prints `use-case coverage: commercially_accessible=N without_use_case=M` on every
  run. `--enforce-use-case-coverage` turns a gap into a failure. No workflow passes the flag.
- `scripts/use_case_matching_regression.py`: the before and after comparison below, reproducible without a
  database.

## 9. Matching comparison

Eight representative buyer requirements, top four results each, `origin/main` against this branch. The three
Research & Education scenarios change, as intended: the newly scored Booster and Unitree EDU editions enter the
top four. Every other scenario, including the no-use-case control, is unchanged. Scores tie often, and ties
resolve by slug in this harness; production also uses evidence freshness.


### Research & Education, no country, any transaction

CHANGED

| Rank | Before | After |
|---|---|---|
| 1 | unitree-g1-edu-plus-u2 (89) | unitree-g1-edu-plus-u2 (89) |
| 2 | unitree-g1 (84) | booster-k1-educational (86) |
| 3 | unitree-h1 (82) | booster-k1-professional (86) |
| 4 | agility-digit (77) | booster-t2-professional (86) |

### Research & Education, Germany, buy

CHANGED

| Rank | Before | After |
|---|---|---|
| 1 | unitree-g1 (88) | booster-k1-educational (89) |
| 2 | unitree-h1 (86) | booster-k1-professional (89) |
| 3 | unitree-g1-edu-plus-u2 (80) | booster-t2-professional (89) |
| 4 | booster-k1-educational (79) | unitree-r1-edu-u4 (89) |

### Research & Education, Czechia, buy, budget up to EUR 40,000

CHANGED

| Rank | Before | After |
|---|---|---|
| 1 | unitree-g1-edu-plus-u2 (86) | booster-k1-educational (91) |
| 2 | unitree-g1 (83) | booster-k1-professional (91) |
| 3 | booster-k1-educational (81) | unitree-g1-edu-plus-u2 (86) |
| 4 | booster-k1-geek (81) | unitree-r1-edu-u4 (84) |

### Manufacturing, no country, payload 10 kg, manipulation required

UNCHANGED

| Rank | Before | After |
|---|---|---|
| 1 | agility-digit (83) | agility-digit (83) |
| 2 | 1x-neo (78) | 1x-neo (78) |
| 3 | unitree-h1 (73) | unitree-h1 (73) |
| 4 | unitree-r1-edu-u4 (73) | unitree-r1-edu-u4 (73) |

### Warehouse & Logistics, United States, RaaS

UNCHANGED

| Rank | Before | After |
|---|---|---|
| 1 | agility-digit (95) | agility-digit (95) |
| 2 | apptronik-apollo (54) | apptronik-apollo (54) |
| 3 | agibot-a2-ultra (54) | agibot-a2-ultra (54) |
| 4 | booster-k1-educational (54) | booster-k1-educational (54) |

### Events & Entertainment, Bulgaria, rent

UNCHANGED

| Rank | Before | After |
|---|---|---|
| 1 | engineered-arts-ameca (89) | engineered-arts-ameca (89) |
| 2 | agibot-a2-ultra (79) | agibot-a2-ultra (79) |
| 3 | agility-digit (57) | agility-digit (57) |
| 4 | apptronik-apollo (54) | apptronik-apollo (54) |

### Home, United States, buy

UNCHANGED

| Rank | Before | After |
|---|---|---|
| 1 | 1x-neo (80) | 1x-neo (80) |
| 2 | engineered-arts-ameca (79) | engineered-arts-ameca (79) |
| 3 | unitree-g1 (79) | unitree-g1 (79) |
| 4 | unitree-h1 (79) | unitree-h1 (79) |

### Control: no use case stated, Germany, buy

UNCHANGED

| Rank | Before | After |
|---|---|---|
| 1 | booster-k1-educational (94) | booster-k1-educational (94) |
| 2 | booster-k1-geek (94) | booster-k1-geek (94) |
| 3 | booster-k1-professional (94) | booster-k1-professional (94) |
| 4 | booster-t2-professional (94) | booster-t2-professional (94) |

3 of 8 scenarios changed.

Decision D1 would not alter any of these top-four lists: with the additions in place, G1 Basic is already
outside the top four of the three Research & Education scenarios.

## 10. Not done

No production import, no publication change, no merge, no deployment, no schema change, no new use-case
category, no robot-profile or use-case-page change, no external research.
