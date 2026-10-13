# Open FI Planner — product and architecture specification

Status: proposed target specification; implementation has not begun.

The following companion documents refine behavior without reducing this target scope. Their conventions are proposed, not yet approved implementation decisions:

| Document | Responsibility |
|---|---|
| [Calculation contract](calculation-contract.md) | Units, quick-calculator equations, period timing, cash allocation, reconciliation, and examples |
| [Plan model](plan-model.md) | Conceptual entities, immutable revisions, actual observations, and run provenance |
| [Analysis contracts](analysis-contracts.md) | Outcome definitions, simulation populations, strategy/module templates, longevity, and source gates |
| [Access and operations](access-and-operations.md) | Roles, sharing, jobs, retention, restoration, offline operation, and trust boundaries |
| [Delivery acceptance](delivery-acceptance.md) | Bounded stages, measurable exit criteria, finding dispositions, and unresolved decisions |
| [Review and handoff](spec-review-handoff.md) | Review evidence, documentation task state, and verification record |

This document defines product scope; companions propose exact behavior. A conflict must be resolved explicitly rather than silently dropping scope or treating a proposed default as user-approved. Documentation checks do not establish financial correctness of an unimplemented application.

## 1. Purpose and scope

Open FI Planner is a self-hosted financial independence and lifetime planning application. It combines an approachable quick FIRE calculator with detailed lifetime cash-flow planning, historical retirement testing, Monte Carlo simulation, and tax-aware optimization.

One consistent household plan underlies every analysis. A user can begin with a few inputs, progressively add detail, and reuse the same plan for retirement testing, cash flow, taxes, longevity, and legacy planning. Both a private home lab and a community server use the same application.

The application answers:

- When can I afford to retire, and what changes would let me retire sooner?
- Will my money support my planned retirement?
- How much can I spend, and how much might spending fluctuate?
- Which accounts should I contribute to or withdraw from?
- How do taxes, Social Security, healthcare, housing, and debt affect my plan?
- What happens when markets, inflation, income, or life circumstances change?
- What will I leave to my heirs?
- How does actual progress compare with my forecast?

Brokerage trading, tax-return filing, and legal estate-document preparation are outside the initial scope. Bank connections are optional future integrations; manual operation must remain fully functional.

The supplied scope refers to five previously discussed sites, a separately linked longevity analysis, and advanced tax planning capabilities. Those links and source contents were not supplied here. Their claimed feature coverage is unverified in this document; source collection and methodology review remain specification work.

## 2. Entry experiences

### Quick calculator

Visitors can begin without registering. Inputs are age, annual after-tax income, annual expenses, current invested assets, expected real return, and target withdrawal rate.

Results update immediately and include annual and monthly savings, savings rate, target retirement portfolio, estimated years until retirement, estimated retirement age, portfolio growth, a year-by-year projection, and an interactive savings-rate versus retirement-time chart.

Editing income, expenses, savings, or savings rate updates related values consistently. The interface makes the edited value and resulting adjustments understandable. An **Expand into full plan** action preserves the inputs and exposes the assumptions used to translate the simple calculation into a detailed plan.

Quick-calculator income is already after tax. Expansion must preserve that meaning and avoid applying income taxes a second time; detailed tax modeling requires an explicit transition to gross income and its tax characteristics.

### Guided lifetime planner

Setup covers, in order:

1. Household members and location.
2. Accounts, assets, and debts.
3. Income.
4. Expenses.
5. Savings priorities.
6. Life milestones.
7. Retirement spending strategy.
8. Investment and inflation assumptions.

Users can skip details and return later. Missing information uses visible, editable assumptions rather than hidden defaults.

## 3. Main application areas

| Area | Purpose |
|---|---|
| Overview | Current finances, retirement timeline, plan health, and major tradeoffs |
| Current finances | Household members, accounts, assets, debts, and balances |
| Plan timeline | Income, expenses, milestones, and changes over time |
| Cash flow | Sources and uses of money |
| Retirement spending | Withdrawal strategy and spending constraints |
| Simulations | Fixed projections, historical tests, and Monte Carlo |
| Taxes and healthcare | Tax estimates, Social Security, ACA, Medicare, and account-access rules |
| Compare and optimize | Scenario comparison, sensitivity tests, and strategy searches |
| Progress | Actual balances and results versus projections |
| Legacy | Estate, inheritance, and charitable giving |
| Reports | Exportable results, assumptions, and plan summaries |

