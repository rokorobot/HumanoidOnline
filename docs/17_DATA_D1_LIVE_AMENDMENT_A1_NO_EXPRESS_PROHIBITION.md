# DATA-D1.LIVE — Amendment A1: `NO_EXPRESS_PROHIBITION`

> **STATUS: PROPOSED — NOT RATIFIED.**
>
> This document amends `16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`
> (RATIFIED v0.1, 2026-07-29, main @ `6875a34`). It has **no force** until the
> product owner ratifies it in §12.
>
> **Nothing in this amendment authorizes a fetch.** It defines a third
> eligibility state and the narrow capability that state may carry. Every source
> still requires its own recorded review (§5 of the base contract) before any
> request is issued, and this amendment approves **no source**.
>
> **Implementation authorized by this document: none.** It is a docs-only
> proposal. Schema, models, migrations, adapters, extraction tooling, APIs and UI
> are untouched and must remain so until a later, separately authorized slice.

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
| **`NO_EXPRESS_PROHIBITION`** | A named reviewer searched six specified places at a recorded time and **found no prohibition**. The publisher has expressed nothing either way. | The six-axis search record of §5, including **where terms and licensing pages were looked for and not found**. | ⚠️ **Limited radar mode only** — §6 capability matrix. | ❌ **Never.** No canonical write, no `VERIFIED` claim, no satisfaction of Gate W, under any circumstances. |
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

A source may receive `NO_EXPRESS_PROHIBITION` **only when all ten are true**.
Any one failing means the state is refused; the correct outcome is `UNKNOWN` or
`PROHIBITED`, never a partial grant.

| # | Requirement |
|---|---|
| **1** | **No applicable agent-specific `Disallow` exists.** Neither our agent nor the AI-crawler class it belongs to is named with a `Disallow` in `robots.txt`. A wildcard `Allow: /` does not cure a named `Disallow`. |
| **2** | **The relevant paths are not disallowed.** Every path prefix the review covers is permitted for the group that applies to us — evaluated for the exact prefixes, not for the host in general. |
| **3** | **No TDM, AI-use or database-extraction rights reservation applies.** No `Content-Signal` restriction, no Article 4 (EU 2019/790) reservation, no `noai`/`noimageai` directive, no sui-generis database-right notice, no licence term reserving extraction. |
| **4** | **No accessible terms or policy prohibits automation, scraping, data mining or systematic extraction.** Terms of use, acceptable-use policy, legal notice, licensing page and copyright notice — whichever exist and are reachable. |
| **5** | **The review records where terms and licensing pages were searched.** The list of URLs tried, and their outcomes, including the ones that 404'd. "No terms page found" is a claim about a search, and the search must be reproducible by someone else. |
| **6** | **Ordinary requests are accepted without bypassing access controls.** The declared user agent, at the declared rate, with no impersonation, no proxy rotation, no fingerprint evasion and no header manipulation beyond ordinary conditional-request validators. |
| **7** | **No login, CAPTCHA, paywall, `403` block or other technical denial is present** on the paths under review. |
| **8** | **The reviewer, timestamp, URLs, hashes and supporting excerpts are recorded** — for every axis, including the axes that came back empty. |
| **9** | **The review has not expired** (§7: 30 days by default). |
| **10** | **The source is explicitly enabled for the limited radar mode.** Reviewing is not enabling — the base contract's §5 step 5, restated because it is the step most often skipped. Enablement names the mode; a source enabled for limited radar is not enabled for anything else. |

**Silence must be recorded as silence, never rewritten as permission.** Where a
document does not exist, the record says it does not exist and lists where it
was sought. Where a document exists and is silent on automation, the record
quotes enough of it to show the silence is real and not a missed clause. No
field anywhere may be set to a value meaning "permitted" on the strength of an
absence.

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
| HTTP content signals | `Content-Signal` values if present; response headers bearing on reuse (`X-Robots-Tag` and equivalents); an explicit nil finding if absent. |
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
| Candidate claims with source class `AGGREGATOR` | The class reflects **where the content was actually seen**, never what it claims to be about. An aggregator page reproducing a manufacturer's figure is `AGGREGATOR` (the Figure 02 precedent, MEDIA-01). |
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

**Default expiry: 30 days.** Shorter than the 90-day terms validity of LIVE.2,
deliberately. A 90-day validity suits a legal document that changed
deliberately; this state rests on an *absence*, and an absence can be filled at
any moment by a publisher who adds a terms page, a `Content-Signal` or a
Cloudflare rule without ever telling anyone. The `robots.txt` re-read at every
run start (LIVE.2) is unchanged and continues to apply.

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

