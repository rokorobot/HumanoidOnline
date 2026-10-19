# Catalogue promotion automation: design (Workstream B)

**Status: DESIGN + implementation in a draft PR. Not activated, and no executor is installed.**
It builds on PR A (the stable-ID importer). Owner decision D5
(`AUTOMATED_COMMERCIAL_INTELLIGENCE_PIPELINE_2026-10-19.md`) gives GitHub Actions no production
write access. The executor is therefore code only:
- the CLI `promotion execute`;
- its draft workflow and role, kept in `promotion_executor_proposal/`;
- the permissions and recovery proposal, in `PROMOTION_EXECUTOR_SECURITY_PROPOSAL_2026-10-19.md`.

The CI `promotion verify` step, which gates PRs carrying a manifest, is installed. Where this
document says "the workflow", read "the executor, once D5 is decided".

## 1. Flow and the single approval

```
discovery (existing A4 adapters) -> candidate_claim rows (existing)
  -> `promotion propose`  (operator, read-only on production)
       writes: db/catalogue/promotions/<id>.json   (the pinned manifest)
               db/catalogue/promotions/<id>.md     (review, rendered from the manifest)
               the catalogue edit itself           (applied deterministically from the manifest)
  -> draft PR -> CI `promotion verify` (digest, scope, classification, catalogue diff == manifest)
  -> OWNER APPROVAL = merging that PR into protected `main`   <- the one approval
  -> workflow `catalogue-promotion.yml` (push to main touching db/catalogue/promotions/**)
       runs `promotion execute` (fail-closed gates, section 4), then posts the receipt
```

- **Pinned approval.** The approval binds to the manifest's `digest` and to the merge commit.
  - The digest is a sha256 over the canonical JSON of the manifest without its `digest` field.
  - `execute` re-verifies the digest, verifies that `main@<sha>` contains exactly that manifest,
    and verifies that the catalogue files at that commit equal "base catalogue + manifest
    changes".
  - Anything else (edited after merge, a different commit, extra catalogue edits) refuses.
- **Reject or defer.** Close the PR with label `promotion:rejected` or `promotion:deferred` and a
  comment giving the reason. The decision is durable in GitHub history.
  - `promotion propose` refuses to re-propose a claim id that a closed `promotion:rejected` PR
    carries, unless `--reconsider` is passed.
  - It does so by reading a committed decisions log, `db/catalogue/promotions/decisions.json`,
    which the rejecting PR comment workflow appends to.
  - v1 keeps this as a CLI step (`promotion decide`), committed through a normal PR.

## 2. The manifest (version 1)

```json
{
  "manifest_version": 1,
  "promotion_id": "2026-10-19-unitree-g1-compute",
  "digest": "<sha256>",
  "base": {
    "catalogue_commit": "<sha of main the proposal was built on>",
    "robot_fingerprints": {"unitree-g1": "<sha256 of the robot's id-free preflight rows>"}
  },
  "scope": {"robots": ["unitree-g1"], "allowed_tables": ["specification"]},
  "items": [
    {
      "robot": "unitree-g1",
      "edition": "G1",
      "variant_slug": null,
      "field": "extended_specs.compute_base",
      "definition": "compute_base",
      "unit": null,
      "existing_value": null,
      "proposed_value": "8-core high-performance CPU",
      "interpretation": "Onboard base computer as stated by Unitree for the G1 (base) edition",
      "claim_id": "93b8f345-...",
      "claim_field_key": "unitree.spec[G1]/Electrical Characteristics/Basic Computing Power",
      "source_url": "https://www.unitree.com/g1/",
      "observed_at": "2026-10-18",
      "content_hash": "<fetched_page.content_hash>",
      "evidence_locator": "spec table row 'Basic Computing Power', column G1",
      "evidence_class": "MANUFACTURER",
      "confidence": "HIGH",
      "classification": "ROUTINE",
      "conflict": "NONE",
      "expected_change": {"table": "specification", "kind": "ADDED",
                          "match": {"robot": "unitree-g1", "definition": "compute_base"}},
      "display": "Robot detail spec table: 'Onboard computer: 8-core high-performance CPU', with source"
    }
  ],
  "restricted_impact": {"prices": 0, "availability": 0, "publication": 0,
                        "commercial_status": 0, "images": 0, "deletions": 0,
                        "unrelated_robots": 0}
}
```

The preflight expected-change manifest is **derived** from `items[].expected_change`. It is never
hand-written, so the review and the gate cannot disagree.

## 3. Validation and classification (`promotion propose` / `verify`)

Each check is a pure function over (claim row, page row, source row, catalogue JSON, spec
definitions). Each one either passes or yields a reason.

