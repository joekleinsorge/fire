# Local API for scripts, Claude, and Codex

The planner has a deterministic HTTP API. No LLM, browser automation, or external service is required to read inputs, attach metadata, update a plan, or run a projection. The browser and API use the same SQLite data, validation, revision history, and permissions. The same service also has a stdio MCP bridge for ChatGPT and Codex; see [conversational planning setup](assistant-planning.md).

## Start and connect

Start the server against the database that contains your plan:

```sh
python3 -m fireplanner.server --database data/private/planner.sqlite3 --port 8080
```

Use your actual database path and configured port. The ordinary default is `data/planner.sqlite3`; starting against a different database creates a different workspace. No existing database is migrated or replaced by these instructions.

A standard-library client is included. From the repository directory:

```sh
python3 -m fireplanner.client login --email YOUR_LOCAL_ACCOUNT_EMAIL
python3 -m fireplanner.client plans
python3 -m fireplanner.client get PLAN_ID
python3 -m fireplanner.client project PLAN_ID --wait
```

The login command prompts for your existing local password. It stores a 24-hour session in `~/.config/openfi/session.json` with owner-only permissions, never prints the token, and binds the session to that server URL. Use `--url http://127.0.0.1:PORT` before the command to select another port. `OPENFI_URL` and `OPENFI_API_TOKEN` are supported for scripts. `logout` revokes the token and removes the matching session file. Expired sessions require another login.

Claude or Codex can invoke the same client commands once you have signed in. Give the assistant the repository path and the saved plan ID from Settings. It can read the complete plan, make a proposed change, calculate it, and submit the update. Keep downloaded financial JSON and session files outside version control. This repository's `data/` directory is ignored.

## Update metadata or assumptions

Read the latest envelope first. Its `version` protects your saved plan from conflicting edits. For example, write this **synthetic example** to `data/private/update.json`, replacing version `1` with the version you just read:

```json
{
  "version": 1,
  "changes": {
    "metadata": {
      "notes": "Confirm education beneficiaries before enabling contributions.",
      "sources": {"checking": {"as_of": "2026-09-30", "status": "user confirmed"}}
    }
  }
}
```

```sh
python3 -m fireplanner.client patch PLAN_ID data/private/update.json
```

`PATCH /api/plans/{id}` applies JSON Merge Patch to the **plan document** under `changes`. Objects merge recursively, arrays replace the whole array, and `null` deletes a field. Metadata does not affect financial arithmetic. Existing source details, unrelated fields, and sibling metadata keys survive. Every accepted update validates the resulting plan and creates a saved revision; a stale version returns HTTP 409. Reload and reconcile a conflict; do not blindly retry with a new version.

To change one account, first read the complete `accounts` array, update the matching stable `id`, retain all other entries and fields, and submit that full array under `changes.accounts`. The same applies to streams, debts, children, child accounts, and future purchases. Updating notes alone does not establish a tax rule, verify an assumption, or update a balance: change the corresponding financial field explicitly.

After API edits, use **Settings → Reload saved plan** in an open browser tab. Unsaved browser edits require confirmation before replacement. Saving an old browser copy after an API change is rejected with a version conflict. The app does not silently overwrite unsaved browser inputs with API data.

## HTTP interface

The machine-readable [OpenAPI schema](../web/openapi.json) covers the core integration routes and plan inputs. The running app serves it at `/openapi.json`, with a human guide at `/api-guide.html`.

| Method and route | Purpose |
|---|---|
| `GET /api/health` | Check server availability |
| `GET /api/capabilities` | Discover calculation modes and limitations |
| `POST /api/auth/token` | `{email, password}` → `{access_token, token_type, expires_in, user}` |
| `GET /api/auth/me` | Inspect the authenticated identity |
| `POST /api/auth/logout` | Revoke the current token |
| `GET /api/plans` | List household plan envelopes |
| `GET /api/plans/{id}` | Read `{id, name, version, plan}` |
| `POST /api/plans` | Create from `{name, plan}` |
| `PUT /api/plans/{id}` | Replace from `{name, version, plan}` |
| `PATCH /api/plans/{id}` | Partial update from `{version, changes}` |
| `POST /api/project` | Calculate `{plan}` without saving |
| `POST /api/plans/{id}/run` | Log a version-pinned plan projection or simulation |
| `POST /api/plans/{id}/scenarios` | Save a full snapshot or `{name, base_version, changes, metadata}` |
| `GET /api/plans/{id}/scenarios/{scenario_id}` | Read an immutable scenario snapshot |
| `POST /api/plans/{id}/scenarios/{scenario_id}/run` | Log a calculation of a saved scenario |
| `GET /api/plans/{id}/runs` | Read calculation history; `limit` and `before` paginate |
| `GET /api/jobs/{id}` | Retrieve immutable inputs, status, and stored results |
| `GET /api/plans/{id}/revisions` | Read immutable input versions |
| `GET /api/plans/{id}/export` | Owner JSON export; `?format=csv` for annual results |

Authenticated requests send `Authorization: Bearer TOKEN`. Browser session cookies remain supported. Unauthenticated calculation routes operate only on the supplied JSON and cannot read saved household data. Tokens inherit the user's household and role: viewers cannot edit, and household isolation applies to every plan read or write. Content-Type must be `application/json`; mutation requests are limited to 1 MiB.

## Input semantics

- Money is in today's purchasing power and the plan currency; no automatic currency conversion.
- Rates are decimals in JSON: `0.04` means 4%. `age`, `retirement_age`, and `horizon` are in years.
- `accounts` holds financial accounts and personal asset records for backwards compatibility. The UI separates personal assets. `cash`, `investment`, and `retirement` are financial types; `property` and personal `other` assets count toward net worth and cannot fund spending. Legacy `other` holdings with source types `health_savings`, `employer_equity`, or `education_restricted` remain financial holdings, restricted unless access is explicitly set. Retained source metadata is not an eligibility or tax calculation.
- Surplus income is deposited into the first available financial account, and withdrawals follow array order. Set that order deliberately; account-specific returns apply to deposited savings.
- `available` is modeled spending access, not a legal determination of when withdrawals are allowed. `return_rate` and `fee_rate` belong to individual accounts; the plan return is the fallback for accounts without a rate.
- Streams use `amount` per occurrence, `every_months` as cadence, `start_month` inclusive, and `end_month` exclusive. Month 1 follows the valuation month. The browser translates calendar choices to these indices. Ending work requires an explicit income end date; changing retirement age alone does not rewrite cash flows.
- Reference debts (`balance_only: true`) remain constant. Their payments must already be included in spending. Standard debts model payments separately; avoid double-counting.
- `members` and `child_accounts` store children and education forecasts separately. Unassigned education holdings remain restricted financial accounts until you explicitly map and transfer their balance; do not duplicate it.
- `metadata` is an arbitrary object for provenance, user notes, documents, or review status. Records also preserve extra metadata, `notes`, and `source_details` through browser edits. `household_source` retains the original imported information; it is not the current calculation input. Unknowns remain unknown until supported by new information.