## 4. Shared household and financial model

Every saved private plan belongs to a household and supports one or more people. Anonymous quick entry uses an unsaved draft of the same model; saving establishes authenticated household ownership. Scenario changes and analyses must retain the same financial meanings across calculation modes.

### Household members

Record birth date or year, relationships, account ownership, retirement timing, planning horizon or life expectancy, filing status, Social Security assumptions, survivor assumptions, and location. Support future moves and associated changes in jurisdiction.

### Accounts

Support cash and savings, taxable brokerage, traditional and Roth IRAs, inherited traditional and Roth IRAs, employer retirement accounts, HSA, 529 education accounts, and country-module equivalents.

Each account can specify owner, balance, tax treatment, cost or contribution basis, asset allocation, growth and dividends, fees, contributions, employer match, withdrawal restrictions, and beneficiary treatment.

### Real assets and liabilities

Support primary residences, rental properties, other property and assets, mortgages, student loans, credit cards, and other secured and unsecured debts.

Properties include purchase and sale events, appreciation, transaction costs, maintenance, property taxes, insurance, rental income, and associated loans. Loans include interest rate, term, payment schedule, extra payments, and payoff events.

Total net worth, investable assets, and assets available to fund spending are distinct measures. An asset's inclusion in net worth does not imply that it is liquid or accessible for retirement withdrawals.

## 5. Income, expenses, and life events

Users can add unlimited named streams.

Income types include salary, self-employment, part-time work, bonuses, pensions, Social Security, rental income, annuities, RSU vesting and sales, inheritance, other windfalls, asset-sale proceeds, and custom income.

Expense types include everyday living, housing, healthcare, childcare, education, travel, vehicle replacement, family support, charitable giving, one-time purchases, and custom expenses.

Every stream supports:

- Start and end dates, ages, or milestone-based timing.
- Monthly, quarterly, annual, and one-time amounts.
- Recurrence, such as replacing a car every eight years.
- Fixed nominal amounts, inflation adjustment, and growth above or below inflation.
- Custom stepped or curved changes over time.
- Inflation beginning now or when the stream begins.
- Temporary enable and disable controls.

The timeline displays these schedules visually.

Milestones include financial independence, retirement, part-time work, debt freedom, property purchase or sale, relocation, Social Security claiming, Medicare enrollment, having a child, and the end of the plan. Triggers can use a date, age, portfolio threshold, or combined conditions.

## 6. Cash-flow planning

Users define an ordered list of priorities. A typical order is required expenses and loan payments, emergency fund, employer match, selected account contributions, extra debt payments, investment of remaining income, and discretionary spending.

Each priority supports a fixed amount, percentage, maximum permitted contribution, or target balance. Retirement settings specify withdrawal order and treatment of shortfalls.

Provide annual income and spending charts, contribution and withdrawal charts, interactive Sankey diagrams, detailed annual cash-flow tables, and explanations of unfunded expenses and unmet goals.

## 7. Investment and simulation engine

All modes consume the same household model and use consistent cash-flow, tax, fee, inflation, and investment conventions. Never silently mix real and nominal rates.

### Fixed-assumption projection

Support user-selected returns by asset class, inflation, income growth, nominal and inflation-adjusted views, detailed account balances, and cash flows. This mode powers the quick calculator and supplies an understandable baseline.

### Historical backtesting

Support rolling historical retirement periods, selected historical ranges, single starting years, stocks, bonds, cash, gold, inflation, dividends, fees, scheduled rebalancing, constant allocations, glide paths, and historical stress periods.

Clearly distinguish complete and incomplete retirement periods. Every result identifies its dataset and years. Dataset conventions must establish whether returns already include dividends to prevent double-counting.

### Monte Carlo

Support configurable trial counts, historical resampling, block resampling, parametric return models, asset correlations, custom return and inflation distributions, reproducible random seeds, and individual trial inspection.

Show medians, percentile bands, extreme outcomes, and retirement-date distributions. Store settings sufficient to reproduce the run.

## 8. Retirement withdrawal strategies

