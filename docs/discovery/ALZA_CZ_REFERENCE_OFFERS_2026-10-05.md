# Alza.cz reference offers — proposals and one-time reverification (2026-10-05)

Everything below is a **dated reference snapshot** ("Reference offer verified <timestamp>"), never a live price or live stock. Nothing here is an accepted claim; nothing is in `db/catalogue/robots/*.json`; nothing touched production. Alza.cz is an approved *provider / reference source*, **not** approved for automated monitoring, scheduled fetching or polling.

## Evidence base

**One-time, owner-directed verification** of exactly the 14 authorised product URLs, 2026-10-05 15:06–15:08 UTC: one plain HTTP GET each with the declared `HumanoidOnlineMarketBot/0.1` user agent, 4 s apart, no retries, no circumvention. 11 returned HTTP 200; **3 returned a Cloudflare HTTP 403 block page** and are recorded as *could not reverify* (no retry, no workaround).

| Page | HTTP | Retrieved (UTC, end of request) | Bytes | raw sha256 |
|---|---|---|---|---|
| /unitree-g1-edu-u2-d13150281.htm | 200 | 2026-10-05T15:06:55Z | 755,486 | `666483944c0e4f3f…` |
| /unitree-h2-basic-d13215767.htm | 403 | 2026-10-05T15:07:00Z | 65,624 | `0fbf914037437d21…` |
| /unitree-h2-edu-d13215768.htm | 200 | 2026-10-05T15:07:05Z | 754,239 | `f7fde46d836abe6a…` |
| /unitree-r1-edu-u2-d13408319.htm | 403 | 2026-10-05T15:07:10Z | 65,627 | `172bc1d36acda2d4…` |
| /unitree-r1-edu-u4-d13408321.htm | 200 | 2026-10-05T15:07:14Z | 756,299 | `47ffb9af0c575544…` |
| /unitree-r1-edu-u5-d13408322.htm | 200 | 2026-10-05T15:07:20Z | 756,230 | `352f8f6267464545…` |
| /unitree-r1-edu-u6-d13408323.htm | 403 | 2026-10-05T15:07:24Z | 65,627 | `2ea96d499888e34e…` |
| /unitree-g1-edu-u4-d13150282.htm | 200 | 2026-10-05T15:07:29Z | 759,495 | `7b490866e5a1b560…` |
| /unitree-g1-edu-u5-d13079624.htm | 200 | 2026-10-05T15:07:35Z | 780,037 | `7bd63b18ebe269dc…` |
| /unitree-g1-edu-u6-d13150284.htm | 200 | 2026-10-05T15:07:40Z | 756,153 | `139640c6621ebaee…` |
| /unitree-h2-edu-u2-d13501544.htm | 200 | 2026-10-05T15:07:45Z | 757,004 | `74b5976bab4ba52a…` |
| /unitree-r1-basic-d13408317.htm | 200 | 2026-10-05T15:07:51Z | 757,930 | `1a116954f6db08b4…` |
| /ubtech-walker-tienkung-embodied-intelligence-d13233810.htm | 200 | 2026-10-05T15:07:56Z | 765,406 | `f9d59f990a913002…` |
| /ubtech-walker-tienkung-embodied-intelligence-bazar-d13509114.htm | 200 | 2026-10-05T15:08:01Z | 764,812 | `ce8e316ea8410367…` |

The 200 pages that map to reviewed items were recorded with `manual_capture` and ingested into a **disposable local database** (7 pages → 14 proposals, all `NOT_VERIFIED`, none decided). The pages themselves are third-party, ~750 KB each and are not committed. VAT: each product page's structured offer states `valueAddedTaxIncluded: true` and also shows a `bez DPH` figure; the proposal carries that wording verbatim as the price basis. The structured availability label (`InStock`, `Discontinued`) is kept as markup only; the visible wording decides.

Every verified price and availability **equals** the earlier category-listing value: **no price or availability changed**.

Row status key: **VERIFIED PRODUCT PAGE** · **CATEGORY LISTING ONLY** · **COULD NOT REVERIFY** · **IDENTITY REVIEW REQUIRED**.

## A. Ready for owner claim review (verified product page, identity mapped)

