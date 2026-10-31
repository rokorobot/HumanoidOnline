# treg sweep (docs/29 D7)

Collects the 10 registry-v2 queries × 4 treg surfaces, then builds `observations.json` and `REPORT.md`.
Needs the treg CLI logged in with the dedicated token; run with `TREG_TELEMETRY=0`.
Never run `treg upload` or the `cli_auth` injector (docs/29 §3.2). Each run needs owner spend authorization (§9).

```bash
RUN=docs/measurements/ai-visibility/aeo-pilot-2026-11-r2
python3 docs/measurements/ai-visibility/treg_sweep/collect.py $RUN   # paid: ≈ $0.09; resumable, skips existing files
python3 docs/measurements/ai-visibility/treg_sweep/build.py   $RUN
python3 docs/measurements/ai-visibility/treg_sweep/report.py  $RUN   # R1 wording; edit headings/§7 for R2
```
