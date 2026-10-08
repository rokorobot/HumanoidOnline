# Use-case revision — original methodology applied to all published robots (2026-10-08)

Proposal for owner review. **Production is unchanged** and still shows the 24 associations imported earlier today.
Only `use_case_fits` arrays in the catalogue files change. No schema, scoring framework or new test is introduced.

## Method

The first catalogue fits (WS2B, July 2026, and G1 EDU Plus, August 2026) were editorial judgements, as the
catalogue README states for `MEDIUM` confidence: "a reasonable editorial judgement (most subjective
`use_case_fit` rows)". They were not gated on an evidence row. Their conventions, applied here unchanged:

- **Basis:** the robot's recorded positioning, capabilities and deployments.
- **Scores:** 0.80 to 0.85 purpose-built and proven; 0.70 to 0.75 clearly positioned; 0.60 positioned but early
  or thinly documented; 0.50 a secondary or plausible use. Seed scores were discounted by 0.05 to 0.15.
- **Several use cases per robot:** one primary, others secondary at a lower score (as Apollo and Ameca in the
  seed, and G1 EDU Plus in the catalogue).
- **Confidence:** MEDIUM for a clear positioning, LOW for an indicative judgement.
- **Readiness:** the robot's own commercial status. Left empty where the status is UNKNOWN, or where the
  application itself is undemonstrated for an industrial use.

Demonstrated and plausible uses are kept apart in the text of each row. A plausible use says "Editorial
judgement" in its note and "Not a demonstrated application" in its public limitation, scores 0.50 to 0.60 and
carries LOW confidence. No deployment, capability or commercial fact is added anywhere.

The earlier pass today required a sourced excerpt for every row. That was stricter than the original method and
is why it defaulted to Research & Education.

## Before and after

| Measure | Production today | Revised |
|---|---|---|
| Associations | 24 | 57 |
| Published robots with a use case | 23 of 42 | 37 of 42 |
| Robots with more than one use case | 1 | 20 |
| Commercially accessible robots covered | 13 of 16 | 15 of 16 |
| Home | 1 | 1 |
| Warehouse | 1 | 4 |
| Manufacturing | 3 | 8 |
| Events | 2 | 19 |
| Research | 17 | 25 |

Home stays at one robot: NEO is the only published robot positioned for domestic use. Events grows most because
demonstration is the realistic second use of the Unitree and Booster development platforms, and the only use of their non-programmable base editions.

## Changes to the current 24 associations

All 24 are retained. Four are adjusted:

| Robot | Change | Reason |
|---|---|---|
| `booster-k1-geek` | Research unrated to 0.70 | Same SDK, ROS2 and simulation support as its sibling configurations; the original method scores that. Lower than their 0.80 for the 30 min runtime and short warranty. |
| `ubtech-walker-s2` | Manufacturing 0.60 to 0.70 | Mass-produced and delivered industrial model; must not rank below its predecessor Walker S1 (0.60). |
| `unitree-g1` | Research stays unrated (decision D1), now secondary | Events becomes its primary use. |
| `unitree-h2` | Research stays unrated, now secondary | Events becomes its primary use. |

## All 42 published robots

