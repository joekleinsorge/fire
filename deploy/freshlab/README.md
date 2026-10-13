# Freshlab deployment staging

This chart is prepared for Freshlab's existing Istio Gateway, Longhorn, and
VolSync. It is not deployed by this repository. Copy it into Freshlab's
`apps/openfi` directory and let its root ApplicationSet reconcile the chart.
The image, replica count, route, and backup settings must be finalized first.
Keep all household data and account credentials outside both repositories.

1. Run the Python tests and build the current reviewed application for
   `linux/amd64` using the repository Dockerfile. Publish the image to the
   chosen registry, then set `image` to its immutable `@sha256:` reference.
   For a private registry, provision an image-pull Secret through Freshlab's
   encrypted secret workflow and set `imagePullSecrets` to its name.
2. Validate the chart with `helm lint` and `helm template`, plus Freshlab's
   `make lint` and `make validate`. Reconcile initially with `replicas: 0`
   and the route disabled. This creates the retained Longhorn claim.
3. Install the private SQLite database onto `openfi-data` while the app is
   stopped, using an ephemeral pod mounting the claim as UID/GID 10001.
   Transfer a consistent SQLite backup, never an active database without its
   WAL. Check SQLite integrity and file mode 0600. Do not put the database,
   source JSON, exports, or credentials in a ConfigMap, image, or Git.
4. Provision `openfi-data-volsync-restic` using the existing encrypted Restic
   repository-secret pattern. Enable backups, set one replica, and verify the
   health endpoint, login, saved plan, original source profile, and scenarios
   through port forwarding before enabling the TLS route. SQLite is single
   process; the deployment uses Recreate to avoid overlapping instances.
5. Enable the route after confirming Gateway TLS and DNS configuration.
   The proposed hostname is `fi.kleinsorge.dev`. Native local-account login
   protects saved financial data; this app does not currently support Dex.
   Do not assume proxy headers provide authentication. Confirm unauthenticated
   requests to saved-plan endpoints return 401.
6. Verify an encrypted VolSync backup and a restore to a separate temporary
   claim. Snapshot copies must retain the entire data directory (SQLite plus
   any WAL files). Before upgrades also use `scripts/backup.py` for an online
   SQLite backup. Keep the prior image digest and a matching database backup.

The chart keeps PVC pruning disabled. Restore into a new claim and validate
it before repointing the deployment; do not delete the original claim.

## Private source import

`scripts/import_household.py` takes a supplied household JSON document and
creates a new, owner-only database, generated login, and importable plan JSON:

```sh
python3 scripts/import_household.py data/private/household-source.json \
  --database data/private/planner.sqlite3 \
  --credentials data/private/login.json
```

It refuses existing database/credential paths. Use it offline, not against a
running server. The full source is preserved in the plan and shown in Settings.
The importer distinguishes original facts from draft modeling assumptions;
reference-only debts retain their balances without adding duplicate cash
payments. Child birth dates, beneficiary mappings, and unknown mortgage terms
are not invented. Disabled purchases retain costs without inventing timing.
Base, conservative, and adverse scenarios are labeled illustrative drafts.

The `data/` directory is excluded from Git and the Docker build context. The
Dockerfile only copies application code and web assets. Do not embed a private
source document as a test fixture or static web resource.
