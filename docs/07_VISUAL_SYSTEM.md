# HumanoidOnline — Visual System (UI-D1)

**Status: UI-D1 — FROZEN design baseline for WS3.** Approved by the product owner as the
governing design baseline (not inspiration). This document defines the visual language,
tokens, and product primitives that later workstreams (WS3 Intelligence UI, WS4 Compare,
WS5 Buyer Intent) implement — see the WS3 COMPONENT MAP for the pattern→component
mapping. It does **not** implement product routes. See the NON-GOALS section.

---

## 0. Design law

> **Graphic boldness around the data, never instead of the data.**

HumanoidOnline is serious commercial-intelligence software, not a poster site. The
aesthetic exists to make a hard, ambiguous dataset — maturity, obtainability, price
epistemics, evidence — *legible and trustworthy*. Every bold move (extreme type,
signal orange, hard rules, machine language) must clarify or frame data. The moment a
graphic move competes with a price, a status, or a confidence level for the reader's
attention, it is wrong.

Corollaries, binding:

1. **Data is never decorated into ambiguity.** A price is a price; a rule is not drawn
   through it, an accent color is not laid behind it, type-scale drama does not shrink
   it below its neighbours.
2. **UNKNOWN is a designed state, not an empty cell.** (AGENTS.md rule 6.) NULL renders
   as an explicit, styled unknown — never `$0`, "N/A", "free", or a fabricated number.
3. **No commercial fact without evidence** (AGENTS.md rule 7). Price, availability,
   commercial status, deployment, and regional availability always render with their
   provenance affordance (`EvidenceStamp` / `ConfidenceIndicator`).
4. **Enum labels are rendered verbatim** from `docs/03_DATA_DICTIONARY.md`. The visual
   system styles them; it never renames, merges, or invents them.

## 0.1 FROZEN UI LAWS

These are frozen for WS3. They override any local styling temptation.

- **COLOR.** The palette is technical white / near-black / signal orange / neutral grey.
  **Orange means:** selected · active · primary action · critical commercial signal ·
  progress/current position. Orange is **never** generic decoration.
- **SHAPE.** Square / near-square; hard borders; almost no radius; no floating glass
  surfaces; no shadows unless functionally necessary.
- **INFORMATION.** Maturity / Obtainability / Evidence **always remain separate**. Never
  a single "available" flag.
- **UNKNOWN.** UNKNOWN is information; it is never visually hidden; it is never converted
  to false or zero.
- **INTERACTION.** Experimental shell, conventional controls. (Bold hero/identity;
  ordinary, predictable filters, forms, tables.)
- **DATA.** Commercial truth outranks visual completeness. A blank you must show honestly
  beats a tidy grid that lies.

## 1. Discipline gradient (where boldness is allowed)

Experimentation is a budget that is spent at the top of the funnel and conserved where
users make decisions. This gradient is **binding** on every composition:

```
HOME / HERO              → highly experimental allowed
ROBOT IDENTITY HEADER    → highly experimental allowed
SECTION TRANSITIONS      → experimental allowed
ROBOT CATALOGUE          → controlled
COMPARE TABLE            → disciplined
FILTERS                  → highly conventional usability
WIZARD                   → usability first
ADMIN                    → almost completely conventional
```

Reading the gradient: the identity header of a robot page may carry a five-story
display name and vertical machine labels; the pricing block two inches below it is
disciplined, tabular, and quiet. Filters and the wizard look like tools, not art.
Admin (WS7 visibility) is effectively unstyled convention. **The further a surface is
from a commercial decision, the bolder it may be; the closer, the quieter.**

---

## 2. Visual identity

**Industrial editorial brutalism + experimental systems graphics + robotics control
documentation + manufacturing identity.**

The reference points are a machine's control panel, a torn-grid editorial spread, an
engineering data sheet, and a factory asset tag — not a consumer marketing page. The
surface should feel *instrumented*: everything is labelled, indexed, serialized, and
sourced, as if the page itself were a piece of monitored equipment. Warmth comes from
the paper and ink tones (never pure `#000`/`#fff`); rigor comes from the mono machine
layer and hard rules; a single signal orange carries urgency and wayfinding.