| Canonical robot | Alza product (SKU) | Identity | Condition | Price CZK | Availability → status | Seller wording | Verified (UTC) | Basis | Proposal state | Remaining review |
|---|---|---|---|---|---|---|---|---|---|---|
| `unitree-r1-edu-u4` | [Unitree R1 EDU U4](https://www.alza.cz/unitree-r1-edu-u4-d13408321.htm) (`BUN_R1EDU_U4`) | HIGH | **NEW** | 731 990,- | Skladem 1 ks → AVAILABLE | `Skladem 1 ks` | 2026-10-05T15:07:14Z | VAT included (structured); bez DPH 604 950,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | owner accept / reject |
| `unitree-r1-edu-u5` | [Unitree R1 EDU U5](https://www.alza.cz/unitree-r1-edu-u5-d13408322.htm) (`BUN_R1EDU_U5`) | HIGH | **NEW** | 622 990,- | Skladem 2 ks → AVAILABLE | `Skladem 2 ks` | 2026-10-05T15:07:20Z | VAT included (structured); bez DPH 514 868,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | owner accept / reject |
| `unitree-g1-edu-plus-u2` | [Unitree G1 EDU U2](https://www.alza.cz/unitree-g1-edu-u2-d13150281.htm) (`uni_G1_U2`) | MEDIUM | **NEW** | 917 990,- | Skladem 5 ks → AVAILABLE | `Skladem 5 ks` | 2026-10-05T15:06:55Z | VAT included (structured); bez DPH 758 669,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | confirm identity (MEDIUM) |
| `unitree-h2-edu` | [Unitree H2 EDU](https://www.alza.cz/unitree-h2-edu-d13215768.htm) (`uni_H2_EDU`) | HIGH | **NEW** | 1 309 990,- | Skladem 2 ks → AVAILABLE | `Skladem 2 ks` | 2026-10-05T15:07:05Z | VAT included (structured); bez DPH 1 082 636,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | owner accept / reject |
| `unitree-h2-edu` **config U2** | [Unitree H2 EDU U2](https://www.alza.cz/unitree-h2-edu-u2-d13501544.htm) (`BUN_H2EDU_U2`) | MEDIUM | **NEW** | 1 507 990,- | Skladem 1 ks → AVAILABLE | `Skladem 1 ks` | 2026-10-05T15:07:45Z | VAT included (structured); bez DPH 1 246 273,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | confirm identity + `u2` configuration variant |
| `ubtech-walker-tienkung-embodied-intelligence` | [Ubtech Walker Tienkung (embodied intelligence)](https://www.alza.cz/ubtech-walker-tienkung-embodied-intelligence-d13233810.htm) (`ubtech2501`) | MEDIUM | **NEW** | 2 491 790,- | Momentálně nedostupné → NOT_AVAILABLE | `Momentálně nedostupné` | 2026-10-05T15:07:56Z | VAT included (structured); bez DPH 2 059 331,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | confirm identity (MEDIUM) |
| `ubtech-walker-tienkung-embodied-intelligence` | [Ubtech Walker Tienkung (embodied intelligence)](https://www.alza.cz/ubtech-walker-tienkung-embodied-intelligence-bazar-d13509114.htm) (`ubtech2501_closeout`) | MEDIUM | **USED** | 2 199 990,- | Použité - skladem 1 ks → AVAILABLE | `Použité - skladem 1 ks` | 2026-10-05T15:08:01Z | VAT included (structured); bez DPH 1 818 174,- | 2 proposals (price, availability), `NOT_VERIFIED`, undecided (disposable DB only) | confirm identity (MEDIUM) |

NEW and USED Walker Tienkung rows are independent offers (`condition` is part of the offer identity): the USED unit's stock does not make the NEW offer available, its price does not replace the NEW price, and only the NEW offer can be the headline price.

## B. Still unresolved

| Canonical target | Alza product (SKU) | Condition | Price CZK | Availability wording | Evidence | Why unresolved |
|---|---|---|---|---|---|---|
| `unitree-h2` | [Unitree H2 Basic](https://www.alza.cz/unitree-h2-basic-d13215767.htm) (`uni_H2_basic`) | NEW | 863 990,- | `Skladem 2 ks` | COULD NOT REVERIFY (HTTP 403) — CATEGORY LISTING ONLY | Could not reverify (403); listing value only. H2 Basic → `unitree-h2` is MEDIUM identity and needs reviewer confirmation too. |
| `unitree-r1-edu-u2` | [Unitree R1 EDU U2](https://www.alza.cz/unitree-r1-edu-u2-d13408319.htm) (`BUN_R1EDU_U2`) | NEW | 425 990,- | `Skladem 1 ks` | COULD NOT REVERIFY (HTTP 403) — CATEGORY LISTING ONLY | Could not reverify (403); listing value only. Identity HIGH. |
| `unitree-r1-edu-u6` | [Unitree R1 EDU U6](https://www.alza.cz/unitree-r1-edu-u6-d13408323.htm) (`BUN_R1EDU_U6`) | NEW | 731 990,- | `Skladem 2 ks` | COULD NOT REVERIFY (HTTP 403) — CATEGORY LISTING ONLY | Could not reverify (403); listing value only. Identity HIGH. |
| — (no canonical target) | [Unitree G1 EDU U4](https://www.alza.cz/unitree-g1-edu-u4-d13150282.htm) (`uni_G1_U4`) | NEW | 1 242 990,- | `Skladem 3 ks` | VERIFIED PRODUCT PAGE 2026-10-05T15:07:29Z | G1 EDU U4: configuration of the G1 EDU family; **no new robot row** (owner decision). Product page verified, so the data is retained as evidence for a future configuration-level model. |
| — (no canonical target) | [Unitree G1 EDU U5](https://www.alza.cz/unitree-g1-edu-u5-d13079624.htm) (`unitreeG1_EDU`) | NEW | 1 242 990,- | `Skladem 2 ks` | VERIFIED PRODUCT PAGE 2026-10-05T15:07:35Z | G1 EDU U5: same. |
| — (no canonical target) | [Unitree G1 EDU U6](https://www.alza.cz/unitree-g1-edu-u6-d13150284.htm) (`uni_G1_U6`) | NEW | 1 349 990,- | `Skladem 2 ks` | VERIFIED PRODUCT PAGE 2026-10-05T15:07:40Z | G1 EDU U6: same. |
| — (no canonical target) | [Unitree R1 Basic](https://www.alza.cz/unitree-r1-basic-d13408317.htm) (`BUN_R1_B`) | NEW | 229 990,- | `Skladem 3 ks` | VERIFIED PRODUCT PAGE 2026-10-05T15:07:51Z | **R1 Basic — IDENTITY REVIEW REQUIRED, UNMATCHED.** |

### R1 Basic — what the product page adds

The verified product page (SKU `BUN_R1_B`, NEW, 229 990,- CZK, `Skladem 3 ks`) states "24 DoF (noha 6, paže 5, pas 2)" — **no head joints**, no R1 AIR / R1 / EDU wording, no manufacturer reference. The canonical `unitree-r1` has 26 joints including the head. There is no manufacturer-grade evidence here, so the identity question stays open (R1 AIR, R1, another configuration, or retailer packaging); no proposal exists and none is made.

### Walker Tienkung · Embodied Intelligence / TK2301 — current result

- **NEW** (`ubtech2501`): 2 491 790,- CZK, `Momentálně nedostupné` → `NOT_AVAILABLE` (Alza's structured label says `Discontinued`; the visible wording, "temporarily unavailable", decides, and `DISCONTINUED` is refused as a mapping). Verified 2026-10-05T15:07:56Z.
- **USED** (`ubtech2501_closeout`): 2 199 990,- CZK, `Použité - skladem 1 ks` → `AVAILABLE`. Verified 2026-10-05T15:08:01Z. Raw wording kept in evidence; no stock column.

## Identity decisions applied (owner, 2026-10-05)

Official Unitree structure is G1 / G1 EDU and H2 / H2 EDU, so U2/U4/U5/U6 are retailer or equipment configurations: **no new robot rows**; G1 EDU U4/U5/U6 get no proposals; *H2 EDU U2* is a variant-scoped offer of `unitree-h2-edu`; *H2 Basic* → `unitree-h2` (confirmation); *R1 Basic* unmatched. The existing `unitree-g1-edu-plus-u2` predates this and is not refactored. Follow-up (not in this PR): *Review canonical G1 EDU vs retailer/configuration U2/U4/U5/U6 modelling*.

## Pipeline (owner-authorised steps; none run against production)

1. `discovery source register alza-cz --name Alza.cz --class DISTRIBUTOR --homepage https://www.alza.cz/ --by <owner>` — stays disabled, no cadence; automated-source ToS stays fail-closed.
2. `discovery proposals capture alza-cz --url … --body-file … --retrieved-at <true time> --provenance <work order> --by <owner>` — no network.
3. `discovery proposals ingest-alza --robot-slug … --fetched-page … --body-file … --by …` → review (`accept` with explicit choices) → `claims create` → `claims materialize` → PR → import → `claims verify`.
