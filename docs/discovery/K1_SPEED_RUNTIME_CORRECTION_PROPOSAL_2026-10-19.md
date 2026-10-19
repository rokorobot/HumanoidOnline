# Booster K1: walking speed and runtime correction proposal (2026-10-19)

**Status: PROPOSAL. No catalogue value has changed.** The six values held in Batch 2 (PR #170) stay
as they are until the owner decides the semantics and display described below. This proposal
changes no core field.

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

## Proposed correction (for a later scoped batch, after the semantics decision)

1. **Walking speed.** Record Booster's statement as the manufacturer walking speed: either
   `walk_speed_ms = 2.0`, if the field means the manufacturer's stated walking speed, or the
   long-tail `max_speed` (TEXT, "Maximum speed (as stated)") = "2 m/s", leaving `walk_speed_ms`
   for whatever the ratified meaning is. The value 0.40 is removed from `walk_speed_ms` in
   either option, because it never stated a walking speed.
2. **Runtime.** Keep **both** measurements, each with its own test speed and source, in
   `operating_time` (TEXT, "Operating time (as stated)"), e.g. for Geek:
   - "20 min (walking at 1.1 m/s), Booster official specification";
   - "~30 min at 0.4 m/s, RobotShop EU listing".

   `runtime_minutes` (a single number) cannot carry a test condition. Options: (a) leave it
   UNKNOWN and show `operating_time`; (b) keep the manufacturer figure (20 / 70) with a
   `spec_caveat` naming the 1.1 m/s condition; (c) keep the retailer figure with a caveat.
   **Recommendation: (b)**, the manufacturer as primary source, with both statements visible.
3. **Spec caveats** on `walk_speed_ms` / `runtime_minutes` stating the condition, so compare
   tables and robot pages never show a runtime without its speed.

## Owner decisions required

1. What `walk_speed_ms` means (manufacturer-stated walking speed vs typical vs maximum), and
   whether `max_speed` is used alongside it.
2. Which runtime is primary in `runtime_minutes`, or whether it stays UNKNOWN.
3. The display rule: is a runtime always shown with its test speed? (Recommended.)

Once decided, the change is an ordinary scoped batch: three K1 records, a manifest, a rehearsal
and a preflight, as in Batches 1 and 2.
