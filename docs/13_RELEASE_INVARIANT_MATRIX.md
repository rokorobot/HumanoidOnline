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
| L5 | Fail closed in production | WS8 §3 | Automated | `test_r1_admin_is_not_mounted_when_unconfigured`, `test_r1_partial_configuration_still_fails_closed`, `test_unknown_policy_fails_closed_at_check_time`, `test_unknown_policy_is_rejected_at_wiring_time`, `test_there_is_no_global_disable_switch`, `test_malformed_trusted_ingress_config_fails_loudly` | R1, R3, R7 | **PASS** — admin, abuse control, ingress config (WS8.1) + database URL and canonical origin (WS8.2, `test_config_contract.py`, `__tests__/site-origin.test.ts`) |
| L6 | PII containment | WS8 §3 | Automated | `test_pii_containment.py` (5 tests) | R2, R5 | **PASS** |
| L7 | Reversibility + schema rollback doctrine | WS8 §3 | Attested | migrations remain additive; no destructive change and no synthetic down-migration introduced by WS8.2. **Application rollback is proven possible against a migrated schema** — `test_database_ahead_of_the_build_is_not_blocking`, `test_ahead_database_passes_verification_against_the_real_database`. Rollback drill still owed | R9, R30 | PARTIAL — doctrine conformance **PASS**, drill PENDING (WS8.8) |
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
| P1 | Forwarding headers trusted only from configured trusted ingress | Automated | `test_forwarding_header_from_untrusted_peer_is_ignored`, `test_forwarding_header_ignored_when_no_ingress_is_trusted`, `test_chain_walks_right_to_left_skipping_trusted_hops`, `test_spoofed_forwarding_header_cannot_buy_a_fresh_budget`, `test_malformed_trusted_ingress_config_fails_loudly` (+ boot-time validation in `app.main`) | R3 | **PASS** (pre-deployment) · deployed proof PENDING (R29) |
| P2 | Singleton API instance for MVP | Attested | Config prepared (WS8.7): one `api` service, `uvicorn --workers 1`, no replicas — asserted by `test_single_api_instance_and_worker`. **No second FastAPI process**: the admin boundary is realized at the ingress, not by an extra application instance | R26 | PENDING (binding requires the deployed VPS) |
| P3 | Process-local abuse state only behind a storage abstraction | Automated | `RateLimitStore` protocol + `InMemoryFixedWindowStore`; limiter constructed with an injected store | R3 | **PASS** |
| P4 | Admin on a separate protected host/listener | Attested | Config prepared (WS8.7): public Caddy listener answers **404** for `/admin*` (covers `/admin/statics/*`); a second Caddy listener published **only** on `127.0.0.1:8001` proxies `/admin*` to the same singleton API, reached via SSH tunnel; SQLAdmin auth still mandatory — asserted by `test_public_listener_refuses_admin`, `test_admin_listener_is_published_on_loopback_only`, `test_only_caddy_publishes_ports` | R27 | PENDING (boundary realized only when deployed) |
| P5 | Ingress trust + admin boundary operator-configurable and testable | Attested | Provider accepted: Hostinger KVM 4 (root VPS) satisfies the filter. Operator-owned `deploy/Caddyfile` + `docker-compose.prod.yml` make both semantics explicit and testable; externally re-proven at R29 | R26 | PENDING (capability accepted; realization requires deployment) |

## 3. Frozen laws inherited from earlier contracts

### WS0 / product-contract semantics

| Invariant | Source | Class | Evidence | Gate | Status |
|---|---|---|---|---|---|
| UNKNOWN ≠ 0 / false / unavailable | WS0 | Automated | `test_r14_unknown_specs_stay_null_and_are_never_coerced`, `test_knowledge_api.py`, `e2e/catalogue.spec.ts` | R15 | **PASS** |
| QUOTE_ONLY ≠ UNKNOWN | WS0 | Automated | `test_r15_price_trichotomy_holds_across_the_catalogue` (every published robot, not one) | R15 | **PASS** |
| maturity ≠ obtainability ≠ evidence | WS0 | Automated | `test_r15_three_dimensions_never_collapse` — asserts no `available` boolean exists anywhere | R15 | **PASS** |
| No commercial fact without evidence (G2) | WS0 | Automated | `test_r15_g2_every_published_commercial_fact_carries_evidence` (live DB, not trusting the importer) + both G2 gates | R15 | **PASS** |
| Deterministic, LLM-free scoring | WS6 | Automated | `test_matching_engine.py` (40 tests) | R15 | **PASS** |

