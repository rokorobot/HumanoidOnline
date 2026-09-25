# CI / deployment watcher v1

Purpose: replace manual follow-up after CI and merges with one read-only
observation report per CI run. It runs in existing GitHub Actions: no server, model,
database access, application dependency installation or new public endpoint.

**Default-off.** The observer job runs only when the repository variable
`WATCHER_ENABLED` is exactly `true`. Merging this workflow activates nothing;
activation is a separate owner step (see below).

## Behavior

- After each `CI` workflow completes, including reruns, the watcher reads that run
  and the jobs from its latest attempt. A failure in post-job cleanup counts as a
  failure.
- **PR / non-production runs → informational.** The report is CI-only, never
  claims that the existing production site validates the PR, and the job always
  exits 0. Ordinary CI already enforces PR failures; the watcher does not duplicate
  that.
- **`push` runs on `main` → enforced production observation:**
  1. CI passed for the exact commit, and `main` still points to it.
  2. Optional provider deployment checks, if enabled (see below).
  3. Live probes, all read-only GETs:
     - API `/health` (`status=ok`) and `/ready` (`status=ok`, `database=up`);
     - web `/`, `/robots`, `/manufacturers`, `/find-a-humanoid`: HTTP 200, HTML,
       and the "humanoid" marker;
     - **closed surfaces** API `/api/discovery-review` and web `/discovery-review`
       must return **404**. They are mounted only in relaxed environments. Any 2xx
       is a hard **FAIL**: a non-public surface is being served.
  4. Re-check enabled provider pointers and `main` after the probes.
- Poll for up to 15 minutes, every 30 seconds. Each request has a timeout,
  redirects are refused, and response size and pagination are bounded. Partial
  evidence is written after every round. The workflow timeout is 20 minutes.
- Output is an Actions job summary plus a 14-day JSON/Markdown artifact. The
  watcher never posts PR comments, email or Slack messages, and never reruns,
  merges, deploys, rolls back, migrates, imports catalogue data or changes
  publication.

### What a production PASS means

Without provider checks, the scope reads
**"production health — deployment identity not verified"**. A PASS then means that
CI passed on this commit and production was healthy and serving its critical routes
when observed. It does **not** prove that this commit is the one live: the probes may
reach the previous build while a deployment is still in progress. Enabling provider
checks adds exact deployment-identity verification for the enabled providers.

## Results and exit codes

| Result | Meaning | Production exit |
|---|---|---|
| PASS | Every check in the stated scope passed. | 0 |
| SUPERSEDED | `main` had already moved on when evaluation began, or moved on during polling. The newer `main` run is the enforcement point. | 0 |
| FAIL | CI or a job failed, a provider reports a failed deployment, or a closed surface is served. | 1 |
| UNVERIFIED | Missing required configuration (`WATCHER_API_ORIGIN`, or an enabled provider's IDs/token), authorization failure, or malformed or missing evidence. | 1 |
| TIMEOUT | A pending state did not resolve within the deadline: an unhealthy endpoint, the network, or CI still running. | 1 |

PR-scope reports always exit 0; their result is recorded for information only.
Rows marked `NOT_APPLICABLE` (a provider check that is not enabled) or `NOT_CHECKED`
are neutral. No automatic remediation is authorized by this observer.

## Configuration

Set these through the repository's Actions **variables**. Default mode needs **no
secrets**: only the built-in `GITHUB_TOKEN` (`contents: read`, `actions: read`).

| Type | Name | Required | Value |
|---|---|---|---|
| Variable | `WATCHER_ENABLED` | to activate | `true` turns the observer on; anything else leaves it off. |
| Variable | `WATCHER_API_ORIGIN` | yes, for production | API HTTPS origin, e.g. `https://humanoidonline-api.vercel.app`. |
| Variable | `WATCHER_WEB_ORIGIN` | no | Public web origin; defaults to `https://humanoidonline.com`. No redirects. |
| Variable | `WATCHER_PROVIDER_CHECKS` | no | Comma-separated subset of `netlify`, `vercel-api`, `vercel-web`. Empty = none. |

### Optional provider deployment checks

Only a provider listed in `WATCHER_PROVIDER_CHECKS` is checked. A listed provider
with missing configuration is `UNVERIFIED`; an unlisted one is `NOT_APPLICABLE`. An
unknown name in the list is `UNVERIFIED`.

| Provider | Needs | Verifies |
|---|---|---|
| `netlify` | secret `WATCHER_NETLIFY_TOKEN`, variable `WATCHER_NETLIFY_SITE_ID` | `published_deploy` has the exact `commit_ref`, production context, ready state; site `ssl_url` equals `WATCHER_WEB_ORIGIN`. |
| `vercel-api` | secret `WATCHER_VERCEL_TOKEN`, variables `WATCHER_VERCEL_API_PROJECT_ID`, `WATCHER_VERCEL_API_ALIAS` (+ `WATCHER_VERCEL_TEAM_ID` if needed) | Alias → project → deployment with the exact Git SHA, production target, READY. `WATCHER_API_ORIGIN` must equal this alias. |
| `vercel-web` | secret `WATCHER_VERCEL_TOKEN`, variables `WATCHER_VERCEL_WEB_PROJECT_ID`, `WATCHER_VERCEL_WEB_ALIAS` | Same, for the `humanoid-online` Vercel project. The public site is Netlify, so leave this off unless that project matters. |

Neither provider offers read-only, project-scoped tokens; the observer only
performs GETs, but a token itself may permit more. Provider credentials are sent
only to the exact provider API host, never to live-site probes. Do not paste tokens
into chats, source files, reports, command arguments or logs. Reports contain
selected identity and status fields, never raw provider responses, environment
dumps, job logs or response bodies.

## Activation (owner-approved, separate from merging)

1. Merge after owner approval. The watcher stays inert because `WATCHER_ENABLED`
   is unset. `workflow_run` always uses the default branch's copy, so nothing is
   active from a feature branch either.
2. Set `WATCHER_API_ORIGIN`, and `WATCHER_WEB_ORIGIN` if it differs from the
   default.
3. Set `WATCHER_ENABLED=true`. Then use **Run workflow** on `main` with the latest
   `main` CI run ID to confirm a PASS before relying on automatic runs.
4. Optional, later: provider checks, by adding their secrets and variables and
   listing them in `WATCHER_PROVIDER_CHECKS`.

Reports are under **Actions → Deployment watcher → run summary** and the run's
`deployment-observation-*` artifact. GitHub's own notification behavior depends on
the user's settings.

**Security boundary.** All `workflow_run` observer code is checked out from trusted
`main`, never from the observed PR head, and upstream artifacts are not consumed.
Manual observation from other branches is disabled. The PR `test` job runs the
watcher's own unit tests without any secrets.

**Hard dependency.** The CI workflow must stay named `CI` at
`.github/workflows/ci.yml`.

## Local verification

```sh
python -m unittest discover -s scripts -p 'test_deployment_watcher.py' -v
WATCHER_API_ORIGIN=https://humanoidonline-api.vercel.app \
  python scripts/deployment_watcher.py --run-id <main CI run id> --timeout 120
```

Set `GITHUB_TOKEN` in the environment, never on the command line. Local reports go
to the ignored `var/deployment-watcher/`.

## API references used

- [GitHub workflow_run and security boundary](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- [GitHub workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs)
- [Netlify API: sites and published_deploy](https://open-api.netlify.com/)
- [Vercel alias lookup](https://vercel.com/docs/rest-api/aliases/get-an-alias)
- [Vercel deployment identity](https://vercel.com/docs/rest-api/deployments/get-a-deployment-by-id-or-url)
