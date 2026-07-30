# DR-A1 — A third eligibility state: `NO_EXPRESS_PROHIBITION`

| | |
|---|---|
| **Status** | **OPEN — awaiting product-owner decision** |
| **Raised** | 2026-07-30 |
| **Revision** | 2 (2026-07-30) — owner review corrections: `AGGREGATOR`-only class precondition · restriction-applicability rules frozen · operational ceilings made an implementation precondition |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Amends** | `docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md` (RATIFIED v0.1, main @ `6875a34`) |
| **Normative text** | `docs/17_DATA_D1_LIVE_AMENDMENT_A1_NO_EXPRESS_PROHIBITION.md` |
| **Evidence** | `scratchpad/eligibility/ELIGIBILITY_REPORTS.md` §4–§5 (assessments of 2026-07-29 and 2026-07-30) |

This record captures **why the decision is being asked for and what turns on
it**. The amendment document carries the normative text; nothing here is
binding.

## 1. Context

The verified catalogue has stood at **seven robots**. The discovery queue holds
**43 candidates with zero specifications, zero prices and zero images**. That is
not a tooling gap — the DATA-D1 pipeline, the DATA-D1.LIVE schema, the identity
resolver and the review surface all exist. It is an **eligibility** gap: no
source has ever been enabled, because DATA-D1.9 requires terms that
affirmatively permit automated access, and no assessed source has them.

Two assessments produced that finding.

**2026-07-29 — official manufacturer sources.** Five of the sources the owner
most wants expressly prohibit automated access in their own terms: Unitree's
store, Agility Robotics, Boston Dynamics, Sanctuary AI, Engineered Arts. The
contract refused them, correctly, before any request was sent. The route is
permission, and four request emails are drafted and unsent.

**2026-07-30 — aggregators and competitor directories.** Seven radar sources
supplied by the owner, plus the IEEE Robots Guide lead carried over. Two —
`robotsguide.com` and `roboselect360.com` — serve a byte-identical
Cloudflare-managed block naming `ClaudeBot` with `Disallow: /` and asserting an
Article 4 (EU 2019/790) rights reservation. Both are properly refused.

**But four are different, and they are the reason this record exists.** The
Mimic, Lineroid, WhichHumanoid and RoboZaps are permissive on `robots.txt`, name
no agent-specific disallow, publish no rights reservation, present no technical
denial — and either have **no terms page at all** or have one that never
mentions automated access.

The contract refuses all four. Not because they said no; because they said
nothing.

## 2. The decision

**Should DATA-D1.LIVE recognise a third eligibility state for sources that have
expressed no prohibition, authorizing narrowly bounded radar discovery while
leaving every canonical-truth guarantee untouched?**

The question is *not* whether to relax the standard for published facts. It is
whether one word — `tos_status = ALLOWED` — should continue to gate two
genuinely different questions:

| Question | Nature |
|---|---|
| May we send this publisher an ordinary HTTP request? | About the publisher's expressed wishes |
| May what we read become a published HumanoidOnline fact? | About source authority, trace, and human verification |

The proposal answers the first with a bounded yes and the second with an
unconditional no.

## 3. Options considered

### Option 1 — Change nothing

Keep the affirmative-permission bar for all automated access.

*For:* maximally conservative; zero new surface; the standard already survived
two real assessments; no risk of a state being misread as permission later.

*Against:* the catalogue stays at seven for as long as the permission emails go
unanswered — and they may go unanswered indefinitely. It treats a publisher who
has never considered the question identically to one who has explicitly refused,
which is a defensible policy but not a distinction-preserving one.

### Option 2 — Ask every source for permission (status quo plus effort)

Extend the permission-request approach from manufacturers to aggregators.

*For:* produces `ALLOWED` — the strongest artefact; builds relationships; an
aggregator's business model often makes indexing easy to agree to.

*Against:* slow and externally gated; four emails have been drafted since
2026-07-29 and none is sent. It is complementary to, not a substitute for, the
decision at hand — and it should be done regardless of the outcome here.

### Option 3 — Human-in-the-loop acquisition only

A person reads the pages; `MANUAL_BOOTSTRAP` records what they say.

