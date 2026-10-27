# Conversational planning with ChatGPT, Codex, and Finances

The planner exposes stdio MCP tools and an authenticated HTTP API. Both use the same SQLite plans, revisions, scenarios, engine, and saved run results. Talking to an assistant does not create a second financial model.

## What gets saved

- A plan has a stable ID and numbered revisions. Assumptions, account access choices, cash-flow dates, notes, metadata, and sources are durable inputs.
- A scenario is an immutable named alternative. It includes the complete candidate plan, its starting baseline, an optional verified baseline revision number, and rationale/provenance metadata. Refinements create another scenario instead of rewriting the earlier one.
- Each projection or simulation run records the exact input snapshot, settings, plan/scenario identity, request metadata, timestamp, execution status, and stored engine result. Fixed scenario runs also calculate and save the preserved baseline for later comparison. Seeded simulation results include their original settings and outcome counts.
- Viewing an old run reads stored results; it does not recalculate under a newer engine or current assumptions. Rerunning creates another entry. Failed and cancelled attempts remain in history.
- Open **Scenarios → Calculation history**, refresh, and choose **View saved run**. You can inspect outcomes, annual results, original assumptions, export inputs/results, or open the inputs as an independent working copy. Older entries are paginated.
- Records persist through browser closure and server restart. SQLite backups include this history. Explicit plan deletion removes its revisions, scenarios, and runs. Removing a scenario card alone does not erase its logged calculation snapshots.

## Local setup

Run the app against the database containing your real plan. For this repository's imported household workspace:

```sh
python3 -m fireplanner.server --database data/private/planner.sqlite3 --port 8080
```

Keep the default loopback binding. From another terminal, sign in to the existing local account:

```sh
python3 -m fireplanner.client login --email YOUR_LOCAL_EMAIL
python3 -m fireplanner.client plans
```

For this workspace, an assistant session may be kept in the ignored `data/private/assistant-session.json`. A remote Codex session on this same computer can use it:

```sh
python3 -m fireplanner.client --session-file data/private/assistant-session.json plans
python3 -m fireplanner.client --session-file data/private/assistant-session.json runs PLAN_ID
```

If the existing private import credentials are available and you authorize the assistant to use this account, it can renew a session without placing a password in a prompt or command argument:

```sh
python3 -m fireplanner.client --session-file data/private/assistant-session.json login --credentials-file data/private/login.json
```

No OpenAI inference API key is required by the planner or MCP bridge. A local planner session lasts 24 hours and can be refreshed with the login command. Never paste its token or password into a conversation. `--session-file` or `OPENFI_SESSION_FILE` selects a private session location; `--url` selects another configured planner address.

## Local MCP clients and phone-driven Codex

The bridge runs without opening another network port:

```sh
python3 /absolute/path/to/fire/scripts/planner_mcp.py --url http://127.0.0.1:8080
```

Use this command as a stdio MCP server in a client that supports local MCP servers. The process delegates the authority of the signed-in planner account. The bridge rereads the local session on each tool call, so refreshing that session does not require rebuilding the plugin.

When controlling Codex from a phone, the Codex session must execute on the computer or private host that can reach this planner. A cloud session's `localhost` is not your computer. That host can use the same MCP command or the CLI below. Having a phone does not require publishing the financial application as a website.

## ChatGPT with your Finances plugin

Finances and the planner are separate integrations. ChatGPT can use the installed Finances plugin to obtain account information, then the planner's tools to save explicitly mapped balances and run models. The planner does not scrape bank accounts or modify the Finances provider. Do not send bank credentials to the planner.

Suggested conversational workflow:

> Use Finances for the account information I authorize. Read my saved planner inputs, identify missing facts, and propose a baseline and useful alternatives. Map holdings explicitly and keep source dates. Save each scenario with its assumptions and rationale, run the engine, and show the results with saved scenario and run IDs. Keep all cases in Calculation history.

