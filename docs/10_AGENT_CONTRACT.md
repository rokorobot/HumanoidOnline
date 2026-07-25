# AGENT-01 — Machine & Agent Accessibility

> ## STATUS: RATIFIED v0.1 — 2026-07-25 — NO IMPLEMENTATION until a separate build trigger
>
> Ratified by the product owner (Robert) on 2026-07-25. The laws below are now
> **FROZEN**. Ratification authorizes the AGENT-01 v0.1 architecture (canonical
> governed data → governed projection → semantic HTML / JSON-LD / sitemap /
> robots.txt / llms.txt) and unblocks the bounded first build slice — but does
> **not** start implementation. The build begins only on a separate, explicit
> owner trigger. Ratification record + statement-in-force: §Ratification record.
>
> **Dependency satisfied (A2).** AGENT-01's block on DATA-D1 has LIFTED: DATA-D1
> is no longer merely to-be-ratified — it is **ratified, built, merged
> (`main @ 3dca8cc`), and acceptance-gated (§27 A–K)**. AGENT-01's projections
> therefore sit behind a live, governed discovery boundary (DATA-D1 §22/§23).
>
> Subordinate to the existing frozen laws: **MEDIA-01 / MEDIA-01.8** (imagery),
> **DATA-D1** (discovery/promotion), and the **UNKNOWN / G2 / evidence** laws
> remain binding throughout.

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

## Frozen laws (v0.1)

- **AGENT-01.1 — Canonical Identity.** Every public entity has one stable,
  canonical, machine-addressable identity URI.
- **AGENT-01.2 — Semantic Parity.** Machine-readable representations may expose
  only semantics available from the governed application layer.
- **AGENT-01.3 — Explicit Uncertainty.** `UNKNOWN` must never be coerced into
  `0`, `false`, empty string, "unavailable", or any other factual value — it is
  omitted or rendered as explicit unknown.
- **AGENT-01.4 — Provenance Preservation.** Facts exposed to machines retain
  their **canonical** evidence semantics — `verified_at` (freshness) and evidence
  `confidence` where available — and nothing more (A3). Machine surfaces never
  expose discovery-layer internals or a candidate's trace metadata; and where a
  fact has no provenance, provenance is **omitted, never fabricated** (cf. 01.3).
- **AGENT-01.5 — Typed Action Parity.** Future commercial actions must be
  exposed through governed typed services rather than requiring simulated UI
  interaction.
- **AGENT-01.6 — Projection Only.** HTML, JSON-LD, APIs, feeds, MCP, and future
  agent interfaces are projections of the same canonical governed model. None
  may become an independent source of truth.
- **AGENT-01.7 — Published-Canonical-Only Surface.** Machine and agent surfaces
  expose only canonical entities with `is_published = true`. Discovery candidates
  and promoted-but-unpublished entities are excluded. *(This closes the boundary
  created by DATA-D1's safe default of promoting new robots as UNPUBLISHED —
  DATA-D1 §22/Gate I + §23. The public read layer already filters `is_published`,
  so a governed projection built on it inherits this; the law makes it explicit
  and binding on every future surface.)*

## Cross-workstream invariant (binds MEDIA-01, DATA-D1, and every projection)

> Competitive-discovery data is never promoted into canonical machine-readable
> output merely because DATA-D1 discovered it. Promotion requires the normal
> verification/evidence path.

Applies to JSON-LD, APIs, feeds, MCP, and any future agent surface. MEDIA-01's
VERIFIED-identity + no-`GENERATED` image rule is the imagery-specific instance
of this same invariant.

## Dependency & sequencing (satisfied)

AGENT-01 sat **after** DATA-D1 in the governance queue; that dependency is now
**satisfied**:

```
DATA-D1 contract ratified (#19) -> DATA-D1 v0.1 built + hardened + merged (#20, main 3dca8cc)
    -> §27 acceptance gates A-K proven -> AGENT-01 review -> AGENT-01 ratification (this doc)
    -> AGENT-01 build slice (separate owner trigger)
```