| # | Check | Fails as |
|---|---|---|
| 1 | Claim's candidate is MATCHED_EXISTING to exactly this robot (identity and generation) | REVIEW_REQUIRED |
| 2 | Edition named in the field key (`[G1]`) is the robot's own edition: an explicit edition→robot map in the manifest, never inferred from family names | REVIEW_REQUIRED |
| 3 | Source is enabled and eligible (ToS ALLOWED or OWNER_AUTHORIZED; robots not disallowed) | REVIEW_REQUIRED |
| 4 | Claim has a fetched page with a content hash and observation time (immutable observation) | REVIEW_REQUIRED |
| 5 | Value normalizes under the definition's `value_type`/`unit`; a non-value ("/", "-", "") is UNKNOWN, never 0 or false | REVIEW_REQUIRED (no item for UNKNOWN) |
| 6 | Catalogue has no value for this field (addition). An existing different value is a change | REVIEW_REQUIRED |
| 7 | No other active claim for the same field disagrees | REVIEW_REQUIRED (`conflict`) |
| 8 | A spec definition exists for the field. A new definition is new semantics | REVIEW_REQUIRED |
| 9 | Observation is within the freshness window (default 30 days) | REVIEW_REQUIRED |
| 10 | Target is not price, availability, publication, commercial status, image/rights, evidence withdrawal or deletion | RESTRICTED |

`ROUTINE` means every check passes and the item is an addition. Only an all-ROUTINE manifest may
use the fast lane; `verify` refuses to mark a manifest executable otherwise. A disputed claim is
never promoted automatically.

## 4. `promotion execute` (after merge), fail-closed in this order

1. **Manifest.** Digest, commit and catalogue-diff verification (section 1). `manifest_version`
   must be supported. Every item must name a published `compare_peer` (public verification
   needs one), found here, never after a write.
1b. **Approval (`approval`).** `--approved-pr N` is required. PR N must be merged, its base
   `main`, `merge_commit_sha` equal to `--commit`, `merged_by` in the allowlist
   `PROMOTION_APPROVERS` (unset or empty = REFUSED, never open), and its changed files exactly
   the manifest `.json`, its `.md` review and the scoped robot JSON file(s). The manifest read
   with `git show <commit>:<path>` must equal the manifest being executed (same digest). Any
   API error = REFUSED. The receipt records PR number, head sha, merge sha and merger.
   `--no-github` does not bypass this; a local pilot (`--local-branches --no-github`) records
   `approval: SIMULATED_LOCAL`.
2. **Halt switch.** Refuse if an open GitHub issue carries label `promotion-incident`. A
   post-commit failure opens one, which stops every later promotion until the owner closes it.
3. **Concurrency.** The workflow concurrency group `catalogue-promotion` (no cancel). Inside the
   database, `pg_try_advisory_lock(hashtext('catalogue-promotion'))`. Refuse if a discovery
   `crawl_run` is RUNNING.
3b. **Privileges (`privileges`).** On the production connection: refuse if the role is a
   superuser, a member of `neon_superuser`, owns any humanoid table, has UPDATE / DELETE /
   TRUNCATE on any, or lacks INSERT on `specification` / `evidence_source`. ROUTINE is additions
   only, so its role (`catalogue_promoter_routine`) has INSERT only. The result is in the receipt.
4. **Already applied?** If production already shows every item's post-state (the rows and
   values exist exactly) and the base fingerprints do not match, the run ends as
   `ALREADY_APPLIED` with a receipt and no write. An identical manifest never applies twice.
4b. **Eligibility (`eligibility`).** The manifest's own classification is not trusted (its digest
   proves integrity, not eligibility). Each item is re-derived read-only from production with
   `propose` against the base catalogue; every item must still be ROUTINE with no conflict and
   equal on robot, definition, variant, value, claim value, source URL, observation date and
   content hash. A source disabled, a claim now in conflict, a changed page hash or a stale
   observation refuses as `REFUSED:eligibility`.
5. **Baseline.** Production's per-robot fingerprint equals `base.robot_fingerprints`. Otherwise
   refuse as `BASE_DRIFT`: production changed since review, so a new review is needed. The
   gates read every table except the explicit, symmetric `exclude_tables` (the lead / buyer
   tables, recorded in the receipt); any other unreadable table fails closed.
6. **Safety point.** Create a Neon branch `promo-<id>-<utc>` from `production`, with an explicit
   `parent_id` (`NEON_PRODUCTION_BRANCH_ID`). Before the first create the parent is verified to
   exist, be the default branch, be named `production`, and own the endpoint of the production
   URL; each response's `parent_id` must equal it. Parent id and LSN are in the receipt (a local
   pilot checks the template database is the production database). It is retained; cleanup is
   an owner decision. Any mismatch or failure refuses.