### MEDIA-01 (`09_MEDIA_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| Only VERIFIED-identity, rights-cleared images display | Automated | `test_truth_regressions.py` — **all 16 cells**, asserted against a restatement of the law rather than the implementation | R11 | **PASS** |
| Missing image renders IMAGE UNAVAILABLE, never a placeholder | Automated | `RobotGallery` / `RobotCard` + `test_robot_images.py` | R11 | **PASS** |
| `hero_image_url` cannot bypass the eligibility gate | Automated | `test_r11_hero_image_url_cannot_bypass_the_gate` — plants an un-cleared URL and reads every public surface | R11 | **PASS** |
| ATTRIBUTION_REQUIRED never renders without attribution | Automated | the eligibility gate now enforces it, plus unit / end-to-end / whole-catalogue sweep | R11 | **PASS** |

### DATA-D1 (`11_DATA_D1_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| Candidate ≠ canonical; discovery never auto-promotes | Automated | `test_discovery.py` A–K | R12 | **PASS** |
| Structural isolation (no canonical → discovery FK) | Automated | `test_K_structural_isolation` | R12 | **PASS** |
| Candidate data absent from public **response bodies** | Automated | `test_r12_candidate_data_never_appears_in_any_public_response_body` — real source/candidate/claim with sentinels, every public body searched | R12 | **PASS** |
| Promotion is human-gated and idempotent | Automated | `test_H5_promotion_is_idempotent`, `test_discovery.py` | R12 | **PASS** |
| **`promotion_audit` is append-only** | Automated | `test_r6_admin_cannot_create_edit_or_delete_audit_rows`, `test_r6_orm_listeners_are_registered`, `test_r6_update_is_refused`, `test_r6_delete_is_refused`, `test_r6_insert_is_still_allowed` | R6 | **PASS** |
| No live crawling (fixture-only) | Automated | `test_r13_*` — no HTTP client reachable from the adapter, FixtureAdapter is the only concrete adapter, and a public request sweep runs with outbound sockets made fatal | R13 | **PASS** |
| Promotion docs truthful to implemented gates | Automated | `test_r12_promotion_docs_match_implemented_gates` + `test_r12_deferred_gates_are_still_deferred` | R12 | **PASS** |

### AGENT-01 (`10_AGENT_CONTRACT.md`)

| Invariant | Class | Evidence | Gate | Status |
|---|---|---|---|---|
| 01.1 canonical identity URI | Automated | `e2e/agent-accessibility.spec.ts` | R14 | **PASS** |
| 01.2 semantic parity | Automated | `__tests__/jsonld.test.ts` | R14 | **PASS** |
| 01.3 explicit uncertainty (UNKNOWN never coerced) | Automated | `agent-truth.test.ts` — empty/whitespace strings omitted, a genuine `0` KEPT (dropping it is the mirror-image error), no placeholder strings; `test_r14_unknown_specs_stay_null_and_are_never_coerced` server-side | R14 | **PASS** |
| 01.4 provenance preserved, never fabricated | Automated | `agent-truth.test.ts` asserts no invented provenance keys; `test_r15_evidence_carries_provenance_not_just_a_flag` | R14, R15 | **PASS** |
| 01.5 typed action parity | — | — | — | **N/A** — later separately-ratified slice; gate CLOSED |
| 01.6 projection only | Automated | `agent-truth.test.ts` — an empty governed read yields an empty projection, never a fallback | R14 | **PASS** |
| 01.7 published-canonical-only surface | Automated | `test_r14_unpublished_robot_is_absent_from_every_public_surface` (real unpublished robot + sentinels, 404 on direct fetch) · `test_r14_unpublished_robot_is_absent_from_matching_and_leads` · `agent-truth.test.ts` proves the projection adds nothing back | R14 | **PASS** |

## 4. WS8.4 gate status

