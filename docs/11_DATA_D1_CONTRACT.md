# DATA-D1 — Competitive Discovery & Verification Contract

> ## STATUS: RATIFIED v0.1 — 2026-07-25 — NO IMPLEMENTATION until a separate build trigger
>
> Ratified by the product owner (Robert) on 2026-07-25. The laws below are now
> **FROZEN**. Ratification authorizes the DATA-D1 v0.1 **architecture** (RADAR →
> CANDIDATE → TRACE → VERIFY → PROMOTE) and unblocks the bounded v0.1 build slice
> (§25) — but does **not** itself start implementation. The build begins only on a
> separate, explicit owner trigger. Ratification record + statement-in-force: §30.
> This contract freezes **principles**, not implementation details.
>
> Subordinate to the existing frozen laws: **MEDIA-01 / MEDIA-01.8** remain
> authoritative for imagery; the **UNKNOWN** semantics, **G2** ("no commercial
> fact without evidence"), canonical-taxonomy-only, and no-LLM/no-randomness-in-
> scoring laws remain binding throughout. See `docs/09_MEDIA_CONTRACT.md`,
> `docs/10_AGENT_CONTRACT.md` (also draft), and the delivery/data laws.

### Revision note — refinements folded in (2026-07-25, owner-approved; now in force)

This draft incorporates six refinements beyond the original outline, plus a
v0.1 promotion-authority clarification. They are marked inline as
**Refinement (v0.1):**. Summary:

- **R1 / DATA-D1.9 — Radar eligibility gate:** a source's ToS + robots/access
  policy is reviewed *before* it can become a crawler target (eligibility, not
  just rate).
- **R2 / DATA-D1.10 — Discovery layer is not a shadow database:** minimal
  candidate retention (identity leads, URLs, specific claims only); never a
  copied competitor corpus.
- **R3 — Candidate images reference-only:** URLs/metadata until traced; no
  competitor/editorial binary image cache (§10).
- **R4 — Identity matching deterministic in v0.1:** ambiguity → human; an LLM
  may one day *propose* a match but may never *auto-merge* identities (§6).
- **R5 — Canonical evidence reuse:** promotion writes through the existing
  G2/evidence model; DATA-D1 creates no parallel canonical evidence system (§8).
- **R6 — Structural-isolation acceptance gate:** candidate data cannot surface
  through canonical/API query paths before promotion (§27).
- **Promotion authority (v0.1):** automation may autonomously reach a structured
  promotion *proposal*; human approval is required **only** at the canonical
  mutation gate (P8); `RECHECK_REQUIRED` may be raised autonomously (workflow
  metadata, not a canonical fact change); **no deterministic auto-promotion in
  v0.1** (§18).

---

## 0. Purpose

DATA-D1 expands HumanoidOnline from a manually curated seven-robot catalogue into
a scalable humanoid-market discovery system **without turning competitor
databases into canonical sources.** It establishes a governed pipeline:

```
COMPETITOR / WEB DISCOVERY
        ↓
DISCOVERY CANDIDATE
        ↓
IDENTITY RESOLUTION
        ↓
SOURCE TRACING
        ↓
PRIMARY / AUTHORITATIVE EVIDENCE
        ↓
VERIFICATION
        ↓
PROMOTION GATE
        ↓
HUMANOIDONLINE CANONICAL CATALOGUE
```

Governing principle: **Competitors are radar, never truth.** A competitor may
tell HumanoidOnline what to investigate. It may not determine what HumanoidOnline
asserts as verified fact.

## 1. Scope

DATA-D1 governs automated or semi-automated discovery of: new humanoid robots;
new manufacturers; new variants/models; changed commercial status; changed
pricing; changed availability; changed specifications; new deployments; new
official evidence; candidate robot imagery; potentially stale HumanoidOnline
records.

DATA-D1 produces **research candidates and verification work**, not automatically
trusted catalogue facts.

## 2. DATA-D1 Laws (Frozen v0.1)

### DATA-D1.1 — Competitors are discovery sources only
A competitor directory, marketplace, publication, comparison site or aggregator
may reveal that a robot may exist; indicate a known robot may have changed;
provide a possible manufacturer URL; expose fields worth investigating; provide
candidate factual values; reveal candidate images; identify possible suppliers or
offers. It may **not** directly create or overwrite canonical verified data.
`competitor claim ≠ canonical fact`.

### DATA-D1.2 — Discovery never equals verification
Every externally discovered fact begins **below** VERIFIED status.

```
Competitor reports: payload = 25 kg
  → candidate payload = 25 kg, status = NOT_VERIFIED, discovered_from = competitor
Manufacturer spec confirms 25 kg
  → canonical payload = 25 kg, confidence = VERIFIED
```

Only independently qualifying evidence may promote it.

### DATA-D1.3 — No wholesale competitor-database copying
DATA-D1 must not clone a competitor catalogue; bulk-republish competitor
descriptions; reproduce competitor field arrangements as content; import
competitor records directly into canonical tables; mirror competitor image
libraries; or treat competitor API output as HumanoidOnline's verified dataset.
This is a **product-governance prohibition**, independent of whether a particular
extraction is technically possible.

### DATA-D1.4 — Canonical promotion requires provenance
Every promoted fact must preserve enough lineage to answer: *What do we assert?
Where did the evidence come from? When was it observed? When was it verified? How
confident are we? What discovery event caused us to investigate it?* Discovery
provenance and canonical evidence provenance are **different**: the competitor
remains useful lineage but does not become the evidence supporting the verified
fact.

### DATA-D1.5 — UNKNOWN remains UNKNOWN
`UNKNOWN ≠ 0`, `≠ FALSE`, `≠ NOT_AVAILABLE`, `≠ SKIPPED`. Failure to find
confirming evidence does not prove a claim false. A candidate price with no
manufacturer confirmation resolves to `price = UNKNOWN` (candidate unresolved) —
never `0`, never "not for sale".

### DATA-D1.6 — Identity must resolve before facts can attach
A discovered item cannot attach to an existing robot merely because its name is
similar. Resolution considers, where available: manufacturer, model name, model
generation, official URL, aliases, announcement date, commercial generation,
model imagery, predecessor/successor relationships. `Figure 01 / 02 / 03` and
`Unitree H1 / H1-2` must remain distinct where the manufacturer establishes them
as separate products. **Ambiguous identity blocks canonical promotion.**

### DATA-D1.7 — Deduplication is evidence-aware
A newly discovered robot is first tested against: canonical robot identity; known
aliases; manufacturer identity; existing unresolved candidates. The crawler must
not create `Unitree G1` / `Unitree Robotics G1` / `G1 Humanoid Robot` / `G1` as
four canonical robots. When uncertain, `POSSIBLE_DUPLICATE` is preferable to
silently merging two identities.

### DATA-D1.8 — Conflicting sources are preserved, not averaged away
Given `A: 20 kg`, `B: 25 kg`, `C: 30 kg`, DATA-D1 must not compute `25 kg` by
averaging or voting. It raises `CONFLICT_DETECTED` with individual claims
retained. Resolution considers source authority, publication date, model/version
applicability, specification context, and supersedence. Until resolved,
`canonical confidence ≠ VERIFIED` — **unless a pre-existing, ratified governed
normalization rule deterministically resolves it** (e.g. the existing
manufacturer-declared-retirement → DISCONTINUED rule). DATA-D1 does not introduce
*new* auto-resolution rules under the guise of "normalization."

### DATA-D1.9 — Radar eligibility is gated *(Refinement R1, v0.1)*
A source is not a crawler target by default. Before a source joins the radar set,
its **Terms of Service and robots/access policy are reviewed**, and radar
membership is a recorded, reviewed decision. A source that forbids automated
access is **not radar-eligible even for discovery** (etiquette in §14 governs
*how* we crawl an eligible source; this law governs *whether* a source is
eligible at all). This protects the discovery layer legally at the point of
inclusion, not merely at the point of promotion.

### DATA-D1.10 — The discovery layer is not a shadow database *(Refinement R2, v0.1)*
DATA-D1.3 forbids copying competitor data into *canonical* tables. This law
extends the boundary to the **candidate layer itself**: the EU *sui generis*
database right concerns extraction/re-use of a *substantial part* of a protected
database, and that exposure exists **even if nothing ever reaches canonical.**
Therefore the candidate store retains only what is needed to drive
investigation — **identity leads, source URLs, and the specific claimed values
under investigation** — and never a full mirror of competitor records or their
descriptive prose/corpus. Candidate data is never served publicly (§22). The
discovery layer is a research work-queue, not a copied database.

## 3. Discovery Source Classes

How a candidate was *discovered* (not its canonical evidence strength):

```
COMPETITOR_DIRECTORY · MARKETPLACE · EDITORIAL · SEARCH_RESULT · DISTRIBUTOR
MANUFACTURER · PRESS_RELEASE · OFFICIAL_DOCUMENT · OFFICIAL_VIDEO · OTHER
```

## 4. Evidence Priority

A **search priority**, not an automatic confidence algorithm (a lower-priority
source may hold better evidence for a specific claim than a higher generic page):

```
1. Manufacturer product page
2. Manufacturer specification / technical documentation
3. Manufacturer press/media material
4. Manufacturer announcement
5. Official manufacturer store
6. Official distributor/integrator
7. Directly attributable deployment/customer source
8. Credible editorial source
9. Competitor directory/marketplace
```

## 5. Candidate Model

DATA-D1 introduces a discovery layer **structurally separate** from canonical
`robot`. Conceptually:

```
discovery_candidate {
    id
    entity_type
    candidate_name
    candidate_manufacturer
    discovery_source_type
    discovery_source_name
    discovery_url
    discovered_at
    last_seen_at
    candidate_data        // R2/DATA-D1.10: minimal — claimed values under
                          // investigation + identity leads; NOT a copied corpus
    identity_status
    candidate_status
    possible_robot_id
    possible_manufacturer_id
    verification_state
}
```

Exact schema is implementation design until ratified. The **law** is: discovery
data and canonical data must remain structurally distinguishable, and (per
DATA-D1.10) `candidate_data` is minimal-by-design, not a shadow copy.

## 6. Candidate Queue State Machine

```
DISCOVERED → IDENTITY_REVIEW → SOURCE_TRACE → VERIFICATION
          → READY_FOR_PROMOTION → PROMOTED
```

Side states: `POSSIBLE_DUPLICATE · CONFLICT · INSUFFICIENT_EVIDENCE · REJECTED ·
STALE · RECHECK_REQUIRED`. No crawler may jump `DISCOVERED → PROMOTED`.

**Refinement (v0.1) — identity matching (R4):** in `IDENTITY_REVIEW`, matching is
**deterministic/heuristic** (manufacturer + model + official URL + alias signals),
consistent with the frozen no-LLM/no-randomness-in-scoring law. **Ambiguity
routes to a human**, never to a machine merge. An LLM may — in a *future,
separately ratified* iteration — *propose* a candidate match for human
confirmation, but may **never auto-merge identities.**

## 7. Promotion Gate

A candidate becomes canonical only when all applicable gates pass:

- **P1 — identity:** the exact robot/model is sufficiently resolved.
- **P2 — provenance:** a qualifying source is recorded **as a standard
  `evidence_source` row** (R5, §8).
- **P3 — claim support:** the source actually supports the value being promoted.
- **P4 — conflict:** no unresolved evidence conflict invalidates the assertion.
- **P5 — normalization:** units/enums/status comply with canonical rules.
- **P6 — schema:** the canonical schema supports the field (DATA-D1 cannot invent
  a canonical field merely because competitors expose one).
- **P7 — validation:** existing catalogue/schema validation passes (G2, MEDIA-01,
  UNKNOWN semantics).
- **P8 — promotion path:** promotion occurs through the existing governed
  importer/service. **This is the sole human-approval gate in v0.1** (§18).

## 8. No direct crawler writes to canonical truth

Hard architectural boundary:

```
crawler → discovery store / candidate queue → verification
        → promotion service → canonical catalogue
```

Forbidden: `crawler → UPDATE robot SET …` or `crawler → rewrite
db/catalogue/robots/*.json` without passing the promotion gate. Extends the
standing principle: *no automation writes canonical truth merely because it
discovered something.*

**Refinement (v0.1) — canonical evidence reuse (R5):** promotion writes a normal
`evidence_source` row through the **existing** importer/service, using the
existing `source_type` / `confidence_level` enums and the G2 rule. DATA-D1
introduces **zero** new canonical evidence primitives; discovery provenance lives
**only** in the candidate layer and is linked from, not merged into, the canonical
evidence record. There is exactly one canonical evidence system.

## 9. Source tracing

From a competitor lead, DATA-D1 attempts to resolve the manufacturer website,
official product page, official store, technical document, press release, and
original image source. Outcomes:

- `TRACE_CONFIRMED` — original/authoritative source identified.
- `TRACE_PARTIAL` — some identity evidence found; the claim itself not confirmed.
- `TRACE_FAILED` — no independent qualifying source found.

`TRACE_FAILED` is **not an error requiring fabricated completion** — it is a
legitimate research outcome.

## 10. Image discovery and MEDIA-01

MEDIA-01 / MEDIA-01.8 remain authoritative. Discovered imagery is only a
**candidate image**. Pipeline:

```
candidate image → exact-model verification → source/provenance tracing
  → MEDIA-01 identity / rights / usage-basis evaluation
  → catalogue suitability evaluation → robot_image
```

A competitor-hosted image therefore does **not** automatically receive
`source_type = MANUFACTURER`, `is_official = true`, or `usage_basis =
OFFICIAL_MANUFACTURER_MEDIA`; those fields must reflect actual provenance. (Cf.
the Figure 02 correction: an image credited to an OEM but *retrieved* from an
editorial page is `EDITORIAL` retrieval, not manufacturer media.)

**Refinement (v0.1) — reference-only candidate images (R3):** during discovery
and investigation, candidate images are held as **URLs + metadata only**. DATA-D1
does **not** download or store competitor/editorial image **binaries** — there is
no candidate image cache. Only after tracing to an OEM/permitted source and
clearing MEDIA-01 do we self-host the OEM copy (the existing MEDIA-01 practice).
DATA-D1 may never bypass MEDIA-01 / MEDIA-01.8.

## 11. Newly discovered robots

DATA-D1 may create a candidate even with only partial information (e.g.
manufacturer + model + official URL found; height/payload/price/image UNKNOWN).
The system must **not require completeness for existence**: `verified existence ≠
complete specifications`.

## 12. Freshness and recheck policy

Each evidence-backed datum ultimately supports `observed_at`, `verified_at`,
`last_checked_at`. DATA-D1 may raise `RECHECK_REQUIRED` when the underlying source
changes; an official page disappears; a price is unchanged beyond policy; a new
generation appears; availability may have changed; or contradictory new evidence
appears. A stale source does **not** erase the existing canonical value — it
initiates verification.

**Refinement (v0.1) — autonomous RECHECK:** raising `RECHECK_REQUIRED` is
**workflow metadata about a record, not a canonical fact change**, and may be done
**autonomously** without the P8 human gate. Changing the underlying *value* still
requires promotion.

## 13. Change detection

Future iterations may detect: new robot / variant; price change; commercial-status
change; source disappearance; new official specification; deployment announced;
discontinuation; new image available. `change detected ≠ canonical change
accepted` — a detected change creates a candidate event, nothing more.

## 14. Rate limits and crawler etiquette

DATA-D1 behaves as a controlled research crawler, **not** an indiscriminate
scraper (this section governs *how* we crawl a source that DATA-D1.9 has already
deemed eligible): identify itself where technically applicable; respect site
access controls and crawler policy; conservative request rates; per-host
rate-limiting; caching; avoid re-downloading unchanged pages/assets; back off on
errors/throttling; **no authentication bypass; no CAPTCHA bypass; no defeating
technical access controls**; allow per-domain disablement; record crawl failures
rather than hammering a site. Objective: *high-value discovery, not maximum
extraction throughput.*

## 15. Discovery frequency

No single universal cadence: fast-changing commercial sources checked more often;
manufacturer catalogues moderate; stable technical docs low; failed/unavailable
sources on exponential backoff. Exact schedules are implementation policy, not
frozen.

## 16. Cross-source corroboration

Multiple competitors reporting the same robot may raise **candidate priority** but
must **never** raise canonical **confidence** by itself. `A,B,C all report Robot
X` → `priority = HIGH`, not `confidence = VERIFIED`. Verification still requires
qualifying evidence.

## 17. Candidate scoring

A prioritization score may decide what to investigate first (inputs: number of
independent discoveries, manufacturer identified, official URL found, commercial
relevance, newness, user demand, catalogue gap, source quality). But **`priority_
score ≠ confidence`** — scoring must never be reused as factual confidence.

## 18. Promotion authority

For DATA-D1 v0.1:

```
crawler              → discovers
automation           → traces, verifies, assembles evidence, PROPOSES
validator            → checks (G2 / MEDIA-01 / UNKNOWN / schema)
human/governed gate  → approves the canonical mutation (P8)
```

Not: `fully autonomous discovery → production truth`.

**Refinement (v0.1) — promotion-authority clarification:**
- Automation may **autonomously** run the entire pipeline **up to and including a
  structured promotion proposal**. Producing a proposal is not a canonical write.
- **Human approval is required only at the canonical mutation gate (P8)** — one
  place, clearly drawn.
- **`RECHECK_REQUIRED` may be raised autonomously** (workflow metadata, §12).
- **No deterministic auto-promotion in v0.1.** Later versions may permit narrow
  deterministic auto-promotion for tightly defined evidence classes, but only via
  a **separately ratified** rule. That capability is **not** authorized by
  DATA-D1 v0.1.

## 19. Auditability

Every promotion must be reconstructable:

```
candidate → discovery URL → trace result → evidence URL → claim extracted
  → normalization → verification result → canonical mutation
```

We must be able to answer *"why did this field enter HumanoidOnline?"* months
later.

## 20. Failure states

`SOURCE_NOT_FOUND` · `IDENTITY_AMBIGUOUS` · `CLAIM_UNCONFIRMED` · `SOURCE_CONFLICT`
· `SOURCE_UNAVAILABLE` · `MEDIA_UNVERIFIED` · `POSSIBLE_DUPLICATE`. **None may
silently fall through to VERIFIED.** DATA-D1 treats failure honestly.

## 21. Data retention

Rejected/unresolved candidates normally remain as **research history** rather than
being deleted immediately (`candidate today = unresolved` may become
`officially announced next month`; history also prevents repeated rediscovery
appearing as new work). Retention is refined during implementation — **subject to
DATA-D1.10**: retained history is minimal (leads/URLs/claims), never a growing
copied corpus.

## 22. API boundary

The public catalogue/API exposes **canonical** data, not raw discovery
candidates, unless a future research endpoint is deliberately created. `/api/robots`
must never return `NOT_VERIFIED` competitor claims merely because DATA-D1 stores
them. This is also a prerequisite for AGENT-01.

## 23. AGENT-01 invariant

DATA-D1 creates a cross-workstream law: **machine-readable / agent-accessible
interfaces may expose canonical truth, evidence and explicit uncertainty, but must
never silently promote discovery-candidate data merely because an agent requested
it.**

```
DATA-D1 discovery → verification → canonical truth → AGENT-01
```

not `DATA-D1 candidate → AGENT-01 public answer`. This is why AGENT-01
ratification stays blocked until DATA-D1 is ratified (see `docs/10_AGENT_CONTRACT.md`).

## 24. Initial competitor radar set

The implementation supports **configurable** sources, not hard-coded product
assumptions. An initial set *may* include already-identified competitors (e.g.
WhichHumanoid, Humanoid.guide, RobotHub, BotInfo, Androids.com, RoboDirectory).
**This list is configuration, not part of the frozen contract**; adding/removing a
radar source must not require a schema change. **Per DATA-D1.9, each candidate
source passes the radar-eligibility (ToS/robots) review before activation** — some
of these may be discovery-eligible, rate-limited, or excluded depending on that
review.

## 25. First build slice — DATA-D1 v0.1 (BLOCKED until ratified)

Deliberately narrow after ratification:

- **A. Discovery store** — the noncanonical candidate persistence layer (minimal
  retention per DATA-D1.10; structurally isolated per §27 gate).
- **B. Source adapter interface** — `discover(source) → Candidate[]`; each
  competitor is an adapter; each adapter only runs against a radar-eligible source
  (DATA-D1.9).
- **C. Identity matching** — deterministic resolution against existing robot /
  manufacturer / candidate / aliases; ambiguity → human (R4).
- **D. Verification queue** — the governed state machine (§6).
- **E. OEM/source tracing** — locate authoritative sources (§9).
- **F. Promotion proposal** — structured proposal (autonomous; not a write).
- **G. Human approval / promotion gate** — no autonomous canonical write (§18).
- **H. Audit/provenance** — persist candidate → evidence → promotion chain (§19),
  writing canonical evidence through the existing G2 model (R5).

## 26. Deliberate v0.1 non-goals

Not in the first implementation: autonomous canonical promotion; general-purpose
whole-internet crawling; LLM-generated specifications; **LLM auto-merge of
identities**; AI-generated robot imagery; competitor-content republication; a
competitor image **binary cache**; autonomous purchasing; provider outreach;
transactional marketplace operations; AGENT-01/MCP implementation; Rent/Buy/Lease
workflows; full historical price tracking; arbitrary competitor schema cloning.
DATA-D1 is **discovery + verification infrastructure**.

## 27. Proposed acceptance gates

DATA-D1 is not complete unless tests prove at least:

- **A** — competitor discovery does not become canonical (competitor payload, no
  authoritative evidence → canonical unchanged).
- **B** — independently verified fact can promote (manufacturer confirms →
  canonical mutation succeeds through the governed path).
- **C** — ambiguous identity blocks (could be Figure 02 or 03 → no promotion).
- **D** — duplicate detection ("Unitree Robotics G1" → links to existing Unitree
  G1; no duplicate canonical robot).
- **E** — conflicting authoritative evidence → `CONFLICT`, no silent overwrite.
- **F** — unknown stays unknown (verification fails → UNKNOWN/unresolved).
- **G** — image candidate obeys MEDIA-01 (identity/source not cleared → not
  display-eligible; and no binary was cached — R3).
- **H** — crawler cannot directly write canonical tables (architectural/test
  guard).
- **I** — public API excludes unresolved candidates.
- **J** — provenance survives promotion (canonical fact traces back through
  evidence and discovery lineage).
- **K — structural isolation (Refinement R6, v0.1):** candidate data **cannot
  surface through any canonical/API query path before promotion** — candidate
  tables are structurally separate from canonical, with no FK/join/query path that
  lets a candidate be read as canonical truth. This is the testable form of the §5
  / DATA-D1.10 law.

## 28. Proposed operational metrics

Measure verified expansion, not extraction volume: candidates discovered; new
robots discovered; duplicates suppressed; candidates awaiting verification;
official sources traced; promotion proposals generated; promotions approved;
conflicts detected; unconfirmable claims; stale canonical records detected; crawl
failures. **Not** "number of scraped records." Success metric = **verified
catalogue expansion.**

## 29. Expected product effect

From `human remembers robot → manually researches → adds record` to `market radar
→ detects → traces source → builds evidence package → governed verification →
canonical promotion` — the scalable path `7 → 50 → 200 → 500+` **without**
sacrificing the evidence discipline that differentiates HumanoidOnline.

## 30. Ratification record

**RATIFIED v0.1 by the product owner (Robert) on 2026-07-25.** This contract
freezes **principles**, not implementation. Ratification authorizes the
architecture `RADAR → CANDIDATE → TRACE → VERIFY → PROMOTE` and unblocks the
bounded v0.1 build slice (§25). It does **not** start implementation: the build
begins only on a separate, explicit owner trigger.

**Ratification statement (in force, 2026-07-25):**

> DATA-D1 Competitive Discovery & Verification Contract v0.1 is ratified.
> Competitor and external sources may create noncanonical research candidates
> only. Canonical HumanoidOnline truth requires identity resolution, independent
> qualifying evidence, provenance, validation and governed promotion. No discovery
> crawler may write canonical facts directly. Radar sources are ToS/robots-gated
> before use; the discovery layer retains minimal candidate data and never becomes
> a shadow database. MEDIA-01 remains authoritative for imagery. UNKNOWN semantics
> and all existing data laws remain binding. Promotion is human-gated at the
> canonical mutation (no deterministic auto-promotion in v0.1). Proceed with the
> bounded DATA-D1 v0.1 implementation described in the contract.

**Ratified v0.1 promotion authority:** human approval required for every canonical
promotion — high automation up to the proposal, low risk of silent catalogue
corruption. Narrow deterministic auto-promotion may be ratified **later,
separately**, once DATA-D1 has real operating history; it is not authorized now.

---

**Next authorized step:** the DATA-D1 **v0.1 build slice** (§25 A–H) may be built
once the owner issues a separate build trigger. The build must land through the
normal PR-gated ritual and satisfy the §27 acceptance gates (A–K). Until then, no
DATA-D1 implementation is authorized. AGENT-01 (`docs/10_AGENT_CONTRACT.md`)
remains blocked until DATA-D1 is built.
