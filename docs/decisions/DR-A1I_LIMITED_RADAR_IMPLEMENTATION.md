# DR-A1I — Limited Radar Implementation Contract

| | |
|---|---|
| **Status** | **OPEN — awaiting product-owner decision on the contract as a whole.** The `MANUAL_ONLY` sub-decision is **RESOLVED: ADOPTED**, 2026-07-30. |
| **Raised** | 2026-07-30 |
| **Revision** | 2 (2026-07-30) — `MANUAL_ONLY` adopted; eligibility-to-mode contradiction resolved; revocation scoped; PR #36 rebase consequence recorded |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Implements** | `docs/17` §13.1 step 1 (Amendment A1, RATIFIED, `main @ 626d1ce`) |
| **Normative text** | `docs/18_DATA_D1_LIVE_A1_LIMITED_RADAR_IMPLEMENTATION_CONTRACT.md` |
| **Base** | `main @ 626d1ce873d650a3f3a46381b33a3f970e9e8648` |

This record captures **why the contract is shaped the way it is and what turns
on ratifying it**. The contract carries the normative text; nothing here binds.

## 1. Context

Amendment A1 is ratified and merged. It creates the `NO_EXPRESS_PROHIBITION`
eligibility state, restricts it to `AGGREGATOR`-class sources, sets a 90-day
validity, freezes the restriction-applicability rules, and makes frozen per-host
operational ceilings a precondition of implementation. Its §13.1 requires a
separate implementation contract before any code.

This is that contract. It is deliberately written **before** any
network-capable code exists, because limits chosen after an adapter exists get
chosen to fit the adapter.

## 2. The decision

**Should the frozen implementation specification for `LIMITED_RADAR` — schema,
modes, database enforcement, HTTP ceilings, lifecycle, failure semantics,
acceptance gates and slice order — be ratified as written, so that
implementation may begin under it?**

Ratification authorizes **no source, no fetch and no code**. It authorizes the
*next* documents and slices to be written against a fixed target.

## 3. What repository inspection changed

Three findings materially shaped the contract, and none of them was assumable
from the conversation.

**`AGGREGATOR` is not on `main`.** A1's central rule names an enum value that
arrives with migration `0004` — PR #35, still an unmerged Draft. The
implementation migration is therefore `0005`, strictly dependent on `0004`. This
is the hard reason the existing stack must be rebased and merged before A1-I1
begins, and it converts a sequencing preference into a build dependency.

**`main` is thinner than the working tree suggested.** No acquisition layer, no
`MANUAL_BOOTSTRAP`, no `/discovery-review` — all three live only in the unmerged
stack. The contract records the inventory explicitly (§1) so a later reader does
not mistake stack state for `main` state.

**`radar_eligible` is load-bearing for `MANUAL_BOOTSTRAP`.** Replacing it with a
three-value mode enum would force bootstrap sources to declare `FULL_RADAR`.
That is the one open decision — §6 below.

## 4. Options considered on the central design question

The central question is how to replace boolean eligibility.

### Option 1 — widen the boolean

Keep `radar_eligible`, make it return true for the new state.

*Rejected.* Every existing call site would silently gain limited-radar sources,
including `ingest()`, and nothing in the type system would distinguish "may
fetch fully" from "may fetch within a narrow bound". This is precisely the
"boolean compatibility mapping" A1's reviewers ruled out.

### Option 2 — a second boolean

Add `limited_radar_eligible` alongside `radar_eligible`.

*Rejected.* Two booleans encode four states, two of which are meaningless
(`both true`, and `limited true while full false but tos = ALLOWED`). Invalid
combinations that the database cannot refuse will eventually be written.

### Option 3 — an explicit mode enum *(chosen)*

One column, mutually exclusive values, mapped to eligibility states by a
database `CHECK`.

*For:* invalid combinations become unrepresentable rather than merely
discouraged; the class precondition, the state requirement and the enablement
attribution are enforced by the same constraint; and removing `radar_eligible`
forces every call site to state which mode it means.

