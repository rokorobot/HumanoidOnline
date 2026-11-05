# Ecosystem-blend design concepts (2026-11): proposal only

**Status: SUGGESTION. Nothing here is product code. Nothing has been deployed.**
UI-D1 (`docs/07_VISUAL_SYSTEM.md`) is frozen. Adopting any of this needs an owner-ratified amendment.

These pages combine the current HumanoidOnline design with the newer grammar used by
[RentHumanoid.com](https://renthumanoid.com) and [Humanoid.Company](https://humanoid.company).
They use real catalogue data from the live API (snapshot of 2026-11-05). No price or status is invented.

| File | What it shows |
|---|---|
| [`A-home-evolution.html`](A-home-evolution.html) | **Conservative.** Today's home page with four additions: ecosystem rail, offer board in the hero, acquisition pathway, and condensed headings. |
| [`B-home-control-room.html`](B-home-control-room.html) | **Bolder and closer to the family look.** The headline is a fact ("19 humanoids obtainable now"). It adds a full offer board, a requirement-brief "pass" and an ecosystem section. Includes a mobile layout. |
| [`C-robot-detail.html`](C-robot-detail.html) | Robot page (A2 Ultra). Availability and pricing are merged into **one offer board**. A request pass is prefilled from the selected row. |
| [`D-catalogue-board.html`](D-catalogue-board.html) | Catalogue with **mode tabs** (Purchase / Rental / RaaS / Lease) and a **Cards / Board** view switch. |
| `shots/` | Rendered screenshots of the concepts, plus the three live sites for reference. |

Open any `.html` file directly in a browser. Robot photos load from `apps/web/public/robots/`.
Fonts come from Google Fonts here only for the mockups. Production would self-host them.

## What to keep, adopt or drop

| Element | HumanoidOnline today | RentHumanoid / Humanoid.Company | Verdict | Why |
|---|---|---|---|---|
| Paper "data register" for catalogue, compare, specs | Paper | Everything dark | **Keep** | Dense data is easier to read for long stretches on paper. The evidence colours (verified green, caution amber, unknown hatch) were tuned for paper. |
| Robot names in editorial serif | Yes | Condensed caps | **Keep** | This is the tier-1 rule. It also makes HO look like the intelligence brand, not the rental board. |
| Signal colour | Orange | Amber (RH), lime (HC) | **Keep orange** | Family rule: shared structure, one accent per brand. HO orange · RH amber · HC lime. |
| Section headings | Arial bold (fallback) | Archivo condensed 900 | **Adopt** | Much stronger, and shared across the family. UI-D1 already asks for a heavy condensed grotesk (Archivo Black is on its list). |
| Departure board of offers | 4 cards on home; availability and price in two separate tables on detail pages | Live board: mode · region · provider · price · status | **Adopt** | The biggest functional gain. One row answers "can I get it, where, from whom, for how much, how sure are we?" On the detail page it removes the cross-check between two tables. |
| Numbered pathway stepper | None | Six-step adoption pathway | **Adopt** | It explains the funnel and links to RentHumanoid. Orange marks the current position, which UI-D1 already allows. |
| Boarding-pass request form | Lead dialog | Form plus a coloured stub | **Adapt** | The stub shows exactly which offer the request is about. HO version: ink stub, orange only on the send button. This is still lead capture only (AGENTS rule 9). |
| Ecosystem rail | Footer link only | Platform table / footer | **Adopt (thin)** | It shows the family without taking space from the product. |
| Big-number hero | Serif slogan | "04 PLATFORMS", "00 HUMANOIDS…" | **Option (B)** | The headline becomes a data fact. It must be server-rendered and must never show a placeholder 0. |
| "GATE 01" section labels | "01 — Section" index | Gate badges | **Drop** | HO's index already does this job. The airport metaphor belongs to RentHumanoid. |
| Live clock | Catalogue-updated date | Live UTC clock | **Drop** | Decoration with no data in it. The "catalogue updated" date is the honest clock. |
| Scrolling ticker | None | Marquee | **Adapt to a static strip** | Motion competes with data and hurts screen-reader use (R18). |
| Cards, filters, spec tables, UNKNOWN hatch, confidence bars | Yes | — | **Keep** | They are the product's trust layer. |

## Recommendation

Use **B (home) + C (robot page) + D (catalogue board view)**. **A** is the low-risk first step if
you want to change less at once. C and D give the most practical value. B gives the strongest
family identity.

**Owner selection (2026-11-05): B for the home page, plus C and D.** This is a design-direction
choice. It does not yet amend UI-D1 or approve a build.

## Decisions needed before any build

1. Amend UI-D1 to adopt a condensed grotesk (Archivo) and self-host the fonts (`next/font`). Production uses system fallback fonts today.
2. Approve the offer board as the primary obtainability pattern (home + detail).
3. Approve the ecosystem rail and the cross-links to RentHumanoid.

## Follow-up for RentHumanoid (not part of this change)

The RentHumanoid hero shows **"00 HUMANOIDS RENTABLE TODAY"** while it loads, and later
"03". A placeholder zero breaks "unknown stays unknown". Show a dash until the data
arrives, or render the count on the server. Humanoid.Company already does this correctly
("Pending feed" plus a dash).