| Strategy | Intended core behavior |
|---|---|
| Constant dollar | Fixed spending with optional inflation adjustment |
| Percent of portfolio | Selected percentage of current assets |
| 1/N | Spread assets across remaining years |
| VPW | Adjust withdrawal percentage with remaining horizon |
| Custom VPW | User-configured VPW assumptions |
| Dynamic SWR | Recalculate spending against a defined sustainability method |
| Endowment | Blend previous spending and current portfolio value |
| Guyton-Klinger | Adjust spending when guardrails are crossed |
| 95% rule | Limit reductions relative to prior-year spending |
| CAPE-based | Link withdrawal rate to market valuation |
| Sensible Withdrawals | Adjust a baseline using defined market rules |
| Hebeler Autopilot II | Blend inflation-based and longevity-based withdrawals |
| Vanguard Dynamic Spending | Percentage withdrawals constrained by annual changes |
| Variable Z-value | Control spending response to portfolio changes |
| Fixed nominal spending | Keep the dollar amount unchanged |

Each strategy requires a plain-language explanation, published methodological reference, exact formula, timing convention, editable parameters, minimum essential spending, maximum spending, applicable annual increase or reduction limits, optional legacy target, and transparent treatment of outside income and extra expenses.

These names and summaries are a capability inventory, not complete algorithm definitions. Select and document methodological variants before implementing each strategy. Do not silently substitute a formula for an ambiguous name.

## 9. Results and outcome definitions

Display portfolio survival rate, failed-cycle or trial counts, first-shortfall age or year, years until financial independence, portfolio at retirement, ending portfolio, annual and lifetime spending, spending-cut frequency and size, essential-spending shortfalls, largest annual spending changes, lifetime taxes, net legacy, and goal completion rates.

Relevant distributions include average, median, standard deviation, minimum, and maximum. Provide charts, histograms, sortable tables, range selection, and individual-path inspection.

Report these outcomes separately:

- Portfolio survives.
- Essential spending is funded.
- Desired lifestyle is funded.
- Legacy target is met.

A strategy must not receive an unqualified success label merely because it cuts spending below an acceptable level. Numerical definitions of each outcome, thresholds, and evaluation horizon must appear with results.

## 10. Taxes, Social Security, and healthcare

### Tax engine

Use versioned country and jurisdiction modules. Initial US coverage targets federal income tax, state tax modules, filing status and deductions, ordinary income, qualified dividends, capital gains, payroll and self-employment taxes, NIIT, taxable Social Security, RMDs, withdrawal penalties and exceptions, inherited-account distributions, Roth conversions and access timing, backdoor and mega-backdoor Roth modeling, and 72(t)/SEPP distributions.

Provide an effective-tax-rate fallback when detailed rules are unavailable. Identify modeled rules, unsupported rules, tax year, and fallback use explicitly. Detailed US coverage is a staged target; unsupported jurisdictions must never appear fully modeled.

### Social Security

Support manual benefits or benefit estimation, claiming-age comparisons, early reductions, delayed credits, planned earnings, spousal and survivor benefits, the earnings test, and benefit-reduction scenarios.

### Healthcare

Model pre-Medicare premiums and out-of-pocket spending, ACA eligibility and subsidies with reconciliation assumptions, Medicare premiums, IRMAA thresholds and applicable lookback, and healthcare growth independent of general inflation.

### International planning

Country modules supply account types, taxes, pension assumptions, and estate treatment. Start with the US; later expand to Canada, the UK, Australia, Germany, and the Netherlands.

Display currency is separate from conversion. Cross-currency plans require explicit exchange-rate assumptions.

## 11. Longevity and legacy

### Longevity analysis

Include the “Rich, Broke or Dead” concept: fixed horizons, mortality-table-based survival probabilities, individual and joint-household longevity, financial outcomes conditional on being alive, probabilities of being alive with adequate assets, alive with a shortfall, or deceased, and adjustable longevity assumptions.

Keep mortality results visually separate from investment outcomes. Record mortality-table provenance and assumptions about joint survival; do not imply that mortality probabilities are investment success probabilities.

### Estate analysis

Model gross estate by asset and account, debt, administrative costs, liquidation taxes, net beneficiary receipts, applicable basis step-up, federal estate and jurisdiction-specific inheritance taxes, charitable bequests, survivor cash-flow changes, and effects of Roth conversions on heirs.

## 12. Compare, sensitivity-test, and optimize

### Scenario comparison