Two structural pairs define the system and both are used across the compositions:

- **Dual surface.** The system is *both* light-on-dark (near-black ink surface — the
  "control room" register, for hero and identity headers) *and* dark-on-light (technical
  off-white paper — the "data sheet" register, for catalogue, compare, filters, wizard).
  Off-white ink on dark is `#E7E3D8`, never pure white.
- **Dual display.** Headlines run in *two* voices — a high-contrast **editorial serif**
  (Didone/modern) for expressive lines, and a heavy **industrial grotesk** (condensed,
  bold) for machine/product names (a five-story robot name). See §4.

Signature textures from the references: faint scanline/monitor texture on experimental
surfaces, halftone/dither treatment for imagery, serial numbers and coordinates, corner
crop marks and registration stars, boxed monospace label bars, and dot-matrix markers.

---

## 3. Palette

Concrete values (frozen). Tokens live in `docs/design/tokens.css`.

### Core

| Role | Token | Hex | Use |
|---|---|---|---|
| Primary ink / dark surface | `--ho-ink` | `#131210` | Text, hard rules, dark sections. Warm near-black. |
| Raised dark surface | `--ho-ink-2` | `#1D1B18` | Cards on dark. |
| Paper (primary surface) | `--ho-paper` | `#EFEBE2` | Page background. Technical off-white. |
| Raised paper | `--ho-paper-2` | `#F7F4EC` | Cards on paper. |
| Off-white ink (on dark) | `--ho-paper-ink` | `#E7E3D8` | Text on dark surfaces. Never pure white. |
| **Signal orange (accent)** | `--ho-signal` | `#FF4A00` | Thin precision rules, dot markers, small chips, alert surface. |
| Signal (2nd rule) | `--ho-signal-2` | `#E23C00` | Deeper line in a 2–3 rule set. |
| Signal, text-safe on paper | `--ho-signal-ink` | `#C33200` | Orange *text* on paper (contrast-safe). |

The signal orange is **rationed**. A composition reads as ink-on-paper (or paper-on-ink)
with a few orange *events*: a section-index tick, a 2–3 line precision rule cutting near
a headline, a dot-matrix marker, one active control, a live-rental flag. Orange is never
a decorative wash behind data and never used to mean "good".

### Surface modes (tri-surface — see §1 discipline gradient)

| Mode | Token scope | When |
|---|---|---|
| **Paper** (dark-on-light) | default `:root` | The data register: catalogue, compare, filters, wizard, spec tables. |
| **Dark** (light-on-dark) | `.ho-dark` | The control-room register: home hero, robot identity header, market-snapshot bands. |
| **Orange alert** (black-on-signal) | `.ho-orange` | **Loud status/alert only** (e.g. a "RENTAL LIVE / ACTIVE" panel). Never on data-dense pages — this restriction *is* the discipline gradient at its sharpest. |

### Warm neutral grey scale

`--ho-grey-900 #262420` · `-800 #35322C` · `-700 #4A463E` · `-600 #635E54` ·
`-500 #7C776B` · `-400 #9C968A` · `-300 #BDB7AB` · `-200 #D6D1C6` · `-100 #E7E3DA`.

Greys carry structure (hairlines, muted labels, disabled/derived text) and, crucially,
the **UNKNOWN** state.

### Semantic state colors (restrained — no rainbow)

Only three semantic hues beyond ink/paper/signal, each earned:

| Token | Hex | Meaning | Rule |
|---|---|---|---|
| `--ho-verified` | `#2E6B4F` | `confidence_level = VERIFIED` | Muted technical green. Only `VERIFIED` may render green; requires `verified_at`. |
| `--ho-caution` | `#9A6B12` | Quote-only, warnings, stale evidence | Muted amber. A *flag to read carefully*, not an error. |
| `--ho-unknown` | grey `#7C776B` | Unknown / no confirmed data | Grey + 45° hatch. **Never red, never orange.** |

