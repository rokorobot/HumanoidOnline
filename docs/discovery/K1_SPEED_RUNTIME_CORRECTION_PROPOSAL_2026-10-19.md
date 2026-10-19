# Booster K1: walking speed and runtime correction proposal (2026-10-19)

**Status: DECIDED (owner, 2026-10-19). Documentation only:** the correction itself ships in a
separate scoped PR with its own manifest, rehearsal and owner approval. Until then the six values
held in Batch 2 (PR #170) stay as they are.

## What the two sources state

| Edition (catalogue) | Catalogue today | RobotShop EU listing (2026-08-16, in the record's summary) | Booster official page (`booster.tech/booster-k1?target=en`, observed 2026-10-18; discovery claim) |
|---|---|---|---|
| K1 GEEK (`booster-k1-geek`) | walk_speed_ms **0.40**; runtime_minutes **30** | "a 2Ah battery giving **~30 min runtime at 0.4 m/s**" | Walking Speed **2 m/s** (`fc370db3`); Battery life **20 min (walking at 1.1 m/s)** (`c6f067a5`) |
| K1 Educational (`booster-k1-educational`) | 0.40; 80 | "a 5Ah battery giving **~80 min runtime at 0.4 m/s**" | **2 m/s** (`89e5d72c`); **1 h 10 min (walking at 1.1 m/s)** (`a55b65de`) |
| K1 Professional (`booster-k1-professional`) | 0.40; 80 | "a 5Ah battery giving **~80 min runtime at 0.4 m/s**" | **2 m/s** (`f79a4674`); **1 h 10 min (walking at 1.1 m/s)** (`57368c23`) |

## Finding

- **`walk_speed_ms = 0.40` is a test condition, not a walking-speed specification.** RobotShop
  states 0.4 m/s as the speed at which its runtime was measured. Booster's own specification
  states a walking speed of **2 m/s**, with no other qualifier, for all three editions.
- **Neither runtime is wrong; they measure different things.** RobotShop: ~30 / ~80 min at
  0.4 m/s. Booster: 20 min / 1 h 10 min at 1.1 m/s. Higher speed, shorter runtime: the pairs are
  consistent with each other. Each runtime is only meaningful together with its test speed.

## Decided semantics

1. **`walk_speed_ms` is the manufacturer-stated walking speed.** For K1 that is Booster's
   "Walking Speed: 2 m/s", which the owner reads as **up to 2 m/s**, so the value is **2.0** for
   all three editions. A spec caveat states "up to", and that the figure is Booster's
   specification, not a measured cruising speed.
2. **`runtime_minutes` holds one primary observation: the manufacturer's**, with its measurement
   condition. That is **20 / 70 / 70 min**: Geek "20 min", Educational and Professional
   "1 h 10 min", each **measured walking at 1.1 m/s**. The condition is never dropped: it is
   stated in the field's spec caveat.
3. **Measurement conditions are source-specific.** A runtime is only meaningful with its test
   speed, and different sources test at different speeds. Neither observation is converted,
   averaged or adjusted to the other's condition.
4. **Multiple runtime observations.** The schema has one `runtime_minutes` per robot and no
   per-observation runtime table, so there is **no second specification row**. The alternative
   observation, RobotShop EU listing (retrieved 2026-08-16) "~30 min runtime at 0.4 m/s" (Geek) /
   "~80 min runtime at 0.4 m/s" (Educational, Professional), is preserved verbatim, with its
   source and date, in the `runtime_minutes` spec caveat and in `specs_note`.
5. **0.4 m/s is a test condition, never a speed specification.** It appears only next to the
   RobotShop runtime it qualifies.
6. **Display.** Robot-detail and comparison pages show `runtime_minutes` together with its caveat
   (conditions and the alternative observation). Summaries and use-case wording are rewritten so
   that no runtime figure appears without its test speed and source.

## Correction PR scope

The three K1 records only, scoped `--only booster-k1-geek --only booster-k1-educational --only
booster-k1-professional`:
- `walk_speed_ms` 0.40 → 2.0;
- `runtime_minutes` 30 / 80 / 80 → 20 / 70 / 70;
- two spec caveats per robot;
- `specs_note` provenance;
- summary and use-case wording.

It adds no specification rows and changes no schema, prices, offers, availability, images,
evidence or publication.