| Gate | Class | Status | Evidence |
|---|---|---|---|
| R16 Journeys A/B/C | Automated | **PASS** | `e2e/journeys.spec.ts` — explore→compare matrix, wizard→match→lead capture, use-case→suitable robot→detail; each asserts the governed result, not a page load |
| R17 WCAG 2.2 AA (automated) | Automated | **PASS** | All **five** frozen obligations covered — not "axe reports zero violations": **(1) every §5.1 public route** — `e2e/accessibility-axe.spec.ts` axe WCAG 2.2 AA on `/`, `/robots`, `/robots/[slug]`, `/compare`, `/manufacturers`, `/manufacturers/[slug]`, `/use-cases`, `/use-cases/[slug]`, `/find-a-humanoid`, `/matches/[id]`, **404** + interactive states (dialog open, validation error), zero violations, desktop **and** Pixel-7; **(2) keyboard-only journeys** — `e2e/keyboard.spec.ts` skip-link→main focus, keyboard-only nav activation, open→submit the lead dialog by keyboard; **(3) focus behaviour** — dialog focus-trap (Tab/Shift+Tab stay inside), Escape closes + returns focus to opener, invalid field takes focus; **(4) semantic headings/forms/dialogs** — `e2e/semantics.spec.ts` one H1 + main landmark + one `contentinfo` (footer) landmark + named primary nav per route, programmatic form labels, dialog role/`aria-modal`/accessible-title, invalid↔alert wiring; **(5) mobile target size** — `e2e/responsive.spec.ts` direct ≥24×24 measurement of the deliberate controls **plus** axe's `target-size` rule by name on the Pixel-7 profile |
| R18 screen-reader | **Attested** | **PASS** | `docs/14_R18_SCREEN_READER_ATTESTATION.md` completed by a named human operator — **Robert Konecny / Product Owner, 2026-07-26, NVDA + Chrome / Windows, head `5a3ca6a`**. §1–§8 PASS across the frozen §9.4 surfaces (nav, catalogue, robot detail, wizard, matches, lead dialog); §9 mobile N-A (desktop scope). NOT self-attested — a person completed the record; axe green (R17) does not satisfy it |
| R19 responsive | Automated | **PASS** | `e2e/responsive.spec.ts` on a real **mobile-chromium (Pixel 7)** project in CI + desktop: no horizontal overflow, cards not clipped, compare/spec tables scroll in-container, primary actions operable |
| R20 empty/error states | Automated | **PASS** | `e2e/ux-states.spec.ts` — 404, compare<2 prompt, price trichotomy (never $0), availability-unknown≠unavailable, invalid-email announced, API-failure retains input; `__tests__/robot-gallery.test.tsx` for the missing-image state |
| R21 lint / jsx-a11y | Automated | **PASS** | `.eslintrc.cjs` (jsx-a11y recommended at error, `--max-warnings=0`) wired into CI `web-build`; real defects fixed, not silenced |

**R17 note — axe is an oracle for detectable defects, not for conformance.** That
is why R18 is a separate Attested gate, and why R17 is proven by four specs across
all five obligations (above), not axe alone. The exploratory axe pass found and
this slice fixed real defects: a critical `aria-pressed` on a link, keyboard-inaccessible
scroll regions, a page-inflating off-screen skip-link, two mobile horizontal
overflows (identity-header grid, evidence rows), and three contrast failures
(muted-grey text, quote amber, and the illegible bright-orange validation error).
The broadened R17 suite then surfaced three more, also fixed minimally: the skip link
scrolled but did **not** move focus (added `tabIndex={-1}` to `<main>` so activating
it lands focus in the landmark); the lead-dialog close button measured 22px wide
(min-size raised to the 24×24 AA target-size minimum); and the `<footer>` exposed **no**
`contentinfo` landmark because it was rendered inside `<main>` (fixed by *composition*,
not a faked `role`: the shared footer is now rendered once by `RootLayout` as a sibling
of `<main>`, and the per-page instances were removed — `semantics.spec.ts` asserts
exactly one `contentinfo` per route). Every fix was a minimal markup/composition
correction — **UI-D1 layout and type are unchanged** (the footer renders identically,
same place, same styles); the palette's muted/amber/signal semantics are preserved,
only their exact lightness meets AA.

**R17 — robot-detail navigation is an intentional UI-D1 variance (not a WCAG
waiver).** The every-route semantic suite makes explicit that `/robots/[slug]` is
the only public route without a primary-nav landmark: it renders its frozen dark
identity header (`idhead`) and does not repeat `SiteNav`, whereas the sibling detail
pages (`/manufacturers/[slug]`, `/use-cases/[slug]`) do. This is **conformant**:
WCAG 2.2 SC 3.2.3 (Consistent Navigation) governs the relative *order* of navigation
mechanisms **when they are repeated** — it does not require the same navigation on
every page. `e2e/semantics.spec.ts` asserts the absence on robot detail (locking the
variance so it cannot drift accidentally) and, separately, that the nav which *is*
repeated appears identically named on every browse surface. Recorded as a deliberate
UI-D1 composition variance, decided by the design owner; **no `DarkNav` added in WS8.4.**

