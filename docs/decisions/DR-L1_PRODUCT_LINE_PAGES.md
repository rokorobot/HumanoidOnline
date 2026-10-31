# DR-L1 — Product-line pages

**Status:** PROPOSED — 2026-10-31, for owner decision (§5). Implements nothing until approved.
**Related:** docs/23 (CITATION-01.2, 01.8, 01.9), docs/24, `aeo-pilot-2026-10-r1` baseline, AGENTS.md rules 2, 6, 7.

## 1. Problem

Buyers and AI answer engines ask about product lines: "How much does the **Unitree G1** cost?", "How tall is the **Unitree G1**?", "Unitree G1 vs **Booster K1**". The catalogue publishes **editions** only (`G1 Basic`, `G1 EDU Plus U2`, `K1 Educational`, `K1 GEEK`, `K1 Professional`). No page answers at the level of the question, so none can be cited for it. R1 baseline: 0 of 40 answers cited HumanoidOnline.

A slug collision makes this worse: `/robots/unitree-g1` is the **G1 Basic** edition, not the line.

## 2. Why not derive lines from names

The name prefix is wrong in both directions. It groups `Figure 02`/`Figure 03` and `Walker S1`/`Walker S2`, which are successive models, not editions of one product. It would also miss any line whose editions are named differently. Line membership is therefore a **fact that needs a source**, like any other catalogue fact.

## 3. Proposal

**Data (one reviewed schema PR):**
- A new table `product_line (id, slug, manufacturer_id, name, source_url, observed_at, is_published)`.
- A nullable column `robot.product_line_id`.
- The catalogue file `db/catalogue/product_lines.json` is the reviewed input, imported like robots.
- Membership cites the manufacturer page that lists the editions together.
- No fact moves to the line. Price, height, availability and specs stay on the editions.

**Page (one PR after the data PR):**
- `/lines/<slug>`, e.g. `/lines/unitree-g1`. H1 is the line name.
- A generated **direct answer** comes first. Template: "The <Line> is sold in <n> published editions. <Edition>: <price state per offer — amount, currency, price type, seller, observed date>. … Standing height <value> (<edition>) …". Every value comes from an edition record and is labelled with its edition. An edition with several offers shows each one; for example, G1 Basic currently holds three PUBLIC prices (USD 13,500, USD 17,900, CNY 85,000), and G1 EDU Plus U2 holds one (CZK 917,990).
- An edition table (price state, availability, height, DoF, SDK access), each row linking to its edition page.
- `ProductGroup` JSON-LD with `hasVariant` pointing to the edition `Product`s.
- Listed in the sitemap and in `llms.txt`. Edition pages link up to their line.
- UNKNOWN stays UNKNOWN per edition. The line never fills an edition gap from a sibling.

**Initial lines (5 lines, 16 published robots):**

| Line | Editions |
|---|---|
| Unitree G1 | `unitree-g1` (G1 Basic), `unitree-g1-edu-plus-u2` |
| Unitree H2 | `unitree-h2`, `unitree-h2-edu` |
| Unitree R1 | `unitree-r1`, `unitree-r1-edu-u1` … `-u6` |
| Booster K1 | `booster-k1-educational`, `-geek`, `-professional` |
| Booster T2 | `booster-t2-education`, `booster-t2-professional` |

Excluded: Figure 02/03 and Walker S1/S2 (different models).

## 4. Out of scope

- No merge or renaming of edition records.
- No change to the `/robots/unitree-g1` slug.
- No line-level price, availability or spec stored anywhere.
- No new comparison semantics.

## 5. Owner decisions

| ID | Decision | Recommendation |
|---|---|---|
| L1 | Line membership is governed data: table + catalogue file + source per line | Approve |
| L2 | URL `/lines/<slug>` | Approve |
| L3 | The direct answer may lead with the **lowest published edition price per currency**, labelled with its edition, price type, seller and source. Prices in different currencies are never converted or compared. This is a derived, reproducible statement under CITATION-01.9 | Approve |
| L4 | The five initial lines in §3 | Approve |
| L5 | Delivery in two PRs: (a) schema + import + API, (b) page + sitemap + llms.txt + JSON-LD | Approve |
