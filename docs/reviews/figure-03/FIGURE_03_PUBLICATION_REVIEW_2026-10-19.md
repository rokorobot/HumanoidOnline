# Figure 03: publication review (2026-10-19)

**Status:** review package for the owner's publication decision.
- `figure-03` stays **unpublished** (`is_published = false`).
- This PR changes only the catalogue summary; it adds no image.
- Nothing is merged, imported or published without separate owner authorization.

## 1. Summary (owner-approved text, the only catalogue change in this PR)

> Figure 03 is Figure AI's third-generation general-purpose humanoid robot, succeeding the retired Figure 02. Manufacturer-reported specifications include a 20 kg payload, 1.2 m/s speed and five-hour runtime, with measurement conditions unspecified. Figure has documented the robot's arrival at BMW Group Plant Spartanburg. General purchase availability and public pricing remain unconfirmed.

Every statement restates a fact already recorded with evidence (sections 2–5). No new claim is introduced.

## 2. Specifications and measurement caveats (unchanged)

**Source:**
- Figure's official product page, https://www.figure.ai/figure (stat block).
- Captured 2026-10-18 by automated discovery of the owner-authorized source `figure-ai-official`.
- Promoted in owner-approved batch 1 (2026-10-19).
- It is an automated capture, not independently verified.

| Spec | Value | Caveat (as published on the record) |
|---|---|---|
| Height | ≈173 cm | Figure states 5'8"; converted and rounded |
| Weight | 61 kg | — |
| Payload | 20 kg | Kind of payload (rated, peak, per arm) not stated |
| Speed | 1.2 m/s | Stated as the robot's speed; conditions not given |
| Runtime | 300 min (5 h) | Duty cycle not stated |

All other spec fields are UNKNOWN (NULL), never defaulted. That includes DOF, hands, battery, autonomy and SDK.

## 3. Figure 02 → Figure 03 succession

- `figure-03` is a separate, successor-generation record. It is never merged with `figure-02`.
- `figure-02` is DISCONTINUED and published.
- The relationship is stated in the Figure 03 summary and specs note. The schema has no structured predecessor field, and none is added here.

## 4. Commercial status: PILOT (owner decision 2026-10-04)

The evidence is two manufacturer posts, both retrieved 2026-10-04 by agent-assisted research (confidence MEDIUM, not human-verified):

- **Figure × Catalyst Brands agreement** (2026-05-26). It is a commercial agreement to deploy "Figure humanoids". The post does not name Figure 03 specifically.
- **"F.03 at BMW"** (2026-06-30): "our latest generation robot - Figure 03 - arrived in Hall 52, one of the assembly and logistics halls at BMW Group Plant Spartanburg."

COMMERCIAL, RAAS_DEPLOYMENT and EARLY_ACCESS are not claimed.

## 5. BMW evidence and its limitations

- **Supports:** Figure 03 was physically present at a customer facility (BMW Spartanburg, Hall 52) by the end of June 2026. That backs the PILOT classification.
- **Does not establish:** operational deployment, a start date, duration, task scope, unit count or commercial terms.
- **Owner decision:** no structured `deployment` record is created at this stage. The evidence stays attached to the commercial-status classification only.

## 6. Pricing and availability

- No pricing offer and no availability offer exist. Both display as **UNKNOWN**, never as "not available" or zero.
- Third-party catalogue prices (e.g. competitor listings) are radar only under DATA-D1. They are not used.

## 7. Primary image: candidate only, retained privately, final metadata NOT assigned

- **Not in the repository:** the owner-selected candidate image is held privately by the owner, outside the repository and the website. No image binary is committed, and no `robot_image` row is created.
- **Identity:** the image depicts Figure 03 (chest marking "F03", Figure logo; front full-body; sha256 `bdc94e53…`). The visual identity is consistent with the robot.
- **What it is:** an **AI-edited cutout** with the background removed, derived from an owner-supplied photograph. It is **not** an unmodified manufacturer original.
- **Underlying photograph:** the owner identified it as the TIME photograph in "Figure 03 Is The Robot in Your Kitchen" (https://time.com/7324233/figure-03-robot-humanoid-reveal/). The article credits it "Photograph by Spencer Lowell for TIME".
- **Rights:** republication rights are **not confirmed**. The photograph is commissioned editorial work by TIME, not Figure media.
- **Before final catalogue image metadata:** confirm identity sign-off, provenance (retrieval page and edit history), and republication rights or an explicit owner rights decision.
- **Fallback:** if Figure 03 is published before then, the site shows **"Image unavailable"** (MEDIA-01), never a substitute image.

## 8. Missing information

- No capabilities and no use-case fits, so the detail page will show fewer sections than most robots.
- Not recorded: announcement year (Figure's launch post), model code, DOF, hand type and DOF, battery capacity, autonomy level, SDK/API.
- No price, availability or confirmed deployment.
- No display-eligible image (section 7).

## 9. Publication-integrity assessment

| Area | Assessment |
|---|---|
| Specifications | Publishable. Manufacturer-sourced, provenance kept, caveats visible on the detail page. |
| Summary | Publishable. Restates evidenced facts only. |
| Commercial status | Publishable as PILOT. Evidence is manufacturer posts (MEDIUM); limits stated. |
| Deployment | Correctly absent. Arrival ≠ deployment. |
| Pricing / availability | Correctly UNKNOWN. |
| Image | **Not ready.** Rights and provenance are unconfirmed; it would publish as "Image unavailable". |
| Completeness | Thin (no capabilities or fits). Acceptable for an honest record, but weaker than peers. |

**Owner decisions required:**
1. Publish Figure 03 now, with "Image unavailable", or wait.
2. Image path: confirm rights for the TIME-derived cutout, or source a Figure-published full-body image.

## 10. Rehearsal (local restore of a read-only production dump, 2026-10-19)

- **Command:** `import_catalogue.py --only figure-03`, run twice.
- **Run 1:** 1 robot row updated; nothing else written.
- **Run 2:** a no-op.
- **Preflight** with `db/catalogue/figure_03_summary_expected.json`: **PASS**. 1 business change (robot `figure-03` CHANGED, summary only); 0 history rows appended.
- **Identity check:** **PASS**. 0 ID changes, 0 added, 0 removed; touched = only `robot figure-03`. Dangling audit targets 25, unchanged.
- **After the run:** `is_published` = false, `commercial_status` = PILOT, no offers changed.
- **Before any production import:** re-rehearse on a fresh dump (production has had other changes since this dump), and cut a fresh Neon safety branch.
