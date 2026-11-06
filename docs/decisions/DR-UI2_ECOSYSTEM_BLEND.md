# DR-UI2 — Ecosystem blend: UI-D1 amendment

**Status:** APPROVED FOR BRANCH BUILD — 2026-11-05, Robert Konecny (product owner), in thread. The owner chose concepts **B (home) + C (robot page) + D (catalogue)** from `docs/design/concepts/2026-11-ecosystem-blend/` and approved writing this amendment and building it on a branch with **no merge and no deployment**. Ratification of the amendment happens when the owner merges the PR.
**Amends:** `docs/07_VISUAL_SYSTEM.md` (UI-D1).
**Related:** AGENTS.md rules 1, 6, 7, 9, 10; UX-01 (buyer-facing labels); MEDIA-01 (`docs/09_MEDIA_CONTRACT.md`).

## 1. Decision

HumanoidOnline adopts the structural grammar it shares with RentHumanoid.com and Humanoid.Company where it helps a buyer. It keeps its own data register where that works better.

### Adopted

| # | Change | Where |
|---|---|---|
| 1 | **Self-hosted typefaces.** The preferred faces UI-D1 already names are now loaded (`next/font`, self-hosted at build time, no third-party request at runtime): **Archivo** (variable width and weight) as DISPLAY-GROTESK, **Playfair Display** as DISPLAY-SERIF, **JetBrains Mono** as MACHINE. The 3-tier hierarchy (§4) is unchanged. | all routes |
| 2 | **Condensed section titles.** Section titles use Archivo at weight 900, width 62%, at a larger size. | all routes |
| 3 | **Ecosystem rail.** A thin strip above every page names the four platforms (HumanoidOnline · RentHumanoid · HumanoidMart · HumanoidLease) with their real status (live platforms link out). It is a `<header>` (banner), **not** a navigation landmark, so the frozen landmark structure (Primary + Footer, and no Primary on robot detail) is unchanged. | all routes |
| 4 | **Offer board (robot page).** The pricing table becomes one board: **one row per offer** (mode × region × provider × configuration × condition). The row shows the availability status, the price (with its full terms), and the evidence for each. A price is only joined to an availability record with exactly the same key; it is never attached to a different seller or region. A price with no availability record, or the reverse, shows the missing side as unknown. | `/robots/[slug]` |
| 5 | **Request from a row.** Each board row has a "Request" action. It opens the existing lead dialog with a stub that shows the selected offer. It preselects the matching preferred transaction and pre-fills an editable message that names the offer. It is still lead capture only (AGENTS rule 9). The buyer's country is **not** prefilled from the offer region. | `/robots/[slug]` |
| 6 | **Obtainable-now board (home).** The four "Obtainable now" cards become a board with one row per commercially accessible robot: modes, headline price with seller and region, maturity. Mode tabs link to the filtered catalogue. | `/` |
| 7 | **Fact headline (home).** The hero leads with the live count from `/api/market-snapshot` ("N humanoids obtainable now"). It is server-rendered and never shows a placeholder 0. The fixed claim "Find the right humanoid." stays inside the H1. | `/` |
| 8 | **Ecosystem section (home).** One section names the four platforms and their status. | `/` |
| 9 | **Catalogue mode tabs + board view.** Tabs All / Purchase / Rental / RaaS / Lease (live counts under the current filters) and a Cards / Board switch (`view=board`). The board is a denser reading of the same list data; it hides nothing. | `/robots` |

### Kept (unchanged)

Paper data register for catalogue, compare, specs and wizard; serif robot names; signal orange as HumanoidOnline's only accent; the three independent dimensions; six price states; UNKNOWN hatch; confidence ramp; EvidenceStamp; MEDIA-01 gallery; filter panel; landmark structure.

### Not adopted

"GATE" section labels (the section index already does this job), a live clock (decoration with no data), a moving ticker (motion competes with data and hurts screen-reader use), the all-dark page (data reads better on paper), and other brands' accent colours.

## 2. Family colour rule

Shared structure, one accent per brand: HumanoidOnline **orange** `#FF4A00`, RentHumanoid **amber** `#FFB400`, HumanoidMart **violet** `#8F6BFF` (live since 2026-11-06), Humanoid.Company **lime** `#BFFF00`. On HumanoidOnline the other accents appear only as small identity marks in the ecosystem rail and section, never on data.

## 3. Follow-ups (not in this change)

- Move the primary photo into the robot identity header (concept C). Needs a MEDIA-01-safe design so provenance badges and "representative" labels move with it.
- RentHumanoid shows "00 HUMANOIDS RENTABLE TODAY" while loading. It should show a dash until data arrives.