*For:* open today, needs nobody's permission, already ratified and built, and it
is how the current seven were built. Correct, and unaffected by this decision.

*Against:* it does not scale to hundreds of pages, and it consumes the owner's
own time — the scarcest input in the project. It closes the specification gap
slowly and does nothing for change detection.

### Option 4 — `NO_EXPRESS_PROHIBITION` *(the proposal)*

A third state, strictly weaker than `ALLOWED`, authorizing bounded radar only,
**available to `AGGREGATOR`-class sources alone**.

*For:* preserves the distinction between "they permitted" and "they said
nothing" **in the record itself**; unblocks the qualifying aggregator candidates
on review; keeps Gate W, Gate S, Gate T, Gate X, P2 and P8 untouched; scales
change detection; and the capability matrix ends every authorized path in a
human reviewing something. The class restriction confines the widening to the
sources that motivated it, leaving manufacturers, official stores and authorized
distributors on the unchanged `ALLOWED` bar.

*Against:* a genuinely new state to implement, gate and test; it is a place where
future carelessness could erode the standard; and it accepts a lower authority
basis than the contract has required so far. It also increases the number of
ways a source can be enabled, and every such way is a way to be wrong.

### Option 5 — Crawl anything not technically blocked

Rejected without analysis. It contradicts §0.1, which the owner ratified, and
would make the platform's central claim false.

## 4. Recommendation

**Adopt Option 4, and pursue Option 2 in parallel and unchanged.**

The reasoning that decides it: this platform's differentiator is not *how much*
it knows but *how well-founded* every published claim is. Nothing in the
proposal touches that. A `NO_EXPRESS_PROHIBITION` source can produce exactly one
kind of output — a `NOT_VERIFIED` candidate claim, class `AGGREGATOR`, with an
excerpt, queued for a human. It cannot verify, cannot promote, cannot satisfy
Gate W, cannot override a manufacturer, cannot be republished and cannot supply
an image. The canonical guarantees are unchanged in both letter and mechanism.

What it changes is the **input rate to human review** — which is the actual
bottleneck. And the four candidate sources are, by the owner's own competitive
assessment, the ones most worth watching: The Mimic occupies evidence-first
territory, HumanoidHub occupies catalogue-and-compare. Knowing what they list,
and where they disagree with each other and with us, is radar in the precise
sense the contract already permits in principle.

**Two cautions attach to the recommendation.**

*First, the honest cost.* This is the first time the project widens an access
rule rather than tightening one. The discipline that made the earlier
assessments produce correct answers came partly from the rule being simple. A
third state is a third thing to get right, and the place it will fail is not the
first review — it is the fifth, when someone records "no terms found" without
recording where they looked. Requirement 5 and requirement 8 exist against
exactly that, and they should be enforced in code, not in good intentions.

*Second, the naming.* `NO_EXPRESS_PROHIBITION` over `NO_PROHIBITION` is not
pedantry. The short name describes the source; the long name describes our
search. When a review later proves defective, that distinction is what separates
"the publisher changed" from "we looked badly" — and only the second is
actionable.

*Third, added at revision 2: the `AGGREGATOR` restriction may narrow the payoff
below what motivated the proposal.* The four candidate sources were described in
the 2026-07-30 assessment as "`COMPETITOR_DIRECTORY` / `AGGREGATOR`" without
deciding between them, and those are distinct enum values. Honest
classification — which §2.1 requires and adversarial example 16 protects — could
exclude some of them, and the amendment must not be rescued by relabelling. If
the reviews come back and the qualifying set is one source rather than four,
that is a signal to write a second amendment naming `COMPETITOR_DIRECTORY`
explicitly, with its own reasoning, rather than to stretch this one. The
recommendation to adopt still stands: the state is correct in shape, and its
scope is a separate question that should be decided on its own evidence.

## 5. Consequences if adopted

