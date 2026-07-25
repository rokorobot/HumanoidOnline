# AGENT-01 — Machine & Agent Accessibility

> ## STATUS: DRAFT — NOT RATIFIED — NO IMPLEMENTATION AUTHORIZED
>
> This document is **architectural reasoning captured for continuity**, not an
> approved contract. Nothing here authorizes code.
>
> **Final ratification is blocked on DATA-D1 contract ratification.** AGENT-01
> depends on the rules DATA-D1 establishes for what discovered competitor data
> may and may not become; freezing AGENT-01 language before DATA-D1 risks
> wording that DATA-D1 then forces us to reinterpret.
>
> The laws below are **Proposed laws** (draft). The term *Frozen* is reserved
> and MUST NOT appear against these until ratification.

---

## Purpose

HumanoidOnline is simultaneously **a website for people** and **a verified
humanoid-market knowledge/action layer for machines** — search/discovery
crawlers, LLMs, and (later) procurement agents. This contract governs how the
canonical, governed model is *projected* to machines, without ever creating a
second source of truth or weakening the MEDIA-01 / DATA-D1 / evidence laws.

Four distinct audiences, one canonical model:

```
 Human visitor         -> UI
 Search/discovery bots -> semantic HTML + structured data
 LLMs                  -> clean entity pages + machine-readable data
 Future agents         -> typed services / API / (later) MCP
```

## Proposed laws (DRAFT — not frozen)

- **AGENT-01.1 — Canonical Identity.** Every public entity has one stable,
  canonical, machine-addressable identity URI.
- **AGENT-01.2 — Semantic Parity.** Machine-readable representations may expose
  only semantics available from the governed application layer.
- **AGENT-01.3 — Explicit Uncertainty.** `UNKNOWN` must never be coerced into
  `0`, `false`, empty string, "unavailable", or any other factual value — it is
  omitted or rendered as explicit unknown.
- **AGENT-01.4 — Provenance Preservation.** Facts exposed to machines retain
  evidence, confidence/freshness, and provenance semantics where applicable.
- **AGENT-01.5 — Typed Action Parity.** Future commercial actions must be
  exposed through governed typed services rather than requiring simulated UI
  interaction.
- **AGENT-01.6 — Projection Only.** HTML, JSON-LD, APIs, feeds, MCP, and future
  agent interfaces are projections of the same canonical governed model. None
  may become an independent source of truth.

## Cross-workstream invariant (binds MEDIA-01, DATA-D1, and every projection)

> Competitive-discovery data is never promoted into canonical machine-readable
> output merely because DATA-D1 discovered it. Promotion requires the normal
> verification/evidence path.

Applies to JSON-LD, APIs, feeds, MCP, and any future agent surface. MEDIA-01's
VERIFIED-identity + no-`GENERATED` image rule is the imagery-specific instance
of this same invariant.

## Dependency & sequencing

AGENT-01 sits **after** DATA-D1 in the governance queue:

```
PR #16  ->  PR #17  ->  DATA-D1 contract  ->  DATA-D1 ratification / build sequencing
        ->  AGENT-01 final review / ratification  ->  AGENT-01 build slice
```

**No AGENT-01 implementation before that gate.**

## First build slice (scoped — BLOCKED until ratified)

- `/robots/[slug]` -> `Product` + `Organization` JSON-LD
- `sitemap.xml` (split by entity type; meaningful `lastmod`)
- a deliberate `robots.txt` bot policy (allow search/discovery bots; explicit
  stance on training bots) — a business decision, not a config default
- `/llms.txt` with the semantics statements (`UNKNOWN` ≠ `0`; commercial
  maturity ≠ obtainability; evidence status ≠ commercial status) — treated as a
  useful-but-non-canonical proposal, not architected around

Constraints baked in: **no new canonical DB model; no parallel agent API.**
JSON-LD flows `canonical DB -> governed projection -> page + JSON-LD`, never
`page logic -> bespoke JSON-LD facts`. Emit a `schema.org` `image` only when
`identity_status = VERIFIED` (MEDIA-01); never coerce an `UNKNOWN` spec into a
`PropertyValue` (AGENT-01.3); never emit competitor-sourced data as canonical
structured output (cross-workstream invariant).

## Current-state notes

- **AGENT-01.1 is already largely satisfied** — robot detail pages live at
  stable `/robots/[slug]` routes today (not opaque `?id=` state). The slice's
  real new work is JSON-LD + sitemap/robots/llms.txt, not URL redesign.
- **AGENT-01.2 is cheap** — the Next.js App Router renders facts server-side, so
  the canonical facts are already in delivered HTML.
- **AGENT-01.3 / AGENT-01.4 are the moat** — the existing `status: UNKNOWN` vs
  `value: null` discipline and the evidence model (`source_url`, `confidence`,
  `verified_at`) let machines receive *fact + certainty + evidence + freshness*,
  not a bare fact. This is the direct machine-readable extension of MEDIA-01.
