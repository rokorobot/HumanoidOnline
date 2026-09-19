# CI / deployment watcher v1

Purpose: replace manual follow-up after CI and merges with one commit-specific,
read-only observation report. Runs in existing GitHub Actions; no server, model,
database access, application dependency installation, or new public endpoint.

## Behavior

- After each `CI` workflow completes, including reruns, the watcher reads that run
  and the jobs from its latest attempt. Post-job cleanup failures are failures.
- A PR/non-production run produces a **CI-only** report. It never claims the
  existing production site validates the PR. Preview-deployment checks are not
  part of v1.
- For a `push` CI run on `main`, verify CI and that `main` still equals the exact
  observed SHA, then verify all three production targets:
  - Netlify: configured site ID and primary HTTPS origin; `published_deploy`
    must have the full matching `commit_ref`, production context, ready state.
    A successful build that was never published is insufficient.
  - Vercel API and web projects: resolve each configured production alias,
    verify the project ID, then inspect its actual deployment. Require the
    matching full Git SHA, production target and READY state. A generic GitHub
    Vercel success status alone is insufficient.
- After identity passes, GET API `/health` and `/ready` and check their JSON
  values; GET web `/`, `/robots`, `/manufacturers`, `/find-a-humanoid` and require
  HTTP 200, HTML content type, and the Humanoid marker. This is a basic smoke
  check, not a browser journey or a full catalogue/schema validation.
- Recheck deployment pointers and `main` after probing. The report is an
  observation over this interval, not an atomic guarantee across providers.
- Wait up to 15 minutes, polling every 30 seconds. Each request has a timeout,
  redirects are rejected, response size and pagination are bounded. Partial
  evidence is written after every polling round. Workflow timeout is 20 minutes.
- Produce an Actions job summary and a 14-day JSON/Markdown artifact. No PR
  comments, email, Slack messages, reruns, merges, deployments, rollbacks,
  migration execution, catalogue imports or publication changes occur.

## Results

| Result | Meaning |
|---|---|
| PASS | All checks for the explicitly stated scope passed. PR scope is CI only. |
| FAIL | CI/job or the observed deployment reports failure/cancellation. |
| UNVERIFIED | Missing configuration/credentials, authorization failure, malformed or missing identity evidence. |
| TIMEOUT | A pending state did not resolve: old deployment still live, provider/network unavailable, unhealthy endpoint, or CI still running. |
| SUPERSEDED | `main` advanced; this historical commit is not certified live. |

Every result other than PASS returns a nonzero exit code. A red observer can mean
missing evidence, not a production outage; read the report. A deployment that
fails before replacing the old published deployment may appear as TIMEOUT while
the old commit remains live. The exact provider failure can be investigated
separately. No automatic remediation is authorized by this observer.

## One-time configuration

In the repository's Actions secrets/variables settings, configure the following.
Do not paste tokens into chats, source files, reports, command arguments or logs.
Use the narrowest provider access available for these projects. The observer
only performs GETs even if a provider credential itself permits broader actions.

| Type | Name | Value |
|---|---|---|
| Secret | `WATCHER_NETLIFY_TOKEN` | Token allowed to read the production site. |
| Secret | `WATCHER_VERCEL_TOKEN` | Token allowed to read both Vercel projects. |
| Variable | `WATCHER_NETLIFY_SITE_ID` | Production Netlify site UUID (not the display name). |
| Variable | `WATCHER_WEB_ORIGIN` | Primary Netlify HTTPS origin; defaults to `https://humanoidonline.com`. Must match site `ssl_url`; no redirects. |
| Variable | `WATCHER_API_ORIGIN` | Actual API HTTPS origin, exactly matching the Vercel API alias below. |
| Variable | `WATCHER_VERCEL_TEAM_ID` | Team ID if needed by the Vercel account. |
| Variable | `WATCHER_VERCEL_API_PROJECT_ID` | Project ID for `humanoidonline-api`. |
| Variable | `WATCHER_VERCEL_API_ALIAS` | Stable API production hostname, without `https://` or a path. |
| Variable | `WATCHER_VERCEL_WEB_PROJECT_ID` | Project ID for `humanoid-online`. |
| Variable | `WATCHER_VERCEL_WEB_ALIAS` | Stable production hostname for that Vercel project. |

