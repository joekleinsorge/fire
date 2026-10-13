# Local operations

Run one application process per SQLite database. The startup recovery step requeues interrupted jobs; multiple application processes against the same database are unsupported. Only bind to loopback for the default local installation. Docker also exposes loopback only. For remote access, configure a trusted TLS reverse proxy and deploy behind it; no host or TLS configuration is applied by this repository.

## Data and recovery

The database includes password hashes, hashed session tokens, household ownership, plans, immutable revisions, observations, and job snapshots/results. Treat it and every backup as private financial data. Infrastructure administrators can read stored plan data; application role checks do not change that trust boundary. The application does not encrypt its database or backup files.

Create a consistent backup without copying live WAL files:

```sh
python3 scripts/backup.py data/planner.sqlite3 /your/private/backup/planner-2026-10-12.sqlite3
```

The helper refuses to overwrite a file, creates it with owner-only permissions, uses SQLite's online backup API, and checks integrity. Use an encrypted destination and your own retention schedule. No automatic retention, remote backup, or RPO/RTO guarantee is configured.

To restore, stop the server, preserve the current database, and choose the backup as a new database path:

```sh
python3 -m fireplanner.server --database /your/private/backup/planner-2026-10-12.sqlite3
```

Prefer copying the backup into a private working location first so the original remains immutable. Restored sessions may still be valid until their expiry: invalidate sessions before exposing a restored instance. Account recovery without SMTP requires an authorized local operator; no password-reset endpoint or automatic identity-provider integration is claimed.

Before upgrading, stop the application, create a backup, and retain the previous code/image. Test a restore into a separate path. The initial schema is created idempotently; future incompatible migrations will need explicit migration tooling. A rollback should restore a matched database backup and application version.

## Jobs and limits

The local worker persists queued/running/completed/failed/cancelled states. A cancelled running calculation can finish CPU work but cannot publish a result. Queue admission is bounded; simulation trial/horizon limits prevent unbounded computation. This is a local workload guard, not a benchmarked community capacity plan. Unexpected errors retry at most twice after the initial attempt; validation errors fail directly. No distributed lease guarantees or incremental progress percentages are claimed.

## Exports and deletion

JSON exports preserve the saved plan envelope; the API accepts its `plan` contents to create a new saved plan. CSV exports the annual fixed projection with plan revision and calculation provenance; it is not a statutory or simulation report. Printable browser output supplies a basic report. Observations never automatically create income or transactions.

Financial inputs and secrets are excluded from normal request logging. Data, caches, session databases, and logs are ignored by version control. Deleting a file or restoring a backup does not implement household-level retention/deletion semantics; automated erasure across backups remains a release gate.