MCP provides `update_account_balances` for existing account IDs, source provider, source date, and optional external account ID. It preserves every other account field and all other records. It does not automatically advance the whole plan valuation date: review mixed balance dates and update that baseline deliberately. `create_scenario`, `run_scenario`, `list_runs`, and `get_run` support the durable workflow.

### Private ChatGPT connection

OpenAI documents Secure MCP Tunnel as a way for ChatGPT to call a private stdio MCP server. It requires a tunnel identity, appropriate Platform/ChatGPT permissions, a runtime key for the tunnel client, and a running client on the planner's host. The planner itself stays on loopback. See the [official setup and permissions guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

Prepare a tunnel profile using the current supported `tunnel-client` and the stdio command above. The official guide currently shows this command shape:

```sh
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile openfi \
  --tunnel-id YOUR_TUNNEL_ID \
  --mcp-command "python3 /absolute/path/to/fire/scripts/planner_mcp.py --url http://127.0.0.1:8080"
tunnel-client doctor --profile openfi --explain
tunnel-client run --profile openfi
```

Supply the runtime key through the tunnel client's supported environment/secret mechanism, never as a literal command argument or repository file. The bridge is **single-user and preauthenticated locally**: restrict tunnel access to your intended account/workspace; do not share it as an anonymous public server. A multi-user public deployment would need separate per-user OAuth; it is not provided by this bridge.

Add the private MCP connection in ChatGPT using the same tunnel, complete the account's approval step, and verify `get_profile` / `list_plans`. Availability depends on the target account/workspace. This repository prepares the tools; it does not create a tunnel, change account permissions, install a plugin into ChatGPT, or claim that a live connection has been established. Connecting ChatGPT is complete only after a real tool call from that account succeeds.

## Durable CLI example

Create an alternative by saving this **synthetic** scenario request in an ignored private directory. Replace the version and assumptions with the actual saved inputs and the changes you intend:

```json
{
  "name": "Retire at 60",
  "base_version": 4,
  "changes": {"retirement_age": 60},
  "metadata": {
    "rationale": "Test earlier retirement timing",
    "assumption_status": "illustrative",
    "notes": "Income end dates and retirement spending must also be reviewed explicitly."
  }
}
```

```sh
python3 -m fireplanner.client scenario PLAN_ID data/private/scenario.json
python3 -m fireplanner.client run PLAN_ID --scenario SCENARIO_ID --kind project --wait
python3 -m fireplanner.client run PLAN_ID --scenario SCENARIO_ID --kind simulate --settings data/private/simulation.json --wait
python3 -m fireplanner.client runs PLAN_ID
python3 -m fireplanner.client job RUN_ID
```

The scenario creation response includes the exact `scenario.id` created by that request, alongside the backward-compatible scenario list. A run returns immediately by default; `--wait` waits up to 60 seconds and returns a still-pending status with `timed_out: true` if necessary. Use `job RUN_ID --wait` to check again. Pending work continues in the app's durable worker after the assistant conversation ends.

Simulation settings can contain `{"mode":"parametric","trials":300,"seed":42,"volatility":0.15}`. These are illustrative settings, not observed market facts. By default (`"return_basis":"geometric"`) the median simulated annual return equals the plan or account return, so a single portfolio's fixed projection is its median path; `"return_basis":"arithmetic"` instead treats the return as the expected average, whose median compounds about volatility²/2 lower. `{"mode":"sequence"}` runs one stress path: the plan return every year except `shock_returns` (default −15%, −13%, −24% real) starting at retirement or `shock_start_year`. Saving a scenario that changes the plan-level return does not override returns entered on individual accounts; alter the relevant account fields explicitly when intended.

`project PLAN_ID` now logs a saved projection. `preview PLAN_ID` is explicitly temporary and is reserved for exploratory checks, never a claimed durable result. Numerical conclusions must refer to completed stored runs, with limitations from the original inputs retained.