7. **Rehearsal.** Create a second branch, `rehearse-<id>-<utc>`, and import the scoped robots
   there.
   - `import_preflight.py --manifest <derived>` against the safety branch must PASS (no
     unexpected change, no missing expected change).
   - `import_identity_check.py` must PASS: no ID_CHANGED, no AMBIGUOUS, no lost audit target,
     and ADDED equal to the manifest's additions.
   - The rehearsal branch is deleted after the run.
8. **Apply.** Scoped `import_catalogue.py --only <robots>` against production. One transaction;
   no `--authorize`, so the fast lane cannot delete. Every importer run first takes
   `pg_advisory_xact_lock(hashtext('catalogue-write'))`; the executor's `before_write` hook then
   recomputes the scoped fingerprints inside that transaction, before the first write, and
   refuses (nothing written) if they differ from the manifest base.
9. **Post-verify (production vs safety branch).**
   - Repeat the same preflight and identity check. They must equal the rehearsal results
     exactly.
   - Publication and commercial status are unchanged.
   - The number of dangling audit targets has not grown.
10. **Public verification**, with bounded retries: up to 12 × 60 s, covering the API's 300 s
    cache. For each item:
    - the API `/api/robots/<slug>` returns the value, unit and source;
    - the API entry matches key, variant, value, unit, `source_url` and `observed_at`;
    - the published page `/robots/<slug>` has the value inside the spec row of that definition's
      label (`div.srow`), with the source link (`href` = source URL) or source label in the same
      row;
    - `/compare?ids=<slug>,<peer>` has the value in this robot's cell of that label's row
      (`tr` / `th.rowlab` / `td`). **Known gap:** the web compare matrix renders only the fixed
      `COMPARE_FIELDS`, not extended specs, so this check cannot pass until the web renders them
      or compare is dropped from the gating set (owner decision before any real run).
    - A catalogue-only change needs no deployment. If the manifest declares
      `requires_deploy`, it waits for the normal deploy gates first.
11. **Receipt.** The receipt JSON records:
    - manifest id, digest and commit;
    - robots and fields;
    - preflight and identity reports, before/after fingerprints and the safety branch;
    - API and page checks, timings, and any deferred items.

    It is uploaded as an artifact and posted as a comment on the merged PR, which makes it
    durable.

**Failures:**
- Steps 1–7 write nothing to production.
- Step 8 rolls back on any exception.
- A failure at step 9 or 10 opens the `promotion-incident` issue with the reports and keeps the
  safety branch.
- There is **no automatic rollback**. Restoring from the safety branch could overwrite
  concurrent legitimate changes, so recovery is an owner decision with the receipt in hand.
- A retry of a failed run is safe: step 4 (already applied) or step 5 (drift) decides.

## 5. Credentials and least privilege

| Secret / variable | Purpose | Scope |
|---|---|---|
| `CATALOGUE_PROMOTION_ENABLED` (repo variable) | master switch; unset = the workflow does nothing | — |
| environment `catalogue-production` | holds the secrets; restricted to `main` | — |
| `CATALOGUE_DATABASE_URL` | production write for the importer | role `catalogue_importer` (proposed `db/roles/catalogue_importer.sql`: DML on catalogue tables only, no DDL, no discovery/lead tables); **creating it is an owner action** |
| `NEON_API_KEY`, `NEON_PROJECT_ID` | branch create/delete only | a project-scoped Neon API key |
| `GITHUB_TOKEN` | PR comment, incident issue | `pull-requests: write`, `issues: write`, `contents: read` |

Connection strings are never echoed. Errors print the exception type only, as the existing CLIs
already do.

**Follow-up (not done): app writers outside the importer are not serialised by the
`catalogue-write` lock.** `apps/api/app/admin_ops.py` is read-only (nothing to lock);
`apps/api/app/services/discovery/materialize.py` only appends a `catalogue_write_audit` row in
`verify_applied` and edits catalogue JSON files, so the lock is not an obvious two-line change
there. The in-transaction fingerprint recheck covers a concurrent catalogue write; locking those
writers is a follow-up.

## 6. Owner decisions before activation

1. Merge and deploy PR A (the importer), then rehearse this workflow's dry-run mode on the
   production copy.
2. Create the `catalogue_importer` role, the Neon API key and the `catalogue-production`
   environment.
3. Set `CATALOGUE_PROMOTION_ENABLED=true`.
4. Branch protection on `main`: the merge is the approval, so a required review by the owner
   should be enforced.
5. Optional migration, a durable `catalogue_promotion_receipt` table. v1 does not need it,
   because step 4 makes re-application idempotent from the data itself.
