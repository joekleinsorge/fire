# Implementation status

Open FI Planner is now a usable local planning application rather than a landing page or single-input calculator. It provides a multi-screen workspace backed by a shared monthly household plan. This is a substantial working implementation, while the broader five-stage product specification remains a roadmap rather than a claim of completion.

## What works

The browser workspace covers a six-input quick FI calculator with linked savings edits, a savings-rate comparison chart and expansion into a full plan, plus an overview, editable assets and debts, recurring income and spending, retirement assumptions and simulations, scenario comparison, progress observations, account settings, and child planning. Child profiles can hold separate 529 and Trump Account forecasts, including education-use assumptions and Trump Account contributions through the year the child turns 17. Child account balances never enter the parent's investable assets or FI target, but household-funded contributions (and, when enabled, education shortfalls the household covers) are paid from household cash in the account withdrawal order and reduce the parent's projection; unaffordable amounts are reported as unfunded. Employer, pilot, and contributions marked external do not affect household cash. Future purchases model one-time costs plus ongoing or time-limited upkeep in today's dollars; only open-ended upkeep raises the FI target. A purchase can be partly financed (a loan whose payments start the next month), kept as a non-spendable asset with an assumed growth rate, and can sell an existing account (less selling costs) and pay off a debt from the proceeds, which covers moving to a new home. Unpaid debt is capitalized and each shortfall is reported once, including after a loan's maturity. A purchase scenario saves a full independent copy of the plan with its starting baseline so the two paths can be compared and either can be opened. Projections report both the FI age at or after planned retirement and the earliest age spendable assets reach the target, so trade-offs that move the crossing remain visible when retirement age is fixed. Signed-in users reopen their last plan on load, and scenarios or observations created before signing in are saved with the plan's first save. Plans can be calculated anonymously in a working session. Local accounts can save versioned plans; the Freshlab chart also supports optional Dex/OIDC login through an in-pod oauth2-proxy restricted to the configured owner. Settings lists saved revisions and restores older inputs as a new version. Plans also support scenario records, comparison, and progress observations, including confirmed observation removal. JSON import/export and CSV exports are available.

The browser code is plain, dependency-free JavaScript. The former app.js is split by topic into core state and helpers, overview, records, assumptions, projection and simulation, scenarios, observations, and session scripts, with startup in main.js at app.js's old place in the load order; the input, run, child, purchase, planning and completion scripts are unchanged.

The Python standard-library server uses SQLite for transactional persistence and a durable local job queue. It runs as a single server/worker process. Household isolation and plan roles are enforced at the API. This is a deliberate initial deployment choice instead of the target PostgreSQL/distributed-worker topology.

The monthly engine models real-dollar balances, scheduled after-tax streams, account-specific real returns and fees, availability and withdrawal order, debt payments, essential and desired spending outcomes, and FI target timing based on modeled retirement cash flows. Seeded simulation produces outcome denominators and annual percentile bands. Personal property and other personal assets count toward net worth but cannot fund spending, with fixed assumed returns and no automatic sale or linked debt. Restricted financial holdings remain separate from personal property. The full-plan workflow accepts an explicitly empty account list while entering initial assumptions.

## Boundaries

The quick estimator assumes annual savings arrive at each projection-year end. It does not simulate retirement spending. The full-plan progress ratio uses accounts available for spending; observations map to monthly periods after the recorded valuation baseline. Scenario asset paths align on common ages only when currency and price basis match.

The calculations are planning estimates, not a ledger, tax filing, benefits determination, or guarantee. The model uses floating-point arithmetic and simplified monthly debt interest. Stream values are entered after tax. The selected currency controls display formatting; there is no exchange-rate conversion. Users must supply return assumptions, income, expenses, benefits, healthcare costs, and other inputs they want represented.

The app does not provide statutory federal/state/international taxes, Social Security estimates, ACA/Medicare eligibility, RMD/Roth/SEPP rules, reviewed named withdrawal strategies, mortality or joint-life transitions, jurisdiction-specific estate calculations, complete property transaction accounting, or professional multi-client workflows. Child account forecasts do not validate 529 contribution/program limits, qualified education expenses, state tax treatment, Trump Account eligibility or tax treatment, pilot eligibility, withdrawals, or post-18 IRA rules. Only the Trump Account contribution caps are checked: the statutory 2026–27 amounts, with later inflation-indexed caps held at the same amount in today's dollars. These are not a tax module. Trump Account contributions stop by the projected growth-period end year, while any later balance continues under the user's assumed return and fees. These areas need reviewed source modules and remain release gates.

## Remaining product and operational work

- PostgreSQL migration, distributed workers, production identity-provider configuration, quotas and capacity benchmarks, encrypted backup integration, retention behavior across restored backups, and production recovery targets.
- Reviewed historical data and inflation/rebalancing semantics, correlated return simulations, and source-reviewed withdrawal methods.
- Full property and contribution ledgers, account-specific withdrawal/tax rules, broader schedule and milestone variants, and progress CSV imports.
- Reviewed tax, benefits, healthcare, mortality, estate, and international modules, including complete 529 and Trump Account rules.
- Guest/public sharing, professional workflows, PDF methodology reports, and formal accessibility evaluation.

## Verification

Verification on 2026-10-15: all 60 Python unit/API tests pass, including engine coverage for household-funded child contributions, future purchases (financing, assets, sales, payoffs, limited upkeep), matured-debt shortfalls, and earliest FI age; JavaScript syntax validation, Python compilation, `helm lint`, authenticated and unauthenticated chart rendering, and `git diff --check` pass. Browser review exercised child creation, a 529 funding forecast, and a Trump Account contribution projection in an isolated, unsaved test session, and verified the current Trump Account form guidance, employer-contributor label, and account-fee input. A scripted headless-browser pass (2026-10-13) exercised every view, child and account creation, adding a purchase, a signed-out purchase scenario and observation, registration and first save, a persisted scenario, reload with plan restoration, comparison, and a 390px viewport without horizontal overflow or console errors. Earlier browser review covered anonymous calculation, local registration, saving/reopening, projection, simulation, scenario loading, and a narrow viewport without horizontal overflow. Formal accessibility conformance, production deployment, statutory validation, and performance benchmarks have not been completed.

## October16 planning completion update

The deployed household workflow now has source-labeled guided updates,
conserving child-account mapping, purchase-linked rental income, strict pilot
birth-year/attestation checks, progressive MFJ Florida tax/reference rules,
nominal taxable basis with funded deposits, explicit dividend tax drag, RMDs,
and funded Roth conversions. See `docs/local-api.md` for exact boundaries.
Earlier statements above that no reviewed jurisdiction module exists describe
the previous implementation. These additions do not establish future-law,
provider data, full tax-return, Medicare/ACA eligibility, or survivor modeling.
Personal facts remain unknown until sourced or deliberately entered as budgets.