Duplicate a plan and change selected assumptions. Compare retirement age, spending, allocation, buying versus renting, debt repayment versus investing, Social Security claiming, withdrawal strategies, Roth conversion strategies, and location or tax regime. Show assumption differences alongside result differences.

### Sensitivity analysis

Explore configurable ranges for current and retirement spending, income and income growth, stock and bond returns, inflation, fees, withdrawal rate, retirement date, and longevity.

### Optimization

Search for maximum spending at a selected success threshold, minimum starting portfolio, earliest feasible retirement, contribution and withdrawal order, Roth conversion schedules, capital-gain harvesting, Social Security claiming combinations, and allocation glide paths.

Objectives include minimizing taxes, maximizing spending, maximizing ending wealth, and meeting legacy targets. Display constraints, assumptions, alternatives, and tradeoffs. Every proposed result can be saved as a separate scenario before adoption. Report the search method and limitations rather than implying a proven global optimum when none is established.

## 13. Progress, reports, and sharing

Progress tracking supports manual balances, CSV imports, actual net-worth history, actual-versus-projected overlays, explanatory notes, and plan revision history.

Exports include printable summaries, PDF reports, annual-results CSV, simulation-results CSV, JSON plan backups, and a complete assumptions and methodology appendix.

Sharing supports private household collaboration, explicit read-only guest access, revocable expiring links, optional passwords, sanitized public scenarios with identities and balances removed, and compact URLs for basic calculator inputs. Detailed financial plans must never be embedded in public URLs. Public-scenario publication requires a preview of exactly what is disclosed.

## 14. Deployment and architecture

### Deployment profiles

| Requirement | Home lab | Community server |
|---|---|---|
| Users | One household or a small trusted group | Multiple isolated households |
| Authentication | Local login or existing identity provider | Registration/invitations and configurable identity provider |
| Sharing | Optional | Explicit permissions and revocable links |
| Simulation capacity | Configurable local worker | Per-user quotas and queued jobs |
| Administration | Simple maintenance panel | Users, quotas, jobs, and storage |
| Internet dependency | None for normal operation | None for normal operation |

### Components and responsibilities

| Component | Responsibility |
|---|---|
| Responsive web frontend | Plan entry, progressive disclosure, visualization, comparison, and reports |
| Application API | Authentication, authorization, plan revisions, validation, jobs, and result access |
| Shared calculation engine | Financial accounting and calculation conventions across every analysis mode |
| PostgreSQL | Households, permissions, plans, revisions, job metadata, and result metadata |
| Durable job queue | Persistent scheduling and dispatch of simulations and optimization work |
| Background workers | Execute calculations against immutable plan and dependency versions |
| Local file storage | Larger result artifacts, imports, and exports; optional S3-compatible backend |
| Data/rule update process | Review and install versioned market data and tax rules independently |
| Reverse proxy | HTTPS termination and routing |

Deploy with Docker Compose and the same images for both profiles. A single machine is sufficient for the initial topology; workers can move to another host later. Database versus artifact-storage boundaries and queue technology remain design decisions.

### Calculation lifecycle

1. Validate and snapshot the selected plan revision, assumptions, and dependency versions.
2. Run an interactive baseline or enqueue a larger analysis with its settings and seed.
3. Execute the shared engine against that snapshot, recording progress and diagnostics.
4. Persist results and provenance together, associating artifacts with their household.
5. Display results with their original inputs even if the editable plan subsequently changes.

Retries must not publish duplicate result sets. Cancellation and worker failures must have explicit job states. Household authorization applies to job creation, status, cancellation, result retrieval, and exports.

### Operations

Require no mandatory external service, subscription licensing, or telemetry by default. Configure CPU, memory, worker limits, simulation progress, cancellation, and queue status. Provide automatic backups, documented restoration, migrations, upgrade guidance, health checks, and useful logs. SMTP is optional for invitations and recovery; document recovery behavior when SMTP is absent.

Data updates are reviewed and installed separately from application updates. Normal use relies on locally available rules and datasets. Establish capacity through benchmarks of realistic plans and trial counts, including community concurrency; do not guess sizing in advance.

## 15. Privacy and community administration

Enforce household isolation and owner, editor, and viewer permissions. Administrators manage operations without routine access to financial plans. Any support access requires an explicit, audited workflow.

Require encryption in transit, protected backups and secrets, user data export and deletion, rate limits, simulation quotas, and exclusion of sensitive plan values from normal logs. Public examples are stored separately from private plans.

