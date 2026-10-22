# HO-DATA-02C — Targeted P0 Evidence Recovery: research results (2026-10-22)

**Work order:** "HO-DATA-02C 2026-10-22", AGENT_ASSISTED_RESEARCH (docs/26 R5), confirmed in chat. The scope was
commercially relevant robots with major P0 gaps; historical robots were deprioritized. Retrieval was read-only.
Nothing was written to the catalogue, production or any discovery source.

**Method:** three Sonnet research agents used WebFetch, which returns a model summary of each page. The
orchestrator then re-fetched every candidate value raw with curl. Only values seen in the raw body count as CLEAN.

## Result

| Record | P0 field | Value | Verbatim label | Source | Verification | Recoverability |
|---|---|---|---|---|---|---|
| 1x-neo | walk_speed_ms | 1.4 | `Walking speed 1.4 m/s` (beside `Max run speed 6.2 m/s`) | https://www.1x.tech/neo (sha256 721f1a7a63b54c93…) | RAW_VERIFIED | **CLEAN** |
| 1x-neo | battery_wh (P1) | 842 | `Battery Capacity 842 Wh` | same | RAW_VERIFIED | **CLEAN** (stated directly, no derivation) |
| engineered-arts-ameca | weight_kg | 62 | `Weight 137.7 lbs \| 62 kg` (agent) | https://www.engineeredarts.com/robot/ameca/ | AGENT_RELAYED. The raw page is script-rendered (6 KB, no spec text). | Needs a raw capture |
| engineered-arts-ameca | degrees_of_freedom | 61 | `Ameca features 61 actuated degrees of freedom` (agent: head/face 27 + upper body 34) | same | AGENT_RELAYED | Needs a raw capture. The figure may exclude the legs (caveat). |
| ubtech-walker-s2 | payload_kg | — | `can lift 15kg payload` / `可抬起15公斤重物` | ubtrobot.com EN/CN | RAW_VERIFIED | Not recoverable: a whole-body lift, not an arm payload (D3) |

**CLEAN P0 recovered by 02C: 1** (1X NEO walking speed). Together with the 12 values in PR #191, P0 UNKNOWN would be
106/258 = **41.1%**. If the two Ameca values were confirmed raw, it would be 104/258 = 40.3%.

## Checked and not stated on the first-party documents read (with documents)

| Record(s) | Fields | Documents read | Note |
|---|---|---|---|
| unitree-h1 | payload, runtime, DoF | unitree.com/h1 | H1 payload cell is "/". Only per-limb DoF is given (no derivation, D1). Only 864 Wh is stated for battery, no runtime. The H1-2 column values (27 DoF, 7 kg rated) are a different model and are not propagated. |
| unitree-g1, g1-edu-plus-u2, h2, h2-edu, r1, r1-edu-u1…u6 | walk_speed_ms (11 cells) | unitree.com/g1, /H2, /R1; support.unitree.com (script-rendered, empty); github unitree_rl_gym | No speed anywhere on Unitree first-party pages that could be read. Lead: a reseller-hosted G1 manual (mybotshop) suggests about 2 m/s; the original needs to be found on a Unitree host. |
| booster-k1 ×3 | payload_kg | booster.tech/booster-k1; docs.booster.tech K1 overview + specifications | No payload or load row for any edition |
| ubtech-walker-s2 | height, weight, speed, DoF, runtime | EN/CN product pages, both spec images, /about/news, /product-brochure, /support/downloads | The spec images are component diagrams only. The downloads page is empty. Lead: a Walker S2 brochure and SDK PDF exist on third-party hosts (funduinoshop, storyblok) and need a first-party copy. |
| ubtech-walker-s1 | speed, runtime, DoF | walker-s1 product page, brochure page, downloads | The spec image was not legible to the agent (not raw-checked) |
| agility-digit | speed, DoF, runtime | agilityrobotics.com /solution, /solutions/digit, /solutions/digit-5, /product-sheet | Every page now presents Digit 5 ("in development"). There is no current-Digit spec sheet, and Digit 5 values are not used (D7). |
| apptronik-apollo | speed, DoF | apptronik.com, /apollo/apollo-2 | The page is Apollo 2 (identity question: is the catalogue's "Apollo" this product?). A brochure is linked but was not found. |
| figure-03 | DoF | figure.ai/figure, /news/introducing-figure-03 | No DoF anywhere |
| 1x-neo | DoF | 1x.tech/neo | Only per-part rows (hands 22×2, arms 7×2, neck 3, spine 2, legs 6×2). No total, so no derivation (D1). |

## What this shows

Commercially relevant manufacturers with active product pages mostly leave the remaining P0 gaps undisclosed on
those pages. The remaining recoverable value sits in **manuals, brochures and SDK documents**. These are either
script-rendered (Unitree, Engineered Arts) or found today only on third-party hosts (UBTECH, the Unitree G1 manual).
Both obstacles need an owner decision:

1. An owner-supplied capture or a browser-based retrieval for script-rendered first-party doc centres, with no
   circumvention.
2. A policy on whether a byte-identical copy of a manufacturer PDF hosted by a third party can be used once its
   origin is established. The proposed conservative answer is no: find the first-party URL.

Batch retrieval log (URLs and outcomes): the three agent reports, as relayed in session. Raw captures were made by
the orchestrator for 1x.tech/neo, engineeredarts.com/robot/ameca and ubtrobot.com EN/CN.
