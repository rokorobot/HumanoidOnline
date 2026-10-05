# Alza.cz reference offers — proposed, NOT materialized (2026-10-05)

Status of everything below: **proposal-grade evidence, requires owner review**. Nothing here is an accepted claim, nothing is in `db/catalogue/robots/*.json`, nothing touched production. Alza.cz is an approved *provider/reference source*; it is **not** approved for automated monitoring, so these are dated evidence snapshots, never live prices or live stock.

## Evidence base and its limits

- Two category-listing captures retrieved by plain HTTP GET with the declared `HumanoidOnlineMarketBot/0.1` user agent during the 2026-10-05 inspection (robots.txt read the same day: product/manufacturer paths are not disallowed). Under this WorkOrder Alza is **not** contacted again to create fixtures.
  - `https://www.alza.cz/unitree/v49936.htm?evt=re&exps=humanoidni+robot` — 954,132 bytes, raw sha256 `48a659a67f5316bc273bd189e2255653c7eb64413332873676701a2b51e1d927`
  - `https://www.alza.cz/ubtech/v6390.htm` — 702,863 bytes, raw sha256 `c850ab3930f72d8e11dbd68805bc13fa9396a3a7dfcbf8a451c2a035d236ced5`
- Observation **date** is 2026-10-05; the exact retrieval time was not retained, so `retrieved_at` cannot be supplied to `manual_capture` as a true timestamp. The captures are not committed (900 KB, third-party page); the owner decides whether they are to be preserved.
- The Unitree capture is **page 1 of 3** of the filtered listing (`24 dalších…` pager): the listing is not proven complete, and e.g. *Unitree G1 Basic* did not appear on it.
- Values come from the **category listing**, not the product-detail pages. Product-detail pages were not fetched. VAT basis is not stated on a listing, so none is recorded.
- **All rows need manual reverification on the product page before acceptance** (`requires_reverification`).

## Unitree (existing catalogue robots)

