"""GENERATED FILE — do not hand-edit.

Regenerate with:
    uv run db/generate_migration_manifest.py

Bundled fallback for deployments where the canonical repo-root
`db/schema.sql` and `db/migrations/` are not reachable at runtime (e.g.
Vercel with Root Directory=apps/api, which ships only this tree). Mirrors
`app.db.migration_state.expected_migrations()` exactly — same version set,
same sha256 of each forward migration's file content, baseline presence-only.

This is never an independent source of truth: `db/schema.sql` and
`db/migrations/*.sql` remain canonical. Drift between the two is a CI
failure, not a runtime decision — see
`apps/api/tests/test_migration_manifest.py::test_bundled_manifest_matches_canonical_migrations`.
"""
from __future__ import annotations

#: Mirrors app.db.migration_state.BASELINE_VERSION — presence-only, never
#: checksum-compared (db/schema.sql is canonical and is edited in place).
BASELINE_VERSION = "0000_schema"

#: version -> sha256 of the forward migration file's exact text, in the same
#: order db/bootstrap.py applies them. Does NOT include the baseline.
MIGRATIONS: dict[str, str] = {
    "0001_add_commercial_lead_message": (
        "fbb1094e13a343a5d16c175633e219feffaff4e4b8483f5bb28811a8fa657451"
    ),
    "0002_add_robot_image": (
        "246305d8e5277dd66480478ef3802cf3d367852e3be914e145af235e1eedaa14"
    ),
    "0003_add_discovery_layer": (
        "fecf8f33219c48de404e8f051f6ee3d4480b74b8597965b94559b706ee01ea96"
    ),
    "0004_add_live_acquisition_layer": (
        "3e2b33cd59679f6c54214a6905d3731952dbc5f3d7dfb5c9f731c7af203fdea9"
    ),
    "0005_add_robot_span_and_reach": (
        "eb82503ef77fc50fa2acb42630310ff723839bfa14b9123ab549fd20f2cf762a"
    ),
    "0006_add_unknown_commercial_status": (
        "f0b1208bfaabc2585d29b639aa03aa17ccb01643f2d61d4dc814c3d429b2bb35"
    ),
    "0007_default_commercial_status_unknown": (
        "8ec46af3bc018bc22af747321e035d24074f0baa72418336172a4a43f355bb6d"
    ),
}
