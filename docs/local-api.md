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

## Contributions, access, taxes and funded closings (engine 2.2)

Account `payroll_contribution_monthly` deposits money already withheld from net-pay income. Set `contribution_start_month` and exclusive `contribution_end_month`; it is not a household cash expense. `available_from_age` explicitly unlocks an otherwise restricted financial account at the beginning of the first eligible model month. It is a planning assumption, not legal eligibility. `withdrawal_tax_rate` is an entered effective rate on gross withdrawals: a $100 gross withdrawal at 20% supplies $80 for spending and records $20 of tax. No statutory future income-tax return is inferred.

`reserve_account_id`, `cash_reserve_target`, and `surplus_account_id` route monthly surplus into the reserve up to its target and then into the specified cash/investment account. They do not execute real trades or force existing account transfers.

Purchase `transaction_costs` includes buyer closing and moving expenses without adding them to property value. `require_full_funding: true` checks the down payment, transaction costs, full linked debt payoff and `minimum_cash_reserve` (an after-tax liquid reserve requirement) before executing a closing. A blocked transaction preserves the old asset and loan, draws no new loan, and incurs no new upkeep. `purchase_funding_gap` reports the additional liquidity needed; `purchase_unfunded` reports the entire unexecuted cash purchase obligation, so the ledger does not pretend that any funds were spent. `replaces_expense_monthly` removes entered existing essential expenses only after a successful closing and before `replaces_expense_end_month`.

For `nominal_loan: true`, plan `inflation_rate` converts future fixed nominal payments and balances into plan-start dollars. Original loan rate and amortization still determine the initial principal-and-interest payment. `debt_inflation_adjustment` records the change in the debt's real purchasing power. Existing reference debts remain unamortized until actual terms are entered.

Scenario IDs in `archived_scenario_ids` are hidden from the current comparison list, with an option to show earlier drafts. Records and saved calculations are preserved. A scenario with metadata `status: needs_inputs` cannot be run: it would otherwise produce a misleading no-purchase projection. Automatic upload of browser-only scenarios/observations when saving a new plan is disabled.

`household_contribution_monthly` is a funded transfer from household cash into an existing account (for example, an unassigned 529 pool). It increases that account, decreases cash once, and does not reduce total net worth. Unmet transfers are recorded separately as `account_contribution_unfunded`, not as fictitious spending or asset value. Do not also enter the same transfer as an expense stream or a child-account contribution.

`replaces_retirement_expense_monthly` removes an explicitly allocated current-home operating budget from essential retirement expenses after a successful move. Use it only where the baseline budget includes those exact expenses; do not invent a housing allocation without labeling the assumption.

### Linked project upkeep

A future purchase may set `upkeep_until_purchase_id` to another purchase ID.
Its upkeep stops in the month after that referenced purchase successfully closes.
A blocked or disabled closing leaves the original upkeep in place. This supports
a pool installed before a move without charging its upkeep after the property
is sold. References must identify another purchase in the snapshot.

`GET /api/plans/{id}/latest-runs` returns one completed result summary per
scenario and calculation kind, independent of history pagination. It requires
the same household access as the plan. Full immutable results remain available
through each returned job ID.