*Separately, manual R18 testing exposed a genuine **navigation/discoverability** weakness
(distinct from the WCAG question): once on a robot record there was no visible return path
to home or the catalogue. Fixed with the **smallest** UI-D1-preserving escape — a two-link
breadcrumb `HumanoidOnline / Robot Catalogue` (→ `/` and `/robots`) inside the dark identity
header, deliberately **not** wrapped in `<nav>` and **not** the full `SiteNav`, so the
no-primary-nav variance holds exactly (the absence assertion still passes: zero navigation
landmarks on robot detail). `semantics.spec.ts` asserts both escape links exist with
meaningful accessible names ("HumanoidOnline home", "Robot Catalogue") and correct targets;
the links use `--ho-paper-ink` on `--ho-ink` (AA) and pass axe contrast + target-size.*

**R21 note — narrow, documented exceptions only.** One `eslint-disable-next-line`
(the lead-dialog backdrop pointer-dismiss, redundant with Escape + a labelled Close
button) and one precise rule *config* (`no-noninteractive-tabindex` allows the
labelled scroll-region pattern that WCAG 2.1.1 requires and axe enforces). No
a11y rule is blanket-disabled to get green.

## 5. WS8.3 gate status

| Gate | Class | Status | Evidence |
|---|---|---|---|
| R11 MEDIA-01 | Automated | **PASS** | Full 16-cell matrix; the dead SQL twin removed so exactly one eligibility implementation exists; `hero_image_url` bypass closed (Q6) and proven by injection; ATTRIBUTION_REQUIRED without a credit is now ineligible (Q14) |
| R12 DATA-D1 | Automated | **PASS** | Candidate data absent from real **response bodies**, proven with planted sentinels rather than route-name matching (Q7); promotion docs corrected to name only implemented gates (Q8a); P3/P5/P7 remain deferred and a test holds them out |
| R13 no live crawling | Automated | **PASS** | No HTTP client reachable from the discovery adapter; `FixtureAdapter` is the only concrete adapter; a public request sweep runs with `socket.create_connection` made fatal |
| R14 AGENT-01 | Automated | **PASS** | Unpublished entities absent from every public surface, from matching and from lead capture, proven by injection (Q9); JSON-LD coercion gap closed (Q12) with `0` deliberately retained; provenance never fabricated |
| R15 whole-surface truth | Automated | **PASS** | Price trichotomy across the whole catalogue; three dimensions never collapsed; G2 asserted against the live database; evidence carries provenance |

**R11 note — `hero_image_url` is gated, not removed.** The column is in the frozen
API contract, so it keeps its nullable shape; it may now only carry a URL that a
display-eligible image also carries, and serializes as `null` otherwise. MEDIA-01
is the single authority on which imagery crosses the boundary.

**R11 note — attribution is a rights OBLIGATION, not a fourth dimension.** MEDIA-01
has three independent dimensions (identity / rights / usage). `attribution` is the
credit line owed by the `ATTRIBUTION_REQUIRED` rights state, and that obligation is
**not** overridable by `usage_basis`: a display policy cannot waive a known
licensing condition. So `VERIFIED + ATTRIBUTION_REQUIRED + OFFICIAL_MANUFACTURER_MEDIA
+ no attribution → IMAGE_UNAVAILABLE`. (Official media of genuinely unknown licence
is modelled as `rights_status=UNKNOWN` + `usage=OFFICIAL_MANUFACTURER_MEDIA`, so no
attribution licence is ever falsely asserted.) Verified against the real catalogue:
**7/7 images still display**, and Figure 02 (`ATTRIBUTION_REQUIRED`) keeps its
`© Figure AI` credit — the rule tightens the gate without dropping a cleared image.

**R14 note — a genuine `0` is kept on purpose.** Omitting it would be the exact
mirror of coercing UNKNOWN into `0`. UNKNOWN is `null` and is omitted; `0` and
`false` are real canonical values and are asserted. Both halves are pinned.

## 6. WS8.2 gate status

