# 09 — MEDIA-01: Verified Product Imagery Contract (v0.1, FROZEN)

Robot imagery is part of HumanoidOnline's verified-intelligence moat, on equal
footing with verified facts, specs, and commercial status. A convincing but fake
robot image is as damaging as a fabricated price. This contract is frozen for
v0.1; changes require product-owner ratification (cf. AGENTS.md rule 1).

## 1. Scope

- **Governed — identity imagery:** any visual that purports to depict a *specific
  named robot* — Catalogue, Robot Detail, Compare, and (Phases 3–5)
  Rent / Buy / Lease.
- **Not governed — decorative / abstract:** landing backgrounds, section
  graphics, generic category illustrations, abstract machine motifs,
  loading / empty-state graphics, editorial concepts that do not represent a
  named robot. The existing dithered/halftone/schematic design language stays here.

## 2. The laws (frozen)

- **MEDIA-01.1 — Identity truth.** A visual attached to a named robot must depict
  that exact robot / model.
- **MEDIA-01.2 — No synthesis.** AI-generated, reconstructed, look-alike, concept,
  or model-substitute visuals are forbidden for catalogue identity imagery. No
  `GENERATED` source type exists for robot identity images anywhere in the system.
- **MEDIA-01.3 — Honest absence.** No verified usable visual → `IMAGE_UNAVAILABLE`.
  The space is never filled synthetically, with a look-alike, or with a silent blank.
- **MEDIA-01.4 — Provenance.** Every usable robot image carries source / provenance
  metadata (the authoritative page establishing it, plus source name / type /
  attribution / verification timestamps).
- **MEDIA-01.5 — Verification.** An image is **not** display-eligible merely because
  an `image_url` is non-null. It must be identity-verified **and** rights-cleared.
- **MEDIA-01.6 — Presentation fidelity.** The design system may resize,
  responsively crop within approved bounds, frame, letterbox, and place UI
  treatment around a verified image. It may **not** generate missing content, alter
  the robot's appearance, remove or replace material parts of the scene in a
  misleading way, redraw the robot, or transform it into a different visual
  representation.
- **MEDIA-01.7 — Commercial inheritance.** The same verified image records feed
  Compare → Rent → Buy → Lease. One image-truth system, never a second marketplace one.
