# HO-DATA-SR-01 — Standing Manufacturer Research Work Order

**Status:** OWNER-RATIFIED 2026-10-22 (product owner, HumanoidOnline project conversation).
This file is the repository record of that decision; recording it does not widen it.
**Authority basis:** [`docs/26`](26_DATA_D1_LIVE_AMENDMENT_A3_AGENT_ASSISTED_RESEARCH.md) (A3,
`AGENT_ASSISTED_RESEARCH`) §2.1, §6A.9, §6A.10. This is an on-demand research work order. It is
**not** an A4 standing source authorization under
[`docs/28`](28_DATA_D1_OWNER_AUTHORIZED_SOURCE_AMENDMENT_A4.md).
**Effective:** 2026-10-22 through 2027-01-19 inclusive (expires 2027-01-20 00:00 Europe/Prague),
unless revoked earlier.
**Reference:** `HO-DATA-SR-01`, version 1.1 (dynamic model scope).
**Operating model:** [`08_DEVELOPMENT_ROADMAP.md`](08_DEVELOPMENT_ROADMAP.md) §1.2 (HO-DATA Fast Lane).

## 1. Authorized — repeated research within this order

1. **Targets.** Missing P0/P1 core and useful manufacturer-stated extended specifications for
   **currently published** catalogue robots and for **every model or edition later added to the
   canonical catalogue** during the term, published or not. New additions join the research scope
   automatically; no per-model research question is asked. The catalogue slug identifies the
   target. A model seen but not yet registered may be researched only far enough to draft an
   identity/evidence proposal; creating or publishing its record is separately governed.
2. **Sources.** Public, manufacturer-controlled first-party product pages, datasheets, manuals,
   developer/SDK documentation and official document hosts relevant to an in-scope model, including
   first-party links discovered while researching one. Distributors, marketplaces, third-party
   mirrors, laboratories and archives are **outside** this order (narrower than what `docs/26` §2.1
   would allow a work order to name).
3. **Trigger.** Repeated **on-demand** batches, started by the owner or by a bounded research run
   that a human invokes. No new work order is needed per batch, model or first-party document.
4. **Actions.** Retrieve and read accessible sources; identify model and exact edition; quote and
   normalize directly supported claims and exact unit conversions; record URLs, dates, excerpts,
   hashes where possible, conflicts, absences and access blocks; produce research reports and
   candidate evidence manifests. Preserve UNKNOWN. Stop on an access block; never circumvent
   authentication, `robots.txt`, CAPTCHAs or other access controls.
5. **Provenance.** Each batch records `HO-DATA-SR-01`, target slug and edition, the record's
   canonical/publication status, retrieval actor, method and date, sources and outcomes, and
   provenance `AGENT_ASSISTED_RESEARCH`. Outcomes are reported as CLEAN, CONFLICT,
   IDENTITY/POLICY BLOCKED, CHECKED_NOT_STATED or RETRIEVAL BLOCKED. Nothing becomes human
   `VERIFIED` or `MANUAL_BOOTSTRAP` through this order (`docs/26` §4, §8).

## 2. Not authorized by this order (PROPOSE ONLY)

- Catalogue commits, promotion PRs, merges, production writes, changes to `is_published`, or
  enabling/scheduling any discovery source. Each is a separate boundary (`docs/26` §6A.10). A
  later owner approval may combine named actions for one exact PR head, manifest and rehearsal;
  only those actions then run, within that scope.
- Unattended or clock-triggered crawling. Standing automation still needs `docs/16` / `docs/28`
  eligibility and enablement on its own.
- Overriding identity or edition conflicts, copying values between variants, guessing
  undisclosed facts, or asserting price, availability or commercial status from technical research.
- Adding source classes beyond §1 item 2 without a new owner decision.

## 3. Production approval retained

**One owner approval per validated production batch**, not per research batch. Each batch is
presented as one exact-head change set with first-party provenance, caveats, expected-change
manifest, passing CI and a production-clone rehearsal (roadmap §1.2, FL-2 to FL-4). Adding a model
to research scope never authorizes its creation, first publication or a change to `is_published`.

## 4. Revocation, expiry and changes

The owner may revoke or narrow this order at any time by an attributed instruction; retrieval stops
at once on revocation or at expiry. New catalogue models do not extend the term. A new order is
required after expiry. Scope changes are appended below, never edited in place.

| Date | Change | By |
|---|---|---|
| 2026-10-22 | Ratified: 90-day revocable order; future catalogue models (incl. unpublished editions) included automatically | Product owner |
