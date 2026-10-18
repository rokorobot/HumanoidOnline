# DATA-D1.LIVE — Amendment A4: OWNER_AUTHORIZED source access

**Status: implementation draft — requires PR review and owner acceptance before merging.**

**Owner direction:** 2026-10-18. Add an internal source authorization basis independent of a publisher's terms review for approved, publicly accessible discovery surfaces. The initial owner-directed targets are Unitree, Booster, AgiBot, Agility Robotics, Figure and Alza.cz.

## Semantics

- `SOURCE_PERMISSION` preserves the existing affirmative-ToS eligibility route.
- `OWNER_AUTHORIZED` records the owner's business decision to activate governed discovery. **It does not assert publisher permission, and does not convert `tos_status=UNKNOWN` to `ALLOWED`.** It cannot override a source already recorded `PROHIBITED` or `RESTRICTED` or a technical access block.
- Every authorization and revocation event has an attributed, append-only audit row. The current source row is a projection, not an audit trail.
- A separate robots decision and reviewed scope are still required. The fetcher checks actual robots.txt on every run; a URL disallowed for our agent or otherwise unavailable remains unfetched. No evasion or credential bypass.
- Separate hosts require separate registrations: e.g. `shop.unitree.com` is not approved by `www.unitree.com`; `store.agibot.com` is not approved by `www.agibot.com`.
- **Authorization, enabling, scheduling and executing are four independent acts.** This change implements the first; it does not activate six unreviewed adapters.

## Source and catalogue invariants

An adapter requires reviewed seeds/patterns, approved paths, identity verification, bounded fetch and regression fixtures before activation. Proposals are not canonical facts; accepted claims and editorial publication retain their existing independent approval process. Retailer availability and price claims apply to the seller/market/condition and are never treated as global manufacturer statements.

## CLI example (after migration)

```bash
# Example only. Record a genuine robots observation rather than guessing ALLOWED.
python -m app.cli.discovery source review unitree-robotics-official \
  --reviewed-by 'Product owner' --tos-decision UNKNOWN \
  --robots-decision ALLOWED --path-prefix /products/
python -m app.cli.discovery source authorize-owner unitree-robotics-official \
  --by 'Product owner' --reason '2026-10-18 A4 product owner direction' \
  --path-prefix /products/
# Do not enable until this source's adapter is reviewed and in ADAPTERS.
```

Revocation: `source revoke-owner KEY --by ... --reason ...` disables the source and appends an audit event. New source activation is subject to owner approval after reviewing a PR, migration rehearsal and adapter/robots checks.

## Deployment order and controls

1. Schema baseline (`db/schema.sql`) and forward migration (`0025`) plus matching models, registry, CLI and tests, in a dedicated PR.
2. Tests/CI, including against a disposable test database, must pass on an exact reviewed PR head. Rehearse migration on a production clone.
3. Implement independently reviewed adapters for each source (Alza needs a separate distributor adapter). Register source-specific hosts and patterns, offline fixtures and policy cases.
4. Owner reviews exact PR and production activation plan. Merge/deploy before migrating and then register distinct owner approvals; no fake ToS approvals.
5. Configure source-specific cadence only after approved adapter and eligibility are ready. Verify scheduled observation report without canonical mutation.
