# Release Invariant Matrix — MVP v0.1

> **STATUS: IN PROGRESS — opened at WS8.1, completes at WS8.9.**
>
> Required by the ratified WS8 Release Contract (`12_WS8_RELEASE_CONTRACT.md`
> §10, gate **R33**). This is the finite, auditable manifest that replaced an
> unbounded "every frozen law has a regression test" claim.
>
> **A law with no row is a release blocker. A row with no evidence is a release
> blocker.** Rows are populated only where the evidence legitimately exists
> *now*; everything else is explicitly `PENDING` against the slice that owes it.
> Nothing here may be marked `PASS` on the strength of an intention.

## How to read this

Each row carries an evidence class from WS8-L8 — exactly one, never a hybrid:

| Class | Meaning |
|---|---|
| **Automated** | a command or CI job; artifact = job/run output |
| **Attested** | a named operator + dated evidence artifact |
| **Observed** | measurement from the deployed production system |

Status values: `PASS` (evidence exists and is green today) · `PENDING` (owed by
a later slice) · `N/A` with a reason.

---

## 1. WS8 laws (`12_WS8_RELEASE_CONTRACT.md` §3)

| ID | Invariant | Source | Class | Evidence | Gate | Status |
|---|---|---|---|---|---|---|
| L1 | No new product/commercial capability | WS8 §3 | Automated | `R34` diff assertion (WS8.9) | R34 | PENDING (WS8.9) |
| L2 | Whole-surface release candidate | WS8 §3 | Attested | WS8.9 sign-off covers every §2 surface | R33 | PENDING (WS8.9) |
| L3 | Differentiated depth per surface | WS8 §3 | Attested | slice PRs map to §5 depth | R33 | PENDING (WS8.9) |
| L4 | No law weakening to pass a gate | WS8 §3 | Attested | per-PR review; **WS8.1 note below** | R33 | IN PROGRESS |
| L5 | Fail closed in production | WS8 §3 | Automated | `test_r1_admin_is_not_mounted_when_unconfigured`, `test_r1_partial_configuration_still_fails_closed` | R1, R7 | **PASS** (admin) · PENDING (config, WS8.2) |
| L6 | PII containment | WS8 §3 | Automated | `test_pii_containment.py` (5 tests) | R2, R5 | **PASS** |
| L7 | Reversibility + schema rollback doctrine | WS8 §3 | Attested | rollback drill | R9, R30 | PENDING (WS8.2, WS8.8) |
| L8 | Evidence of readiness by declared class | WS8 §3 | Attested | this matrix | R33 | IN PROGRESS |
| L9 | Explicit policy over implicit default | WS8 §3 | Automated | `test_r4_default_posture_is_strict_same_origin`, `test_r4_wildcard_origin_is_not_an_accepted_policy`, `e2e/security-headers.spec.ts` | R4 | **PASS** |
| L10 | Anonymity preserved under abuse control | WS8 §3 | Automated | `test_legitimate_repeat_submission_is_not_treated_as_abuse`; no auth dependency added to either write path | R3 | **PASS** |
| L11 | Prove what the slice can actually prove | WS8 §3 | Attested | staged gates §9.0.1 honoured — R1 claims application authz only | R1, R27, R29 | **PASS** (WS8.1 scope) |

**L4 note (WS8.1).** One pre-existing test was *changed*, and it must be read as
a strengthening, not a weakening: `test_admin_mounted` asserted that
`GET /admin/` returned **200 to an anonymous caller**. That green test was gap
B1 written down as an expectation. It is now
`test_admin_is_not_anonymously_reachable`, asserting anonymous 200 can never
recur. No other existing assertion was modified.

## 2. Deployment Execution Profile (`12` §6)

| ID | Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|---|
| P1 | Forwarding headers trusted only from configured trusted ingress | Automated | `test_forwarding_header_from_untrusted_peer_is_ignored`, `test_forwarding_header_ignored_when_no_ingress_is_trusted`, `test_chain_walks_right_to_left_skipping_trusted_hops`, `test_spoofed_forwarding_header_cannot_buy_a_fresh_budget` | R3 | **PASS** (pre-deployment) · deployed proof PENDING (R29) |
| P2 | Singleton API instance for MVP | Attested | binding to infrastructure | R26 | PENDING (WS8.7) |
| P3 | Process-local abuse state only behind a storage abstraction | Automated | `RateLimitStore` protocol + `InMemoryFixedWindowStore`; limiter constructed with an injected store | R3 | **PASS** |
| P4 | Admin on a separate protected host/listener | Attested | boundary realized | R27 | PENDING (WS8.7) |
| P5 | Ingress trust + admin boundary operator-configurable and testable | Attested | provider acceptance filter | R26 | PENDING (WS8.7) |

## 3. Frozen laws inherited from earlier contracts

### WS0 / product-contract semantics

| Invariant | Source | Class | Evidence | Gate | Status |
|---|---|---|---|---|---|
| UNKNOWN ≠ 0 / false / unavailable | WS0 | Automated | `test_knowledge_api.py`, `e2e/catalogue.spec.ts` | R15 | PENDING re-assertion (WS8.3) |
| QUOTE_ONLY ≠ UNKNOWN | WS0 | Automated | `test_knowledge_api.py` | R15 | PENDING re-assertion (WS8.3) |
| maturity ≠ obtainability ≠ evidence | WS0 | Automated | `test_knowledge_api.py`, `test_matching_engine.py` | R15 | PENDING re-assertion (WS8.3) |
| No commercial fact without evidence (G2) | WS0 | Automated | `db/seed/seed.sql` self-check, `db/validate_catalogue.py` | R15 | PENDING re-assertion (WS8.3) |
| Deterministic, LLM-free scoring | WS6 | Automated | `test_matching_engine.py` (40 tests) | R15 | PENDING re-assertion (WS8.3) |

