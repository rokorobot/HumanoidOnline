"""The one `catalogue-write` advisory lock shared by every database write path that changes
catalogue rows or their audit trail (issue #179).

It is transaction-scoped (`pg_advisory_xact_lock`): it is released by the COMMIT or ROLLBACK
of the transaction that took it, never explicitly. The promotion executor takes it inside the
importer's transaction (its `before_write` hook); `materialize.verify_applied` takes it before
reading the imported rows and appending `catalogue_write_audit`. Holders therefore serialize:
a verification never interleaves with a promotion apply. Keep this the only spelling of it.
"""
CATALOGUE_WRITE_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext('catalogue-write'))"