*Against:* it is a wider change than a boolean flag, and it touches `ingest()`,
which is ratified and working code.

## 5. Notable design consequences worth the owner's attention

**Expiry cannot be a `CHECK` constraint.** PostgreSQL requires `CHECK`
expressions to be immutable and `now()` is `STABLE`, so no constraint can
compare `eligibility_expires_at` against the current time. Expiry is enforced in
the request-construction path plus a `BEFORE INSERT` trigger on `crawl_run` and
`fetched_page`. This is stated in the contract rather than discovered during
implementation, because it means the expiry gate must be proven behaviourally —
gate G6 asserts an **empty transport call list**, not a status field.

**`ck_eligibility_check_negative_finding` is the load-bearing constraint of the
whole amendment.** A1 rests on the difference between "we searched and found
nothing" and "we never looked". The structured check table refuses a
`NO_RESTRICTION_FOUND` result that does not record what was searched. Without
that constraint the state degrades into an unfalsifiable assertion within a
year.

**Four new `fetch_outcome` values** — `NOT_FOUND`, `TOO_LARGE`,
`BLOCKED_BY_SCOPE`, `BUDGET_EXHAUSTED` — because the existing seven cannot
express the failures the ceilings create, and recording them all as `ERROR`
would make the run report useless exactly where it matters.

**Byte ceilings count decompressed bytes, measured while streaming.** A limit
applied after decompression is not a limit.

**Gates A1-G31 … A1-G41 were added** beyond the thirty requested, covering
`MANUAL_ONLY` and scoped revocation. They are normative, not conditional —
`MANUAL_ONLY` is adopted (§6).

## 6. The sub-decision — RESOLVED

**`MANUAL_ONLY`: ADOPTED by product-owner instruction, 2026-07-30.**

`MANUAL_BOOTSTRAP` reaches `ingest()` through `radar_eligible`, which this
contract removes. With only `DISABLED` / `LIMITED_RADAR` / `FULL_RADAR`
available, a bootstrap source would have to be recorded as `FULL_RADAR`: an
assertion of automated-access capability for a source that makes no requests at
all. `MANUAL_ONLY` says the true thing — enabled for attributed human-entered
ingest, permitted zero requests — and the §5.4 `CHECK` plus gates A1-G31…G41
make it enforced rather than asserted.

### 6.1 The contradiction the owner's review caught

Revision 1 contained two rules that could not both hold. The §4.2 mapping table
said `UNKNOWN`, `PROHIBITED`, expired and missing reviews permit only
`DISABLED`; the §5.4 `CHECK` permitted `MANUAL_ONLY` whenever `robots_status =
NOT_APPLICABLE`, regardless of `tos_status`. Left alone, one of them would have
been "fixed" during implementation — and the likely fix was the wrong one:
tightening the `CHECK` to require `ALLOWED`, which would have locked manual
research behind an automated-access permission.

**The resolution is that automated eligibility states govern only the automated
modes.** `tos_status` records an assessment of whether *this platform may send a
publisher a request*. It was never the right instrument for deciding whether *a
named human may type a record*, and using it that way was a category error that
happened to be invisible while `radar_eligible` collapsed everything into one
boolean.

### 6.2 Why this matters beyond the schema

The old arrangement required PR #36 to write `tos_status = ALLOWED` — a claim
that affirmative permission had been found — in order to do something entirely
legitimate that needed no permission at all. **A gate that can only be passed by
making a false statement is measuring the wrong thing.** That is the strongest
argument for the correction, and it is worth remembering the next time a gate
proves inconvenient: the question to ask first is whether the gate is asking the
right question.

Two consequences follow, both now frozen:

- **PR #36's rebase must stop writing `ALLOWED`** (contract §5.5). Its truthful
  default is `radar_mode = MANUAL_ONLY`, `tos_status = UNKNOWN`,
  `robots_status = NOT_APPLICABLE`, `is_enabled = true`. Nobody should later
  "fix" the resulting test failure by reinstating `ALLOWED`, which is why gates
  G37 and G38 exist.
