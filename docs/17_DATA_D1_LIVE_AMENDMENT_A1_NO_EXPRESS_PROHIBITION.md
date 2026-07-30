# DATA-D1.LIVE — Amendment A1: `NO_EXPRESS_PROHIBITION`

> **STATUS: RATIFIED — 2026-07-30, Robert Konecny (product owner).**
> Laws and definitions in this document are **FROZEN**. See §13.
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`
> (RATIFIED v0.1, 2026-07-29, main @ `6875a34`).
>
> **Ratification changes what is *permitted in principle*. It authorizes no
> fetch, approves no source, and authorizes no implementation.** It defines a
> third eligibility state and the narrow capability that state may carry. Every
> source still requires its own recorded review (§5 of the base contract, plus
> §2.1 and §4 here) before any request is issued, and this amendment approves
> **no source**.
>
> **Implementation authorized by this document: none.** Schema, models,
> migrations, adapters, extraction tooling, APIs and UI are untouched and remain
> so until a **separate implementation contract** is ratified — covering enums,
> limited-radar mode, database constraints, expiry behaviour and the numerical
> ceilings required by §10.3.
>
> **Revision history.** Revision 3 (2026-07-30) — default eligibility validity
> set to **90 days**, aligned with the `ALLOWED` terms-review validity (§7), and
> expiry stated explicitly as a **fail-closed access-suspension event that
> triggers nothing** (§7.1); ratified at this revision. Revision 2 (2026-07-30) —
> product-owner review corrections: the state restricted to `AGGREGATOR`-class
> sources (§2.1); requirement 3 turned on whether a restriction *applies to the
> proposed use*, with the training-only distinction frozen (§4.1); hard per-host
> operational ceilings made a precondition of any implementation (§10.3).

---

## 1. The current problem

DATA-D1.9 and LIVE.2 require an **affirmative** reading of a source's terms
before any automated access. `radar_eligible` implements exactly that:

```python
self.is_enabled
and self.tos_status == "ALLOWED"
and self.robots_status in ("ALLOWED", "NOT_APPLICABLE")
and self.eligibility_reviewed_at is not None
and bool(self.eligibility_reviewed_by)
```

That rule was written against a specific failure — a crawler filling the
catalogue with plausible, unverifiable market claims acquired from people who
never agreed to it. It has since done real work. The 2026-07-29 assessment found
five official manufacturer sites whose terms expressly prohibit automated
access, and the 2026-07-30 assessment found two aggregators serving a
Cloudflare-managed block that names our agent class and reserves text-and-data-mining
rights under Article 4 of EU Directive 2019/790. In every one of those
cases the contract produced the correct answer, and produced it before anyone
sent a request.

**But the rule has a second effect that was not its purpose.** Consider a source
that:

- serves `robots.txt` with `User-agent: * / Allow: /`;
- names no agent-specific `Disallow`, ours or anyone's;
- publishes no `Content-Signal`, `noai` directive or other rights reservation;
- has **no terms-of-use page at all**, or has one that never mentions automated
  access;
- answers ordinary requests normally, with no block, challenge or login.

Such a publisher has prohibited nothing. There is no clause to point at, no
signal to honour and no technical denial to respect. The contract nevertheless
refuses the source, because `tos_status` can only be `ALLOWED` when an
affirmative permission exists — and silence is not permission (DATA-D1.9).

Four of the seven radar sources assessed on 2026-07-30 match that profile
exactly: **The Mimic, Lineroid, WhichHumanoid and RoboZaps** (§9). All four are
refused today, and not one of them has said no.

*How many of the four this amendment actually unblocks is not four by
assumption.* It is decided by the `AGGREGATOR` class precondition (§2.1) and by
fresh reviews under §4, and may be fewer — see §9.

The consequence is concrete. The verified catalogue has stood at seven robots
since MEDIA-01 completed. The discovery queue holds 43 candidates with **zero
specifications, zero prices and zero images**, because no source has ever been
enabled. The blocking constraint is no longer "sources prohibit us" — for these
four it is "the contract requires a permission that the publisher had no
occasion to give."

**This amendment does not lower the bar for canonical truth.** It separates two
questions the contract currently answers with one word:

| Question | Answered by |
|---|---|
| *May we send this source an ordinary HTTP request?* | an access question — about the publisher's expressed wishes |
| *May what we read become a published HumanoidOnline fact?* | an evidence question — about source authority, trace and human verification |

Today both are gated on `tos_status = ALLOWED`. Conflating them means a source
must grant us publishing-grade permission before we may so much as read a page
we would only ever use as a lead. `NO_EXPRESS_PROHIBITION` answers the first
question and answers the second with an unconditional **no**.

## 2. Definition

**`NO_EXPRESS_PROHIBITION`** means:

> After a **named, timestamped and reproducible** eligibility review, **no
> prohibition on the proposed automated access was found** in:
>
> - `robots.txt`;
> - agent-specific directives;
> - HTTP content signals;
> - accessible terms of use;
> - accessible licensing or copyright notices;
> - technical access behaviour.

**It does not mean the publisher granted permission.**

### 2.1 Class precondition — `AGGREGATOR` only *(amended, correction 1)*

**`NO_EXPRESS_PROHIBITION` may be granted only to a source whose recorded
`discovery_source_class` is `AGGREGATOR`.**

This is deliberately narrow. Amendment A1 was motivated by competitor
directories and aggregated robot-information sources, and it is scoped to
exactly that. Under this amendment:

| Source class | Automated acquisition requires |
|---|---|
| `AGGREGATOR` | `ALLOWED`, **or** `NO_EXPRESS_PROHIBITION` under this amendment |
| `MANUFACTURER` | `ALLOWED` — unchanged |
| `OFFICIAL_STORE` | `ALLOWED` — unchanged |
| `AUTHORIZED_DISTRIBUTOR` | `ALLOWED` — unchanged |
| every other class | the pre-amendment rules, unchanged |

No other class is widened. A later need to broaden the state **requires another
amendment**, not an interpretation of this one.

**A source's class may never be rewritten to make it eligible.** Classification
records what a source *is* — where its content was actually seen and what
function it serves — and it is set by the same evidence discipline as everything
else. Relabelling an editorial outlet, a competitor directory or a manufacturer
as `AGGREGATOR` to bring it inside A1 is falsification of the record, and it is
the single most likely way this amendment would be abused. `COMPETITOR_DIRECTORY`
and `EDITORIAL` are distinct enum values from `AGGREGATOR`; a source honestly
belonging to either **does not qualify** under A1 as written, and the correct
response is a later amendment that names those classes explicitly, never a
reclassification.

**Within the eligible class, classification alone grants nothing.** Being an
`AGGREGATOR` is a precondition, not a qualification: every source still requires
its own complete review under §4 and the owner's explicit enablement under
requirement 10.

**Manual human research is unaffected by all of the above.** `MANUAL_BOOTSTRAP`
(base contract §2.1) performs no automated access, is not gated by per-source
eligibility, and remains available for every source of every class — including
those A1 excludes and those that expressly prohibit automation.

### 2.2 Why the name is long

The name is deliberately long and deliberately negative. It was chosen over the
shorter `NO_PROHIBITION` because the shorter form reads as a property of the
source ("this source has no prohibition") rather than as a property of *our
search* ("we looked, in these six places, at this time, and found none"). The
distinction matters when the review turns out to have been wrong: a review that
missed a linked PDF is a defective review, not a source that changed its mind.

Three restatements, because each is a thing someone will later be tempted to
assume:

- **This state is a finding about our own search, bounded in time and scope.**
  It asserts what a named person did not find in named documents on a named
  date. It asserts nothing about what the publisher wants.
- **Silence must be recorded as silence.** A review that writes "no terms page
  exists" into a field meaning "the terms permit this" has falsified the record.
  The state exists so that silence has somewhere truthful to go.
- **It is not a waiting room for `ALLOWED`.** A source does not graduate from
  `NO_EXPRESS_PROHIBITION` to `ALLOWED` by being crawled without complaint.
  `ALLOWED` requires an affirmative clause or written permission — nothing else,
  and no amount of elapsed silence.

## 3. Exact semantic distinction between the four states

| State | What it asserts | Evidence required | Radar fetch | Path to canonical |
|---|---|---|---|---|
| **`ALLOWED`** | The publisher **affirmatively permits** the proposed automated access — an explicit clause, a published crawling/indexing policy, an API or feed whose terms cover the use, or written permission recorded as the eligibility artefact. | The exact permitting passage, quoted, with URL and hash; or the correspondence granting it. | ✅ Full, within reviewed path prefixes and rate policy. | ✅ Subject to source class, trace (P2), Gate W, human verification and P8 promotion — unchanged. |
| **`NO_EXPRESS_PROHIBITION`** | A named reviewer searched six specified places at a recorded time and **found no prohibition**. The publisher has expressed nothing either way. **Available only to `AGGREGATOR`-class sources** (§2.1). | The six-axis search record of §5, including **where terms and licensing pages were looked for and not found**. | ⚠️ **Limited radar mode only** — §6 capability matrix. | ❌ **Never.** No canonical write, no `VERIFIED` claim, no satisfaction of Gate W, under any circumstances. |
| **`UNKNOWN`** | The review is **incomplete, unattributed, expired, or could not be performed** — a terms page that would not render, a host that returned nothing, an assessment nobody finished. | Whatever was recorded, marked incomplete. | ❌ None. | ❌ None. |
| **`PROHIBITED`** | A prohibition **was found** — an anti-robot clause, an agent-specific `Disallow`, a rights reservation, or a technical denial. | The exact prohibiting passage or directive, quoted, with URL and hash. | ❌ None. | ❌ None. |

**The two failure modes this table is drawn against:**

- **Collapsing `UNKNOWN` into `NO_EXPRESS_PROHIBITION`.** "We could not read the
  terms" is *not* "we read the terms and found nothing." `robotsguide.com`
  returns `403` on every path but `robots.txt`, so its terms cannot be read at
  all — that is `UNKNOWN` on the terms axis and `PROHIBITED` overall on the
  agent-directive and technical-behaviour axes. A source whose terms page fails
  to render is `UNKNOWN`, and `UNKNOWN` is never fetched.
- **Collapsing `NO_EXPRESS_PROHIBITION` into `ALLOWED`.** These states must
  remain distinguishable in the database, in the run report and in the review
  UI, because they authorize different things and because a later reader must be
  able to tell "they said yes" from "they said nothing". An implementation that
  maps the new state onto `ALLOWED` for convenience defeats the entire
  amendment.

`UNKNOWN` and `PROHIBITED` are unchanged by this amendment. `ALLOWED` is
unchanged by this amendment. Only a new, strictly weaker state is added.

## 4. Eligibility requirements

**Precondition (§2.1): the source's recorded `discovery_source_class` is
`AGGREGATOR`.** A source of any other class cannot receive this state however
well it satisfies the ten requirements below, and the requirements are not
assessed for it. The precondition is stated separately from the numbered
requirements because it is a question about *what the source is*, answered before
any review of *what the source says*.

Given the precondition, a source may receive `NO_EXPRESS_PROHIBITION` **only when
all ten are true**. Any one failing means the state is refused; the correct
outcome is `UNKNOWN` or `PROHIBITED`, never a partial grant.

| # | Requirement |
|---|---|
| **1** | **No applicable agent-specific `Disallow` exists.** Neither our agent nor the AI-crawler class it belongs to is named with a `Disallow` in `robots.txt`. A wildcard `Allow: /` does not cure a named `Disallow`. |
| **2** | **The relevant paths are not disallowed.** Every path prefix the review covers is permitted for the group that applies to us — evaluated for the exact prefixes, not for the host in general. |
| **3** | **No rights reservation applies *to the proposed limited-radar use*.** The test is applicability, not the mere presence of a directive: a reservation covering automated access, scraping, extraction, text-and-data mining, database extraction or database reuse is disqualifying; a reservation covering **only** model training is binding but not, by itself, disqualifying. Resolved by §4.1, which is frozen. |
| **4** | **No accessible terms or policy prohibits automation, scraping, data mining or systematic extraction.** Terms of use, acceptable-use policy, legal notice, licensing page and copyright notice — whichever exist and are reachable. |
| **5** | **The review records where terms and licensing pages were searched.** The list of URLs tried, and their outcomes, including the ones that 404'd. "No terms page found" is a claim about a search, and the search must be reproducible by someone else. |
| **6** | **Ordinary requests are accepted without bypassing access controls.** The declared user agent, at the declared rate, with no impersonation, no proxy rotation, no fingerprint evasion and no header manipulation beyond ordinary conditional-request validators. |
| **7** | **No login, CAPTCHA, paywall, `403` block or other technical denial is present** on the paths under review. |
| **8** | **The reviewer, timestamp, URLs, hashes and supporting excerpts are recorded** — for every axis, including the axes that came back empty. |
| **9** | **The review has not expired** (§7: 90 days by default). |
| **10** | **The source is explicitly enabled for the limited radar mode.** Reviewing is not enabling — the base contract's §5 step 5, restated because it is the step most often skipped. Enablement names the mode; a source enabled for limited radar is not enabled for anything else. |

**Silence must be recorded as silence, never rewritten as permission.** Where a
document does not exist, the record says it does not exist and lists where it
was sought. Where a document exists and is silent on automation, the record
quotes enough of it to show the silence is real and not a missed clause. No
field anywhere may be set to a value meaning "permitted" on the strength of an
absence.

### 4.1 Applicability of rights restrictions — FROZEN *(amended, correction 2)*

Requirement 3 turns on **whether a restriction applies to the activity we
propose**, not on whether a restriction exists. Without this distinction two
reviewers can read the same directive and reach opposite decisions — which is
the failure this subsection exists to prevent. The following rules are frozen.

1. **A training-only restriction is binding.** Material acquired from such a
   source must **never** be used to train or fine-tune any model. This holds
   whether or not the source is ever enabled, and it is already the platform's
   position independent of any directive.
2. **A training-only restriction does not, by itself, prohibit limited
   non-training radar retrieval.** A publisher who reserves training rights and
   otherwise permits ordinary indexing has restricted a use we do not make.
   Examples of the shape: `Disallow-Training: /`, `Content-Signal: ai-train=no`
   *standing alone*, `noai` where its stated scope is training.
3. **A prohibition on automated access is disqualifying.** Anti-robot clauses,
   `Disallow` directives applying to us, "no automated device" terms.
4. **A scraping, extraction, text-and-data-mining, database-extraction or
   database-reuse reservation applicable to the proposed radar activity is
   disqualifying.** This includes an Article 4 (EU 2019/790) reservation and any
   sui-generis database-right notice covering systematic extraction. What we
   propose *is* systematic extraction, and calling it "radar" does not move it
   outside such a reservation.
5. **A general AI-use restriction is interpreted conservatively.** Where a
   directive restricts "AI use" without a determinable scope — and so might
   cover retrieval, grounding or reference consumption rather than training
   alone — the reviewer may **not** resolve the ambiguity in our favour. The
   result is `UNKNOWN`, and `UNKNOWN` is never fetched. When it cannot be
   determined whether a restriction applies, it applies.
6. **`noimageai` authorizes nothing about images, in either direction.** Images
   are outside this amendment entirely (§6.2): no download, no reuse, no
   MEDIA-01 verdict, regardless of what any image directive says or omits.

**Note the asymmetry, because it is deliberate.** Rule 2 is the only place this
amendment declines to treat a restriction as disqualifying, and it is narrow: it
applies where the restriction's scope is *determinably* limited to training. The
moment scope is unclear, rule 5 sends the source to `UNKNOWN`. A reviewer who
finds themselves constructing an argument for why a broad directive "probably
means training" has already failed rule 5.

**This is internal eligibility policy, not a legal conclusion.** It states how
this platform resolves ambiguous machine-readable signals when deciding whether
to send a request. It offers no view on what any directive means in law, and
§12's disclaimer on legal opinions is unaffected.

## 5. Review evidence requirements

The §5 procedure of the base contract applies unchanged, with these additions
specific to this state. The output is a `source_eligibility_review` record whose
`tos_decision` is `NO_EXPRESS_PROHIBITION` and whose notes carry the search
record.

**Per axis, the review records:** the URL(s) tried · the HTTP status of each ·
the content hash of anything retrieved · a bounded excerpt (≤1000 characters,
LIVE.6) of any passage bearing on automated access · and, where nothing was
found, an explicit statement that nothing was found.

| Axis | Minimum record |
|---|---|
| `robots.txt` | Full file content, hashed and timestamped. The **entire** file — including every named-agent group. A review that quotes only the wildcard group has not read the file. |
| Agent-specific directives | The named groups present, and an explicit finding that neither our agent nor its class appears in any of them. |
| HTTP content signals | `Content-Signal` values if present; response headers bearing on reuse (`X-Robots-Tag` and equivalents); an explicit nil finding if absent. **Where any restriction is found, the review records the §4.1 rule applied and the scope determined** — a signal recorded without a scope determination is an incomplete review. |
| Accessible terms of use | Every URL tried, with status. Where a terms page exists, its hash and the passage governing (or failing to govern) automated access. Where none exists, the list of paths tried and the footer/sitemap locations searched. |
| Accessible licensing / copyright notices | Licence statements, copyright footers, per-page rights notices, dataset licences. Where a licence exists and permits reuse, that belongs on the `ALLOWED` axis, not here. |
| Technical access behaviour | Observed status codes for ordinary requests to representative paths under review, the user agent used, and an explicit finding of no block, challenge, interstitial or login. |

**The negative findings are the substance of the record, not filler.** This state
is defined by absence, so an unrecorded absence is an unevidenced state. A
review that says "no prohibition found" without saying where it looked cannot be
audited, cannot be reproduced, and must be rejected.

**The review is reproducible.** Another person, given the record, must be able to
repeat the same requests and reach the same finding. That is what makes an
expired review re-reviewable rather than merely stale.

## 6. Capability matrix

### 6.1 Authorized under `NO_EXPRESS_PROHIBITION`

| Capability | Bound |
|---|---|
| Low-rate radar discovery | Within the declared per-host rate limit and per-run page cap. Slower than `ALLOWED`, never faster. |
| Explicitly bounded public-page retrieval | Only the path prefixes named in the review, only pages reachable without any access control. An enumerated list or a bounded prefix — never "the site". |
| Discovery-candidate enrichment | Writes to the discovery layer only (LIVE.5, Gate C). |
| Candidate claims with source class `AGGREGATOR` | Consistent by construction: §2.1 limits the state to `AGGREGATOR` sources, so a claim acquired under it is `AGGREGATOR` because the source is, not because the claim was labelled to fit. The class reflects **where the content was actually seen**, never what it claims to be about — an aggregator page reproducing a manufacturer's figure is `AGGREGATOR` (the Figure 02 precedent, MEDIA-01). |
| Claim status `NOT_VERIFIED` | The only status such a claim may ever carry. |
| Short attributed evidence excerpts | ≤1000 Unicode characters per excerpt (LIVE.6), retained as evidence, never republished (§6.2). |
| Conflict detection | Surfacing that this source disagrees with another. Detection only — never resolution, never averaging (§6.1 of the base contract). |
| Preparation of a human review queue | The output of this state is **work for a person**, and that is its entire purpose. |

### 6.2 Prohibited under `NO_EXPRESS_PROHIBITION`

Each of these is prohibited **absolutely** — not "unless the operator confirms",
not "unless the source seems fine with it".

| Prohibited | Note |
|---|---|
| Canonical promotion | No row acquired under this state may reach a canonical table by any path. |
| A `VERIFIED` claim | The state cannot produce verification; only a human acting on authoritative evidence can. |
| Satisfaction of Gate W | §8. An aggregator-only trace never satisfies DATA-D1 P2 where an official source exists. |
| Overriding manufacturer evidence | A conflicting aggregator value is surfaced beside the authoritative one, never substituted for it. |
| Public republication of source text | Excerpts are retained as **evidence for a reviewer**, not published to users, agents, sitemaps, `llms.txt` or any machine surface (AGENT-01.7). |
| Image downloading or reuse | Reference URLs only, and no MEDIA-01 verdict may be inferred (LIVE.9, Gate M). |
| Recursive or unrestricted crawling | Bounded lists and prefixes only. No link-following beyond the reviewed bound. |
| Hidden API discovery | Undocumented or internal endpoints are out of scope even when trivially reachable. A `Disallow: /api/` is a statement; so is the absence of documentation. |
| User-agent spoofing | LIVE.3, restated. |
| Proxy rotation | LIVE.3, restated. |
| CAPTCHA or Cloudflare bypass | LIVE.3, restated. |
| Continued access after any technical denial | A block ends access immediately and triggers §7 revocation. **A block is a finding, not an obstacle** (LIVE.3). |
| Commercial availability, maturity or deployment conclusions without their own evidence | The three axes stay separate (LIVE.7) and each signal carries its own excerpt (LIVE.6). An aggregator's summary label is not evidence for three axes. |

**The shape of the matrix is the point.** Everything authorized ends in a human
looking at something. Nothing authorized ends in a published fact.

## 7. Expiry and revocation

**Default expiry: 90 days** *(product-owner decision, 2026-07-30)*.

The rationale, recorded so it is not re-litigated:

- **It aligns with the existing `ALLOWED` terms-review validity** set by LIVE.2.
  One validity period across both states means one rule to implement, one rule
  to test and one rule to remember.
- **It avoids giving the weaker, silence-based state a longer lifetime than
  affirmative permission.** A review that found *nothing* must not outlive a
  review that found an explicit grant. Any expiry beyond 90 days would invert
  the evidence hierarchy this amendment otherwise maintains everywhere.
- **It is a maximum validity period, not a guarantee.** Ninety days is the
  longest a finding may stand before it must be redone. It is not an assertion
  that access remains acceptable throughout — only that the finding is not
  automatically stale before then.
- **It does not replace run-start policy checks or the immediate revocation
  triggers.** Those are the continuous protections and they are unchanged:
  `robots.txt` is re-read at the start of every run and cached at most 24 hours
  (LIVE.2), so an agent-specific block or a new `Content-Signal` halts the
  source on the next run rather than waiting for any expiry; the six triggers
  below take effect on occurrence; and any access-denial response ends access on
  the spot (§7.5).

The expiry and the continuous checks answer different questions. The checks ask
*has anything changed since we last looked?* The expiry asks *is this finding
still recent enough to rely on at all?* Neither substitutes for the other.

**The state becomes unusable immediately when any of the following occurs.**
Immediately means: the source is disabled, an in-flight run halts with
`HALTED_BY_POLICY`, and re-enablement requires a fresh full review — not an
extension of the old one.

1. `robots.txt` changes materially.
2. Terms or licensing content changes materially.
3. A rights-reservation signal appears (`Content-Signal`, Article 4 notice,
   `noai`, database-right notice, licence change).
4. An agent-specific block appears — ours or our class's.
5. Requests begin returning access-denial responses (`401`, `403`, `429`
   sustained, challenge interstitials, login walls).
6. The publisher objects, by any means, formal or informal. **An objection is
   effective on receipt and needs no verification, no legal assessment and no
   escalation.** The source is disabled first and discussed afterwards.
7. The review expires.

**Material change** is any change to a passage bearing on automated access,
reuse, licensing or rights reservation. When it is unclear whether a change is
material, it is material — the cost of an unnecessary re-review is minutes; the
cost of a missed prohibition is the platform's central claim.

**`PROHIBITED` never downgrades into this state automatically.** A source that
once expressed a prohibition and later drops it from its terms does not become
`NO_EXPRESS_PROHIBITION` by the disappearance of a clause. It requires a fresh,
named, full review that examines whether the prohibition genuinely ended — a
site redesign losing a legal page is not a publisher changing its mind. This
rule exists because the alternative is an automated path from "they said no" to
"we may fetch", which is exactly the reinterpretation §0.1 forbids.

### 7.1 What expiry actually does — and what it does not

**Eligibility expiry is a fail-closed access-suspension event. It is never a
crawl, fetch, refresh, retry, scheduling or content-acquisition trigger.**

This is stated first because it is the most dangerous available
misunderstanding. An expiry is a deadline that *removes* a permission. Nothing
about it initiates work: it does not schedule a re-review, it does not queue a
refresh, it does not cause a single page to be requested. A system in which an
expiry sets something running has inverted the rule — expiry is the moment
activity stops, and it stays stopped until a person acts.

Expiry governs **future access**, not the **record of past evidence**. The two
are separated deliberately.

**On the day the review expires (after 90 days):**

- the source enters `REVIEW_EXPIRED` — or whichever existing fail-closed state
  the implementation uses — and is disabled;
- **new acquisition is blocked.** No new request may be constructed for the
  source; the assertion happens *before* the request is built (LIVE.2), so an
  expired review cannot produce a fetch that is noticed and cleaned up
  afterwards;
- **an in-flight run halts** and records `HALTED_BY_POLICY` if expiry is
  detected mid-run — a first-class outcome, not an error to retry;
- **no automatic eligibility review begins.** The expiry does not schedule,
  queue or start a re-review. A named human starts one, or none happens;
- **no robot page is fetched because the review expired.** Expiry causes zero
  requests of any kind;
- existing candidates, claims, evidence excerpts and provenance **remain
  retained**;
- **re-enablement requires a fresh complete eligibility review** — all six axes
  searched and recorded again, the `AGGREGATOR` class precondition confirmed
  again, and the owner's explicit enablement again. **There is no renewal, no
  extension and no "re-confirm the previous finding" path.** A stale review is
  not evidence about today;
- **any later content-acquisition run remains a separate manual-trigger
  decision under LIVE.4.** Passing a fresh review restores eligibility; it does
  not start a run. Those are two decisions and two human acts.

**What expiry does *not* do:**

- **It does not delete or invalidate what was already acquired.** Discovery
  candidates, their `NOT_VERIFIED` claims, evidence excerpts, `retrieved_at`
  timestamps and source attribution all remain. Those rows record *what a source
  said on a date*, which stays true regardless of whether we may still visit.
  Deleting them would destroy the audit trail the whole layer exists to keep.
- **It does not make old claims more or less trustworthy.** They were
  `NOT_VERIFIED` when acquired and they stay `NOT_VERIFIED`. Their
  `retrieved_at` is what tells a reviewer how stale they are, and that field
  already exists.
- **It has no canonical consequence, because there can be none.** Nothing
  acquired under this state ever reached canonical (§6.2, Gate W), so there is
  nothing to withdraw, correct or re-verify in the published catalogue.
- **It does not change cache retention**, which is governed independently by
  LIVE.10 and Gate Q.

**The practical shape, then:** after 90 days the platform keeps everything it
learned and loses the right to learn more until a person re-does the review.
That asymmetry is correct — the evidence record should survive, and the access
permission should not.

## 8. Gate W is preserved, and the precedence order is unchanged

**Source-authority order (unchanged):**

1. manufacturer or other authoritative source;
2. authorized distributor where applicable;
3. aggregator and editorial sources.

**Gate W stands exactly as ratified:**

> *(promotion trace, §11.1)* When an official-class (`MANUFACTURER` /
> `AUTHORIZED_DISTRIBUTOR` / `OFFICIAL_STORE`) source exists for an entity,
> promotion is refused unless the recorded trace (DATA-D1 P2) is to one of those
> classes — an aggregator-only trace does not satisfy P2 for that entity.

This amendment does not weaken, qualify or create an exception to Gate W, and
its capability matrix (§6.2) restates the refusal at the state level so that the
prohibition holds on two independent grounds: by source **class** (Gate S/W) and
by eligibility **state** (this amendment). A future change to one does not
silently unlock the other.

**An aggregator conflict remains visible and can never overwrite the
authoritative claim.** Conflicting values are separate rows with separate
provenance (§9.1, Gate T, Gate X). The higher-ranked value is surfaced for a
human; the lower-ranked one is neither deleted nor averaged nor promoted.

**What this state actually buys, stated without inflation:** it lets the platform
learn *that a robot exists*, *where its maker's page is*, and *that two sources
disagree*. Every one of those is a lead. None of them is a fact.

## 9. Sources motivating the amendment

Assessed 2026-07-30 (`scratchpad/eligibility/ELIGIBILITY_REPORTS.md` §5). Each is
recorded as a **candidate for the new state, not as approved**. None has passed
the complete amended review, because the amended review does not yet exist. On
ratification each must be reviewed afresh against all ten requirements of §4 —
in particular requirement 5, which none of the 2026-07-30 assessments satisfies,
since they did not systematically record where terms pages were sought.

**And each must first satisfy the §2.1 class precondition, which is not a
formality.** The 2026-07-30 assessment described these four as
"`COMPETITOR_DIRECTORY` / `AGGREGATOR` class" without deciding between the two,
and those are **distinct enum values**. A1 admits `AGGREGATOR` only. So each
review must first classify the source honestly on the merits — what its content
actually is and where it was actually seen — and **any of the four that is
properly `COMPETITOR_DIRECTORY` or `EDITORIAL` does not qualify under A1 as
written**.

This is stated plainly because the tempting move is the forbidden one: reaching
for `AGGREGATOR` on all four because A1 was written with them in mind.
Classification follows the evidence, and if the honest answer excludes a source
the remedy is a later amendment naming the additional class — never a
reclassification. It is possible that this correction narrows the amendment's
practical effect to fewer than four sources; that is the correct outcome of
taking the class rule seriously, and the owner should decide with it visible
rather than discover it during implementation.

| Source | Host | Observed 2026-07-30 | Outstanding before the state could be granted |
|---|---|---|---|
| **The Mimic** | `themimic.io` | `User-agent: * / Allow: /`, no agent-specific groups, no content signals, sitemap present. `/terms` returned `404`. | Full terms/licensing search with recorded locations; content-signal and header check; technical-behaviour check on representative paths. |
| **Lineroid** | `lineroid.com` | `Allow: /` with `Crawl-delay: 1`; disallows `/admin`, `/auth`, `/api/*`; named groups for search engines and social crawlers only. `/terms` returned `404`. | As above. `Crawl-delay: 1` is a declared rate the limited mode must honour, and it is a floor, not a target. |
| **WhichHumanoid** | `whichhumanoid.com` | `Allow: /` plus `LLM-Policy: /llms.txt`; the policy file adds the non-standard `Disallow-Training: /`. | As above, plus a careful read of the **full** `llms.txt`. `Disallow-Training` is resolved by **§4.1 rule 2**, not by an exception: it is a training-only restriction, so it **binds us absolutely against training** and does not by itself disqualify non-training radar. That determination holds only if the rest of the policy file confirms the scope is training. If any part of it restricts retrieval, extraction, mining or reuse, **§4.1 rule 4** disqualifies; if the scope cannot be determined, **§4.1 rule 5** gives `UNKNOWN`, not eligibility. |
| **RoboZaps** | `robozaps.com` | `Allow: /`; disallows `/api/` except `/api/v1/`, and `/robots?`. A terms-of-service page **exists** and contains no clause on automated access, scraping, data mining or content reuse; IP stated as belonging to RoboZaps Inc. or manufacturers. | As above. The existing ToS must be read in full and the silence evidenced by excerpt, not by summary. The IP statement bears on republication (already prohibited, §6.2) and not on access. |

**Deliberately excluded, and not eligible examples:**

- **IEEE Robots Guide** (`robotsguide.com`) — `robots.txt` names `ClaudeBot`
  with `Disallow: /` (requirement 1 fails), asserts an Article 4 rights
  reservation with `ai-train=no` (requirement 3 fails), and returns `403` on
  every path but `robots.txt` (requirements 6 and 7 fail, and the terms axis is
  `UNKNOWN` because the page cannot be read). Disqualified four times over. Its
  route is the licence request drafted in `PERMISSION_REQUESTS.md`.
- **RoboSelect360** (`roboselect360.com`) — serves a byte-identical
  Cloudflare-managed block. Disqualified on the same grounds.

Both remain disqualifying under the recorded assessment, and **this amendment
must not be read as reopening either.** They are named here so that a later
reader who finds them in the same assessment file does not mistake their absence
from the candidate table for an oversight.

**Two sources remain unassessed** and are candidates for nothing until they are:
`thehumanoidhub.com` (no `robots.txt` — the SPA catch-all serves page HTML,
which is silence on the robots axis and requires care, not convenience) and
`humanoid.press` (no response obtained).

## 10. Implementation consequences

**None of this is authorized by this document.** It is recorded so that the
ratification decision is made with the cost visible, and so that the later slice
has a specification rather than an inference.

### 10.1 Migration implications for the later implementation slice

| Area | Consequence |
|---|---|
| **Class precondition (§2.1)** | Enforced, not documented. The new state is admissible **only** where `discovery_source.source_class = 'AGGREGATOR'`; the DB `CHECK` extension below must encode the class condition alongside the state, so a `MANUFACTURER` row physically cannot hold it. A test must assert the refusal for `MANUFACTURER`, `OFFICIAL_STORE`, `AUTHORIZED_DISTRIBUTOR`, `COMPETITOR_DIRECTORY` and `EDITORIAL` specifically, not in the abstract. |
| **Restriction scope (§4.1)** | The review record must carry, per restriction found, the rule applied and the scope determined. A structured field is preferable to prose so that "training-only" versus "extraction" is queryable rather than buried in notes — an `UNKNOWN` produced by rule 5 must be visibly distinguishable from an `UNKNOWN` produced by an unreachable page. |
| Enum widening | `eligibility_decision` and `tos_status` each gain `NO_EXPRESS_PROHIBITION`. Additive only; every existing value is retained verbatim. Note the PostgreSQL constraint: `ALTER TYPE ... ADD VALUE` cannot be used in the same transaction that then uses the new value, so the migration sequences the widening ahead of any data write. |
| `discovery_source.radar_eligible` | Currently a boolean property requiring `tos_status == "ALLOWED"`. It must become **mode-aware**: a source in the new state is eligible for *limited radar* and for nothing else. The safest shape is an explicit radar-mode value rather than a widened boolean, so that every call site is forced to state which mode it means and no existing caller silently gains the new capability. |
| DB-level `CHECK` on `is_enabled` | The existing constraint encoding DATA-D1.9 must be extended to admit the new state **only** in combination with the limited mode — the database, not the application, remains the place this is enforced (L7). |
| `source_eligibility_review` | No new column is strictly required; the six-axis search record fits `notes` plus the existing per-axis URL/hash/excerpt fields. A dedicated structured column for the "where we searched" list would be better and should be considered in the slice. The table is append-only and stays so. |
| Expiry | 90 days, matching the `ALLOWED` terms validity, so `expires_at` keeps a single rule across both states rather than becoming state-dependent. The column already exists; nothing about its calculation changes. The slice must assert that expiry is **fail-closed and inert** (§7.1): an expired review blocks a run and starts nothing — no scheduled re-review, no refresh, no request of any kind. A test that proves zero requests result from an expiry belongs in the same suite as the block itself. |
| New acceptance gates | At minimum: a source in this state can never produce `VERIFIED` or a canonical write (state-level, independent of Gate S); a technical denial disables the source within the same run; an expired review of this state blocks a run; the state is never mapped to `ALLOWED` in any projection, report or UI; and `PROHIBITED` cannot transition into this state without a new review record. |
| Run report | The §18 report must print the eligibility **state** per source, not merely "eligible", so an operator reading a report can tell which authority a run was operating under. |
| Rate policy | Limited mode carries its own, stricter rate ceiling, and honours any declared `Crawl-delay` as a floor. |
| Review UI | The `/discovery-review` surface must distinguish the state visibly. A candidate enriched under limited radar must not look like a candidate traced to a manufacturer. |
| No canonical, API, MCP or public-surface change | The new state is invisible to every public and machine surface (AGENT-01.7, Gate O). |

### 10.2 What the slice does *not* get to assume

Ratifying this amendment authorizes **no source**. On ratification the position
is: a third state exists, and zero sources hold it. Each of the four candidates
in §9 needs its own full review, its own owner enablement, and its own recorded
artefact.

**On source class and eligibility, stated precisely.** The base contract's §5
holds that source class predicts nothing about eligibility — an aggregator is
reviewed exactly as a manufacturer is, and the 2026-07-29 assessment showed why:
the official manufacturer sites had the *more* restrictive terms. That remains
true and A1 does not disturb it. What A1 adds is a distinction between two
different questions:

| Question | Answer |
|---|---|
| Does class determine whether a source's terms permit automated access? | **No** — unchanged. Only reading the actual terms determines that, identically for every class. |
| Does class determine which *eligibility states are available* to a source? | **Yes, for this state only.** `NO_EXPRESS_PROHIBITION` is available to `AGGREGATOR` alone (§2.1). Every other class reaches automated acquisition only through `ALLOWED`, exactly as before. |

So the correct rule is: **within the eligible `AGGREGATOR` class, classification
alone grants nothing; every source still requires its own complete review and the
owner's enablement.** Class opens a door; it never walks through it.

### 10.3 Normative prerequisite — hard operational ceilings must be frozen first

**Ratification of A1 authorizes no fetching and does not itself select
operational limits.** Before any implementation code is written and before any
source is enabled, the implementation contract must **freeze hard per-host
ceilings** for:

- **concurrency** — simultaneous in-flight requests per host;
- **request rate** — requests per interval per host;
- **pages per run** — total pages retrieved per host per run;
- **response bytes per page**;
- **total response bytes per run**.

The frozen limits must:

- be **database- or contract-governed**, never arbitrary adapter defaults — a
  ceiling an adapter author can raise by editing a constant is not a ceiling;
- **honour a publisher's declared crawl delay as a minimum delay**, never as a
  target and never as a value to be optimised against (Lineroid's
  `Crawl-delay: 1` is a floor, not a budget);
- **refuse an adapter configuration that exceeds the frozen ceiling** — the
  refusal is a startup failure, not a warning;
- **prohibit unlimited values** in every dimension, including by absence: an
  unset limit must fail closed rather than default to unbounded;
- **remain manual-trigger-only** under LIVE.4.

**No adapter code may precede that numerical decision.** The ordering is
deliberate: limits chosen after an adapter exists get chosen to fit what the
adapter already does.

**This correction pass deliberately invents no numbers.** Choosing them is an
explicit precondition of the separately authorized implementation slice, and it
is a decision for the owner, informed by what each enabled source's own declared
policy asks for.

## 11. Adversarial examples

Each is a case where a plausible reading gives the wrong answer.

| # | Situation | Correct outcome |
|---|---|---|
| **1** | `robots.txt` has `User-agent: * / Allow: /` **and** a named `User-agent: ClaudeBot / Disallow: /`. The wildcard group, read alone, permits us. | **`PROHIBITED`.** Requirement 1 fails. A wildcard `Allow` does not cure a named `Disallow`; the more specific group is the one that applies. This is `robotsguide.com` and `roboselect360.com`. |
| **2** | Terms page returns `404`, so nothing prohibits automation. But the site footer links a "Legal" PDF that does. | **`PROHIBITED`** once found — and the review is defective if it stops at `/terms`. Requirement 5 exists to force the search into the footer, the sitemap and the linked documents, and to record the attempt. |
| **3** | `robots.txt` fetches with `200`; every content path returns `403`. | **`UNKNOWN`** on the terms axis (the page cannot be read) and **`PROHIBITED`** overall (requirements 6 and 7 fail). Never `NO_EXPRESS_PROHIBITION` — "we could not look" is not "we looked and found nothing". |
| **4** | A source qualified cleanly 20 days ago. Today a Cloudflare managed block appears naming our agent class. | **Immediate revocation** (§7.4). The in-flight run halts `HALTED_BY_POLICY`. Re-enablement needs a fresh full review, not an extension. |
| **5** | A qualifying aggregator publishes a spec that exactly matches the manufacturer's published figure. | Still `AGGREGATOR`, still `NOT_VERIFIED`. Agreement is corroboration, not verification, and Gate W still refuses the promotion trace. Two sources asserting the same value are **two rows** (Gate X). |
| **6** | A qualifying aggregator hosts a photograph credited "© Manufacturer". | Reference-only, `retrieval_source_class = AGGREGATOR`, no download, no MEDIA-01 verdict. The credit is a claim the page makes, never an attribution we assert — the Figure 02 precedent. |
| **7** | A source has no terms and no robots restrictions, and its pages are trivially enumerable via an undocumented JSON endpoint that is far cleaner than the HTML. | **Prohibited** (§6.2, hidden API discovery). Convenience is not authority, and an undocumented endpoint is not a published interface. |
| **8** | The publisher emails: "please stop, though I see you're within our robots policy." | **Immediate revocation** (§7.6). The objection is effective on receipt. Being technically within policy is irrelevant; the state was only ever "they have expressed nothing", and they have now expressed something. |
| **9** | A source previously `PROHIBITED` relaunches its site; the old anti-scraping clause is simply gone. | **Not** `NO_EXPRESS_PROHIBITION` by default (§7, final paragraph). A fresh named review must consider whether the prohibition genuinely ended or a redesign lost a page. |
| **10** | A qualifying source's page says "Available now — $16,000". | One `NOT_VERIFIED` claim on the price axis with its excerpt, and **no** availability or maturity conclusion without their own separate evidence (§6.2, last row). One sentence is not evidence for three axes. |
| **11** | Limited-mode radar surfaces a robot absent from the canonical catalogue and from all 43 candidates. | Exactly what the state is for: a new discovery candidate, `NOT_VERIFIED`, queued for a human. This is the amendment's actual value. |
| **12** | An operator argues the source is "obviously fine" and asks to skip the recorded search. | Refused. Requirement 8 makes an unattributed review not a review (DATA-D1.9). The record is the artefact; without it the state does not exist. |
| **13** | A **manufacturer** has a permissive `robots.txt`, no terms page, no rights reservation and no access denial — it would satisfy all ten requirements. | **Does not qualify.** A1 is limited to `AGGREGATOR` (§2.1), and `MANUFACTURER` is not widened. Automated acquisition still requires `ALLOWED`. Human research under `MANUAL_BOOTSTRAP` remains fully available and is the correct route. |
| **14** | A source's policy says only *"Do not use this content to train AI models"*, while otherwise permitting ordinary indexing and retrieval. | **Training remains prohibited, absolutely and permanently.** The training-only statement does not by itself prohibit limited radar access (§4.1 rule 2) — **but every other A1 requirement must still pass**, including the class precondition, the full six-axis search and owner enablement. Rule 2 removes one obstacle; it grants nothing. |
| **15** | A source's policy or notice reserves **text-and-data mining** or **systematic database extraction** — an Article 4 reservation, a sui-generis database-right notice, or a clause against systematic extraction. | **`PROHIBITED`** for the proposed radar activity (§4.1 rule 4). What A1 authorizes *is* systematic extraction; naming it "radar" does not place it outside such a reservation. |
| **16** | A source qualifies on every axis, but an honest classification makes it `COMPETITOR_DIRECTORY`. Reclassifying it `AGGREGATOR` would make it eligible, and the content is arguably aggregated data. | **Does not qualify, and must not be reclassified** (§2.1). Class records what a source is, on the evidence. If the class is genuinely wrong, correcting it is a classification decision made on its own merits and recorded as such — never a step taken *because* it produces eligibility. If A1's scope proves too narrow, the remedy is a later amendment naming the class. |
| **17** | A directive restricts "AI use" without stating whether it covers retrieval and grounding or only training. The permissive reading would qualify the source. | **`UNKNOWN`** (§4.1 rule 5), and `UNKNOWN` is never fetched. When scope cannot be determined, the restriction applies. A reviewer constructing an argument for why it "probably means training" has already failed the rule. |

## 12. Non-goals

This amendment explicitly does **not**:

- authorize any fetch, of any source, official or otherwise;
- approve any of the four candidate sources in §9;
- extend the new state to any class other than `AGGREGATOR` — `MANUFACTURER`,
  `OFFICIAL_STORE` and `AUTHORIZED_DISTRIBUTOR` continue to require `ALLOWED`,
  and `COMPETITOR_DIRECTORY`, `EDITORIAL` and every other class remain governed
  by the pre-amendment rules (§2.1);
- authorize reclassifying any source to bring it inside the eligible class;
- select any operational limit — concurrency, rate, page cap or byte ceiling.
  Freezing those is a **precondition** of the implementation slice (§10.3), and
  no adapter code may precede it;
- permit training on acquired content, under any directive, from any source;
- reopen `robotsguide.com`, `roboselect360.com`, or any source assessed as
  `PROHIBITED`;
- weaken, qualify or create an exception to Gate W, Gate S, Gate T, Gate X, or
  DATA-D1 P2 / P8;
- alter the source-authority precedence order;
- permit image downloading, self-hosting, or any MEDIA-01 verdict;
- permit public republication of any acquired text;
- create a route by which a `NO_EXPRESS_PROHIBITION` claim becomes canonical;
- create an automatic path from `PROHIBITED` to any weaker state;
- change `ALLOWED`, `UNKNOWN` or `PROHIBITED` semantics;
- authorize a scheduler, a hosted crawler, or any non-manual trigger (LIVE.4);
- modify schema, models, migrations, crawler code, extraction tooling, APIs or
  UI — this PR changes documentation only;
- assert that the state is lawful in any given jurisdiction. It is a policy
  about what this platform will do, not a legal opinion, and §5.5 of the base
  contract's assessment ("legal review if the intention is to rely on a
  facts-versus-expression argument") is unaffected.

## 13. Ratification record

```
STATUS:                      RATIFIED (revision 3)
Proposed:                    2026-07-30
Corrected:                   2026-07-30 — owner review, corrections 1-3
                             (class precondition §2.1 · restriction
                             applicability §4.1 · operational ceilings §10.3)
Amends:                      docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md
                             (RATIFIED v0.1, main @ 6875a34)
Implementation authorized:   NONE — documentation only
Sources approved:            NONE
Eligible source class:       AGGREGATOR ONLY (§2.1). MANUFACTURER,
                             OFFICIAL_STORE and AUTHORIZED_DISTRIBUTOR require
                             ALLOWED; all other classes unchanged. Widening
                             requires a further amendment. Reclassification to
                             gain eligibility is prohibited.
Candidate sources:           The Mimic · Lineroid · WhichHumanoid · RoboZaps
                             (candidates only; each requires its own full
                             review under the amended procedure, AND must first
                             satisfy the AGGREGATOR class precondition on an
                             honest classification — which may exclude some)
Explicitly excluded:         robotsguide.com · roboselect360.com — disqualifying
                             directives and access behaviour on the recorded
                             assessment
Training on acquired
  content:                   PROHIBITED — always, under every directive, from
                             every source (§4.1 rule 1)
Operational ceilings:        NOT SELECTED. Freezing per-host concurrency, rate,
                             page cap and byte ceilings is a PRECONDITION of
                             the implementation slice (§10.3). No adapter code
                             may precede it.
Gate W:                      UNCHANGED
Gates S / T / X, P2 / P8:    UNCHANGED
Precedence order:            UNCHANGED
Default expiry:              90 days (owner decision, 2026-07-30) — aligned
                             with the ALLOWED terms-review validity, so the
                             weaker silence-based state never outlives
                             affirmative permission. A MAXIMUM validity, not a
                             guarantee, and no substitute for run-start policy
                             checks or the immediate revocation triggers (§7)
Expiry semantics:            FAIL-CLOSED ACCESS SUSPENSION. Never a crawl,
                             fetch, refresh, retry, scheduling or acquisition
                             trigger. Expiry starts nothing (§7.1)

Ratified by:                 Robert Konecny (product owner)
Ratification date:           2026-07-30
Ratified at:                 revision 3 — amendment content as reviewed at
                             head 1dfc48ac44e69ba57c9ec7dcc749de115710e2d8
                             (6/6 CI green, documentation only)
```

**This document freezes principles only.** Implementing the state — enum
widening, mode-aware eligibility, database constraints, expiry behaviour, gates,
run-report and review-UI changes — requires a **separate implementation
contract**, and enabling any individual source requires that source's own
recorded review and the owner's explicit enablement, source by source, exactly
as the base contract requires today.

### 13.1 Authorized sequence following ratification

Ratified as the order of work, so that no step is taken out of turn:

1. **A separate implementation contract** covering enums, limited-radar mode,
   database constraints, expiry behaviour and the numerical ceilings of §10.3.
   It is ratified before any code is written.
2. **Fresh individual eligibility reviews** of The Mimic, Lineroid,
   WhichHumanoid and RoboZaps, each under the complete amended procedure —
   §2.1 class precondition first, then all ten requirements of §4, with the
   §5 evidence record.
3. **Enablement of only those honestly classified `AGGREGATOR` and passing
   every requirement.** A candidate that fails either test is not enabled, and
   is not reclassified.

**Source-data extraction tooling remains paused** until steps 1–3 above are
reached in order. Ratification does not restart it.