Both Vercel projects are included because the inspected merge commit had success
statuses for `Vercel – humanoidonline-api` and `Vercel – humanoid-online`.
The public website remains the configured Netlify origin. Provider IDs and
aliases must be checked against the actual account before activation; none are
guessed from project names.

GitHub supplies `GITHUB_TOKEN` with only `contents: read` and `actions: read`.
Provider credentials are sent only to the exact provider API host, never to live
site probes. Reports contain selected identity/status fields, not raw provider
responses, environment dumps, job logs, or response bodies.

## Activation and owner gates

Implementation is prepared on `feat/ci-deployment-watcher`, based on
`0440df4bfd7e88456cbe7e193b537cbe0d94d39d`. Follow Robert's WorkOrder process:
report changes before committing, explicit-path staging, Draft PR, no merge
without owner authorization.

1. Review and commit the four scoped files, open a Draft PR, pass existing CI and
   the observer's test job. No provider secrets are exposed to that PR test job.
2. Configure provider secrets and variables through repository settings.
3. Merge only after owner approval. `workflow_run` requires the workflow on the
   default branch, so the automation is not active merely because files exist
   locally or on a feature branch.
4. Observe the merge CI completion. The first production report must verify
   provider identity and live health with the real configured accounts before
   calling the watcher operational.

Reports are available under **Actions → Deployment watcher → run summary** and
the run's `deployment-observation-*` artifact. V1 does not promise delivery to
ChatGPT. GitHub's own notification behavior depends on the user's settings.

To repeat an observation manually, use **Run workflow** on `main` and enter an
existing CI run ID. This observes the run; it does not rerun CI. Manual observation
from other branches is disabled. All `workflow_run` observer code is checked out
from trusted `main`, never from the observed PR head; upstream artifacts and PR
code are not consumed by the privileged observer job.

## Local verification

```sh
python -m unittest discover -s scripts -p 'test_deployment_watcher.py' -v
python scripts/deployment_watcher.py --run-id 34782373044 \
  --sha 0440df4bfd7e88456cbe7e193b537cbe0d94d39d --timeout 45
```

The historical run above is a reference, not a fixed production target. Without
provider configuration it must not produce a production PASS. Local reports go
to ignored `var/deployment-watcher/`. Use environment variables for credentials.

Tests cover exact SHA/workflow/repository matching, cleanup failures,
latest-attempt job pagination, missing provider configuration, wrong
site/project/origin, preview-vs-production separation, stale deployments,
conflicting metadata, changes during probes, readiness/content failures,
bounded polling, report output, token routing and redirect rejection.

### Implementation verification — 2026-09-19

- 27 focused tests passed under Python 3.12.
- Workflow YAML parsed successfully; staged whitespace check passed.
- Read-only execution against run `34782373044` verified all seven CI jobs and
  current `main` at `0440df4`. Overall result was correctly **UNVERIFIED** because
  provider credentials/IDs/aliases are not configured in this environment.
- Provider adapters are fixture-tested, not yet validated against authenticated
  Netlify/Vercel accounts. The workflow has not run in GitHub Actions, and no
  changes have been committed, pushed, merged or activated during preparation.

## API references used

- [GitHub workflow_run and security boundary](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- [GitHub workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs)
- [Netlify API: sites and published_deploy](https://open-api.netlify.com/)
- [Vercel alias lookup](https://vercel.com/docs/rest-api/aliases/get-an-alias)
- [Vercel deployment identity](https://vercel.com/docs/rest-api/deployments/get-a-deployment-by-id-or-url)
