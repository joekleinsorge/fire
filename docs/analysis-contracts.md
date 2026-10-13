# Analysis contracts and source gates

Status: proposed specification conventions, pending product acceptance before implementation. No external sources or current jurisdiction rules have been verified in this review. Addresses R05–R07 and R12; uses the [calculation contract](calculation-contract.md) and [plan model](plan-model.md).

## 1. Outcome definitions

Every report names its evaluation start, end, currency, purchasing-power base, evaluated path set, and outcome-definition version. The retirement evaluation window defaults to the selected retirement milestone through plan end; accumulation shortfalls are separately reported and invalidate an “earliest feasible retirement” claim. No generic success score combines the following outcomes implicitly.

If retirement is never reached or falls after the plan horizon, retirement-window outcomes are unavailable, not vacuously successful. Report that path in the unreached-retirement population. For comparisons across different retirement dates, disclose each evaluation window; do not silently treat a shorter exposure as an equivalent horizon.

| Outcome | Proposed test over the complete evaluation window |
|---|---|
| Portfolio survives | Specified investable portfolio is strictly positive at every observed monthly close, including the final close; a zero balance counts as depletion even if pensions cover expenses. Show the measured asset set. |
| Essential spending funded | Every essential obligation is paid by its modeled due period, with zero unpaid essential amount. Spending cuts cannot retroactively lower an already due need. |
| Desired lifestyle funded | Every baseline desired obligation, including its essential subset, is paid by its modeled due period. Record the desired schedule before strategy cuts so reduced requests cannot redefine success. |
| Legacy target met | Modeled net distributable estate at the declared death or terminal valuation event meets the target in the same price basis. Before estate modules exist, show a separate gross ending-asset proxy and mark net legacy unsupported. |

Compare settled monetary amounts under the calculation contract's precision rules. Its accounting tolerance must not turn a recorded unpaid obligation into a funded one. A first shortfall remains a path outcome even if later windfalls restore balances. Report duration, cumulative amount, maximum amount, and recovery separately. No spending produces no shortfall but must not be described as an adequate lifestyle unless the entered desired/essential needs support that conclusion.

Required results include first depletion/shortfall date, portfolio at retirement and at end, lifetime nominal and real spending separately, tax totals, spending-cut frequency and magnitude, goal completion, and legacy outcomes or explicit unsupported status. Growth charts show the asset set; net worth cannot substitute for available spending assets.

## 2. Path populations and statistics

For each rate, display numerator, denominator, excluded count, and reasons. Complete valid paths form the denominator; failed financial paths remain in it. Incomplete history, invalid inputs, numerical non-convergence, and cancelled computation are not successful paths or ordinary financial failures.

Do not publish a completed success rate if any requested path was silently omitted for engine errors. An incomplete run may show a prominently labeled provisional rate among completed valid paths, with its counts, and cannot satisfy an optimization success threshold.

Historical full-horizon and incomplete-period results are separate populations. Incomplete periods may show observed outcomes to their last available date, but never contribute to a full-horizon retirement survival rate. End-of-period percentiles must not mix portfolios at different horizons.

For a fixed horizon, proposed percentiles use sorted complete-path values and linear interpolation at index `(N - 1) × p`, with zero-based indexing and `p` in `[0,1]`. Show population standard deviation for the evaluated set, using divisor `N`; with one observation it is zero, and with no observations statistics are unavailable. State whether path weights are equal or mortality-weighted. Report medians of each metric directly; a median portfolio path does not imply the same trial supplies every period's median.

Retirement dates include a separate “not reached within horizon” mass. Date percentiles among retirees state their conditional denominator and do not imply that all paths retire. Report median and extremes from valid observed values with population counts. Spending-cut statistics define their reference as the previous year's spending in the same price basis; report dollar changes where a prior value of zero makes percentages undefined.

## 3. Historical and Monte Carlo settings

| Mode | Required settings and validation |
|---|---|
| Historical rolling | Dataset and digest, sample frequency, calendar range, start increments, horizon, complete/incomplete policy, allocation/rebalance timing, fees, price/total-return convention, currency, inflation series, and tax-regime choice |
| Single historical start | All rolling settings plus selected start; explain unavailable tail data rather than extending it silently |
| Historical resampling | Trial count, seed, random-generator/version, return/inflation sampling unit, replacement rule, and aligned asset vector selection |
| Block resampling | Resampling settings plus block length/distribution, overlapping versus non-overlapping blocks, edge/wrap policy, and last-block truncation |
| Parametric | Distribution family per variable, arithmetic/log interpretation, parameters and calibration window, frequency, correlation construction, tail/truncation rules, and inflation/FX dependence |
| All stochastic modes | Trial-index-to-random-stream mapping, draw order, deterministic execution contract, horizon, diagnostic policy, and inspection/export format |