| HumanoidOnline robot | Alza product (listing) | Condition | Price (CZK, as shown) | Availability wording → proposed status | Displayed qty | Identity | Proposal status |
|---|---|---|---|---|---|---|---|
| `unitree-g1-edu-plus-u2` (G1 EDU Plus (U2)) | [Unitree G1 EDU U2](https://www.alza.cz/unitree-g1-edu-u2-d13150281.htm) `uni_G1_U2` | NEW | 917 990,- | Skladem 5 ks → AVAILABLE | 5 | MEDIUM | not yet ingested; requires reverification |
| `unitree-h2-edu` (H2 EDU) | [Unitree H2 EDU](https://www.alza.cz/unitree-h2-edu-d13215768.htm) `uni_H2_EDU` | NEW | 1 309 990,- | Skladem 2 ks → AVAILABLE | 2 | HIGH | not yet ingested; requires reverification |
| `unitree-h2` (H2) | [Unitree H2 Basic](https://www.alza.cz/unitree-h2-basic-d13215767.htm) `uni_H2_basic` | NEW | 863 990,- | Skladem 2 ks → AVAILABLE | 2 | MEDIUM | not yet ingested; requires reverification |
| `unitree-r1-edu-u6` (R1 EDU U6) | [Unitree R1 EDU U6](https://www.alza.cz/unitree-r1-edu-u6-d13408323.htm) `BUN_R1EDU_U6` | NEW | 731 990,- | Skladem 2 ks → AVAILABLE | 2 | HIGH | not yet ingested; requires reverification |
| `unitree-r1-edu-u5` (R1 EDU U5) | [Unitree R1 EDU U5](https://www.alza.cz/unitree-r1-edu-u5-d13408322.htm) `BUN_R1EDU_U5` | NEW | 622 990,- | Skladem 2 ks → AVAILABLE | 2 | HIGH | not yet ingested; requires reverification |
| `unitree-r1-edu-u4` (R1 EDU U4) | [Unitree R1 EDU U4](https://www.alza.cz/unitree-r1-edu-u4-d13408321.htm) `BUN_R1EDU_U4` | NEW | 731 990,- | Skladem 1 ks → AVAILABLE | 1 | HIGH | not yet ingested; requires reverification |
| `unitree-r1-edu-u2` (R1 EDU U2) | [Unitree R1 EDU U2](https://www.alza.cz/unitree-r1-edu-u2-d13408319.htm) `BUN_R1EDU_U2` | NEW | 425 990,- | Skladem 1 ks → AVAILABLE | 1 | HIGH | not yet ingested; requires reverification |

Identity basis per row:

- `unitree-g1-edu-plus-u2`: Alza 'G1 EDU U2' states 29 joint motors + Jetson Orin; catalogue 'G1 EDU Plus (U2)' is 29 DoF + Orin NX. The name differs ('Plus'): reviewer must confirm.
- `unitree-h2-edu`: Alza 'H2 EDU' = catalogue H2 EDU.
- `unitree-h2`: Alza 'H2 Basic' (31 DoF) vs the catalogue's base edition 'H2'; the 'Basic' wording is Alza's: reviewer must confirm.
- `unitree-r1-edu-u6`: Alza U6: 2x BrainCo Revo 2 Touch = catalogue R1 EDU U6.
- `unitree-r1-edu-u5`: Alza U5: 2x BrainCo Revo 2 Basic = catalogue R1 EDU U5.
- `unitree-r1-edu-u4`: Alza U4: 2x Dex3-1 with tactile sensors = catalogue R1 EDU U4.
- `unitree-r1-edu-u2`: Alza U2: 26 DoF, 100 TOPS, no active fingers = catalogue R1 EDU U2 (Smart, no hands).

### Unitree items seen but NOT proposed

- [Unitree G1 EDU U6](https://www.alza.cz/unitree-g1-edu-u6-d13150284.htm) `uni_G1_U6` — 1 349 990,-, Skladem 2 ks: **G1 EDU U6 (41 DoF, Inspire RH56E2): no canonical robot in the catalogue yet**.
- [Unitree G1 EDU U4](https://www.alza.cz/unitree-g1-edu-u4-d13150282.htm) `uni_G1_U4` — 1 242 990,-, Skladem 3 ks: **G1 EDU U4 (43 DoF, Dex3-1): no canonical robot in the catalogue yet**.
- [Unitree G1 EDU U5](https://www.alza.cz/unitree-g1-edu-u5-d13079624.htm) `unitreeG1_EDU` — 1 242 990,-, Skladem 2 ks: **G1 EDU U5 (43 DoF, Inspire RH56DFQ): no canonical robot in the catalogue yet**.
- [Unitree H2 EDU U2](https://www.alza.cz/unitree-h2-edu-u2-d13501544.htm) `BUN_H2EDU_U2` — 1 507 990,-, Skladem 1 ks: **H2 EDU U2 (BrainCo Revo 2 hands bundle): no canonical robot; may be an H2 EDU configuration, owner decision**.
- [Unitree R1 Basic](https://www.alza.cz/unitree-r1-basic-d13408317.htm) `BUN_R1_B` — 229 990,-, Skladem 3 ks: **R1 Basic (24 DoF, no head): the catalogue 'R1' is a 26-joint mid tier; not the same configuration without owner review**.
- 12 further listing items are accessories (batteries, remotes, adapters, hands, charging stations), non-humanoids or other brands: out of scope, nothing proposed.

## UBTECH — Walker Tienkung · Embodied Intelligence (NEW and USED are separate offers)

Canonical robot: `ubtech-walker-tienkung-embodied-intelligence` (new, **unpublished**; model TK2301 in UBTECH's own user manual — see `db/catalogue/robots/`). Not Walker S1/S2.

| Condition | Alza product | Price (CZK) | Availability wording → proposed status | Qty | Observed | Identity | Proposal status |
|---|---|---|---|---|---|---|---|
| **USED** | [Ubtech Walker Tienkung (embodied intelligence)](https://www.alza.cz/ubtech-walker-tienkung-embodied-intelligence-bazar-d13509114.htm) `ubtech2501` | 2 199 990,- (listing shows new-unit price 2 491 790,- beside it; reference only, not an offer) | Použité - skladem 1 ks → AVAILABLE | 1 | 2026-10-05 (date only) | MEDIUM | not yet ingested; requires reverification |
| **NEW** | [Ubtech Walker Tienkung (embodied intelligence)](https://www.alza.cz/ubtech-walker-tienkung-embodied-intelligence-d13233810.htm) `ubtech2501` | 2 491 790,- | Momentálně nedostupné → NOT_AVAILABLE | — | 2026-10-05 (date only) | MEDIUM | not yet ingested; requires reverification |

The USED unit being in stock does **not** make the NEW offer available: the NEW offer is `Momentálně nedostupné` → `NOT_AVAILABLE`; the USED offer is its own row (`condition = USED`).

## Unresolved identity / evidence questions

- Unitree G1 EDU U6 (`uni_G1_U6`): G1 EDU U6 (41 DoF, Inspire RH56E2): no canonical robot in the catalogue yet.
- Unitree G1 EDU U4 (`uni_G1_U4`): G1 EDU U4 (43 DoF, Dex3-1): no canonical robot in the catalogue yet.
- Unitree G1 EDU U5 (`unitreeG1_EDU`): G1 EDU U5 (43 DoF, Inspire RH56DFQ): no canonical robot in the catalogue yet.
- Unitree H2 EDU U2 (`BUN_H2EDU_U2`): H2 EDU U2 (BrainCo Revo 2 hands bundle): no canonical robot; may be an H2 EDU configuration, owner decision.
- Unitree R1 Basic (`BUN_R1_B`): R1 Basic (24 DoF, no head): the catalogue 'R1' is a 26-joint mid tier; not the same configuration without owner review.
- `unitree-g1-edu-plus-u2` ↔ Alza *G1 EDU U2* and `unitree-h2` ↔ Alza *H2 Basic* are MEDIUM confidence (name differs); the reviewer must confirm.
- Product-detail pages must be checked (price, stock, condition, VAT basis) before any claim is accepted; stock quantities change.

## How these would enter the pipeline (owner-authorized steps, none run)

1. `discovery source register alza-cz --name Alza.cz --class DISTRIBUTOR --homepage https://www.alza.cz/ --by <owner>` (stays disabled with no cadence; automated-source ToS stays fail-closed; nothing is reviewed or enabled).
2. Re-retrieve the listing/product pages under an owner work order and record them with `discovery proposals capture alza-cz --url … --body-file … --retrieved-at <true time> --provenance <work order> --by <owner>` (no network; a true retrieval time is mandatory).
3. `discovery proposals ingest-alza --robot-slug … --fetched-page … --body-file … --by …` per robot → review (`accept` with explicit choices) → `claims create` → `claims materialize` → PR → import → `claims verify`.
