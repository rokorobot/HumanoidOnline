# DATA-D1.LIVE — Amendment A3: `AGENT_ASSISTED_RESEARCH`

> **STATUS: RATIFIED BY PRODUCT OWNER — 2026-09-11.**
> **REPOSITORY-EFFECTIVE ON MAIN — merge `883cb1f`.**
>
> **REVISION 4 (§6A / §6B): RATIFIED BY PRODUCT OWNER — 2026-09-11.**
> **REPOSITORY-EFFECTIVE ON MAIN — merge `67a572d`.**
> Laws and definitions in this document are **FROZEN**. See §12.
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`
> (RATIFIED v0.1, 2026-07-29) at **§2.1 — Acquisition modes** (a new research
> mode) and at **LIVE.2 / §5** (one narrow eligibility-review bootstrap
> exception, §2.6). It clarifies `11_DATA_D1_CONTRACT.md` **§8** and **§18**.
> Apart from the §2.6 exception it weakens no existing law, and the rule that
> **all product and source retrieval requires an existing affirmative
> eligibility decision** is unchanged.
>
> **Ratification changes what is permitted in principle. It approves no source,
> grants no permission to retrieve any product or source page, authorizes no
> schema change, and alters no existing catalogue or evidence row.** This
> amendment is governance only: it requires no code, migration or new data
> structure.
>
> **Revision history.** Revision 4 (2026-09-11; ratified by the product owner;
> repository-effective on main at merge `67a572d`) — adds §6A *No implied continuation — explicit
> phase authorization* and §6B *Work-order execution pattern*, records the
> base amendment's repository adoption (merge `883cb1f`) in this header, and
> adds the Revision 4 ratification record to §12. No other section is
> changed. Governing principle: *the owner authorizes actions, not
> trajectories.* Revision 3
> (2026-09-11) — consistency corrections at
> ratification: §2.6 restated as the explicit, sole, narrow
> *eligibility-review bootstrap exception* to LIVE.2, with its exclusions
> listed; every "access policy unchanged" statement narrowed to *product/source
> retrieval policy unchanged*; ratified at this revision. Revision 2
> (2026-09-11) — §2.5 replaced: pre-eligibility retrievals are retained for
> audit only, never support approval and are never relabelled compliant; a
> later eligibility decision permits only a fresh retrieval. §6.1(b): the
> owner's explicit approval is the gate, and the mechanical merge may be
> performed by an authorized agent after that approval. §2.6 added.

---

## 0. Why this exists

`docs/11` §18 already fixes where human judgment sits: automation may trace,
check, assemble evidence and **propose**; a human approves **only** at the
canonical mutation gate. `docs/16` §2.1 recognises two acquisition modes —
`AUTOMATED_LIVE` (an adapter) and `MANUAL_BOOTSTRAP` (a named human reading a
source). Neither describes how supervised catalogue research is now done: the
product owner starts an AI-agent session, the agent opens and reads sources,
extracts the facts, and returns a structured change proposal.

Because no mode names that activity, two failures become likely:

1. **Mislabelling** — agent-read evidence described as `MANUAL_BOOTSTRAP` or as
   "read by the owner". That is forged provenance, the failure this platform
   exists to prevent.
2. **Duplicated research** — the owner re-reading every source page to make
   the evidence count, so the approval gate becomes a second research pass
   instead of a governed decision.

This amendment names the mode, fixes how its evidence is labelled, and states
what human approval means. It leaves the product/source retrieval policy
unchanged (§2). Its one access-related addition is a narrow exception that
lets an agent read a host's policy material so that the eligibility review the
policy requires can actually be prepared (§2.6). It also closes the one
loophole that naming the mode could open: evidence gathered without
eligibility can never be converted into evidence gathered with it (§2.5).

## 1. Definition

**`AGENT_ASSISTED_RESEARCH`** is research in which an AI agent, inside a session
**explicitly initiated by the product owner** (or a named human the owner
designates) for a stated scope, retrieves, inspects and extracts source
evidence, and returns an **evidence package plus a canonical change proposal**.

| | |
|---|---|
| Initiated by | a named human, for a stated scope (a work order), recorded in the proposal |
| Performed by | the agent — code performs the fetch, navigation and extraction |
| Produces | an evidence package and a change proposal — never a canonical write |
| Ends at | the human approval gate (§6) |

`AGENT_ASSISTED_RESEARCH` is a **provenance and approval mode**, not an access
mode. It grants no access to any product or source content (§2). Its only
access-related provision is the narrow eligibility-review bootstrap exception
of §2.6.

## 2. Product/source retrieval policy is unchanged

2.1 **For every access-policy purpose, agent retrieval is automated access.**
The `docs/16` §2.1 classification stands verbatim: *the moment any part of
the fetch, navigation or extraction is performed by code rather than a person,
the activity is `AUTOMATED_LIVE`.* LIVE.2, LIVE.3, DATA-D1.9, `docs/17` (A1)
and `docs/21` (A2) apply to it in full for **all product and source
retrieval**, with no exception. An agent
may retrieve product or source content from a host only while that host holds
a **current, affirmative, attributed eligibility decision** under `docs/16` §5,
valid as LIVE.2 defines, and only on the paths that decision covers. The sole
exception to LIVE.2's eligibility-before-contact rule is §2.6, which covers
policy material only.

2.2 **Owner initiation grants nothing.** That the owner started the session is
not an eligibility decision, exactly as the beneficial purpose of `docs/16`
§0.1 is not one.

2.3 **Standing overrides still apply.** `robotshop.com` / `eu.robotshop.com`
are never retrieved by any agent-driven tooling (`docs/21` §5) — neither for
research nor under the §2.6 exception. No eligibility outcome changes this.

2.4 **Where a source cannot be retrieved compliantly**, the only permitted
routes remain:
- an **owner-supplied capture** — a page the owner captured and supplied. An
  agent may read the capture; that is not access to the host. Provenance
  states: "owner-supplied capture of <URL>, captured <date>, read by agent";
- **manufacturer-supplied evidence** (`docs/16` §2.1);
- another **already-authorized** source;
- otherwise the fact stays, or is withdrawn to, **UNKNOWN**.

2.5 **Retrieval before eligibility.**

1. A retrieval from a host that held no current affirmative eligibility
   decision at the time of retrieval is a **disclosed access-policy defect.**
   Every proposal that contains one says so.
2. The resulting observation **may be retained for audit and history only.**
3. It **may not support canonical approval**, and it is excluded from the
   evidence a proposal relies on.
4. If the host **later** receives a current affirmative eligibility decision,
   the agent may **re-retrieve** the source under compliant access and create
   a **fresh** supporting observation, with its own retrieval timestamp. The
   fresh observation stands on its own; it does not validate the earlier one.
5. Alternatively, the fact may be re-supported through §2.4
   (owner-supplied capture, manufacturer-supplied evidence, or another
   already-authorized source).
6. If neither 4 nor 5 occurs, the unsupported fact is **withdrawn to UNKNOWN.**
7. The original pre-eligibility retrieval is **never relabelled as
   compliant**, never re-dated, and never merged into the fresh observation.
   A later eligibility decision is prospective only.

2.6 **Eligibility-review bootstrap exception.**

This is the **sole, narrow exception** to LIVE.2's eligibility-before-contact
rule. It exists because a `docs/16` §5 review cannot be prepared without
reading the policy material the review is about.

In an owner-initiated session, an agent may make the **minimum read-only
requests** necessary to retrieve **only**:

- `robots.txt`;
- terms of service;
- legal pages;
- acceptable-use / automation-policy pages;

**solely** for preparing a `docs/16` §5 eligibility review.

This exception **MUST NOT** authorize:

- product-page retrieval;
- catalogue or data extraction;
- crawling beyond the policy material;
- authentication or login;
- form submission;
- account interaction;
- purchase or cart interaction;
- any other source research.

Further bounds:

- **LIVE.3 applies in full.** If a policy page is disallowed by `robots.txt`,
  blocked, or readable only by circumventing an access control, the agent stops
  and records the block. The review is then completed by a named human reading
  the material directly, or it remains undecided. A block is a finding.
- The agent produces **only a review draft and a recommendation**: the exact
  governing passages, the `robots.txt` rules for the exact paths proposed for
  later retrieval, and a recommended decision per axis.
- **The eligibility decision itself is always made and recorded by a named
  human reviewer** (`docs/16` §5). The agent never decides eligibility.
- The policy-page retrieval itself **remains disclosed automated access** and
  is recorded as such in the review record.
- This exception supersedes, for the preparation step only, the words
  "manually" in steps 1–2 of the `docs/16` §5 procedure. Every other step of
  that procedure, and every validity rule of LIVE.2, is unchanged.

## 3. Evidence record — existing structures only

Agent-assisted evidence uses the existing canonical evidence system: an
`evidence_source` row written through the existing importer (`docs/11` R5,
`docs/18` SA-07). **No agent-evidence table, no parallel provenance store.**

| Required | Recorded in |
|---|---|
| exact source URL (the page, never a site root) | `source_url` |
| source type | `source_type` (existing enum; distributor pages `OTHER` by convention) |
| source title | `source_title` |
| exact factual excerpt (≤ 1000 characters) | `excerpt` |
| observation timestamp | `observed_at` |
| retrieval actor / method, and eligibility basis | `note` — the fixed statement of §3.1 |
| confidence | `confidence` (§5) |
| conflicts | offer `note` / `specs_note`; conflicting commercial values kept as separate evidence rows |
| region / provider | the offer's `region_code` / `provider_slug`; a storefront's country, never widened to an economic zone or `GLOBAL` |

3.1 **Fixed provenance statement** (wording may evolve; the facts may not):

`RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) — retrieved <date> by <agent>
(<tool>) in a session initiated by <named human> for <scope>, under
eligibility decision <reference> for <host>. Not a MANUAL_BOOTSTRAP reading.
Not human-verified.`

A §2.5 observation instead states `PRE-ELIGIBILITY RETRIEVAL — audit only; may
not support approval (docs/26 §2.5)` and carries no eligibility reference.

3.2 **Specifications** carry no per-field evidence in the canonical model, so
the same statement is recorded in `specs_note`, as the catalogue-authoring
convention already requires for spec provenance.

3.3 **Page hash and locator** (LIVE.6) bind discovery-layer claims.
`evidence_source` has no columns for them; they are recommended in the
evidence package but not required on the catalogue-authoring path.

## 4. Truthful labelling

Agent-retrieved evidence **must never** be described as:
- `MANUAL_BOOTSTRAP`;
- read, checked or verified by the product owner or any named human;
- human-verified;
- `extraction_method = MANUAL` (that value denotes a human);
- compliant, if it was retrieved before eligibility (§2.5.7).

A later genuine human reading of the primary source is recorded as **its own
act** under existing rules. It never rewrites the history of the agent row.

## 5. What agent-assisted evidence may and may not do

**May:**
- support a canonical **change proposal**, when retrieved under compliant
  access (§2);
- carry `LOW` / `MEDIUM` / `HIGH` confidence under the existing rubric
  (`db/catalogue/README.md` §4, `docs/03` §5). Confidence is judged by source
  authority and degree of interpretation, not by who retrieved the page.

**May never, by itself:**
- set `confidence = VERIFIED` or `verified_at`;
- set `is_published = true`;
- set `claim_status = VERIFIED` in the discovery layer;
- set MEDIA-01 `identity_status = VERIFIED` — an identity image still requires
  a named human who looked at it (MEDIA-01, unchanged);
- resolve a conflict, or merge identities (`docs/11` §6 R4, DATA-D1.8).

**Unchanged and binding:** UNKNOWN remains UNKNOWN (DATA-D1.5); conflicts are
preserved, never guessed or averaged (DATA-D1.8); maturity, obtainability and
price semantics never merge (LIVE.7).

## 6. The human approval gate

6.1 **Where.** At the canonical mutation gate, one per path:
- **(a) DATA-D1 promotion** — P8 (`docs/11` §7, §18), via the governed
  promotion service.
- **(b) Catalogue authoring** — a change set to `db/catalogue/`, **merged only
  after explicit product-owner approval**, and loaded by the governed
  importer. The approval is the gate. The mechanical merge may be performed by
  an authorized agent, but only after that approval exists and only for the
  exact change set approved. For this path, `docs/11` §8's prohibition on
  rewriting `db/catalogue/robots/*.json` without passing the promotion gate is
  read as follows: an agent-authored change set is a **proposal, not canonical
  truth,** until it is merged after the owner's approval. P1–P7 are met by the
  proposal plus the repository's own validation (tests, G2, MEDIA-01, CI).

6.2 **What the owner is shown (minimum evidence package):**
- per robot: the identity or reconciliation decision and the duplicate check;
- every proposed fact, with its supporting evidence (URL, title, excerpt,
  `observed_at`, confidence, eligibility reference);
- every conflict and every UNKNOWN field;
- every held item, and why;
- every §2.5 pre-eligibility observation, listed separately and marked as not
  supporting the proposal;
- `is_published` before and after, for every affected robot.

6.3 **What approval means:**
> "I approve this proposed catalogue mutation based on the evidence package
> presented to me."

It does **not** mean "I personally read every source page". It is **not**
verification: approval sets no `verified_at` and no `VERIFIED`. It does not
cure any §2.5 defect.

6.4 **No re-reading duty.** The approver is not required to reopen any cited
source. They may spot-check, reject, or ask for changes. A spot-check that is a
genuine human reading of the primary source may be recorded as such (§4).

6.5 **Record.**
- Path (a): the promotion audit operator.
- Path (b): the owner's explicit approval statement in the change request —
  approver, date, scope, and the exact commit it covers — recorded **before**
  the merge. A merge whose approval is missing, or covers a different commit,
  is not an approved mutation.

No schema change.

## 6A. No implied continuation — explicit phase authorization

*(Revision 4 — ratified by the product owner 2026-09-11;
repository-effective on main, merge `67a572d`.)*

6A.1 **Every materially distinct execution phase requires explicit owner
authorization before it begins.** Distinct phases include at least: a source
eligibility review (§2.6); product or source retrieval; authoring or changing a
canonical change proposal; canonical mutation; commit; push and pull request;
merge; publication; and any cleanup or follow-up work.

6A.2 **Completion or approval of one phase is not authorization for any
logically subsequent phase.** Approval to merge a governance change does not
authorize an eligibility review; an eligibility decision does not authorize
retrieval; research does not authorize mutation; mutation does not authorize a
commit; a commit does not authorize a merge; a merge does not authorize
publication; publication does not authorize unrelated follow-up work.

6A.3 **Within an authorized phase the agent may only:** inspect within that
phase's scope; execute the explicitly authorized action; verify it; report the
result; and recommend a next action.

6A.4 **The agent stops before any recommended next action** unless the owner
explicitly authorizes that action.

6A.5 **Sequencing language is not authorization.** Words such as "after
this", "next", "then", "once merged", "after CI" or "following approval"
describe order only. A later phase described that way — including an
instruction to proceed with a later phase once an earlier one succeeds — is
treated as **PROPOSE ONLY**: the agent completes the earlier phase, reports,
and stops. It becomes authorized only when the owner explicitly authorizes it
after the earlier phase has been reported, or when the work order lists it
under **AUTHORIZED NOW**.

6A.6 **Work orders distinguish two lists:**
- **AUTHORIZED NOW** — actions the agent may perform;
- **PROPOSE ONLY** — possible next actions that must not be performed yet.

Where a work order does not make the distinction, only the immediately
requested action is authorized, and everything after it is PROPOSE ONLY.

6A.7 **External access is its own authorization boundary.** Authorization to
change governance, code or catalogue files, or to merge a pull request, does
not authorize any new network access to third-party sources. Traffic with this
project's own repository host or infrastructure that is strictly necessary to
perform an explicitly authorized repository action is part of that action —
for example: a fetch needed to verify the approved branch state; a push when
push is explicitly authorized; opening the explicitly authorized pull request;
reading CI or check status for that pull request. This applies only to the
project's own repository and infrastructure operation. It **never** authorizes
third-party research or source access.

6A.8 **A source eligibility review is a distinct, externally active phase**
and requires explicit owner authorization naming the hosts. The
"owner-initiated session" of §2.6 means a session whose current work order
explicitly authorizes that review for those hosts.

6A.9 **Product or source retrieval after an eligibility decision is another
distinct phase** and requires explicit owner authorization naming the hosts
and pages. An eligibility decision permits retrieval in principle; it never
starts it.

6A.10 **Canonical mutation, commit, merge and publication remain separate
boundaries**, unless the owner's work order expressly combines specific named
boundaries — for example, "commit, push and open a Draft PR; do not merge".

6A.11 **Authorization is never inferred** from project goals, governance
logic, previous discussions, likely owner intent, the next action being
obvious, or the prior action having succeeded.

6A.12 **If authorization is ambiguous, the agent stops and reports.**

6A.13 **No retroactive justification.** Work performed beyond an authorized
boundary is disclosed as such. It is not reinterpreted as authorized because it
proved useful, and its outputs trigger nothing — no decision is recorded from
them and no further action follows from them — unless the owner explicitly
authorizes their use.

6A.14 **Scope.** This section binds every `AGENT_ASSISTED_RESEARCH` session and
every agent acting on this repository's catalogue or governance under a work
order. It narrows what an agent may do; it never widens any permission.

**Standing processes.** This section does not repeal a standing authorization
that an already-ratified contract explicitly establishes for a system process
(for example the scheduled-freshness trigger of `docs/21` and `docs/22`).
Such an authorization:
- is valid only within the exact scope, trigger, cadence and permissions that
  its own contract grants;
- may not be extrapolated into a new workflow or into new source access;
- can be changed only through the governance process applicable to that
  contract.

The existing scheduled-freshness contracts remain governed by their own
ratified rules.

## 6B. Work-order execution pattern

*(Revision 4 — ratified by the product owner 2026-09-11;
repository-effective on main, merge `67a572d`.)*

    1. INSPECT       within the authorized scope only
    2. REPORT        findings, and the exact intended action
    3. OWNER AUTHORIZATION
    4. EXECUTE       exactly the authorized scope
    5. VERIFY
    6. REPORT RESULT
    7. STOP

Any further phase is presented as a recommendation (**PROPOSE ONLY**) and is
not executed until the owner explicitly authorizes it.

## 7. Publication

Publication stays a **separate, explicit owner decision**. Approving a mutation
never publishes anything. `is_published` remains editorial state (DR-C1; the
importer preserves it).

## 8. `MANUAL_BOOTSTRAP` is unchanged

`MANUAL_BOOTSTRAP` remains valid, and distinct, for sources genuinely read by a
named human and for manufacturer-supplied material. It is no longer the only
path for supervised catalogue research. Owner-supplied captures remain the
route to sources an agent may not access (§2.4).

## 9. Compatibility with the DATA-D1 pipeline

    RADAR → CANDIDATE → TRACE → VERIFY/REVIEW → PROPOSE → HUMAN APPROVAL
          (→ separate, optional PUBLICATION decision)

`AGENT_ASSISTED_RESEARCH` may perform **TRACE** (including the official trace
of `docs/16` §11.1), assemble **VERIFY/REVIEW** evidence, and **PROPOSE** — on
eligible hosts only. It never approves, promotes or publishes. "Verifies" in
`docs/11` §18 means checking that a source supports a claim; it never means
setting `VERIFIED`.

**Writing discovery-layer rows from an agent session is not authorized here:**
`extraction_method` has no truthful value for agent extraction. Adding one
needs a separate implementation contract.

## 10. Adversarial examples

| # | Situation | Correct outcome |
|---|---|---|
| 1 | Agent writes "verified at source" in a note | Refused. The note states agent retrieval (§3.1); confidence ≤ HIGH. |
| 2 | Owner approves the change set; an agent performs the merge | Valid only if the approval statement, covering that exact commit, precedes the merge (§6.5). Every evidence row keeps `verified_at` NULL. |
| 3 | A host's terms prohibit automated access | The agent does not retrieve product or source content. An owner capture, manufacturer material, another authorized source, or UNKNOWN (§2.4). |
| 4 | Agent retrieved before any eligibility decision; the host is later found `ALLOWED` | The old observation stays audit-only and is never relabelled. The agent re-retrieves under the new decision and creates a fresh observation; only that one can support approval (§2.5). |
| 5 | "Just this once" on robotshop.com | Never — neither for research nor under §2.6 (§2.3). |
| 6 | Agent proposes averaging two DoF figures | Refused. The field stays UNKNOWN with the conflict recorded. |
| 7 | Approved robot "should now go live" | Only by a separate publication decision (§7). |
| 8 | Agent drafts an eligibility review and marks the host `ALLOWED` | Refused. The agent recommends; a named human decides and is recorded (§2.6). |
| 9 | While reading a host's terms page under §2.6, the agent "quickly checks" a product page | Refused. §2.6 covers policy material only; product retrieval waits for an affirmative decision (§2.1). |
| 10 | The terms page is disallowed by `robots.txt` or sits behind a challenge page | The agent stops and records the block; a named human reads it directly, or the review stays undecided (§2.6, LIVE.3). |

## 11. Non-goals

This amendment does not:
- approve any source;
- grant permission to retrieve any product or source page, or change LIVE.2,
  LIVE.3, DATA-D1.9, A1 or A2 — other than the §2.6 bootstrap exception, which
  covers policy material only and lets an agent prepare, never decide, a
  review;
- permit any retroactive validation of evidence;
- change any enum or table, or require any code, migration or data structure;
- create an evidence store;
- change the meaning of `VERIFIED` or `verified_at`;
- authorize auto-promotion, merge without explicit owner approval, or
  auto-publication;
- change MEDIA-01;
- reclassify any evidence row that already exists.

## 12. Ratification record

    STATUS:                    RATIFIED — 2026-09-11 (revision 3)
    Ratified by:               Robert Konecny (product owner)
    Amends:                    docs/16 §2.1 (new mode: AGENT_ASSISTED_RESEARCH);
                               docs/16 LIVE.2 / §5 (sole narrow
                               eligibility-review bootstrap exception, §2.6);
                               clarifies docs/11 §8 and §18
    Schema change:             NONE
    Code / migration required: NONE — governance only
    Sources approved:          NONE
    Retrieval policy:          Product/source retrieval policy unchanged —
                               a current affirmative per-host eligibility
                               decision is required before any product or
                               source retrieval. §2.6 introduces only a narrow
                               eligibility-review bootstrap exception (policy
                               material only; review draft only; a named human
                               decides).
    Pre-eligibility evidence:  audit/history only; never supports approval;
                               never relabelled compliant; a later decision
                               permits only a fresh retrieval
    Approval gate:             P8 (promotion), or explicit owner approval of
                               an exact catalogue change set before merge; an
                               authorized agent may mechanically merge only
                               that approved change set after approval
    Approval meaning:          approval of the presented evidence package; not
                               verification; not publication
    RobotShop:                 never retrieved by agent tooling (unchanged)
    Evidence system:           existing evidence_source only; no parallel store
    Repository adoption:       base amendment merged to main @ 883cb1f
                               (PR #49) — repository-effective
    Revision 4:                §6A, §6B — RATIFIED by product owner
                               2026-09-11; REPOSITORY-EFFECTIVE ON MAIN —
                               merge 67a572d (PR #50)

> **Ratification statement — approved by product owner 2026-09-11; effective in
> repository governance when this amendment is merged to main:**
>
> I, Robert Konecny (product owner), ratify Amendment A3
> `AGENT_ASSISTED_RESEARCH`.
>
> An AI agent, in a research session I explicitly initiate, may retrieve,
> inspect and extract source evidence and return an evidence package and a
> canonical change proposal, subject to the source-access rules in this
> amendment.
>
> Agent-retrieved evidence is labelled truthfully as agent retrieval. It is
> never called `MANUAL_BOOTSTRAP`, never attributed to me, and never described
> as human-verified.
>
> Product/source retrieval requires a current affirmative eligibility decision.
>
> For the sole purpose of preparing such a decision, §2.6 permits the minimum
> read-only automated retrieval of `robots.txt` and applicable terms, legal and
> acceptable-use pages. That narrow exception authorizes no product-page or
> catalogue research. The agent may recommend an eligibility outcome; the
> decision itself is always made and recorded by a named human.
>
> A retrieval made before required eligibility is a disclosed access-policy
> defect. Its observation is retained for audit/history only, never supports
> canonical approval, and is never retrospectively relabelled compliant. A
> later affirmative decision permits only a fresh retrieval.
>
> Human approval sits at the canonical mutation gate: P8 promotion, or my
> explicit approval of an exact catalogue change set before merge. An
> authorized agent may mechanically merge only that approved change set after
> approval.
>
> My approval means:
>
> "I approve this proposed catalogue mutation based on the evidence package
> presented to me."
>
> It does not mean I personally read every source page. It sets no `VERIFIED`,
> no `verified_at`, and no publication.
>
> UNKNOWN remains UNKNOWN. Conflicts are preserved. Nothing is guessed or
> averaged.
>
> `MANUAL_BOOTSTRAP` remains valid for genuinely human-read sources.
>
> `robotshop.com` and `eu.robotshop.com` remain prohibited from agent
> retrieval.
>
> Publication remains a separate explicit decision of mine.
>
> This ratification approves no source and authorizes no schema change.

> **Revision 4 ratification statement — approved by product owner 2026-09-11;
> effective in repository governance when Revision 4 is merged to main:**
>
> I, Robert Konecny (product owner), ratify Revision 4 of DATA-D1.LIVE
> Amendment A3.
>
> Every materially distinct agent execution phase requires explicit
> authorization before it begins.
>
> Approval or completion of one phase does not authorize the next phase.
>
> Sequencing language describes order, not permission.
>
> A work order may explicitly authorize multiple named phases in advance under
> AUTHORIZED NOW. Anything not so authorized is PROPOSE ONLY.
>
> External third-party access is a separate authorization boundary.
>
> Eligibility review, source retrieval, canonical mutation, commit, merge and
> publication are separate authorization boundaries unless I expressly combine
> specific named boundaries in the work order.
>
> The agent may recommend the next action, but must stop before executing it
> unless it is explicitly authorized.
>
> Authorization is never inferred from project goals, governance logic,
> previous discussions, likely intent, obvious next steps, or successful
> completion of prior work.
>
> If authorization is ambiguous, the agent stops and reports.
>
> Standing autonomous processes remain valid only to the extent explicitly
> authorized by their own ratified contracts.
>
> Work performed outside an authorized boundary is disclosed truthfully and
> cannot be retroactively treated as authorized merely because it was useful.