Confidence ladder is a **value ramp, not a hue rainbow**:
`LOW` grey-400 → `MEDIUM` grey-600 → `HIGH` ink → `VERIFIED` green. Contrast, not color,
communicates confidence.

---

## 4. Typography roles

DISPLAY is **dual**: a high-contrast editorial serif *and* a heavy industrial grotesk,
used deliberately. Preferred typefaces are named for production; **mockups fall back to
system fonts and require no network**, so the fallback stacks are load-bearing.

| Role | Preferred | Fallback stack | Job |
|---|---|---|---|
| **DISPLAY-SERIF** | Canela / GT Sectra / Playfair Display | `"Didot", "Bodoni MT", Georgia, "Times New Roman", serif` | High-contrast editorial serif. Expressive headlines and **robot names** (e.g. *Digit*, *Atmosphere Fuel Systems*). Weight 500, tracking `-0.01em`. |
| **DISPLAY-GROTESK** | Druk Wide / Aeonik Fono / Archivo Black | `"Helvetica Neue", "Arial Narrow", Arial, sans-serif` (heavy, condensed) | Heavy condensed grotesk. **Model codes & machine/product names** (e.g. `DIGIT`, `AT-R1`, `DROID`), section titles, status words. Weight 800, `font-stretch: 75%`, tight tracking. |
| **INTERFACE** | Inter / Söhne / Neue Haas Grotesk Text | `system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif` | High-legibility grotesk. All UI text, prose, table body, forms. |
| **MACHINE** | JetBrains Mono / IBM Plex Mono / Berkeley Mono | `ui-monospace, Consolas, "SFMono-Regular", Menlo, monospace` | Codes, metrics, enum labels, status logs, field names, indices, serials, coordinates. Tabular numerals. Optional **dot-matrix** display variant for status words. |

### Strict 3-tier hierarchy (GOVERNING RULE — no arbitrary switching)

Every text element belongs to exactly one tier. Do not switch a face for effect.

| Tier | Face | Used for — and ONLY for |
|---|---|---|
| **1 · DISPLAY / EDITORIAL** | DISPLAY-SERIF | **Robot (and manufacturer) NAMES**, and major page moments (the home hero claim). Nothing else. |
| **2 · GROTESK / INTERFACE** | DISPLAY-GROTESK (headings/section titles/model codes) + INTERFACE (navigation, controls, buttons, prose, table body) | Structure and interaction. Headings and model codes are grotesk; nav/controls/body are interface. |
| **3 · MONO / SYSTEM** | MACHINE | Metadata, statuses, dimensions/metrics, IDs, section indices, evidence, coordinates, serials. The instrumented layer. |

- **Identity lockup** (RobotCard title + robot header): tier-1 serif **name** set beside
  a tier-2 grotesk **model code** — e.g. serif *Digit* + grotesk `v5`.
- **DISPLAY-TECHNO is not a tier.** It is an *optional* special-use accent for short
  system words only (`AI-OPS`); reach for it rarely, never for names/headings/body.
- Dot-matrix/LED is a decorative variant of tier-3, not a text tier.

**Extreme type-scale contrast** is a signature: DISPLAY runs to `clamp(3.25rem, 11vw,
9rem)`; MACHINE labels sit at 11px. The gap between loudest and quietest type is
deliberately enormous — but only the *framing* is loud; the *data* sits in the calm
tier-2/tier-3 middle.

---

## 5. Graphic grammar

Each device below has a defined job. Devices are structural, not ornamental.

