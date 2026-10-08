# Three new use-case categories — proposal for owner review (2026-10-08)

**Production is unchanged.** Nothing here is imported until the assignments below are approved.
No schema change, no new scoring framework. The method is the original editorial one recorded in
`USE_CASE_REVISION_2026-10-08.md`: scores 0.70 to 0.75 for a clear positioning, 0.60 positioned but
thinly documented, 0.50 to 0.55 a plausible or secondary use; MEDIUM or LOW confidence; readiness
is the robot's own commercial status.

## New categories

| Slug | Name | Published robots |
|---|---|---|
| `retail-service` | Retail & Service | 3 |
| `healthcare-rehabilitation` | Healthcare & Rehabilitation | 3 |
| `security-inspection` | Security & Inspection | 2 |

Each carries a description, typical tasks, typical requirements and key limitations
(`db/catalogue/use_cases.json`). The Healthcare category states in its key limitations that no
clinical validation or regulatory approval is recorded for any robot in the catalogue.

## Before and after

| Measure | Before (main, production) | After |
|---|---|---|
| Categories | 5 | 8 |
| Associations | 57 | 65 |
| Published robots with a use case | 37 of 42 | 38 of 42 |
| Robots with more than one use case | 20 | 23 |
| Commercially accessible robots covered | 15 of 16 | 15 of 16 |
| Events / Home / Manufacturing / Research / Warehouse | 19 / 1 / 8 / 25 / 4 | unchanged |
| Retail & Service | none | 3 |
| Healthcare & Rehabilitation | none | 3 |
| Security & Inspection | none | 2 |

## Proposed assignments (8 new rows)

| Robot | Category | Score | Primary | Confidence | Readiness | Kind | Basis |
|---|---|---|---|---|---|---|---|
| `galbot-g1` | Retail & Service | 0.75 | yes | MEDIUM | COMMERCIAL | Stated operation | Galbot states G1 runs in its own retail units at 170+ sites in 40+ cities in China. No deployment row; own units in China only. |
| `softbank-pepper` | Retail & Service | 0.70 | yes | MEDIUM | none | Positioned | SoftBank Robotics America lists retail, banking and hospitality. |
| `engineered-arts-ameca` | Retail & Service | 0.50 | no | LOW | COMMERCIAL | Plausible | Editorial judgement: greeting and information roles. Cannot handle products. |
| `softbank-nao` | Healthcare & Rehabilitation | 0.60 | no | MEDIUM | none | Positioned | Maker lists "healthcare and elderly environments". |
| `fourier-intelligence-gr-2` | Healthcare & Rehabilitation | 0.55 | no | LOW | PROTOTYPE | Plausible | Catalogue summary: research and rehabilitation humanoid. |
| `softbank-pepper` | Healthcare & Rehabilitation | 0.50 | no | LOW | none | Plausible | Maker lists healthcare among applications. |
| `1x-eve` | Security & Inspection | 0.55 | yes | LOW | none | Plausible | Catalogue summary names security first. |
| `kepler-k2-forerunner` | Security & Inspection | 0.50 | no | LOW | PROTOTYPE | Plausible | Positioned for hazardous environments, from a third-party page. |

Only Galbot G1 has operation stated by its maker. No row is a recorded deployment, and none claims
one. Every Healthcare row is secondary and says in its public limitation: "No clinical validation
or regulatory approval as a medical device is recorded."

## Changes to existing rows (4, no score changed, none removed)

| Robot | Row | Change | Reason |
|---|---|---|---|
| `softbank-pepper` | Events | primary to secondary | Retail & Service is its recorded positioning; one primary per robot. |
| `1x-eve` | Warehouse | primary to secondary | The summary names security first; one primary per robot. |
| `fourier-intelligence-gr-2` | Research | removed the sentence "Rehabilitation use has no category here." | No longer true. |
| `softbank-nao` | Research | removed the sentence "Healthcare use has no category here." | No longer true. |

The primary flag is not used by matching or shown on the site.

## All 42 published robots reviewed

The eight rows above cover seven robots. The other 35 gain nothing, because the catalogue records
no retail, healthcare, security or inspection positioning for them:

- **Governed, untouched:** `xpeng-iron` (identity-and-reference record, `test_xpeng_iron.py`) and
  `4ne1-mini` (DR-A5 section 18.5). The catalogue records no retail positioning for IRON in any
  case. Both need a separate owner ruling.
- **Considered and left out:** `agibot-a2-ultra` (recorded sources name no sector),
  `hanson-sophia` (public appearances, no service role recorded), `1x-neo` (home only),
  `honda-asimo` and `rainbow-hubo` (no application recorded).
- **No relevant positioning:** the industrial robots (Digit, Apollo, Atlas, Figure 02, Optimus,
  Walker S1, Walker S2), the research platforms (REEM-C, TALOS, Phoenix, Unitree H1) and the
  Unitree and Booster development and base editions.

## Implementation notes

- `db/import_catalogue.py`: the use-case upsert now also writes `typical_requirements` and
  `key_limitations` (columns that already exist and that the detail page already renders).
- The five existing categories still have neither field, in the files or in production. Adding
  them is an owner option, not done here.
- Homepage "Explore by use case": shows the 8 categories in two rows of four. The former eighth
  tile "All use cases" is removed; otherwise Warehouse & Logistics would have dropped off the
  homepage. `/use-cases` is unchanged and shows two full rows.
- Find a Humanoid reads its options from the API, so the three categories appear without a code
  change. `scripts/use_case_matching_regression.py` gains one scenario per new category.

## Effect on matching

The eight existing scenarios are identical before and after. For the three new categories, with no
other requirement stated, the top results do not change either: none of the newly assigned robots
except Ameca has an availability offer, and Ameca's 0.50 equals the neutral value. A buyer choosing
Retail & Service today therefore still sees commercially available robots first, with the
"use-case fit is unverified" warning. This is the engine working as designed, not a defect; it
changes only when a fitted robot gains a recorded offer.

## Verification

Fresh local database: bootstrap, full catalogue import and `validate_catalogue.py` pass
(65 associations, 38 published robots, coverage gap `4ne1-mini` only).
