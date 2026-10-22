# HO-DATA-30 manufacturer evidence research — shared brief

You are researching missing catalogue fields for humanoid robots. Your group file (JSON) lists, per robot record
(slug), its name, current known values and the UNKNOWN fields to research. Research **every** UNKNOWN field, not
just the numeric ones.

## Authority and source rules (binding)
- Basis: standing research work order `HO-DATA-STANDING 2026-10-22` (docs/decisions/DR-D1). Read-only research.
- **Evidence must come from the manufacturer's own hosts**: product pages, spec tables, datasheets/PDFs, manuals,
  press releases and newsroom posts, developer portals and docs, official GitHub organisations, the site's own
  JS/JSON assets (script-rendered sites often carry spec text in their own `/assets/*.js` or `__NEXT_DATA__` JSON;
  reading those is allowed).
- Third-party sites (distributors, shops, wikis, news, humanoid.guide, robotsguide, aiwiki, Wikipedia,
  third-party copies of manufacturer PDFs, archive.org) may be used **only as leads** to find a first-party URL.
  They are NEVER evidence.
- **Never** access robotshop.com in any form. Never bypass a login, paywall, CAPTCHA or bot block. If a site blocks you
  (403, TLS failure, empty script shell with no first-party asset), record it as BLOCKED and move on.
- Do not modify any repository file. Write only inside your output directory.

## Method
1. Use WebSearch/WebFetch to find candidate first-party URLs. WebFetch returns a model summary, so it is NOT evidence.
2. For every page you rely on, fetch the raw body with Bash and save it in your output dir `raw/`:
   `curl -s -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36" --max-time 40 -o raw/<name> "<url>"`.
   If curl fails with a TLS error on Windows, use Python urllib (`python -I` script) instead. For PDFs, extract the
   text with `uv run --with pypdf python -I <script>` (set the `UV_CACHE_DIR` env var to the uvcache path you were given).
   Record `sha256sum` for each saved file.
3. A value counts only if its **verbatim text is present in the saved raw body** (or extracted PDF text). Quote it
   exactly, in the original language.
4. Match the value to the exact record. If the source states it for a different edition, generation or model
   (e.g. H1-2 vs H1, Apollo 2 vs Apollo, Digit 5 vs Digit, ASIMO 2011 vs 2005), it is not a match for that
   record: report it as EDITION_MISMATCH.

## Field semantics: what is CLEAN and what is HELD
Numeric fields (units: height_cm, weight_kg, payload_kg, runtime_minutes, walk_speed_ms, degrees_of_freedom (int),
battery_wh, arm_span_cm, reach_cm, hand_dof (int, per hand)):
- CLEAN: the value is stated, or follows from a pure unit conversion (h→min, km/h→m/s, mm→cm, kWh→Wh, lb→kg).
- HELD_POLICY:
  - summing per-part DoF, V×Ah→Wh or any other arithmetic;
  - a range (e.g. "26-40");
  - combined, dual-arm, posture-dependent or whole-body "lift" payloads (a per-arm or unqualified arm payload is CLEAN);
  - an unlabelled "max speed", or a wheeled base speed, for walk_speed_ms (an explicit walking/moving/locomotion speed of a legged robot is CLEAN);
  - several runtime modes (e.g. standing 3h / walking 1.5h);
  - height-adjustable robots;
  - "preliminary" or "in development" figures.

Booleans (has_vision, has_manipulation, has_sdk, has_api, ros_support, simulation_support, has_teleoperation,
has_language_ui, developer_edition):
- CLEAN true only when the manufacturer **states it in words** for this product:
  - has_vision: cameras, depth or stereo vision, or vision sensors on the robot;
  - has_manipulation: the robot grasps or manipulates objects, or has hands or grippers used for manipulation;
  - has_sdk: an SDK is available;
  - has_api: a programming API is available;
  - ros_support: ROS or ROS 2 support or interface;
  - simulation_support: an official simulation model or support (Isaac Sim/Lab, MuJoCo, Gazebo, Webots, URDF/MJCF published for simulation);
  - has_teleoperation: teleoperation or remote control by an operator is supported;
  - has_language_ui: spoken or natural-language conversation with users is stated in words. Microphones, speakers or "LLM support" alone are HELD_POLICY (D4).
- CLEAN false only when a negative is stated in words (e.g. "only the EDU version supports secondary development").
  An absence, a "/" or a "—" is never false.
- developer_edition, autonomy (enum TELEOPERATED/ASSISTED/SUPERVISED_AUTONOMY/TASK_AUTONOMOUS/HIGHLY_AUTONOMOUS):
  always report as HELD_POLICY with the verbatim evidence (no approved mapping rule yet).

Enum/text:
- mobility (BIPEDAL/WHEELED/HYBRID/QUADRUPED/STATIONARY/OTHER): CLEAN when the locomotion type is stated in words
  ("bipedal", "two legs", "walks", "wheeled base").
- hand_type: CLEAN only when the standard shipped end effector is named. Optional or interchangeable end effectors
  are HELD_POLICY (D5).

## Output (required)
Write `<outdir>/findings.jsonl`, one JSON object per researched cell (every UNKNOWN field of every robot, even when
nothing was found):
```
{"slug":..., "field":..., "status": "CLEAN"|"HELD_POLICY"|"EDITION_MISMATCH"|"CONFLICT"|"CHECKED_SILENT"|"BLOCKED"|"NOT_APPLICABLE"|"NOT_RESEARCHED",
 "value": <proposed value or null>, "verbatim": "<exact quote>", "url": "<source url>", "raw_file": "raw/<name>",
 "sha256": "<full hash>", "note": "<edition, conversion, why held, documents checked if silent>"}
```
- CHECKED_SILENT: name the first-party documents you read in `note`.
- NOT_APPLICABLE: only when the manufacturer's own description makes the field inapplicable (e.g. a robot that does
  not walk → walk_speed_ms). Quote the evidence.
- CONFLICT: two first-party sources disagree. Give both.

Also write `<outdir>/sources.md`: every URL fetched, its HTTP outcome, saved file and sha256, and any blocks.

Final reply: counts by status, the CLEAN rows (slug, field, value, url), and the most valuable unexplored leads.
Evidence (file paths, URLs, quotes) matters more than prose. Do not inflate: a wrong CLEAN is worse than a CHECKED_SILENT.