| Robot | Accessible | Production today | Revised | Basis of new or changed rows |
|---|---|---|---|---|
| `1x-eve` | no | none | Warehouse 0.50 | Editorial judgement, plausible. |
| `1x-neo` | yes | Home 0.60 | unchanged |  |
| `4ne1-mini` | yes | none | none | Held by governance, not by evidence. DR-A5 section 18.5 registers this robot's use cases as a governed claim with no catalogue home. Under the original method it would be Research & Education at about 0.65. Needs an explicit owner decision to change that ruling. |
| `agibot-a2-ultra` | yes | none | Events 0.55 | Editorial judgement, plausible. |
| `agility-digit` | yes | Warehouse 0.85 | Warehouse 0.85, Manufacturing 0.50 | Warehouse demonstrated (GXO deployment). Manufacturing plausible. |
| `apptronik-apollo` | no | Manufacturing 0.70 | Manufacturing 0.70, Warehouse 0.60 | Manufacturing demonstrated in pilot. Warehouse plausible from the pilot's material-movement tasks. |
| `booster-k1-educational` | yes | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `booster-k1-geek` | yes | Research unrated | Research 0.70, Events 0.50 | Research: recorded developer interfaces. Events: competition result cited by the seller. |
| `booster-k1-professional` | yes | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `booster-t1` | no | Research 0.70 | Research 0.70, Events 0.50 | Events: competition context stated by the maker. |
| `booster-t2-education` | no | Research 0.80 | unchanged |  |
| `booster-t2-professional` | yes | Research 0.80 | unchanged |  |
| `boston-dynamics-atlas-electric` | no | none | Manufacturing 0.50 | Editorial judgement, plausible. |
| `engineered-arts-ameca` | yes | Events 0.80 | Events 0.80, Research 0.50 | Events positioned by the maker. Research plausible. |
| `figure-02` | no | Manufacturing 0.70 | unchanged |  |
| `fourier-intelligence-gr-2` | no | none | Research 0.70 | Editorial judgement from recorded positioning. |
| `galbot-g1` | no | none | none | Recorded operation is in retail kiosks, which fits none of the five categories. Not forced into one. |
| `hanson-sophia` | no | none | Events 0.70, Research 0.50 | Editorial judgement from recorded positioning. |
| `honda-asimo` | no | none | none | Historical platform; the catalogue records no application and no current status. |
| `kepler-k2-forerunner` | no | none | Manufacturing 0.60, Warehouse 0.50 | Positioned, from a third-party page. |
| `pal-reem-c` | no | none | Research 0.65 | Editorial judgement from recorded positioning and developer interfaces. |
| `pal-talos` | no | none | Research 0.75 | Editorial judgement from recorded positioning and developer interfaces. |
| `rainbow-hubo` | no | none | none | The catalogue records no specifications, application or status. |
| `sanctuary-phoenix` | no | none | Research 0.50 | Editorial judgement from recorded positioning. |
| `softbank-nao` | no | none | Research 0.75 | Positioned by the maker. |
| `softbank-pepper` | no | none | Events 0.60, Research 0.50 | Positioned by the maker. |
| `tesla-optimus` | no | none | Manufacturing 0.50 | Editorial judgement, plausible. |
| `ubtech-walker-s1` | no | none | Manufacturing 0.60 | Editorial judgement from recorded positioning; pilots not recorded as deployments. |
| `ubtech-walker-s2` | no | Manufacturing 0.60 | Manufacturing 0.70 | Positioned by the maker; delivery stated, no deployment row. |
| `unitree-g1-edu-plus-u2` | yes | Research 0.85, Events 0.50 | unchanged |  |
| `unitree-g1` | yes | Research unrated | Events 0.50, Research unrated | Editorial judgement, plausible. |
| `unitree-h1` | yes | Research 0.70 | unchanged |  |
| `unitree-h2-edu` | yes | Research 0.75 | Research 0.75, Events 0.50 | Editorial judgement, plausible. |
| `unitree-h2` | no | Research unrated | Events 0.50, Research unrated | Editorial judgement, plausible. |
| `unitree-r1-edu-u1` | no | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1-edu-u2` | no | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1-edu-u3` | no | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1-edu-u4` | yes | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1-edu-u5` | yes | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1-edu-u6` | no | Research 0.80 | Research 0.80, Events 0.50 | Editorial judgement, plausible. |
| `unitree-r1` | yes | none | Events 0.50 | Editorial judgement, plausible. |
| `xpeng-iron` | no | none | none | Held by governance: a governed record pinned as identity and reference only (`test_xpeng_iron.py`). Under the original method it would be Events at 0.50, planned and not delivered. Needs an explicit owner ruling. |

## Left without a use case

- **`4ne1-mini`**: Held by governance, not by evidence. DR-A5 section 18.5 registers this robot's use cases as a governed claim with no catalogue home. Under the original method it would be Research & Education at about 0.65. Needs an explicit owner decision to change that ruling.
- **`xpeng-iron`**: Held by governance: a governed record pinned as identity and reference only (`test_xpeng_iron.py`). Under the original method it would be Events at 0.50, planned and not delivered. Needs an explicit owner ruling.
- **`galbot-g1`**: Recorded operation is in retail kiosks, which fits none of the five categories. Not forced into one.
- **`honda-asimo`**: Historical platform; the catalogue records no application and no current status.
- **`rainbow-hubo`**: The catalogue records no specifications, application or status.

## Effect on matching

Same eight buyer requirements as the earlier review, `origin/main` against this branch. A score of 0.50 equals
the neutral value a robot receives with no row, so the plausible rows add the robot to a use-case page without
moving its match score.

**Research & Education, Czechia, buy, budget up to EUR 40,000**

| Rank | Before | After |
|---|---|---|
| 1 | booster-k1-educational (91) | booster-k1-educational (91) |
| 2 | booster-k1-professional (91) | booster-k1-professional (91) |
| 3 | unitree-g1-edu-plus-u2 (86) | booster-k1-geek (88) |
| 4 | unitree-r1-edu-u4 (84) | unitree-g1-edu-plus-u2 (86) |

**Warehouse & Logistics, United States, RaaS**

| Rank | Before | After |
|---|---|---|
| 1 | agility-digit (95) | agility-digit (95) |
| 2 | apptronik-apollo (54) | apptronik-apollo (57) |
| 3 | agibot-a2-ultra (54) | agibot-a2-ultra (54) |
| 4 | booster-k1-educational (54) | booster-k1-educational (54) |

**Events & Entertainment, Bulgaria, rent**

| Rank | Before | After |
|---|---|---|
| 1 | engineered-arts-ameca (89) | engineered-arts-ameca (89) |
| 2 | agibot-a2-ultra (79) | agibot-a2-ultra (80) |
| 3 | agility-digit (57) | agility-digit (57) |
| 4 | apptronik-apollo (54) | apptronik-apollo (54) |

3 of 8 scenarios change; the rest are identical.

## Not done

No production import, no publication change, no schema change, no new category, no new tests. Three existing
tests were updated where the revision changes their expected values: the gap register (now only `4ne1-mini`),
the import-scope dependency list, and the G1 Basic matching check for Events.
