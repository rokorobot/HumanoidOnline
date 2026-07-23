# HumanoidOnline — MVP v0.1 Acceptance Criteria

**Status:** Binding. MVP v0.1 is complete when every MUST criterion below passes against the seed dataset (`db/seed/seed.sql`). Written Given/When/Then so they translate directly into pytest / frontend tests. The seed dataset is intentionally a stress test: it contains public, quote-only and unknown prices; purchasable, RaaS-only, rental-only, research-only and prototype robots; variants; regional differences; and robots with no confirmed availability.

---

## A. Robot catalogue

- **A1.** Given 20 robots in the database, when a user filters by commercial status `COMMERCIAL`, then only robots with `commercial_status = 'COMMERCIAL'` are returned.
- **A2.** Given robots with and without `pricing_offer` rows, when the catalogue renders, then robots with **no pricing rows** show **"No confirmed pricing"**, robots with a **`QUOTE_ONLY`** offer show **"Price on request"**, and the two states are never conflated; never `$0` or blank. (Unknown price ≠ quote-gated price — different facts.)
- **A3.** Given a robot with no current `availability_offer` rows, when its card renders, then it shows "No confirmed commercial availability" and is NOT labeled "not available".
- **A4.** Given the filter `transaction_type=RENTAL`, when applied, then only robots with a current `availability_offer` of type `RENTAL` (status ≠ `NOT_AVAILABLE`/`DISCONTINUED`) are returned. *(Proves Phase 3 readiness without Phase 3 UI.)*
- **A5.** Given a full-text query matching a robot name, when searched, then the robot is returned via `search_vector` (no external search engine involved).
- **A6.** Given `payload_min=10` filter, then robots with `payload_kg IS NULL` are excluded from the *filtered* result only when the filter is explicitly marked "known values only"; default behavior includes them flagged as unknown. Unknown never counts as 0.

## B. Robot detail

- **B1.** Given the RaaS-only robot in the seed (maturity `RAAS_DEPLOYMENT`, no `PURCHASE` offer, deployment evidence attached), when its page renders, then maturity, obtainability, and deployment evidence appear as three distinct facts and the page does NOT claim the robot can be bought.
- **B2.** Given a price with `price_type=ESTIMATED`, when displayed, then it is visibly marked "Estimated".
- **B3.** Given an evidence record with `confidence=VERIFIED` and `verified_at` set, when the related fact renders, then a "Verified {date}" indicator with the source type is shown; facts without evidence show no such indicator.
- **B3a.** Given an evidence record with `LOW`, `MEDIUM`, or `HIGH` confidence and no `verified_at`, when the related commercial fact renders, then its confidence state is displayed ("Low confidence" / "Medium confidence" / "High confidence") and NO "Verified" indicator appears. The full epistemic ladder `LOW → MEDIUM → HIGH → VERIFIED {date}` must be visually distinguishable (the seed exercises all four states).
- **B4.** Given an unknown slug, when requested, then a 404 state renders with a link back to `/robots`.
- **B5.** Given any robot page, the Commercial Action panel renders exactly one CTA — "Request Availability" — and clicking it leads to lead capture (creates `commercial_lead`). No Rent/Buy/Lease buttons exist in v0.1.

## C. Comparison

- **C1.** Given Robot A and Robot B selected, when `/compare?ids=a,b` renders, then their normalized specifications are shown side-by-side, grouped commercial-first.
- **C2.** Given one robot with a `PUBLIC` price and one `QUOTE_ONLY`, when compared, then the price row shows the number for one and "Quote only" for the other — not blank vs number.
- **C3.** Given fewer than 2 valid ids, then the page prompts for selection instead of erroring.
- **C4.** Given a comparison URL, when shared and reopened, then the same comparison renders (state lives in the URL).

## D. Buyer intent

- **D1.** Given a requirement for logistics use in Germany, when the wizard is submitted, then a `buyer_requirement` record is persisted with `country_region` resolved to `DE` and `raw_input` containing the full answers.
- **D2.** Given a transaction preference "Rent", when submitted, then `preferred_transaction='RENT'` is stored even though no rental product exists. *(Demand intelligence before Phase 3.)*
- **D3.** Given a wizard abandoned before contact capture, then the `buyer_requirement` may exist without any `commercial_lead` (contact is not required to see matches).

## E. Matching engine (pure, deterministic — pytest without DB)

- **E1.** Given a robot with known payload below the buyer's required payload, then that robot is excluded and never ranked.
- **E2.** Given a robot with `payload_kg IS NULL` and a stated payload requirement, then the robot is NOT excluded; it scores neutral-uncertain on technical fit and carries a "payload unverified" warning.
- **E3.** Given identical inputs run twice, then byte-identical `match_result` output (ranks, scores, reasons) is produced. No randomness.
- **E4.** Given two robots with equal scores, then order follows the tie rules (commercial sub-score → deployment evidence count → freshest `verified_at` → slug).
- **E5.** Given a stated budget and a robot with only `QUOTE_ONLY` pricing, then budget scores neutral-uncertain with a "pricing is quote-only" warning — not zero.
- **E6.** Given a submitted requirement, then each returned match's `score` equals the weighted sum in its `score_breakdown` (weights 25/20/20/15/10/10) rounded to an integer, and `reasons` has ≥2 entries.
- **E7.** Given requirements that eliminate all candidates, then the API returns `matches: []` with a `no_match_explanation` naming the dominant eliminating constraint, and the UI still offers lead capture.
- **E8.** Given a `DISCONTINUED` robot matching all requirements, then it is excluded.

## F. Commercial lead

- **F1.** Given a user selects "Request availability" on a robot page or match card and provides an email, then a `commercial_lead` is created with `lead_status='NEW'`, linked `requirement_id` (when originating from matches) and `commercial_lead_robot` rows — **without any transaction checkout**.
- **F2.** Given a created lead, when viewed in admin, then its requirement snapshot, matched robots and status are visible, and status can be advanced along the `lead_status` ladder.
- **F3.** Given a lead, then no payment, checkout, escrow or booking step exists anywhere in the flow.

## G. Data integrity & provenance

- **G1.** Given the seed dataset, when loaded into a fresh database created from `db/schema.sql`, then it loads with zero constraint violations.
- **G2.** Given a commercially sensitive published fact (price / availability / status / deployment), then at least one `evidence_source` row exists for it. The seed satisfies this **by construction** — it ends with a self-check `DO` block that aborts the load if any published fact lacks evidence; admin warns on violations at runtime.
- **G3.** Given any robot, `robot.lowest_purchase_price` (cache) never contradicts `pricing_offer` (source of truth) after offer writes.

## H. Non-goals (must NOT exist — reviewer checks)

No checkout · no rental booking · no financing · no escrow · no leasing underwriting · no fleet management · no robot control/teleoperation · no user community · no news CMS · no marketplace seller dashboard · no microservices · no Kubernetes · no vector database. A PR introducing any of these fails review regardless of quality.