Joint resampling draws aligned asset, inflation, and FX vectors so supplied cross-sectional dependence is preserved. Independent sampling is permitted only as an explicit alternative assumption. Parametric correlation matrices require validation for dimensions, symmetry, unit diagonal, and positive semidefiniteness; an invalid matrix must not be silently repaired. Returns below -100% are invalid for an unlevered asset unless the model explicitly transforms or truncates its distribution and discloses the resulting distribution.

Dataset gaps, missing asset history, mixed frequencies, proxy substitutions, and splice rules are explicit versioned decisions. Rebalancing changes asset holdings through ledger transactions; it must not reset wealth. A historical market path may use historical tax rules, current rules projected forward, or a user-defined regime only when that choice and coverage are explicit.

Proposed reproducibility guarantee: identical supported engine build, dependency digests, numerical environment, settings, and seed produce identical serialized period results. Across different supported numerical environments, a declared comparison tolerance may be used, with exact agreement required for discrete event/outcome decisions. If that cannot be guaranteed, restrict the reproducibility claim. Assign random streams by trial index so worker counts, retries, and completion order do not change paths.

## 4. Withdrawal-method sheet

Every named strategy in product §8 requires a separate versioned sheet before it is selectable as a verified method. A name alone is never an algorithm.

| Field | Required content |
|---|---|
| Identity | Strategy ID, human name, formula version, source title/author/date/link, access status, and selected variant |
| Equation | Exact initial and subsequent formulas, symbols with units, parameter domain, and rounding |
| Timing | Portfolio valuation instant, decision frequency, payment schedule, inflation reference, and first/last-period handling |
| Spending meaning | Gross portfolio withdrawal versus after-tax consumption versus total household spending; essential/desired classification |
| Other flows | Outside income, one-time extras, fees, taxes, RMDs, and how portfolio withdrawals fund spending |
| Constraints | Spending floor/cap, annual change limits, legacy target, guardrail precedence, and infeasibility behavior |
| State | Prior spending, reference portfolio, horizon/longevity input, valuation inputs such as CAPE, and versioned external series |
| Verification | Independently computed initial year, ordinary subsequent year, trigger crossing, binding floor/cap, and depleted-assets cases |
| Limitations | Unsupported combinations, source ambiguity, approximation, and validation status |

Proposed integration convention: first compute the strategy's requested spending under its published method, then apply explicit user constraints in a disclosed order, then calculate required portfolio withdrawals after outside income and modeled taxes. If a source formula directly produces gross withdrawals, label and convert that quantity explicitly rather than applying the spending convention blindly.

Reject internally contradictory user constraints, such as essential minimum above the chosen absolute maximum. If available funds cannot meet a valid spending floor, record the unmet amount. Legacy constraints cannot manufacture liquidity or suppress essential-shortfall reporting. The original method and an overridden variant must have distinguishable labels and versions.

No exact formulas for the listed named strategies are asserted here. Until references and independent fixtures are supplied, their method sheets remain source-gated.

## 5. Jurisdiction, healthcare, and estate module sheet

Each module specifies country/jurisdiction, rule version/digest, effective dates/tax years, covered account and income types, required household inputs, basis/history requirements, sources and review date, formulas and boundary tests, statutory rounding, interaction order, carryovers, future-law assumptions, unsupported rules, and a fallback policy.

Coverage is a matrix of rule × year × jurisdiction × supported circumstance, not a single “US taxes supported” flag. Include federal/state interactions, Social Security treatment, account access, inherited accounts, Roth transactions, contribution limits, payroll/self-employment, healthcare eligibility/reconciliation, and estate effects as applicable. The detailed rules remain the Stage 4/5 work described in product §§10–11.

An effective-tax-rate fallback states its income base, timing, exclusions, and rate. Switching to it must be visible in results and scenario comparisons. An unsupported state cannot be reported as a zero-tax state by default. Mixed detailed and simplified modules must declare which tax bases they share and prevent duplicate charges.

