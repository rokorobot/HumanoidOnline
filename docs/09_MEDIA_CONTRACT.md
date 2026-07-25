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

## 3. Acceptable source priority

1. Manufacturer official product images
2. Manufacturer press / media-kit images
3. Official manufacturer video → approved still / frame where permitted
4. Official distributor / integrator imagery
5. Credible third-party editorial photography, with source / licensing recorded

## 4. Identity and rights are SEPARATE dimensions

An image can unquestionably depict the correct robot yet have uncertain reuse
rights. The two are never collapsed into one flag.

```
identity_status:  VERIFIED | UNVERIFIED
rights_status:    PERMITTED | ATTRIBUTION_REQUIRED | UNKNOWN | RESTRICTED
```

**Display-eligibility rule (canonical):**

```
display_eligible  ⇔  identity_status = VERIFIED
                     AND rights_status IN (PERMITTED, ATTRIBUTION_REQUIRED)
```

`rights_status = UNKNOWN` must **never** behave like `PERMITTED` (this mirrors the
platform's `UNKNOWN != 0/false` doctrine). A non-null `image_url` alone is never
sufficient — the eligibility rule is the single gate, applied in one place.

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
  identity_status     -- VERIFIED | UNVERIFIED
  rights_status       -- PERMITTED | ATTRIBUTION_REQUIRED | UNKNOWN | RESTRICTED
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
  correct robot + permitted rights        → DISPLAY
  correct robot + UNKNOWN rights           → IMAGE_UNAVAILABLE
  correct robot + RESTRICTED rights        → IMAGE_UNAVAILABLE
  unverified identity + permitted rights   → IMAGE_UNAVAILABLE
  missing asset                            → IMAGE_UNAVAILABLE
  ```

- No `GENERATED` source type is accepted by import, schema, or API.
- Provenance / attribution is surfaced in the UI for every displayed image.
- `docs/07_VISUAL_SYSTEM.md` imagery rule + anti-pattern amended accordingly.

## 10. Non-goals (v0.1)

No image generation of any kind for identity imagery; no scraping that ignores
licensing; no marketplace image system; no CDN / asset-pipeline infrastructure
beyond storing URLs + provenance; no change to the non-governed decorative graphics.
