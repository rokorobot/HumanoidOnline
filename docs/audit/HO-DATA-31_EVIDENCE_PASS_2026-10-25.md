# HO-DATA-31: evidence-first pass over the remaining open core cells (2026-10-25)

**Status:** research record only. It proposes no catalogue value, changes no file under `db/catalogue/`, and sends no
message. It was retrieved under `HO-DATA-STANDING 2026-10-22` (`docs/decisions/DR-D1`), initiated by Robert Konecny.
Provenance is `AGENT_ASSISTED_RESEARCH` and the results are not human-verified.

**Why:** the owner asked (2026-10-25) for systematic, evidence-first enrichment of the remaining gaps, maximising the
progress we can make independently. This pass checks whether manufacturer sources that HO-DATA-30 did not try still
hold values, and records the answer once so these cells are not researched again by default.

## 1. Measurement (production = main, 2026-10-25)

The population is the 43 published robots × the 22 core detail-page fields (946 cells). P0 covers 6 of those fields
(258 cells). The denominator is never reduced. NULL means UNKNOWN.

| | UNKNOWN | % | Change vs fixed baseline 619 / 119 @ `4f992c9` (2026-10-22) |
|---|---|---|---|
| Core | **479 / 946** | **50.6%** | −14.8 pp absolute; −22.6% relative (140 cells) |
| P0 | **87 / 258** | **33.7%** | −12.4 pp absolute; −26.9% relative (32 cells) |

- Production and main JSON agree on the NULL state of every one of the 946 cells (checked through the public API).
- The change from the 2026-10-23 figure of 483 comes from the four mobility values in #206.
- The programme target of a −30% relative reduction in core UNKNOWN needs **433 or fewer** UNKNOWN cells (619 × 0.7 = 433.3). That is
  **46 cells** more than today.

## 2. Where the 479 UNKNOWN cells stand

| Status | Cells | P0 | Route |
|---|---|---|---|
| CLOSED-UNKNOWN (HO-DATA-30 close-out register) | 207 | – | reopen only on a manufacturer statement or a ruling change |
| NOT_APPLICABLE (Ameca), kept in the denominator | 3 | – | – |
| **Open, checked in this pass** | **269** | **62** | `ho-data-31/open_cell_register.csv` |

The 269 open cells in the register break down as follows:

| Status 2026-10-25 | Cells | P0 | Meaning |
|---|---|---|---|
| RECHECKED_SILENT | 225 | 50 | silent in the HO-DATA-30 sources and in the sources tried here |
| OWNER_CAPTURE | 17 | 4 | Tesla: tesla.com returns 403 to automated retrieval |
| GOVERNANCE_PINNED | 16 | 5 | XPENG IRON (G3 claim pipeline only) and 4NE1 Mini (variant-scoped) |
| HOLD_OWNER_DECISION | 9 | 1 | raw-verified first-party text whose meaning needs an owner ruling (§4) |
| IDENTITY_MISMATCH | 2 | 2 | the value is for another model (H1-2, Walker C1) |

## 3. What was tried

- Four research agents covered 236 researchable cells, grouped by manufacturer:
  - A: Unitree and Booster;
  - B: UBTECH, Rainbow, Galbot, Fourier, AgiBot, Kepler and NEURA;
  - C: 1X, Figure, Apptronik, Boston Dynamics, Agility and Sanctuary;
  - D: SoftBank/Aldebaran, PAL, Honda, Hanson and Engineered Arts.
- They worked only on manufacturer hosts and the manufacturers' GitHub organisations, under the DR-D1 source rules: no
  resellers, wikis, third-party copies or archives, and no bypass of any gate.
- The orchestrator then checked:
  - every returned record script-verified: `verbatim` and `excerpt` are exact substrings of the saved raw body, and the
    file's sha256 matches;
  - UBTECH's image-only spec graphics (Walker S1/S2), which are hardware callouts with no open-field value;
  - JavaScript-rendered pages in a real browser: `support.unitree.com` G1 developer docs (they repeat the product
    table), Kepler (no product content) and Kepler's developer portal (empty).

**Sources tried for the first time:**
- Unitree's GitHub (`unitree_sdk2`, `unitree_rl_gym`, `unitree_rl_lab`, `unitree_sim_isaaclab`, `xr_teleoperate`) and
  the R1 battery accessory page;
- Booster's manuals and GitHub;
- UBTECH's HKEX interim report and docs site;
- Galbot's developer docs and SDK;
- Fourier's Aurora SDK;
- AgiBot's AimDK;
- about 35 Agility pages and the Boston Dynamics Atlas spec sheet (Rev 10/15/2026);
- 17 Figure news posts, and the 1X discover and support pages;
- Aldebaran NAOqi 2.5/2.8 docs;
- the PAL GitHub org and REEM-C pages;
- the Hanson JS asset;
- Engineered Arts docs.

Raw bodies and per-group reports are kept in the session scratchpad, as in HO-DATA-30. The register holds the URL,
sha256 and verbatim text for every candidate.

**Conclusion:** public first-party material for these 269 cells is effectively exhausted. This is the third
independent sweep (HO-DATA-30 phase 1, phase 2 and this pass), and it found **no clean value**. Further progress
depends on owner acts (§5), not on more research.

## 4. Owner decisions (none of these is in a batch)

| ID | Cells | Evidence (raw-verified) | Question |
|---|---|---|---|
| H31-1 | `battery_wh` = 199 Wh on unitree-r1 + R1 EDU U1–U6 (7, P1) | unitree.com/mobile/R1/battery/ (R1 replacement battery): "6000mAh，199Wh"; the same figure is on shop.unitree.com | Does the accessory pack count as the battery shipped in every R1 edition? If yes, it also replaces the current caveat "Unitree states about 1 hour of battery life but no watt-hour capacity." |
| H31-2 | agility-digit `has_language_ui` (1, P1) | agilityrobotics.com/videos/using-an-llm-to-direct-digit (2023-05-30): a voice command interpreted by an LLM | One-way voice command and pre-Digit 5. Strict DEC-08 and edition reading: keep UNKNOWN (recommended). |
| H31-3 | softbank-pepper `walk_speed_ms` (1, P0) | doc.aldebaran.com 2-5 control-walk: "MaxVelXY maximum planar velocity 0.35 default / 0.55 max" (m/s) | A configurable limit of the wheeled base, not a stated speed. Keep UNKNOWN (recommended). |

Releasing H31-1 would lower core UNKNOWN to 472/946 = 49.9%. Release needs an exact Fast Lane batch and its own
approval.

## 5. What can still move the metric

1. **Manufacturer outreach wave 1 (draft #199, owner sends).** It covers CLOSED and open cells for Unitree, Booster,
   UBTECH, 1X, Aldebaran/Pepper, Maxtronics/NAO6 and PAL. Replies reopen cells as first-party statements.
2. **Owner captures of gated first-party documents:**
   - Tesla Optimus pages (17 cells, 4 P0);
   - the Agility Digit spec sheet (form-gated, 6 open cells);
   - the Engineered Arts developer guide (403);
   - Unitree's image-only manual pages.
3. **Owner rulings that would reopen closed cells.** `closeout_register.csv` lists a `value_if_ruling_reversed` for
   each closed cell (for example DEC-10 reach and span labels, DEC-09 V×Ah, DEC-01 autonomy). Any of those is a policy
   change for the owner, not an agent call.
4. **Tooling:** FL-1 (#194) now turns verified research records into a v2 manifest for 19 of the 22 core fields, with
   the rulings above as review gates. When an answer or a capture arrives, the record goes straight into
   `promotion propose --research` and then one batch approval.
