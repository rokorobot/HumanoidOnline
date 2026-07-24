# UI-D1 — Design reference compositions

Static, self-contained proofs of the HumanoidOnline visual system. The written
contract is **[`../07_VISUAL_SYSTEM.md`](../07_VISUAL_SYSTEM.md)**; the shared tokens are
**[`tokens.css`](tokens.css)**. These files are a **design contract + proofs**, not the
product — they implement **no** production routes, React, or API wiring (that is WS3+).

## How to open

Every file is a self-contained `.html` that links only `tokens.css` — **no network, no
CDN, no web fonts required**. Just open it in a browser:

- Double-click any `.html` file, or
- Serve the folder and browse to it:
  ```
  cd docs/design
  python -m http.server 8000
  # then open http://localhost:8000/01-home.html
  ```

Fonts fall back to system faces automatically (serif → Georgia/Times, grotesk →
Helvetica/Arial condensed, mono → Consolas/Menlo), so the compositions render correctly
offline on any machine. With the named preferred typefaces installed, they sharpen.

## The compositions

| File | Surface | Discipline band | Proves |
|---|---|---|---|
| [`00-primitives.html`](00-primitives.html) | paper | — | Every product primitive in isolation, with all states (optional showcase). |
| [`01-home.html`](01-home.html) | dark → paper → orange | highly experimental | Brand identity, editorial-serif hero, market snapshot, tri-surface. |
| [`02-catalogue.html`](02-catalogue.html) | paper | controlled (filters conventional) | RobotCard grammar survives repetition + real filtering. |
| [`03-robot-detail.html`](03-robot-detail.html) | dark header / paper body | header experimental, data disciplined | **Key proof:** three independent dimensions rendered distinctly; all six price states incl. QUOTE_ONLY + UNKNOWN; EvidenceStamp + ConfidenceIndicator with source + verified date. |
| [`04-compare.html`](04-compare.html) | paper | disciplined | High-density ComparisonMatrix across 3 robots; no decoration over data. |
| [`05-find-match.html`](05-find-match.html) | paper | usability first | WizardStep form + MatchScore cards (breakdown / reasons / warnings / empty state). |

## Reading order

1. `07_VISUAL_SYSTEM.md` — the law, discipline gradient, palette, type, grammar, primitives.
2. `00-primitives.html` — the vocabulary, one primitive at a time.
3. `01` → `05` — the vocabulary composed, top of the discipline gradient to the bottom.

## Non-negotiables demonstrated

- **Three independent dimensions** — maturity (`commercial_status`) ≠ obtainability
  (`availability_status`) ≠ evidence. Never an "available" boolean. (See `03`, `04`.)
- **Six price states** — PUBLIC · FROM · RANGE · ESTIMATED · QUOTE_ONLY · UNKNOWN, all
  visually distinct. `QUOTE_ONLY` ("Price on request") ≠ `UNKNOWN` ("No confirmed
  pricing"). NULL is never `$0` / "free" / a guessed number. (See `02`, `03`.)
- **No commercial fact without evidence** — every price/status/availability/deployment
  carries an EvidenceStamp + ConfidenceIndicator. Only `VERIFIED` shows "Verified". (See `03`.)
- **Enum labels verbatim** from `../03_DATA_DICTIONARY.md`.
- **Discipline gradient** — bold at hero/identity, quiet and legible at
  filters/compare/wizard.
