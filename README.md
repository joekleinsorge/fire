# Open FI Planner

A self-hosted financial planning workspace for building a household balance sheet, modeling recurring income and spending, projecting debt and portfolio balances, and comparing retirement scenarios. It runs locally with Python's standard library and stores data in SQLite.

## Run locally

Requires Python 3.11 or later; no packages or external services are required.

```sh
python3 -m fireplanner.server
```

Open http://127.0.0.1:8080. Anonymous users can build and calculate a working plan. Register locally to save versioned plans, scenarios, and progress observations. The default database is `data/planner.sqlite3`; use `--database`, `--host`, and `--port` to override it. No SMTP or internet connection is needed during normal use.

For Docker, run `docker compose up --build` and open the same URL. The Compose volume holds the database. This deployment uses one SQLite-backed server and worker process; it is intended for local or small self-hosted use, not a horizontally scaled service.

## Workspace capabilities

- Six-input quick FI estimate with linked income, expense, savings, monthly-savings, and savings-rate edits, plus a savings-rate chart and annual table. The estimate can expand into a detailed plan.
- Overview with net worth, spendable-asset progress, retirement spending target, projected FI timing, cash flow health, an asset projection, and annual details.
- Editable cash, investment, retirement, property, and other assets; withdrawal order; and amortizing debts.
- Recurring after-tax income and expense schedules with cadence, start/end months, real growth, essential status, and pause controls.
- Retirement assumptions and seeded simulations with annual percentile bands and separate essential-spending, desired-lifestyle, and portfolio-survival outcomes.
- Saved plans with revisions, scenarios, comparisons, progress observations, and JSON import/export. CSV export and browser printing are also available.
- Child profiles with separate 529 education and Trump Account forecasts; child assets stay outside a parent's spendable balance and FI target, while household-funded contributions reduce household cash flow.
- Future purchases (a pool, a new home, tuition) with one-time cost, ongoing or time-limited upkeep, optional financing, a resulting property asset, and sale of an existing home with mortgage payoff, plus purchase scenarios that save a full plan copy with its baseline for side-by-side comparison.
- Local accounts, household isolation, and role-based plan access.

## Model boundaries

Amounts are modeled in constant purchasing power. Stream amounts are entered after tax. Account returns and fees are user assumptions; fixed-return projections and simulation distributions are not forecasts. Property and other assets use fixed assumed returns, default to unavailable for spending, and have no automatic sale or linked debt. Debt interest is approximated monthly from its annual rate. Currency formatting follows the selected plan currency; the app does not convert between currencies.

The application does not calculate statutory taxes, Social Security or other benefit eligibility, healthcare programs, account-specific tax/access rules, mortality, or jurisdiction-specific estate outcomes. Child account forecasts are simplified year-end estimates: 529 qualified-use/state rules and Trump Account eligibility, taxes, and post-18 treatment are not determined. Entering a benefit or healthcare amount manually does not mean the app has verified it. See [implementation status](docs/implementation-status.md) for release limits and [local operations](docs/local-operations.md) for backup and deployment boundaries.

## Product specification

The target product is described in [product and architecture](docs/product-and-architecture.md). Supporting contracts cover [calculations](docs/calculation-contract.md), [plan identity](docs/plan-model.md), [analysis](docs/analysis-contracts.md), [access and operations](docs/access-and-operations.md), and [delivery acceptance](docs/delivery-acceptance.md). The [specification handoff](docs/spec-review-handoff.md) records the earlier review boundary; subsequent implementation work superseded it.
