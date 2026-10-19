# Promotion executor: security and permissions proposal

**Status: PROPOSAL, for owner decision D5.** Nothing here is authorized. GitHub Actions has **no**
production write access. No role, API key, environment or workflow has been created. The draft
workflow and role SQL are in `promotion_executor_proposal/`, outside `.github/workflows` and
`db/roles`, so nothing runs or applies them.

## What needs credentials

`python -m app.cli.promotion execute` (in `apps/api/app/services/discovery/promotion_execute.py`)
is executor-agnostic. It needs four things:
1. **Production database:** read, plus one transactional write through the importer.
2. **Branching:** create a safety branch and a rehearsal branch.
3. **Public read:** HTTPS GET of the API and the site.
4. **Reporting:** post the receipt, and open or read the halt issue.

## Options

| | Executor | Production write credential | Pros | Cons |
|---|---|---|---|---|
| **E1** | GitHub Actions job in environment `catalogue-production`, required reviewer = owner, `main` only | password of a dedicated `catalogue_importer` role in an environment secret | no local machine; full log; approval gate native to GitHub | the credential sits in GitHub; needs D5 approval |
| **E2** | Same job, but the environment requires a **second** reviewer click per run | same | the owner sees each run before the write | a second click, so not literally "one approval" |
| **E3** | An owner-run local command (`promotion execute`) after merge | owner's existing access | no new credential anywhere | the owner's machine must be online; one manual command |
| **E4** | A small cloud job (e.g. on Vercel or Neon) triggered by a signed webhook | that platform's secret store | keeps the credential out of GitHub | new infrastructure (AGENTS.md rule 4) |

**Recommendation: E1.** It is the only option that meets "one approval, zero manual
commands" without new infrastructure. It requires these controls:
- **`catalogue_importer` role:**
  - DML only on catalogue tables;
  - no DDL;
  - no DELETE except what the importer's authorized removals use.
  - It is created by the owner with plain SQL, like `discovery_observer`, never through the Neon
    console.
  - Its SELECT scope is wide, because the preflight and identity snapshots read every table. A
    narrower variant is listed in the SQL file.
- **Neon API key:** project-scoped, used for branch create and delete only. It never prints a
  connection string.
- **Environment `catalogue-production`:**
  - deployment branch `main` only;
  - secrets visible to this one job;
  - required reviewer: the owner (E1, so the merge plus the environment approval are the same
    person on the same SHA), or none if the protected merge alone is accepted as the approval.
- **Branch protection on `main`:**
  - required owner review for any change under `db/catalogue/promotions/**`, via CODEOWNERS;
  - required CI, including the gating `promotion verify` step;
  - no force-push.
- **Approval provenance:** the executor records in the receipt the merge commit, the PR number,
  the approving reviewer and the timestamp, taken from the GitHub API. It refuses when the PR was
  not approved by the CODEOWNER.
- **Halt switch:** an open issue labelled `promotion-incident` blocks every run. A post-commit
  failure opens one.
- **Never echo secrets:** errors print the exception type only.

## Recovery procedure (tested locally; must be re-tested before activation)

1. A failure before apply leaves production untouched. The receipt says which gate failed.
2. A failure during apply rolls back in the importer's transaction.
3. A failure after commit (post-verify or public check) produces an incident, and the safety
   branch `promo-<id>-<utc>` is retained.
4. The owner compares the receipt's identity and preflight reports.
5. If reverting is right, do the narrowest safe action. Either revert the catalogue commit and
   run a scoped import with an authorized `remove` of the added rows, or restore from the safety
   branch **only** if no concurrent legitimate write happened since; the identity check against
   the safety branch shows this.
6. Close the incident issue to re-enable promotions.

## Activation gates (each needs its own owner approval)

1. PR A merged, then importer rollout:
   - production rehearsal on a fresh restore;
   - Neon safety branch;
   - a scoped pilot import.
2. PR B merged with no workflow installed: the current state.
3. D5 decision on the executor (E1 to E4), then creation of the role, key, environment and
   CODEOWNERS.
4. Move the workflow into `.github/workflows`, gated by `CATALOGUE_PROMOTION_ENABLED`, and run
   one dry run (`workflow_dispatch`, `dry_run: true`).
5. Enable the switch for one real ROUTINE manifest, with the owner watching.