IRMAA-style lookbacks and other history-dependent rules need pre-plan history. Missing history produces a visible assumption or unsupported result, not invented past income. Future rule selection states whether amounts are indexed, held fixed, or changed by a user schedule. No current legal values or jurisdiction coverage are claimed by this document.

## 6. Longevity and financial outcomes

Fixed-horizon financial testing remains separate from mortality analysis. Mortality-weighted results name the table/version, cohort or period interpretation, age and other required demographic inputs, interpolation, improvements, and joint-life dependence assumptions. An independence approximation must be labeled if used.

For an individual at time `t`, partition outcomes into alive-and-adequately-funded, alive-and-shortfall, and deceased. Define adequate funding using the selected essential or desired spending criterion, not an unnamed asset threshold. These unconditional probabilities sum to 1. Conditional funding probability divides alive-and-funded by probability alive; it is unavailable when probability alive is zero.

For a household, also retain member-alive states. The three-way summary uses “at least one member alive” for alive and “no members alive” for deceased; survivor spending, income, ownership, and tax changes follow the modeled survivor state. The joint model must be consistent with member marginals. Do not label a household deceased at the first death or count death as financial success.

Death-terminated paths cannot be pooled into complete fixed-horizon financial rates. A longevity analysis may integrate mortality weights over financial paths or jointly sample them, but must state any mortality/market dependence assumption and preserve the denominator used for each result.

## 7. Optimization and professional use

Every search records the decision variables, allowed ranges, discrete choices, objective units, success definition/threshold, hard constraints, evaluation budget, stopping rule, seed, and comparison population. Use the same stochastic path set across alternatives where meaningful, then evaluate a selected proposal on a separately identified validation set to expose selection effects. Display sampling uncertainty and sensitivity; do not claim a guaranteed probability from a finite sample.

A search result distinguishes best evaluated feasible candidate, infeasible candidates, and unresolved numerical cases. It must not imply global optimality unless the method establishes it. Essential-spending, access, and contribution constraints remain active even if the chosen objective minimizes taxes or maximizes legacy. Save every proposed adoption as a separate scenario revision; adoption cannot overwrite the original plan silently.

Professional collaboration is proposed as explicitly granted household membership or scoped access, never an administrator shortcut. Cross-household dashboards require per-household grants. Billing, regulated adviser workflows, legal review, and professional data-retention obligations remain outside this specification until separately defined.

## 8. Source register and gates

| Source group | Current status | Required before release |
|---|---|---|
| Five comparison sites | Names, links, and contents not supplied | Identify sources, verify feature claims, and record scope differences before claiming parity |
| Longevity reference | Separate link not supplied | Identify the referenced method; select licensed mortality data and validated joint-life conventions |
| Advanced tax-planning reference | Link/content not supplied | Identify intended capabilities and authoritative rule sources; map to module coverage |
| Named withdrawal methods | Names supplied; exact variants and references absent | Complete method sheets and independent numerical examples before enabling each method |
| Market and inflation data | No provider, license, or series selected | Resolve redistribution, history, dividends, gaps, frequency, currency, and update policy |
| Tax/benefit/healthcare/estate rules | Target topics supplied; no reviewed modules | Establish authoritative references, years, jurisdiction scope, and boundary fixtures |

These source gates do not block drafting Stage 1's simplified contract. They do block verified-source claims and the release of affected advanced calculations.

## 9. Classification fixtures

| Case | Proposed classification |
|---|---|
| Portfolio 100 throughout; essential unpaid 10 in month 2; later windfall | Portfolio survives; essential and desired outcomes fail; first shortfall remains month 2 |
| Portfolio reaches exactly zero in final month; pension pays every desired bill | Portfolio survival fails; essential and desired funding pass |
| Desired baseline 50; essential 30; strategy requests and funds 30 | Essential passes; desired fails by 20 despite meeting the strategy request |
| Two complete historical paths, one survives; third path lacks five years | Full-horizon survival is 1/2, not 2/3; incomplete path shown separately |
| One of three requested trials fails numerically | Run incomplete; no completed success claim or optimizer feasibility decision |
| Mortality masses: alive-funded 0.60, alive-shortfall 0.15, deceased 0.25 | Sum 1; funding conditional on alive is 0.60/0.75 = 0.80; death is not success |
| Sorted ending assets 0, 100, 200 | Median 100; 25th percentile 50 under the proposed interpolation convention |

Fixtures are specification checks. Their future executable implementations must use the shared engine, not separate formulas written only to satisfy tests.