- **MEDIA-01.8 — Catalogue comparability.** The catalogue-card primary image should,
  where available, depict the exact robot in a **front or near-front full-body view**
  suitable for cross-robot visual comparison (height, proportions, silhouette,
  morphology). Catalogue cards render every image in a **standardized frame and scale
  treatment** (same container size, centered, `object-fit: contain` — never stretched
  or proportionally altered) so robots appear comparably presented. The image itself is
  never distorted, redrawn, composited, normalized, or swapped to a different model for
  a better angle. If no sufficiently comparable verified image exists, use the best
  truthful verified image available, or render `IMAGE_UNAVAILABLE` — never fabricate
  comparability.

  **Catalogue primary-image selection priority** (per robot):
  1. verified front full-body
  2. verified near-front full-body
  3. verified front / near-front partial (only if no full-body)
  4. otherwise `IMAGE_UNAVAILABLE`

  (Selection is applied at curation time; at runtime the card prefers a `FRONT`
  `image_type` among the robot's display-eligible images.)

## 3. Acceptable source priority

1. Manufacturer official product images
2. Manufacturer press / media-kit images
3. Official manufacturer video → approved still / frame where permitted
4. Official distributor / integrator imagery
5. Credible third-party editorial photography, with source / licensing recorded

## 4. Identity, rights, and display policy are THREE SEPARATE dimensions (§H2)

An image can unquestionably depict the correct robot yet have uncertain reuse
rights; and the platform may have a legitimate basis to display an image even
without a formal reuse license on record. These are never collapsed:

```
identity_status:  VERIFIED | UNVERIFIED            -- does it depict THIS exact robot?
rights_status:    PERMITTED | ATTRIBUTION_REQUIRED -- legal/licensing EVIDENCE of reuse
                | UNKNOWN | RESTRICTED
usage_basis:      NONE | OFFICIAL_MANUFACTURER_MEDIA -- platform display POLICY
```

We do **not** encode a business decision to display official manufacturer product
media as `rights_status = ATTRIBUTION_REQUIRED` — that would falsely assert an
attribution license was granted. Instead `rights_status` stays `UNKNOWN` (honest:
no license on record) and `usage_basis = OFFICIAL_MANUFACTURER_MEDIA` records the
ratified policy basis (HumanoidOnline displays official manufacturer product media
for the robots it markets, always credited to and linked from the manufacturer).

**Display-eligibility rule (canonical, one place):**

```
display_eligible  ⇔  identity_status = VERIFIED
                     AND rights_status <> RESTRICTED
                     AND ( rights_status IN (PERMITTED, ATTRIBUTION_REQUIRED)
                           OR usage_basis = OFFICIAL_MANUFACTURER_MEDIA )
```

`RESTRICTED` **always** blocks display (even with a usage_basis). `rights_status =
UNKNOWN` never behaves like `PERMITTED` (mirrors `UNKNOWN != 0/false`). A non-null
`image_url` alone is never sufficient.

## 5. Asset vs provenance (two distinct URLs)

- `image_url` — the actual image asset being rendered.
- `source_url` — the authoritative page / media-kit / source establishing provenance.

One field never performs both jobs; we must always be able to reconstruct *why*
HumanoidOnline trusted an image, not merely *what file* was displayed. Also
preserved: `source_name`, `source_type`, `attribution`, `last_verified_at`.

## 6. `IMAGE_UNAVAILABLE` — first-class honest-absence state

An explicit, labelled UI state (like `UNKNOWN` for facts): reads as "no verified
image", distinct from "loading", never a generated fill or look-alike. It is a
*correct* v0.1 state for a robot whose identity + rights could not be honestly cleared.

## 7. Canonical data model — `robot_image`

`robot_image` is the single image-truth system for a named robot (one robot → many
images). `robot.hero_image_url` remains **dormant / non-canonical** for
compatibility (AGENTS.md rule 3) — it is not the read path and is not deleted here.
Fields (exact DDL is implementation-design in this workstream):

```
robot_image {
  id
  robot_id            -> robot(id)
  image_url           -- asset rendered
  source_url          -- provenance page
  source_name
  source_type         -- MANUFACTURER | PRESS_KIT | DISTRIBUTOR | EDITORIAL | VIDEO_FRAME  (no GENERATED)
  image_type          -- FRONT | SIDE | REAR | ACTION | WORKPLACE | DETAIL | DIMENSIONS
  identity_status     -- VERIFIED | UNVERIFIED (depicts THIS exact robot)
  rights_status       -- PERMITTED | ATTRIBUTION_REQUIRED | UNKNOWN | RESTRICTED (legal evidence)
  usage_basis         -- NONE | OFFICIAL_MANUFACTURER_MEDIA (platform display policy)
  is_official
  is_primary
  attribution
  captured_at
  last_verified_at
  created_at / updated_at
}
```

## 8. v0.1 scope

- **System:** the `robot_image` model + provenance/identity/rights; the
  display-eligibility gate; the `IMAGE_UNAVAILABLE` state; a Robot Detail
  real-image gallery with "Official / Verified ✓" + "Source: …" + attribution;
  importer path that records provenance and rejects any `GENERATED` / unsourced
  identity image; validation; tests.
- **Data pass:** investigate **all seven** current catalogue robots for at least one
  exact-model + provenance-verified + display-permitted image. "Populate all seven"
  means *investigate* all seven — it does **not** authorize lowering the
  evidence/licensing threshold to reach 7/7. A robot with no honestly-clearable
  asset resolves to `IMAGE_UNAVAILABLE`. Forbidden shortcuts: "probably official",
  "similar model", "manufacturer homepage image with unclear model", any AI recreation.

## 9. Acceptance gates

- A robot image may **never** become display-eligible solely because `image_url` is
  non-null.
- The display-eligibility negative matrix is tested:

  ```
  correct robot + permitted rights                         → DISPLAY
  correct robot + UNKNOWN rights + OFFICIAL_MANUFACTURER    → DISPLAY (policy basis)
  correct robot + UNKNOWN rights + usage NONE              → IMAGE_UNAVAILABLE
  correct robot + RESTRICTED rights + OFFICIAL_MANUFACTURER → IMAGE_UNAVAILABLE (RESTRICTED wins)
  unverified identity + permitted rights                   → IMAGE_UNAVAILABLE
  missing asset                                            → IMAGE_UNAVAILABLE
  ```

- No `GENERATED` source type is accepted by import, schema, or API.
- Provenance / attribution is surfaced in the UI for every displayed image.
- `docs/07_VISUAL_SYSTEM.md` imagery rule + anti-pattern amended accordingly.

## 10. Non-goals (v0.1)

No image generation of any kind for identity imagery; no scraping that ignores
licensing; no marketplace image system; no CDN / asset-pipeline infrastructure
beyond storing URLs + provenance; no change to the non-governed decorative graphics.