| Gate | Class | Status | Evidence |
|---|---|---|---|
| R7 fail-closed production configuration | Automated | **PASS** | `test_config_contract.py` — 14 tests. B3 closed (production/staging refuse to start without `DATABASE_URL`; the development URL is unreachable in a strict env). B4 closed (`siteUrl()` refuses to invent an origin). The classifier is the adversarial part: unset/empty/whitespace resolve to **production**, and a typo raises — nothing can be misclassified as development |
| R8 canonical-origin correctness | Automated | **PASS** | `__tests__/site-origin.test.ts` — 12 tests. One authoritative resolver (`lib/site.ts`); JSON-LD, sitemap, robots.txt and llms.txt all proven to emit a staging origin and **never** the production hostname; `next.config.mjs` build guard pinned to the same rule |
| R9 migration integrity | Automated | **PASS** | `test_migration_integrity.py` — 13 tests. `db/bootstrap.py` now compares the recorded sha256 and refuses on drift (exit 1); `app/db/migration_state.py` enforces migration-before-app-start, strict environments refusing to serve. Baseline is presence-only by design (below) |
| R10 one bootstrap truth | **Automated** | **PASS** | `test_bootstrap_docs.py` — 9 tests (bypass commands absent from governed docs, bootstrap named canonical, every migration documented, doctrine stated, no second runner). Supplementary sweep: `README.md` divergent `psql -f` path removed and replaced with an explicit warning; `apps/web`, `apps/api` and `db/catalogue` READMEs reworded to `db/bootstrap.py`; migration `0003` documented plus a checksum-integrity section |

**R9 design note — the baseline is deliberately exempt from checksum comparison.**
`db/schema.sql` is canonical and is *edited* whenever the model changes ("schema
wins", then a forward migration lets existing databases converge — see
`db/migrations/README.md`). Its hash therefore differs legitimately from what any
older database recorded. Verifying it would declare every pre-existing
environment corrupt and, because bootstrap now refuses on drift, would block the
very migrations meant to bring it up to date. **Forward migrations are the
immutable history that is verified.** Both implementations are pinned to this by
`test_baseline_checksum_is_exempt_on_both_sides`.

**R9 design note — a database *ahead* of the build is not an error.** An applied
migration this build does not know about is the normal state during an
application rollback: version B applied `0004`, B proved defective, the operator
rolled the code back to A. Treating that as fatal would make A refuse to start —
wiring shut the very rollback WS8-L7 guarantees. `ahead` is therefore reported
loudly and excluded from the blocking check; `missing` and `drifted` remain
fatal. L7's additive/backward-compatible rule is what makes the older build able
to serve the newer schema.

**Deployment note carried to WS8.7.** `enforce_migration_state_at_startup` defines
the contract; the mechanism guaranteeing migrations have *run* before the process
starts (release phase, init container, deploy step) is R25/R26's. The app also
expects the governed migration files to be reachable (`MIGRATIONS_DIR`), which is
a binding point for whatever packaging WS8.7 chooses.

## 7. WS8.1 gate status

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

### Carried to the deployment gates (R27 / R29)

| Item | Why it is not WS8.1 | Owed by |
|---|---|---|
| **Admin session-cookie attributes.** The SQLAdmin session cookie must be proven to carry the intended production attributes (`Secure`, `HttpOnly`, `SameSite`) rather than inheriting Starlette defaults — `Secure` in particular is opt-in and only meaningful once TLS terminates at the ingress. | Redesigning the admin auth mechanism is outside the authorized WS8.1 scope, and the attribute that matters most (`Secure`) cannot be asserted without a deployed HTTPS surface. | **R27** (configuration) + **R29** (deployed assertion) |

## 8. Registered gaps still open (`12` §8)

Carried forward so nothing is lost between slices. `CLOSED` here means the gate
that owns it has passed.