Ratification of AGENT-01 authorizes the architecture. Implementation still
requires a separate explicit **`build AGENT-01 v0.1`** trigger, and the build
lands through the normal PR-gated ritual.

## First build slice (AUTHORIZED; build requires an explicit owner trigger)

- `/robots/[slug]` -> `Product` + `Organization` JSON-LD
- `sitemap.xml` (split by entity type; meaningful `lastmod`). Lists **only
  `is_published` entities** (AGENT-01.7) — never candidates or unpublished
  promotions.
- a deliberate **inbound** `robots.txt` bot policy (allow search/discovery bots;
  explicit stance on training bots) — a business decision, not a config default.
  **(A4)** This is a *different axis* from DATA-D1.9: `robots.txt` governs bots
  crawling **us** (inbound); DATA-D1.9 governs **our** crawling of external
  sources (outbound, affirmative-permission-gated). Do not conflate them.
- `/llms.txt` with the semantics statements (`UNKNOWN` ≠ `0`; commercial
  maturity ≠ obtainability; evidence status ≠ commercial status) — treated as a
  useful-but-non-canonical proposal, not architected around. **(A6)** It
  describes the **canonical-only** public knowledge surface; discovery candidates
  are never part of it.

Constraints baked in: JSON-LD flows `canonical DB -> governed projection -> page
+ JSON-LD`, never `page logic -> bespoke JSON-LD facts`. The projection reads
only `is_published` canonical entities (AGENT-01.7). Emit a `schema.org` `image`
only when `identity_status = VERIFIED` (MEDIA-01); never coerce an `UNKNOWN` spec
into a `PropertyValue` (AGENT-01.3); expose only canonical `verified_at` /
`confidence` provenance (AGENT-01.4); never emit competitor-sourced or
candidate data as canonical structured output (cross-workstream invariant).

**First-slice OUT-list (A5)** — explicitly NOT in v0.1: no **MCP**; no agent or
**transactional** actions; no new **canonical DB model**; no **parallel agent
API**. The slice is **read-only projections only**. AGENT-01.5 (typed action
parity) and MCP are later, **separately-ratified** slices.

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
- **AGENT-01.7 is already enforced at the read layer** — the public read path
  filters `is_published` (`apps/api/app/routers/robots.py`, `manufacturers.py`),
  so a projection built on it inherits the boundary; the law makes it binding on
  every future surface, including DATA-D1-promoted (unpublished) robots.

## Ratification record

**RATIFIED v0.1 by the product owner (Robert) on 2026-07-25.** Folds in review
refinements A1–A6 (A1 = new law AGENT-01.7; A2 = DATA-D1 dependency lifted; A3–A6
tightening of provenance / crawl-policy / OUT-list / llms.txt). The laws above are
now **FROZEN**. Ratification authorizes the architecture; it does **not** start
implementation — the build begins only on a separate **`build AGENT-01 v0.1`**
trigger and lands PR-gated.

**Ratification statement (in force, 2026-07-25):**

> AGENT-01 Machine & Agent Accessibility v0.1 is ratified. HumanoidOnline exposes
> machine- and agent-readable surfaces (semantic HTML, JSON-LD, sitemap,
> robots.txt, llms.txt, and later APIs/MCP) that are **projections of the
> canonical governed model only**. They expose exclusively canonical entities with
> `is_published = true` — never discovery candidates or promoted-but-unpublished
> entities. UNKNOWN is never coerced to a factual value; provenance is canonical
> `verified_at`/confidence only, omitted where absent, never fabricated. No
> projection creates a second source of truth, and MEDIA-01 / DATA-D1 / evidence
> laws remain binding. The first slice is read-only (JSON-LD on `/robots/[slug]` +
> sitemap/robots.txt/llms.txt) — no MCP, no agent/transactional actions, no new
> canonical model, no parallel agent API. Proceed to the bounded AGENT-01 v0.1
> build only on a separate explicit build trigger.

**Next authorized step:** the AGENT-01 **v0.1 build slice** may be built once the
owner issues **`build AGENT-01 v0.1`**. Until then, no implementation is
authorized.