- **Revocation is scoped** (`revocation_scope`: `AUTOMATED_ACCESS` or
  `ENTIRE_RELATIONSHIP`). A publisher who blocks our crawler has not necessarily
  objected to a person reading their public pages, and revision 1's blunt
  `revoked_at IS NULL OR radar_mode = 'DISABLED'` would have silently widened
  the first into the second. Gate G41 asserts the distinction.

A source may now hold `tos_status = PROHIBITED` **permanently and truthfully**
while remaining manually usable — which is exactly the position of the five
manufacturers whose terms prohibit automation, and the reason the seven-robot
catalogue was legitimate in the first place.

## 7. Consequences if ratified

| | |
|---|---|
| **Immediately** | Nothing. No source, no fetch, no code. |
| **Next** | The existing stack is rebased and merged (#35 → #36 → #37), because `0004` must precede `0005`. Then A1-I1. |
| **Implementation** | Five slices, in order: state and database enforcement → bounded transport against a local fake → discovery extraction → fresh source reviews → a single-source bounded proof. |
| **First live proof** | **One** qualifying `AGGREGATOR`, a small named candidate subset, reviewed before a second source is enabled. A four-source bulk run is not authorized. |
| **Canonical truth** | Unchanged. Gates W, S, T, X and P2/P8 all stand. |
| **Public surfaces** | Unchanged. `/api/robots` byte-identical; `/discovery-review` stays fail-closed as PR #37 built it. |

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Ceilings are quietly relaxed during implementation | Frozen as product limits with per-source values permitted **stricter only**, refused by `CHECK` if looser; missing or unlimited fails closed at startup (G15) |
| An adapter is written before the numbers are fixed | This contract precedes A1-I2 by construction, and A1-I2 forbids a real external adapter — the transport is written against a local fake |
| `LIMITED_RADAR` drifts into `FULL_RADAR` | Mutually exclusive enum, database `CHECK`, no general `is_eligible` boolean anywhere, G5 |
| A source is reclassified to gain eligibility | G3: changing `source_class` resets the mode to `DISABLED` and voids the review |
| The first live run is too broad | A1-I5 authorizes exactly one source and a small named subset |
| Expiry is assumed rather than enforced | G6 and G7 assert an empty transport call list; the trigger backs the code path |
| Stack drift while this is reviewed | This branch touches nothing but two new documents; #32, #35, #36 and #37 are untouched |

## 9. What is explicitly not being asked

Approval to fetch anything, to enable any source, to write any code, to reopen
`robotsguide.com` or `roboselect360.com`, or to widen A1's `AGGREGATOR`-only
scope. **One question remains: whether the frozen specification as a whole is
right.** The `MANUAL_ONLY` sub-decision is settled and is no longer part of the
ask.

## 10. Decision

```
MANUAL_ONLY radar_mode:   ADOPT
Decided by:               Robert Konecny (product owner)
Date:                     2026-07-30
Notes:                    MANUAL_ONLY is an operating mode, not an eligibility
                          finding. Automated eligibility states govern only the
                          automated modes; a manual, zero-request path needs no
                          automated-access permission and must not manufacture
                          one. An existing automation prohibition is recorded
                          honestly and is never weakened because a human is
                          doing the work.

--- contract as a whole: OUTSTANDING ---

DECISION:                 ____________________   (ADOPT / REJECT / AMEND)
Decided by:               ____________________
Date:                     ____________________
Notes:
```

If **ADOPT**: `docs/18` moves to RATIFIED, the existing stack is rebased and
merged in order, and A1-I1 is scoped and authorized as its own slice.
If **REJECT** or **AMEND**: `docs/18` is revised or marked REJECTED and
retained, and no implementation slice is authorized. Source-data extraction
tooling remains paused either way until the sequence in `docs/17` §13.1 is
reached in order.