This is an application access-control requirement; do not imply that it prevents infrastructure operators with database or host access from accessing plaintext data. The deployment documentation must state the trust boundary accurately.

## 16. Calculation quality and reproducibility

Every result retains plan version, engine version, tax-rule version, market-data version, simulation settings, and random seed where relevant. Preserve any additional dependency versions required by the analysis, including withdrawal methodology and mortality tables.

The engine must:

- Reconcile opening balances, growth, contributions, withdrawals, fees, taxes, and closing balances.
- Document contribution, withdrawal, return, rebalancing, and tax timing.
- Prevent double-counting taxes, dividends, property proceeds, and debt payments.
- Preserve internal precision and define rounding at reporting and statutory boundaries.
- Flag unsupported assumptions.
- Explain why a plan fails or a milestone moves.

Validation includes known financial examples, independent reference calculations, accounting invariants, tax boundaries, and reproducible simulations. Other calculators are comparison points rather than unquestionable ground truth.

Before implementation, accept or revise the proposed [calculation contract](calculation-contract.md): time-step resolution; annual/monthly aggregation; event ordering; inflation base date; return and fee conventions; tax settlement and withdrawal gross-up; shortfall treatment; milestone condition evaluation; and behavior for zero savings, already-funded retirement, depleted assets, and unreachable targets. Its settlement contract specifies diagnostics for interacting tax, withdrawal, subsidy, and milestone calculations that do not converge; a concrete solver still requires implementation design and independent validation.

## 17. Delivery sequence

| Stage | Deliverable |
|---|---|
| 1 — Foundation | Self-hosting, household isolation, quick calculator, saved plans, fixed projections, basic accounts and cash flow |
| 2 — Retirement testing | Historical testing, Monte Carlo, withdrawal strategies, detailed results, exports |
| 3 — Lifetime planning | Properties, debts, scheduled events, priorities, milestones, scenario comparison, progress tracking |
| 4 — Tax-aware planning | US taxes, account-access rules, Social Security, ACA, Medicare, tax analytics |
| 5 — Advanced analysis | Optimization, longevity, estate planning, international modules, professional collaboration |

Each stage preserves earlier plan inputs and explicitly identifies capabilities that remain unsupported. Stage 1 establishes a versioned plan model and extension points for later details; it need not implement later-stage rules. Every stage is subject to the accounting and reproducibility requirements.

The [delivery acceptance matrix](delivery-acceptance.md) maps every stage deliverable to observable exit criteria and evidence. It proposes Stage 1 private household roles, Stage 2 read-only result sharing, and Stage 3 public synthetic scenarios and sensitivity analysis; these placements refine previously unstaged features and require acceptance. Accessibility, offline operation, isolation, and reproducibility apply when their relevant surfaces first ship.

Professional collaboration is a target capability whose permissions and workflow remain to be specified. It must preserve household isolation and explicit access grants.

## 18. Outstanding specification decisions

- Supply the five reference sites and separately linked longevity and tax-planning sources; distinguish verified source capabilities from proposed additions. The [source register](analysis-contracts.md) records the missing evidence.
- Choose exact withdrawal formulas, references, variants, and method-specific timing conventions; complete each proposed method sheet before enabling the strategy.
- Accept or revise the shared calculation and analysis conventions: annual quick timing, monthly full-plan approximation, input edit precedence, horizon default, event order, precision, funding priorities, outcome definitions, and convergence policy. Select and validate concrete numerical methods separately.
- Select historical datasets, licensing and redistribution terms, coverage, update policy, missing-data handling, and historical-versus-current tax treatment in backtests.
- Define initial US tax years and state coverage, future-law assumptions, history requirements, and rule-validation ownership.
- Define mortality sources, joint-life assumptions, and estate-module coverage.
- Accept or revise proposed roles, guest downloads, professional access boundaries, and synthetic-public-scenario behavior; specify any professional workflow beyond household-scoped grants.
- Choose queue technology, storage boundaries, retention periods, identity recovery details, backup recovery targets, and benchmark workloads. Resolve preservation of old engine/data versions subject to licenses and deletion policy.
- Accept proposed stage placements and measurable release gates; select a formal accessibility target and Stage 1 implementation scope before selecting a software stack.

These decisions refine the specification; this document does not authorize application implementation, deployment, or publication.