| | |
|---|---|
| **Immediately** | Nothing. Ratification approves no source. Candidates then need their own full reviews under the amended ten-requirement procedure; none of the 2026-07-30 assessments satisfies requirement 5. **And each must first pass the `AGGREGATOR` class precondition on an honest classification — which may leave fewer than four.** |
| **Implementation** | A separately authorized slice, and **not before per-host operational ceilings are frozen** (§10.3): enum widening on `eligibility_decision` and `tos_status`, mode-aware `radar_eligible`, an extended DB `CHECK` encoding the class condition, state-dependent expiry, new acceptance gates, run-report and `/discovery-review` display. Detailed in amendment §10. |
| **Other source classes** | Unchanged. `MANUFACTURER`, `OFFICIAL_STORE` and `AUTHORIZED_DISTRIBUTOR` still require `ALLOWED` for automated acquisition; every other class keeps the pre-amendment rules. Widening needs a further amendment. |
| **Training** | Prohibited on acquired content from every source under every directive — restated as a frozen rule (§4.1 rule 1) rather than left implied. |
| **Canonical truth** | Unchanged. Gate W, Gate S, Gate T, Gate X, P2 and P8 all stand as ratified. |
| **Public surfaces** | Unchanged. The state is invisible to the API, machine surfaces, sitemap and `llms.txt` (AGENT-01.7, Gate O). |
| **Permission strategy** | Unchanged and still primary. `ALLOWED` remains the goal for every source worth a real relationship, and the four drafted emails should go out regardless. |

## 6. Risks and their mitigations

| Risk | Mitigation |
|---|---|
| The state is mistaken for permission by a future reader | The name says otherwise; §3 of the amendment forbids mapping it to `ALLOWED` in any projection, report or UI; a proposed gate asserts it. |
| A defective review records an absence that was never searched for | Requirement 5 (record where you looked) and requirement 8 (attribution) — both to be enforced at write time, not by convention. |
| A publisher's silence ends and we do not notice | **`robots.txt` re-read at every run start** (24 h cache ceiling) and six immediate-revocation triggers, including publisher objection effective on receipt. **Note:** the 220-day expiry (owner decision) is longer than the 90-day `ALLOWED` validity, so it is a backstop rather than a control — the two continuous mechanisms carry this risk alone. Anyone later weakening either must account for that. |
| A source is reclassified to `AGGREGATOR` to make it eligible | Prohibited explicitly (§2.1, adversarial example 16), and the class condition is to be enforced in the DB `CHECK` alongside the state, not left to convention. The honest-classification requirement may narrow the amendment to fewer than four candidate sources — recorded in §9 so the owner decides with it visible. |
| A broad AI-use directive is read as training-only to gain eligibility | §4.1 rule 5: where scope cannot be determined, the restriction applies and the result is `UNKNOWN`. The review must record the rule applied and the scope determined, in a queryable form. |
| An adapter ships with generous or unbounded rate limits | §10.3 makes frozen per-host ceilings a **precondition** of the implementation slice — concurrency, rate, pages per run, bytes per page and per run — contract- or database-governed, unlimited values prohibited, declared crawl delay honoured as a floor. No adapter code precedes the numbers. |
| Scope creep from radar into fact-supply | The capability matrix is explicit on both sides, and the canonical refusal holds on two independent grounds — source class *and* eligibility state. |
| `PROHIBITED` sources drift back in via a site redesign | No automatic downgrade; a fresh named review is required and must consider whether the prohibition genuinely ended. |
| The Cloudflare template spreads and silently disqualifies sources mid-run | Already observed on two of seven hosts. Robots is re-read at every run start; an appearing agent-block halts the run `HALTED_BY_POLICY`. |

## 7. What is explicitly not being asked

This record does not ask for approval to fetch anything, to enable any source,
to write any code, or to reopen `robotsguide.com` or `roboselect360.com`. It
asks for one thing: whether the third state should exist.

## 8. Decision

```
DECISION:            ____________________   (ADOPT / REJECT / AMEND)
Decided by:          ____________________
Date:                ____________________
Notes:
```

If **ADOPT**: `docs/17` moves to RATIFIED, and the implementation slice is
scoped and authorized separately.
If **REJECT**: `docs/17` is marked REJECTED and retained — the reasoning stays
on the record so the question is not re-litigated from scratch, and
human-in-the-loop acquisition (Option 3) plus permission requests (Option 2)
remain the only routes.