### MEDIA-01 (`09_MEDIA_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| Only VERIFIED-identity, rights-cleared images display | Automated | `test_robot_images.py` matrix (9/16 cells today) | R11 | PENDING — full 16-cell matrix owed (Q5) |
| Missing image renders IMAGE UNAVAILABLE, never a placeholder | Automated | `RobotGallery` / `RobotCard` + backend tests | R11 | PENDING (WS8.3) |
| `hero_image_url` cannot bypass the eligibility gate | Automated | — | R11 | PENDING (Q6, WS8.3) |
| ATTRIBUTION_REQUIRED never renders without attribution | Automated | — | R11 | PENDING (Q14, WS8.3) |

### DATA-D1 (`11_DATA_D1_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| Candidate ≠ canonical; discovery never auto-promotes | Automated | `test_discovery.py` A–K | R12 | PENDING re-assertion (WS8.3) |
| Structural isolation (no canonical → discovery FK) | Automated | `test_K_structural_isolation` | R12 | PENDING re-assertion (WS8.3) |
| Candidate data absent from public **response bodies** | Automated | — (today's `test_I` asserts route paths only) | R12 | PENDING (Q7, WS8.3) |
| Promotion is human-gated and idempotent | Automated | `test_H5_promotion_is_idempotent`, `test_discovery.py` | R12 | PENDING re-assertion (WS8.3) |
| **`promotion_audit` is append-only** | Automated | `test_r6_admin_cannot_create_edit_or_delete_audit_rows`, `test_r6_orm_listeners_are_registered`, `test_r6_update_is_refused`, `test_r6_delete_is_refused`, `test_r6_insert_is_still_allowed` | R6 | **PASS** |
| No live crawling (fixture-only) | Automated | `test_ineligible_source_cannot_be_crawled` + no network adapter | R13 | PENDING re-assertion (WS8.3) |
| Promotion docs truthful to implemented gates | Attested | — | R12 | PENDING (Q8a, WS8.3) |

### AGENT-01 (`10_AGENT_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| 01.1 canonical identity URI | Automated | `e2e/agent-accessibility.spec.ts` | R14 | PENDING re-assertion (WS8.3) |
| 01.2 semantic parity | Automated | `__tests__/jsonld.test.ts` | R14 | PENDING re-assertion (WS8.3) |
| 01.3 explicit uncertainty (UNKNOWN never coerced) | Automated | `jsonld.test.ts` — the `0` / `""` case is **not** yet covered | R14 | PENDING (Q12, WS8.3) |
| 01.4 provenance preserved, never fabricated | Automated | — | R14 | PENDING (WS8.3) |
| 01.5 typed action parity | — | — | — | **N/A** — later separately-ratified slice; gate CLOSED |
| 01.6 projection only | Attested | no second source of truth introduced | R14 | PENDING (WS8.3) |
| 01.7 published-canonical-only surface | Automated | — (no test asserts an unpublished entity is **absent**) | R14 | PENDING (Q9, WS8.3) |

## 4. WS8.1 gate status (this slice)

| Gate | Class | Status | Evidence |
|---|---|---|---|
| R1 admin application authorization | Automated | **PASS** | `test_security_boundaries.py` — 6 tests; B1 **stage 1 only** |
| R2 no PII on unauthenticated surfaces | Automated | **PASS** | `test_pii_containment.py` — 3 tests |
| R3 endpoint-aware abuse controls | Automated | **PASS** | `test_rate_limiting.py` — 15 tests |
| R4 explicit cross-origin / header posture | Automated | **PASS** | `test_security_boundaries.py` + `e2e/security-headers.spec.ts` |
| R5 no PII in URLs / query / logs | Automated | **PASS** | `test_pii_containment.py` — 2 tests |
| R6 `promotion_audit` append-only enforced | Automated | **PASS** | `test_security_boundaries.py` — 5 tests |

**Not claimed by WS8.1**, and deliberately so: R27 (network boundary realized)
and R29 (external negative probe). Until both land, **B1 is not fully closed** —
only its application layer is.

## 5. Registered gaps still open (`12` §8)

Carried forward so nothing is lost between slices. `CLOSED` here means the gate
that owns it has passed.

| Gap | Disposition | Owing slice | Status |
|---|---|---|---|
| B1 `/admin` unauthenticated | CLOSE | WS8.1 → WS8.7 → WS8.8 | **stage 1 CLOSED**, stages 2–3 open |
| B2 no abuse control / unstated posture | CLOSE | WS8.1 → WS8.8 | **pre-deployment CLOSED**, deployed probe open |
| B3 `DATABASE_URL` dev default | CLOSE | WS8.2 | open |
| B4 `NEXT_PUBLIC_SITE_URL` prod default | CLOSE | WS8.2 | open |
| B5 audit not append-only | CLOSE | WS8.1 | **CLOSED** |
| D1–D7, D9 | CLOSE | WS8.2 / WS8.6 / WS8.7 | open |
| D8 `event_log` dead | NOT A RELEASE DEFECT | — | documented dormant at R25 (open) |
| D10 scheduled re-verification | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
| Q1–Q3a, Q4–Q14 | CLOSE | WS8.3 / WS8.4 / WS8.5 | open |
| Q3b OG/Twitter imagery | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
| Q8b DATA-D1 P3/P5/P7 gates | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