| Source | Host | Observed 2026-07-30 | Outstanding before the state could be granted |
|---|---|---|---|
| **The Mimic** | `themimic.io` | `User-agent: * / Allow: /`, no agent-specific groups, no content signals, sitemap present. `/terms` returned `404`. | Full terms/licensing search with recorded locations; content-signal and header check; technical-behaviour check on representative paths. |
| **Lineroid** | `lineroid.com` | `Allow: /` with `Crawl-delay: 1`; disallows `/admin`, `/auth`, `/api/*`; named groups for search engines and social crawlers only. `/terms` returned `404`. | As above. `Crawl-delay: 1` is a declared rate the limited mode must honour, and it is a floor, not a target. |
| **WhichHumanoid** | `whichhumanoid.com` | `Allow: /` plus `LLM-Policy: /llms.txt`; the policy file adds the non-standard `Disallow-Training: /`. | As above, plus a careful read of the full `llms.txt`. `Disallow-Training` is not disqualifying — we do not train models on acquired content and the contract forbids it — but a publisher who has thought about machine access may have said more, and requirement 3 turns on exactly that. |
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
| Enum widening | `eligibility_decision` and `tos_status` each gain `NO_EXPRESS_PROHIBITION`. Additive only; every existing value is retained verbatim. Note the PostgreSQL constraint: `ALTER TYPE ... ADD VALUE` cannot be used in the same transaction that then uses the new value, so the migration sequences the widening ahead of any data write. |
| `discovery_source.radar_eligible` | Currently a boolean property requiring `tos_status == "ALLOWED"`. It must become **mode-aware**: a source in the new state is eligible for *limited radar* and for nothing else. The safest shape is an explicit radar-mode value rather than a widened boolean, so that every call site is forced to state which mode it means and no existing caller silently gains the new capability. |
| DB-level `CHECK` on `is_enabled` | The existing constraint encoding DATA-D1.9 must be extended to admit the new state **only** in combination with the limited mode — the database, not the application, remains the place this is enforced (L7). |
| `source_eligibility_review` | No new column is strictly required; the six-axis search record fits `notes` plus the existing per-axis URL/hash/excerpt fields. A dedicated structured column for the "where we searched" list would be better and should be considered in the slice. The table is append-only and stays so. |
| Expiry | 30 days for this state against 90 for `ALLOWED` means `expires_at` becomes state-dependent at write time. It is already a column; only the default calculation changes. |
| New acceptance gates | At minimum: a source in this state can never produce `VERIFIED` or a canonical write (state-level, independent of Gate S); a technical denial disables the source within the same run; an expired review of this state blocks a run; the state is never mapped to `ALLOWED` in any projection, report or UI; and `PROHIBITED` cannot transition into this state without a new review record. |
| Run report | The §18 report must print the eligibility **state** per source, not merely "eligible", so an operator reading a report can tell which authority a run was operating under. |
| Rate policy | Limited mode carries its own, stricter rate ceiling, and honours any declared `Crawl-delay` as a floor. |
| Review UI | The `/discovery-review` surface must distinguish the state visibly. A candidate enriched under limited radar must not look like a candidate traced to a manufacturer. |
| No canonical, API, MCP or public-surface change | The new state is invisible to every public and machine surface (AGENT-01.7, Gate O). |

### 10.2 What the slice does *not* get to assume

Ratifying this amendment authorizes **no source**. On ratification the position
is: a third state exists, and zero sources hold it. Each of the four candidates
in §9 needs its own full review, its own owner enablement, and its own recorded
artefact — reviewed in exactly the same way a manufacturer would be, because
source class predicts nothing about eligibility (§5 of the base contract).

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

## 12. Non-goals

This amendment explicitly does **not**:

- authorize any fetch, of any source, official or otherwise;
- approve any of the four candidate sources in §9;
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
STATUS:                      PROPOSED — NOT RATIFIED
Proposed:                    2026-07-30
Amends:                      docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md
                             (RATIFIED v0.1, main @ 6875a34)
Implementation authorized:   NONE — documentation only
Sources approved:            NONE
Candidate sources:           The Mimic · Lineroid · WhichHumanoid · RoboZaps
                             (candidates only; each requires its own full
                             review under the amended procedure)
Explicitly excluded:         robotsguide.com · roboselect360.com — disqualifying
                             directives and access behaviour on the recorded
                             assessment
Gate W:                      UNCHANGED
Precedence order:            UNCHANGED
Default expiry:              30 days

Ratified by:                 ____________________
Ratification date:           ____________________
```

**On ratification this document freezes principles only.** Implementing the
state — enum widening, mode-aware eligibility, gates, run-report and review-UI
changes — requires a separately authorized slice, and enabling any individual
source requires that source's own recorded review and the owner's explicit
enablement, source by source, exactly as the base contract requires today.