| Gap | Disposition | Owing slice | Status |
|---|---|---|---|
| B1 `/admin` unauthenticated | CLOSE | WS8.1 → WS8.7 → WS8.8 | **stage 1 CLOSED**, stages 2–3 open |
| B2 no abuse control / unstated posture | CLOSE | WS8.1 → WS8.8 | **pre-deployment CLOSED** (fail-closed: no disable switch, unknown policy refuses, malformed ingress config refuses to boot), deployed probe open |
| B3 `DATABASE_URL` dev default | CLOSE | WS8.2 | **CLOSED** |
| B4 `NEXT_PUBLIC_SITE_URL` prod default | CLOSE | WS8.2 | **CLOSED** |
| B5 audit not append-only | CLOSE | WS8.1 | **CLOSED** |
| D5a checksum never compared | CLOSE | WS8.2 | **CLOSED** (R9) |
| D6 divergent README bootstrap | CLOSE | WS8.2 | **CLOSED** (R10) |
| D7 migration `0003` undocumented | CLOSE | WS8.2 | **CLOSED** (R10) |
| D9 no app logging / error / metrics / correlation | CLOSE | WS8.6 | **CLOSED** (R25 — structured JSON request log + `X-Request-ID` correlation across Next↔FastAPI incl. **2xx/4xx/5xx**; **no PII proven over the COMPLETE uvicorn log stream** by a production probe. An unhandled 500 is sanitized in-middleware — generic body, message-free location-only stack, correlation id preserved — instead of letting the framework emit the PII-bearing traceback; uvicorn access log silenced in prod. `/health` + `/ready` preserved and correlated) |
| D1–D4 deployment gaps | CLOSE | WS8.7 | artifacts prepared (Dockerfiles, `docker-compose.prod.yml`, `deploy/Caddyfile`, `.env.production.example`); **open until deployed + attested** |
| R26 deployment shape / DEP bound | **Attested** | WS8.7 | **PENDING DEPLOYMENT / ATTESTATION** — checklist `docs/15_WS8_7_DEPLOYMENT_ATTESTATION.md`; repo-side config asserted by `tests/test_deployment_config.py`, `tests/test_preflight.py` (**digest FORM enforced** by `deploy/preflight.py`, run before any pull/build/up by the supported path `deploy/release.sh` — required-ness alone only proves non-empty) and `tests/test_backup.py` (dump runs **inside** the pinned `db` container over `compose exec`, no credential in any argument, 0700/0600, atomic promotion, container-side `pg_restore` into a scratch database). Public `/health` is served through a separate un-health-checked proxy path so liveness survives a dependency outage. Final pre-Ready hardening adds `tests/test_release_gates.py`: the release refuses to build or start unless **RELEASE_SHA is a full 40-hex id equal to a CLEAN `git rev-parse HEAD`** (staged / modified / non-ignored-untracked all refused; detached HEAD allowed) and the **off-box backup destination resolves** (executable on PATH, compose/env paths readable — never executed); and it writes a durable **release manifest** (`deploy/release_manifest.py`, `0600` outside the repo: schema version, SHA, four pins, both tags, both exact image IDs) which `deploy/rollback.sh` consumes — **no build, no pull**, refusing a missing image or a moved tag. Capability ≠ realized compliance; a named human operator must complete the record against the physical VPS |
| R27 admin boundary realized | **Attested** | WS8.7 | **PENDING DEPLOYMENT / ATTESTATION** — same checklist; externally re-proven at R29 (WS8.8) |
| D8 `event_log` dead | NOT A RELEASE DEFECT | — | **documented dormant** (R25 — model docstring + no application writer proven + zero-write regression) |
| R24 performance | CLOSE | WS8.6 | **CLOSED** — deterministic bundle budgets (`scripts/perf-budget.mjs`, gzipped First Load JS in CI) **+** built-route budget (`e2e/perf-budget.spec.ts`: document bytes / JS asset count+size vs the fixed catalogue). No timing/LCP thresholds; field CWV is post-release SLO (§11.1) |
| D10 scheduled re-verification | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
| Q5 dead SQL clause + 9/16 matrix | CLOSE | WS8.3 | **CLOSED** |
| Q6 `hero_image_url` bypass | CLOSE | WS8.3 | **CLOSED** |
| Q7 route-path-only isolation test | CLOSE | WS8.3 | **CLOSED** |
| Q8a promotion docs overstate gates | CLOSE | WS8.3 | **CLOSED** |
| Q9 no unpublished-absence test | CLOSE | WS8.3 | **CLOSED** |
| Q12 JSON-LD coercion gap | CLOSE | WS8.3 | **CLOSED** |
| Q14 attribution not enforced | CLOSE | WS8.3 | **CLOSED** |
| Q1 no a11y tooling | CLOSE | WS8.4 | **CLOSED** (axe + jsx-a11y) |
| Q2 single chromium project | CLOSE | WS8.4 | **CLOSED** (Pixel-7 mobile project in CI) |
| Q4 no web lint | CLOSE | WS8.4 | **CLOSED** (ESLint + jsx-a11y in CI) |
| Q3a no generateMetadata | CLOSE | WS8.5 | open |
| Q10, Q11, Q13 | CLOSE | WS8.5 | open |
| Q3b OG/Twitter imagery | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
| Q8b DATA-D1 P3/P5/P7 gates | ACCEPT-DEFER | product owner | runbook entry at R30 (open) |