| Device | Rule of use | Token/class |
|---|---|---|
| **Hard rules** | 1px hairline (structure), 2px (section separation), 3px (major boundary). Ink, square-cornered. Rules organize; they never cross data. | `.ho-rule[--med/--bold]` |
| **Signal precision rules** | A 2–3 line orange rule set cutting *across/near* a headline (never across data). Signal, not decoration. | `.ho-signal-rules > .ho-srule` |
| **Square markers** `▪` | 8px solid squares as bullets/"live" dots/active ticks. Ink default; orange only for a live/active fact. | `.ho-marker[--signal]` |
| **Dot-matrix markers** | 2×2 / 2×3 dot blocks (from the refs' corner dot clusters). Rhythm and registration. | `.ho-dots[--signal/--6]` |
| **Dot-matrix / LED text** | Optional display variant for status words (`ACTIVE`, `LIVE`). Offline via `background-clip:text`. | `.ho-dotmatrix` |
| **SystemHeader / MachineMeta** | The slim black top strip. **Functional, not decorative** — carries real page data (index title + record ID, observed date, counts, evidence status). See §5.1. | `.ho-sysheader` |
| **System identifiers** | Every robot/manufacturer carries `model_code`/slug as a boxed `MachineCode` chip. Asset-tagged feel. | `.ho-code` |
| **Boxed label bars** | Top-of-section header bars of monospace technical labels in hairline boxes. | `.ho-chip`, `.ho-chip--inv` |
| **Bracketed status chips** | `[ FLIGHT TESTED ]`, `[[[ WARNING ]]]` — the refs' bracket vocabulary for statuses/flags. | `.ho-bracket[--alert]` |
| **Dotted leaders** | `LABEL ............ VALUE` machine readouts (`SYS.STATUS: ALL OK`). Control-doc voice. | `.ho-leader > .fill` |
| **Section indices** | Sections numbered `01 —`, `02 —` in mono + signal tick; big index numerals in stepped lists. | `.ho-section-index` |
| **Registration marks** | Corner stars `★`, `®`/`©`, F-in-circle logo marks, boxed registration ticks. Sparse "instrument" texture. | `.ho-star`, `.ho-reg-box`, `.ho-circlemark` |
| **Crop-mark corners** | L-bracket crop marks framing hero/identity blocks (orange). | `.ho-cropframe > .ho-crop` |
| **Serials & coordinates** | `SERIAL NO. 001`, `BADGE ID:`, `REF DRS-…`, `37°47′43″ N` strings as vertical or inline machine text. | machine layer |
| **Hazard stripes** | 45° ink/transparent diagonal band for warnings/caution surfaces. | `.ho-hazard` |
| **Halftone / dither imagery** | Robot/hero imagery rendered as dithered/halftone or schematic SVG, never glossy photography. | inline SVG |
| **Scanline texture** | Faint monitor scanlines on *experimental* surfaces only (hero/header). Under data, never over it. | `.ho-scan` |
| **Eye / lens motif** | Concentric-oval "lens/eye" mark for perception/vision/monitoring. | inline SVG |
| **Technical labels** | Field names uppercase mono, wide tracking (`0.14em`). Labels quiet; values loud. | `.ho-syslabel` |
| **Asymmetric editorial grids** | Off-center, ragged columns (7/5, 8/4). Structure via rules, not shadows. | layout |
| **Selective vertical typography** | Vertical machine labels on section spines/card edges. Never body text, never a decision-bearing value. | `.ho-vertical` |
| **Machine-status language** | Statuses read like readouts: `RAAS_DEPLOYMENT`, `ON_REQUEST`, `QUOTE_ONLY`, `CONF: VERIFIED`. Verbatim enums, mono-set. | — |

Anti-patterns (prohibited): drop shadows and soft rounding as primary style; gradients
behind data; glossy photography that displaces specs; color used to imply a value
judgement on a neutral fact; **orange as a background wash on data-dense surfaces**;
scanline/dither texture over tables or prices.

### 5.1 SystemHeader / MachineMeta — functional, not decorative

The slim black strip at the top of every page is a **SystemHeader**: it carries real
page data, not flavour text. It reads as an index/record line for the thing on screen.

- **Home:** `■ HUMANOIDONLINE / COMMERCIAL INTELLIGENCE — 20 PLATFORMS TRACKED`
- **Catalogue:** `■ HUMANOID MARKET INDEX — DATA OBSERVED 24 JUL 2026 — 20 PLATFORMS TRACKED`
- **Robot detail:** `■ ROBOT RECORD / HMD-00147 — EVIDENCE STATUS: HIGH`

The **MachineMeta** fields are the functional payload: observed date, record ID, counts,
evidence status. The "static reference mockup" disclaimer rides along **quiet and small**
on the right (`.ho-sysheader .ref`) — present, but never shouting.

### 5.2 Metadata density — keep it a system, not a parody

Production section headers use the **clean** form: `02 / ROBOT CATALOGUE` — **not**
`02 / CATALOGUE · DISCIPLINE: CONTROLLED`. The discipline gradient is an internal design
rule (this document), not on-screen chrome. Reference compositions may annotate lightly
for teaching, but keep decorative machine-metadata sparse: enough to feel instrumented,
never so much that it self-parodies. When in doubt, delete a label.

---

## 6. Product primitives (design contracts)

Each primitive is a **contract**: purpose, anatomy, states, and the schema data it
renders. These map to future React components (`docs/02_ARCHITECTURE.md` §4) but are
**not built as React here** — UI-D1 specifies them and proves them in static HTML.

Universal rules: primitives render enum labels verbatim; any commercial fact carries an
`EvidenceStamp`/`ConfidenceIndicator`; NULL renders an explicit unknown state.

### 6.1 SystemLabel
- **Purpose:** field/kicker label — the technical voice for "what this value is".
- **Anatomy:** uppercase MACHINE text, 11px, tracking `0.14em`, grey-600.
- **States:** default, on-dark (paper text). No interactive states.
- **Data:** static field names; never a data value itself.

### 6.2 SectionIndex
- **Purpose:** ordinal section marker + editorial wayfinding.
- **Anatomy:** `NN —` in mono, signal-ink number, 28px ink tick.
- **States:** default, active (in-view).
- **Data:** section ordinal (presentational).

### 6.3 MachineCode
- **Purpose:** render a system identifier as an asset tag.
- **Anatomy:** mono, boxed hairline chip.
- **States:** default; link (to canonical record) optional.
- **Data:** `robot.model_code`, `robot.slug`, `manufacturer.slug`, offer IDs.

### 6.4 StatusBadge — DIMENSION 1 (maturity)
- **Purpose:** render `commercial_status` (platform maturity) **only**. Never obtainability.
- **Anatomy:** mono uppercase pill or bracketed chip (`[ COMMERCIAL ]`), hairline ink border.
- **States (verbatim enums):** `ANNOUNCED`, `DEVELOPMENT`, `PROTOTYPE`, `PILOT`,
  `EARLY_ACCESS`, `LIMITED_COMMERCIAL`, `COMMERCIAL`, `RAAS_DEPLOYMENT`, `DISCONTINUED`.
- **Encoding:** a maturity ladder rendered as a value ramp (ghost → solid ink) plus the
  literal label. `RAAS_DEPLOYMENT` is a **success** state (solid), not muted.
  `DISCONTINUED` is struck/ghosted. **No color implies "buyable" — that is Dimension 2.**
- **Data:** `robot.commercial_status`.

### 6.5 AvailabilityState — DIMENSION 2 (obtainability)
- **Purpose:** render obtainability per `transaction_type` × region. Independent of maturity.
- **Anatomy:** a small matrix row: `mode | region | availability_status`.
- **States (verbatim):** `NOT_AVAILABLE`, `WAITLIST`, `PREORDER`, `LIMITED`, `AVAILABLE`,
  `ON_REQUEST`, `DISCONTINUED`; plus the **absence state** (no offer rows). Absence ≠
  `NOT_AVAILABLE`.
- **SHORT / LONG label convention (mandatory — no truncation, no ugly wrap):**
  | State | SHORT (card) | LONG (detail / compare) |
  |---|---|---|
  | absence (unknown) | **"AVAILABILITY UNKNOWN"** | **"No confirmed commercial availability"** |
  Cards use the short, single-line form (`.ho-state`, `white-space:nowrap`); detail uses
  the full sentence. Enum statuses render verbatim either way.
- **Accessibility predicate:** where a binary "commercially accessible?" is shown, it uses
  the one schema rule `is_current AND status NOT IN (NOT_AVAILABLE, DISCONTINUED)` — never
  an ad-hoc list.
- **Data:** `availability_offer` rows (or their absence).

### 6.6 PricingState — the price epistemics primitive
- **Purpose:** render price with its epistemic quality. Price is **never one column**
  (`transaction_type` × `price_type` × `billing_period` × region × provider).
- **Anatomy:** value (or explicit non-value) + `price_type` context tag + billing period +
  region/provider qualifier + `EvidenceStamp`.
- **Distinct states — all six are visually different, with SHORT (card) / LONG (detail):**
  | State | `price_type` / data | SHORT (card) | LONG (detail / compare) |
  |---|---|---|---|
  | PUBLIC | `PUBLIC` | `$16,000` | `$16,000` |
  | FROM | `FROM` | `From $40,000` | `From $40,000` |
  | RANGE | `RANGE` (`price_min`–`price_max`) | `$120k–$200k` | `$120,000 – $200,000` |
  | ESTIMATED | `ESTIMATED` | `~$30,000` (amber) | number + **`ESTIMATED`** flag (amber) |
  | QUOTE_ONLY | `price_type = QUOTE_ONLY` | **"PRICE ON REQUEST"** | **"Price on request"** |
  | UNKNOWN | *no `pricing_offer` rows* | **"NO PRICE DATA"** | **"No confirmed pricing"** |
- **Hard law:** `QUOTE_ONLY ≠ UNKNOWN` — in **both** SHORT and LONG variants. Quote-only is
  a positive claim about the seller's model (needs evidence); unknown claims nothing. They
  must never collapse into one look. NULL never becomes `$0` / "free" / "N/A". Card state
  labels use `.ho-state` (`white-space:nowrap`) so they never truncate with an ellipsis or
  wrap onto three ugly lines.
- **Data:** `pricing_offer` (all matching rows via the offer view), or absence.

### 6.7 EvidenceStamp — DIMENSION 3 (evidence/provenance)
- **Purpose:** attach provenance to any commercial fact. "No commercial fact without
  evidence."
- **Anatomy:** a monospace readout with dotted leaders —
  `VERIFIED · 2026-07-01 · SOURCE: MANUFACTURER_STORE` — carrying a `®`/checkmark when
  verified; `source_type` + `source_title` + `observed_at`/`published_at` +
  (`verified_at` when present) + source link affordance.
- **States:** verified (has `verified_at`), unverified (no `verified_at`), stale (verified
  older than policy window → caution/amber), source-linked vs source-noted.
- **Data:** `evidence_source` (`source_url`, `source_type`, `observed_at`, `verified_at`,
  `confidence`).

### 6.8 ConfidenceIndicator
- **Purpose:** expose `confidence_level` on a displayed fact.
- **Anatomy:** a four-segment meter (value ramp, not hues) + literal label —
  `LOW ▮▯▯▯ / MEDIUM ▮▮▯▯ / HIGH ▮▮▮▯ / VERIFIED ▮▮▮▮`.
- **States (verbatim):** `LOW`, `MEDIUM`, `HIGH`, `VERIFIED`. **Only `VERIFIED` renders a
  "Verified" indicator, and only with `verified_at`.**
- **Data:** `evidence_source.confidence` (+ `verified_at`).

### 6.9 Metric
- **Purpose:** a single physical/technical spec.
- **Anatomy:** SystemLabel (name) over MACHINE value + unit.
- **States:** known; **unknown** (NULL → "UNKNOWN", grey/hatch, never `0`).
- **Data:** `robot.payload_kg`, `height_cm`, `weight_kg`, `runtime_minutes`, `walk_speed_ms`,
  `degrees_of_freedom`, `autonomy`, boolean capability flags (NULL = unknown, not false).

### 6.10 DataCell
- **Purpose:** atom of every table/matrix. Guarantees UNKNOWN rendering.
- **Anatomy:** value | unit | optional qualifier; or explicit unknown fill.
- **States:** value, unknown (hatch), not-applicable `—` (a *different* thing from unknown),
  derived (muted).
- **Data:** any field; enforces "NULL ≠ 0/false".

### 6.11 RobotCard
- **Purpose:** the catalogue/summary unit. Proves the three dimensions survive repetition.
- **Anatomy:** identity lockup (serif **name** beside grotesk **model code**) +
  manufacturer · StatusBadge (Dim 1) · key Metrics (payload/height/mobility) ·
  PricingState (Dim 2 price) · AvailabilityState summary · Compare affordance.
- **States:** default, hover, compare-selected, unknown-heavy (e.g. Optimus: prototype, no
  price, no availability — must still read cleanly).
- **Data:** `robot` + snapshot (`robot_commercial_snapshot`), best-matching `pricing_offer`,
  `availability_offer` summary.

### 6.12 ManufacturerCard
- **Purpose:** manufacturer summary.
- **Anatomy:** name (display) + country region + `commercial_model` + `deployment_status`
  + robot count.
- **States:** default, hover.
- **Data:** `manufacturer`.

### 6.13 SpecificationTable
- **Purpose:** full spec sheet for a robot.
- **Anatomy:** two-column label/value rows built from DataCell; grouped (physical /
  intelligence / developer). Hard-rule separators.
- **States:** value rows, unknown rows (explicit), boolean flags (yes / no / unknown — three
  states, never a coerced checkbox).
- **Data:** `robot.*`, `specification` + `spec_definition` long-tail.

### 6.14 ComparisonMatrix
- **Purpose:** dense, disciplined comparison across N robots (grouped: commercial /
  physical / deployment).
- **Anatomy:** frozen row-label column + one column per robot; DataCell everywhere; `—`
  for not-applicable, hatch for unknown, best-in-row optional emphasis (subtle).
- **States:** value, unknown, N/A; the three dimensions kept in separate labelled groups.
- **Data:** the compared `robot` set + offers + deployments.

### 6.15 WizardStep
- **Purpose:** one requirement question (usability-first surface).
- **Anatomy:** progress index (`STEP 04 / 12`) + question (INTERFACE, not display) +
  large tap targets + explicit "Unknown / skip" affordance + back/next.
- **States:** unanswered, answered, skipped/unknown, error.
- **Data:** buyer requirement inputs incl. `transaction_preference`
  (`UNKNOWN / RENT / BUY / LEASE / RAAS / FLEXIBLE`).

### 6.16 MatchScore / MatchCard
- **Purpose:** render a `match_result` — score + reasons + warnings + category.
- **Anatomy:** `match_category` label (verbatim) + large grotesk numeric score + a
  segmented score-breakdown meter + reasons (`✓`) + warnings (`⚠`, e.g. "pricing is
  quote-only", on a hazard-stripe flag) + one commercial CTA.
- **States (categories verbatim):** `BEST_OVERALL`, `BEST_COMMERCIAL`, `BEST_LOWER_COST`,
  `BEST_DEVELOPER`, `BEST_TECHNICAL`, `ALTERNATIVE`; plus empty state (no match →
  explanation of the eliminating constraint → lead affordance).
- **Rule:** renders only data present in `score_breakdown` / `reasons` / `warnings`. Frontend
  never computes scores (Architecture §2 — FastAPI decides).
- **Data:** `match_result` (deterministic engine, WS6).

---

## 7. Reference compositions

Five self-contained static HTML proofs live in `docs/design/`. They use realistic seed
data (`db/seed/seed.sql`) as static content; they are **mockups, not wired to any API**,
and each renders offline. Optional `00-primitives.html` shows every primitive in isolation.

| File | Surface | Discipline band | What it proves |
|---|---|---|---|
| `01-home.html` | Home / hero | highly experimental | Brand identity, extreme display type, market snapshot, nav — boldness that still frames real numbers. |
| `02-catalogue.html` | Catalogue + filters | controlled / filters conventional | RobotCard grammar survives repetition and real filtering; filters are usable tools. |
| `03-robot-detail.html` | Robot detail | header experimental, data disciplined | **The key proof.** Three independent dimensions rendered distinctly; all price states incl. QUOTE_ONLY + UNKNOWN; EvidenceStamp + ConfidenceIndicator with source + verified date. |
| `04-compare.html` | Compare | disciplined | High-density ComparisonMatrix across 3 robots; no decoration obscuring data. |
| `05-find-match.html` | Wizard + matches | usability first | WizardStep form and MatchScore card with breakdown / reasons / warnings. |

---

## 7.1 WS3 COMPONENT MAP

These patterns are the **frozen baseline** WS3 implements as production React components
(`docs/02_ARCHITECTURE.md` §4). WS3 builds *these patterns*, deriving from the primitives
below — not recreated from scratch off screenshots.

| WS3 component | Derives from primitive(s) | Renders |
|---|---|---|
| **RobotCard** | 6.11 RobotCard = identity lockup (6.1/6.3) + StatusBadge (6.4) + Metric (6.9) + PricingState (6.6) + AvailabilityState (6.5) | Catalogue/summary unit; SHORT state labels. |
| **FilterPanel** | filter rail (tier-2 controls) + SystemLabel (6.1) | Conventional, usable filters. |
| **SystemHeader** | §5.1 SystemHeader + MachineMeta | Functional black top strip. |
| **MachineMeta** | §5.1 (observed date / record ID / count / evidence status) | The header's data payload; reusable inline. |
| **StatusIndicator** | 6.4 StatusBadge / 6.8 ConfidenceIndicator | Enum status + confidence ramp. |
| **CommercialState** | 6.4 StatusBadge (Dim 1) + 6.5 AvailabilityState (Dim 2) | Maturity + obtainability, kept separate. |
| **PricingState** | 6.6 PricingState | Six price states, SHORT/LONG variants. |
| **EvidenceStamp** | 6.7 EvidenceStamp | Provenance readout (source + verified date). |
| **SectionIndex** | 6.2 SectionIndex | `NN / TITLE` clean header. |
| **ComparisonCell** | 6.10 DataCell / 6.14 ComparisonMatrix | One matrix cell: value / unknown / N/A. |
| **WizardProgress** | 6.15 WizardStep (progress bar + step list) | `STEP n / N` + segmented bar. |
| **RequirementStep** | 6.15 WizardStep | One question, usability-first. |

---

## 8. NON-GOALS (what UI-D1 does NOT do)

UI-D1 is a **visual system contract plus reference proofs**. It is explicitly *not* WS3+.

- **No production routes.** UI-D1 does not implement `/robots`, `/robots/[slug]`,
  `/compare`, `/find-a-humanoid`, or `/matches/[id]`. Those are **WS3 (Intelligence UI),
  WS4 (Compare), WS5 (Buyer Intent), WS6 (Matching)**.
- **No Next.js pages/routes, no React components, no API wiring.** The primitives here are
  design contracts for future components, not implementations. No changes to `apps/`.
- **No business logic.** No score computation, availability logic, or price-matching in
  the mockups (Architecture §2: Next renders, FastAPI decides). Seed values are static.
- **No schema, seed, or frozen-doc (01–06) changes.** UI-D1 only *adds* `07`, `tokens.css`,
  the five compositions, and this design index.
- **Reference compositions are proofs, not the product.** They demonstrate the language on
  representative data; production surfaces will be assembled by WS3+ from live API data
  against these same primitives and tokens.
