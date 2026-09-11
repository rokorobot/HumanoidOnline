# DATA-D1.LIVE — Amendment A3: `AGENT_ASSISTED_RESEARCH`

> **STATUS: RATIFIED BY PRODUCT OWNER — 2026-09-11.**
> **REPOSITORY-EFFECTIVE ON MAIN — merge `883cb1f`.**
>
> **REVISION 4 (§6A / §6B): RATIFIED BY PRODUCT OWNER — 2026-09-11.**
> **REPOSITORY-EFFECTIVE ON MAIN — merge `67a572d`.**
>
> **REVISION 5 (owner-authorized public research): RATIFIED BY OWNER
> 2026-09-11 — repository-effective upon merge.**
> Laws and definitions in this document are **FROZEN**. See §12.
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`
> (RATIFIED v0.1, 2026-07-29) at **§2.1 — Acquisition modes** (a new research
> mode) and at **LIVE.2 / §5**: from Revision 5, an explicit owner research
> work order — not a per-host eligibility decision — authorizes an agent's
> retrieval of publicly accessible product and source material (§2.1). LIVE.2,
> DATA-D1.9, `docs/17` (A1) and `docs/21` (A2) continue to govern every
> standing automated process — adapters, the discovery radar and scheduled
> freshness — unchanged (§2.2). Revision 5 also withdraws the
> `robotshop.com` / `eu.robotshop.com` hard override of `docs/21` §5 and
> `docs/22` Phase 10 (§2.3). It clarifies `11_DATA_D1_CONTRACT.md` **§8** and
> **§18**, and the scope of **DATA-D1.9** (§2.2).
>
> **Ratification changes what is permitted in principle. It starts no
> retrieval, approves no source for any standing automated process, authorizes
> no schema change, and alters no existing catalogue or evidence row.** This
> amendment is governance only: it requires no code, migration or new data
> structure.
>
> **Revision history.** Revision 5 (2026-09-11; ratified by the product owner;
> repository-effective upon merge) —
> replaces the per-host eligibility prerequisite for agent research with
> explicit owner work-order authorization (§2.1); keeps LIVE.2 / DATA-D1.9 for
> standing automated processes (§2.2); withdraws the RobotShop hard override,
> recording the browser-pane instability as a tool constraint only (§2.3);
> keeps pre-Revision-5 pre-eligibility observations audit-only and
> un-upgraded (§2.5); lets a work order set its scope by research target and
> source class, with relevant discovered sources in scope unless it restricts
> discovery (§2.1, §6A.9); removes any mandatory policy or `robots.txt`
> pre-review and defines reactive handling of restrictions and blocks actually
> encountered (§2.6); restates no circumvention (§2.7). Consequential edits in §0, §1, §3, §4, §5, §6.2, §6A.1,
> §6A.8, §6A.9, §8, §9, §10, §11 and §12. Revision 4's principle — *the owner
> authorizes actions, not trajectories* — is unchanged. Revision 4 (2026-09-11; ratified by the product owner;
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
what human approval means. From Revision 5 it also states the access basis for
agent research: an explicit owner research work order, within its scope
(§2.1). Standing automated processes keep their per-source eligibility
discipline (§2.2). Evidence retrieved before Revision 5 without the
eligibility the earlier text required is never converted into supporting
evidence (§2.5).

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

`AGENT_ASSISTED_RESEARCH` is a **provenance and approval mode**. From Revision
5 it is also an access basis, but only inside an explicit owner research work
order that authorizes retrieval, and only within that work order's scope
(§2.1, §6A.9). Starting a session is not, by itself, authorization to retrieve
anything.

## 2. Access basis for agent research *(Revision 5)*

2.1 **An explicit owner research work order authorizes agent retrieval.** An
agent may retrieve **publicly accessible** product and source material —
manufacturer pages, distributor and marketplace listings, datasheets, manuals,
support and technical documentation, and search-engine results used to locate
sources — when, and only while, an explicit owner research work order
authorizes that retrieval (§6A.9). **No separate per-host eligibility decision
under `docs/16` §5 is required first.** A work order need not enumerate hosts
or URLs in advance: it may authorize by research target and source class — for
example, "research publicly accessible manufacturer, distributor,
technical-documentation and other directly relevant sources for these robots,
including relevant sources discovered during the research". Relevant publicly
accessible sources discovered during the research are within the authorized
phase unless the work order explicitly restricts discovery. Retrieval outside
the work order's scope — an unrelated target, an excluded source class, or
discovery it restricts — is outside authority (§2.5). The work order is
recorded in every evidence row it supports (§3.1).

2.2 **Standing automated processes are unchanged.** An `AUTOMATED_LIVE`
adapter, the discovery radar (DATA-D1.9, `docs/17`) and a `SCHEDULED_FRESHNESS`
run (`docs/21`, `docs/22`) still require a current, affirmative, attributed
eligibility decision under `docs/16` §5, valid as LIVE.2 defines and enforced
by `radar_eligible`. For them the `docs/16` §2.1 classification stands
verbatim: code-performed fetching is `AUTOMATED_LIVE` and LIVE.2 applies in
full. A research work order is **not** an eligibility decision: it never
enables a `DiscoverySource`, never makes a host radar- or freshness-eligible,
and never registers a freshness target. DATA-D1.9 governs whether a source
joins the radar set; a research session adds nothing to that set and writes no
discovery rows (§9).

2.3 **RobotShop.** No domain-wide governance prohibition applies to
`robotshop.com` or `eu.robotshop.com`. Both are researched like any other
public source under §2.1, §2.6 and §2.7. The Claude Code Browser pane's
instability on those domains is a **tool-stability constraint only**: where
that browser is unstable, the agent uses another suitable read-only retrieval
method (for example a plain HTTP fetch tool) instead. The hard `MANUAL_CHECK`
override of `docs/21` §5 and `docs/22` Phase 10 is withdrawn. The US and EU
storefronts remain separate providers, and an offer is attributed only to the
storefront that states it.

2.4 **Where a source cannot be retrieved within authority**, the only
permitted routes remain:
- an **owner-supplied capture** — a page the owner captured and supplied. An
  agent may read the capture; that is not access to the host. Provenance
  states: "owner-supplied capture of <URL>, captured <date>, read by agent";
- **manufacturer-supplied evidence** (`docs/16` §2.1);
- another **already-authorized** source;
- otherwise the fact stays, or is withdrawn to, **UNKNOWN**.

2.5 **Retrieval outside authority, and historical pre-eligibility
retrievals.**

1. A retrieval outside the scope of an authorizing research work order is a
   **disclosed access-policy defect**. Every proposal that contains one says
   so (§6A.13).
2. Every observation retrieved **before Revision 5** from a host that then
   lacked the eligibility decision the earlier text of this section required
   remains a **historical pre-eligibility observation**. Revision 5 does not
   upgrade it.
3. Both kinds of observation **may be retained for audit and history only.**
   Neither **may support canonical approval**; both are excluded from the
   evidence a proposal relies on.
4. A fact such an observation touched can support approval only through a
   **fresh** retrieval within an authorizing research work order, with its own
   retrieval timestamp, or through §2.4. The fresh observation stands on its
   own; it does not validate the earlier one.
5. If neither occurs, the unsupported fact is **withdrawn to UNKNOWN.**
6. The earlier observation is **never relabelled as authorized or
   compliant**, never re-dated, and never merged into the fresh observation.
   Revision 5 is prospective only.

2.6 **No policy pre-review; restrictions actually encountered are
respected.**

There is **no requirement** to inspect `robots.txt`, terms of service, legal
pages, acceptable-use, privacy or automation-policy pages before
owner-authorized research under §2.1, and this section creates **no
policy-review gate**. The agent may consult such material when it is useful to
the research.

If, during the research, the agent **actually encounters** a clear access
restriction or a technical block, it respects it and reports it:

- a restriction is respected for what it applies to — the path, method, user
  agent or tool it names. It closes a whole host only where it is itself
  clearly host-wide; the agent then stops retrieving from that host and
  reports it;
- a technical block — a login wall, a CAPTCHA or challenge page, a paywall,
  an access control, an explicit block page — ends retrieval of what it
  blocks; nothing is circumvented (§2.7);
- every restriction or block encountered, and how it was respected, is
  recorded in the evidence package (§6.2); the routes of §2.4 remain.

**`robots.txt` is not a permission system.** It neither grants permission nor
is a prerequisite to research. Where the agent actually consults or encounters
it, its rules are read only for the applicable user agent and path: a rule
that disallows the agent's user agent on a path is respected for that path.
This is reactive handling of what is encountered, not a pre-research
eligibility process.

2.7 **No circumvention; proportionate retrieval.** LIVE.3 applies in full.
The agent never bypasses authentication or login requirements, CAPTCHA or
other challenge pages, paywalls, access-control mechanisms or other technical
restrictions; never misrepresents its user agent; and never rotates IPs or
proxies to evade a block. It never submits a form, and never interacts with an
account, cart or checkout. A page that cannot be read without one of these is
recorded as blocked — a block is a finding — and the routes of §2.4 apply.
Retrieval stays proportionate to the work order: only the pages its research
needs, no bulk catalogue extraction and no site mirroring (DATA-D1.10,
LIVE.10).

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
| retrieval actor / method, and authorizing work order | `note` — the fixed statement of §3.1 |
| confidence | `confidence` (§5) |
| conflicts | offer `note` / `specs_note`; conflicting commercial values kept as separate evidence rows |
| region / provider | the offer's `region_code` / `provider_slug`; a storefront's country, never widened to an economic zone or `GLOBAL` |

3.1 **Fixed provenance statement** (wording may evolve; the facts may not):

`RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) — retrieved <date> by <agent>
(<tool>) in a session initiated by <named human> for <scope>, under research
work order <reference> (docs/26 §2.1). Not a MANUAL_BOOTSTRAP reading. Not
human-verified.`

A §2.5 observation retrieved outside authority instead states
`OUTSIDE-AUTHORITY RETRIEVAL — audit only; may not support approval (docs/26
§2.5)`. A historical pre-eligibility observation keeps its original
`PRE-ELIGIBILITY RETRIEVAL` label unchanged.

3.2 **Specifications** carry no per-field evidence in the canonical model, so
the same statement is recorded in `specs_note`, as the catalogue-authoring
convention already requires for spec provenance.

3.3 **Page hash and locator** (LIVE.6) bind discovery-layer claims.
`evidence_source` has no columns for them; they are recommended in the
evidence package but not required on the catalogue-authoring path.

## 4. Truthful labelling

Agent-retrieved evidence **must never** be described as:
- `MANUAL_BOOTSTRAP` — including because the owner initiated or authorized
  the session;
- read, checked or verified by the product owner or any named human;
- human-verified;
- `extraction_method = MANUAL` (that value denotes a human);
- authorized or compliant, if it was retrieved outside authority or is a
  historical pre-eligibility observation (§2.5).

A later genuine human reading of the primary source is recorded as **its own
act** under existing rules. It never rewrites the history of the agent row.

## 5. What agent-assisted evidence may and may not do

**May:**
- support a canonical **change proposal**, when retrieved within an
  authorizing research work order (§2.1);
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
  `observed_at`, confidence, work-order reference);
- every conflict and every UNKNOWN field;
- every held item, and why;
- every access restriction or technical block actually encountered, and how
  it was respected (§2.6);
- every §2.5 observation (outside authority, or historical pre-eligibility),
  listed separately and marked as not supporting the proposal;
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
repository-effective on main, merge `67a572d`. §6A.1, §6A.8 and §6A.9 revised
by Revision 5.)*

6A.1 **Every materially distinct execution phase requires explicit owner
authorization before it begins.** Distinct phases include at least: a source
eligibility review (`docs/16` §5), where one is wanted; product or source
retrieval; authoring or changing a canonical change proposal; canonical
mutation; commit; push and pull request; merge; publication; and any cleanup
or follow-up work.

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

6A.8 **A source eligibility review, where one is wanted** — for example for a
standing automated process (§2.2) — **is a distinct, externally active phase**
and requires explicit owner authorization naming the hosts. Inspecting policy
material inside an authorized research phase (§2.6) is part of that research
phase, not a separate review.

6A.9 **Product or source retrieval is a distinct phase** and requires an
explicit owner research work order that authorizes it. The work order may set
its scope by research target and source class; it need not enumerate hosts or
URLs, and relevant sources discovered during the research are in scope unless
it explicitly restricts discovery (§2.1). An eligibility decision, where one
exists, never starts retrieval.

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
route to sources an agent cannot read within authority (§2.4).

## 9. Compatibility with the DATA-D1 pipeline

    RADAR → CANDIDATE → TRACE → VERIFY/REVIEW → PROPOSE → HUMAN APPROVAL
          (→ separate, optional PUBLICATION decision)

`AGENT_ASSISTED_RESEARCH` may perform **TRACE** (including the official trace
of `docs/16` §11.1), assemble **VERIFY/REVIEW** evidence, and **PROPOSE** —
within an authorizing research work order only (§2.1). It never approves,
promotes or publishes. "Verifies" in `docs/11` §18 means checking that a
source supports a claim; it never means setting `VERIFIED`.

**Writing discovery-layer rows from an agent session is not authorized here:**
`extraction_method` has no truthful value for agent extraction. Adding one
needs a separate implementation contract.

## 10. Adversarial examples

| # | Situation | Correct outcome |
|---|---|---|
| 1 | Agent writes "verified at source" in a note | Refused. The note states agent retrieval (§3.1); confidence ≤ HIGH. |
| 2 | Owner approves the change set; an agent performs the merge | Valid only if the approval statement, covering that exact commit, precedes the merge (§6.5). Every evidence row keeps `verified_at` NULL. |
| 3 | During authorized research the agent encounters a clear, host-wide prohibition of automated access (for example an explicit block page) | The agent respects it: it stops retrieving from that host, records what it encountered, and reports (§2.6). The owner decides; an owner capture, manufacturer material, another authorized source, or UNKNOWN (§2.4). |
| 4 | A fact is supported only by a historical pre-eligibility observation made before Revision 5 | The observation stays audit-only and keeps its label. The fact needs a fresh retrieval within an authorizing work order, or §2.4, or it is withdrawn to UNKNOWN (§2.5). |
| 5 | The Claude Code Browser pane is unstable on `eu.robotshop.com` | The agent does not use that browser for it; it uses another read-only retrieval method. No access control is bypassed (§2.3, §2.7). |
| 6 | Agent proposes averaging two DoF figures | Refused. The field stays UNKNOWN with the conflict recorded. |
| 7 | Approved robot "should now go live" | Only by a separate publication decision (§7). |
| 8 | Agent drafts an eligibility review and marks the host `ALLOWED` | Refused. The agent recommends; a named human decides and is recorded (`docs/16` §5). |
| 9 | A work order authorizes research on named robots across manufacturer and distributor sources; the agent discovers a relevant distributor the work order does not mention | Within scope — relevant discovered public sources are authorized unless the work order restricts discovery (§2.1). Had it restricted discovery, the agent would record the source as a proposal and report (§6A.12). |
| 10 | A product page sits behind a login, CAPTCHA or challenge page | The agent stops for that page and records the block; nothing is bypassed (§2.7, LIVE.3). A block on one path does not by itself close the host (§2.6). |
| 11 | Because a work order let it research a host, the agent proposes enabling that host's `DiscoverySource` or registering a freshness target for it | Refused. A research work order is not an eligibility decision (§2.2). |
| 12 | Before starting authorized research, the agent decides it must first read the `robots.txt` and terms of every host | Not required — no policy pre-review gate exists for work-order research (§2.6). If it does consult `robots.txt`, it reads it only for its own user agent and the paths it retrieves. |

## 11. Non-goals

This amendment does not:
- approve any source for a standing automated process — adapters, the
  discovery radar and scheduled freshness still need their own `docs/16` §5
  decisions (§2.2);
- start any retrieval by itself — retrieval needs an explicit owner research
  work order (§6A.9);
- change LIVE.3, DATA-D1.9, A1 or A2 for standing automated processes —
  Revision 5 changes LIVE.2's reach only for agent research under a work order
  (§2.1), and withdraws the RobotShop hard override (§2.3);
- permit any retroactive validation of evidence (§2.5);
- change any enum or table, or require any code, migration or data structure;
- create an evidence store;
- change the meaning of `VERIFIED` or `verified_at`;
- authorize auto-promotion, merge without explicit owner approval, or
  auto-publication;
- change MEDIA-01;
- reclassify any evidence row that already exists.

## 12. Ratification record

    STATUS:                    RATIFIED — 2026-09-11 (revision 3);
                               Revision 4 RATIFIED; Revision 5 RATIFIED BY
                               OWNER 2026-09-11 — repository-effective upon
                               merge
    Ratified by:               Robert Konecny (product owner)
    Amends:                    docs/16 §2.1 (new mode: AGENT_ASSISTED_RESEARCH);
                               docs/16 LIVE.2 / §5 (Revision 5: an explicit
                               owner research work order authorizes agent
                               retrieval, §2.1); docs/21 §5 and docs/22
                               Phase 10 (Revision 5: RobotShop hard override
                               withdrawn, §2.3); clarifies docs/11 §8, §18 and
                               the scope of DATA-D1.9 (§2.2)
    Schema change:             NONE
    Code / migration required: NONE — governance only
    Sources approved:          NONE for any standing automated process
    Retrieval policy:          Revision 5 — agent retrieval of publicly
                               accessible material is authorized by an
                               explicit owner research work order, within its
                               scope; no per-host eligibility decision
                               is required for it. Standing automated
                               processes keep LIVE.2 / DATA-D1.9 in full.
                               Scope may be set by research target and source
                               class; relevant discovered sources are in scope
                               unless the work order restricts discovery. No
                               mandatory policy or robots.txt pre-review;
                               restrictions and blocks actually encountered
                               are respected and reported (§2.6); no
                               circumvention (§2.7).
                               [Revisions 2–4: a current affirmative per-host
                               eligibility decision was required, with a
                               narrow §2.6 bootstrap exception.]
    Pre-eligibility evidence:  audit/history only; never supports approval;
                               never relabelled; not upgraded by Revision 5;
                               only a fresh retrieval within an authorizing
                               work order, or §2.4, can support a fact (§2.5)
    Approval gate:             P8 (promotion), or explicit owner approval of
                               an exact catalogue change set before merge; an
                               authorized agent may mechanically merge only
                               that approved change set after approval
    Approval meaning:          approval of the presented evidence package; not
                               verification; not publication
    RobotShop:                 Revision 5 — no governance prohibition;
                               researched like any public source; browser-pane
                               instability is a tool constraint only (§2.3).
                               [Revisions 1–4: never retrieved by agent
                               tooling.]
    Evidence system:           existing evidence_source only; no parallel store
    Repository adoption:       base amendment merged to main @ 883cb1f
                               (PR #49) — repository-effective
    Revision 4:                §6A, §6B — RATIFIED by product owner
                               2026-09-11; REPOSITORY-EFFECTIVE ON MAIN —
                               merge 67a572d (PR #50)
    Revision 5:                §2 access basis, RobotShop, pre-eligibility
                               evidence — RATIFIED BY OWNER 2026-09-11 —
                               repository-effective upon merge

> *Historical record, kept verbatim. Its sentences on product/source retrieval
> eligibility, the §2.6 bootstrap exception, pre-eligibility retrieval and
> RobotShop are superseded for agent research by Revision 5 (§2).*
>
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

> **Revision 5 ratification statement — approved by product owner 2026-09-11;
> effective in repository governance when Revision 5 is merged to main:**
>
> I, Robert Konecny (product owner), ratify Revision 5 of DATA-D1.LIVE
> Amendment A3.
>
> An explicit `AGENT_ASSISTED_RESEARCH` work order of mine may authorize an AI
> agent to retrieve and inspect relevant publicly accessible product and source
> material directly. No separate per-host eligibility decision is required
> first.
>
> A work order may authorize research by research target and source class; it
> need not list every host or URL in advance. Relevant public sources
> discovered during the research are within the authorized research unless the
> work order restricts discovery.
>
> There is no requirement to inspect `robots.txt`, terms, legal, acceptable-use,
> privacy or automation-policy pages before ordinary owner-authorized research,
> and there is no policy-review gate. If the agent actually encounters a clear
> access restriction or technical block, it respects it and reports it.
> `robots.txt` is not a permission system; where it is consulted or
> encountered, its restrictions are read only for the applicable user agent
> and path.
>
> The agent never bypasses authentication, login, CAPTCHA, paywalls, access
> controls or explicit technical blocks.
>
> `robotshop.com` and `eu.robotshop.com` are no longer prohibited from agent
> retrieval; they are researched like other publicly accessible sources. The
> Claude Code Browser instability on RobotShop is a tool-stability constraint
> only; where that tool is unstable, another suitable read-only method is
> used.
>
> Standing automated processes — adapters, the discovery radar and scheduled
> freshness — keep their existing per-source eligibility rules. This revision
> changes none of their runtime or schema behaviour.
>
> Agent-retrieved evidence is labelled truthfully as agent retrieval, is never
> `MANUAL_BOOTSTRAP` because I initiated the session, and sets no `VERIFIED`
> and no `verified_at`. Conflicts are preserved; UNKNOWN remains UNKNOWN.
>
> Historical pre-eligibility observations are not upgraded. They remain
> audit/history only; future research freshly retrieves the evidence it
> relies on.
>
> Human approval remains before canonical catalogue mutation. Publication
> remains a separate explicit decision of mine.
>
> The owner authorizes actions, not trajectories: Revision 4 is unchanged.
