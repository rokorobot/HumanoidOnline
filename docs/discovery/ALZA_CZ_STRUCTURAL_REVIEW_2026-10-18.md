# Alza.cz (`www.alza.cz`) structural review: 2026-10-18

Read-only, bounded inspection of the registered source `alza-cz`, done before any adapter
was written. It limits what a future adapter may assume. **It is not an adapter, enables
nothing and records no eligibility decision.**

## Authority

Robert Konecny (product owner), review follow-up to PR #162 (2026-10-18): "six separate,
bounded structural reviews … Inspect applicable robots.txt rules and candidate source pages,
respect technical blocks and applicable restrictions, and produce documented findings for
adapter implementation. Do not perform unrestricted crawling." It rests on the 2026-10-18
owner instruction adding the source to the discovery monitoring programme (docs/28 A4,
`OWNER_AUTHORIZED`). That is an internal business decision, **not publisher consent**, and
`tos_status` stays `UNKNOWN`. The terms of service were not read or assessed.

Method: retrieved 2026-10-18 by an AI agent (Claude Code), with the crawler's own user agent
`HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)` and no other
identity. robots.txt was fetched first and every later URL was checked against it with the
repository's own parser (`app.services.discovery.robots`) before being requested. Requests
were at least 3 s apart, capped at 10 per host, redirects were recorded but not followed,
and nothing was retried. These are agent observations, **not** MANUAL_BOOTSTRAP readings and
not verified facts (docs/16 §2.1). Response bodies were retained locally for adapter fixtures
and are not committed here.

## Requests (1, crawler user agent `HumanoidOnlineMarketBot/0.1`)

| # | Time (UTC) | URL | Result |
|---|---|---|---|
| 1 | 18:47:27 | `https://www.alza.cz/robots.txt` | 403; 65552 B; sha256 `41abdad5cc36…` |

## Finding: BLOCKED_BY_SOURCE

The very first request, `robots.txt`, was answered by **Cloudflare with HTTP 403** and a ~64 KB challenge page (the body contains challenge/captcha markup). This is a **technical access control applied to our declared crawler user agent**.

Under LIVE.3 a block is a finding, not an obstacle. The review therefore **stopped after this one request**:
- no retry, no other user agent, no headless browser, no proxy, no challenge solving;
- no product or listing page was requested;
- robots policy is **unavailable**, which the runner treats as fail-closed (no fetch).

`robots_status` must stay `UNKNOWN` (or `DISALLOWED` if the owner prefers to record the block that way). It must not be `ALLOWED`. **An automated Alza adapter cannot be operated under the current access controls**, whatever the owner's business authorization.

Context: on 2026-10-05, owner-supervised manual captures of two Alza category listings succeeded, and two R1 EDU product pages returned 403 then too. The manual-capture path (`manual_capture` + `alza_cz_reference_proposals`) remains the only supported Alza route.

## What would change this

Only a change on Alza's side: for example a published robots policy reachable by our agent, or an explicit arrangement such as an allow-listed crawler or a data feed or API agreed with the retailer. Any such arrangement is a new source decision for the owner. Engineering around the challenge is prohibited.

## Adapter readiness

| Item | Finding |
|---|---|
| Approved host | `www.alza.cz` (registered) |
| robots.txt | unavailable to our agent (403 challenge) |
| Seeds / paths | none can be approved |
| Blockers | **technical block (BLOCKED_BY_SOURCE)**. Keep the source disabled; manual capture only |
