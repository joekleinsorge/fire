# Calculation contract

Status: proposed specification conventions, pending product acceptance before implementation. This document resolves design ambiguity; it does not claim a calculation engine exists or establish current tax law.

Scope: the shared baseline and extension contracts for later stages. Addresses review findings R01, R02, and R04 in the [review ledger](spec-review-handoff.md). The [product specification](product-and-architecture.md) remains the target scope.

## 1. Quantities and precision

Money has an explicit currency and price basis: nominal at a date, or constant purchasing power at a named base date. Rates identify their period, whether effective or arithmetic, whether real or nominal, and whether they include dividends and fees. Percentages are stored conceptually as fractions: 4% means 0.04.

Preserve internal precision; display rounding must not alter balances or trigger decisions. Proposed accounting tolerance is one minor currency unit per account reconciliation, with the actual residual recorded. This tolerance accommodates computation only: do not forgive an unpaid obligation using it. Currency-specific statutory rounding belongs to a versioned jurisdiction module. Numerical representation and algorithm accuracy must be selected and tested before implementation.

## 2. Quick-calculator contract

Let `A` be current invested assets, `I` annual after-tax income, `E` annual expenses, `r` the effective annual real return after assumed investment fees, `w` the annual target withdrawal fraction, and `a` age in completed years at the plan start. All money is in the same currency and today's purchasing power. No separate tax or fee charge is added in this mode.

Proposed input rules: `A, I, E >= 0`, `0 < w <= 1`, `r > -1`, and age is a nonnegative integer. All inputs must be finite; unreasonable values can carry visible warnings without silently changing them. The calculator does not infer income taxes, pension benefits, access restrictions, or account eligibility from these six inputs.

| Edited field | Values held fixed | Derived values |
|---|---|---|
| Income `I` | Expenses `E` | Savings `S = I - E`; savings rate `s = S / I` if `I > 0` |
| Expenses `E` | Income `I` | Savings and savings rate |
| Annual savings `S` | Income `I` | Expenses `E = I - S`; reject an edit implying negative expenses |
| Monthly savings `M` | Income `I` | Annual savings `S = 12M`, then expenses and savings rate |
| Savings rate `s` | Income `I > 0` | `S = sI`, `E = I - S`; permit negative savings, reject `s > 1` |

When `I = 0`, savings rate is undefined, never displayed as 0% or infinity, and rate editing is unavailable. Negative savings means expenses consume assets; it must not appear as a contribution.

The target portfolio is `T = E / w`. Accumulation uses end-of-projection-year savings and annual observations:

```text
P[0] = A
P[n+1] = P[n] × (1 + r) + S
```

The estimated years to the target is the first integer `n >= 0` for which `P[n] >= T`, before a funding shortfall. Retirement age is `a + n`; there is no fractional-year interpolation in this proposed quick mode. Hitting this simple target is distinct from validating a retirement cash-flow plan.

For any period, a negative raw closing balance becomes zero assets plus an explicit unfunded amount; negative assets must not act as an implicit loan. Stop reporting an FI estimate once a required expense cannot be funded under the quick assumptions. Full plans may continue tracking shortfalls, but this path is not an achievable retirement estimate.

Use the recurrence as the defining reference. An analytic shortcut may locate a crossing only if verified against adjacent integer years. Set a visible projection horizon, proposed default 100 projection years, editable after expansion. Distinguish:

- **Already at target:** `A >= T`, including `E = 0`, with zero years to target. With zero expenses, explain that the result reflects the entered expense level.
- **Target reached within horizon:** give the first annual crossing and its date convention.
- **Not reached within horizon:** no crossing, without claiming mathematical impossibility.
- **Unreachable under constant assumptions:** allowed only when justified by the recurrence, such as `r = 0`, `S <= 0`, and `A < T`.
- **Funding shortfall:** state the first affected projection year and unfunded expenses.

The savings-rate chart holds income, starting assets, return, withdrawal rate, and horizon fixed; each sampled savings rate changes expenses and therefore the target. It must show unreached or shortfall cases without connecting them to a fictitious finite retirement age.

## 3. Shared clock and expansion

Proposed full-plan engine resolution is one calendar month. The opening valuation is a month-end date; the first projected period is the following month. Inputs with a day within a month are assigned to that month's closing cash-flow step. This is a disclosed monthly approximation, not daily interest or transaction modeling. Age triggers use the birth date where known; a birth-year-only record needs a visible assumed birthday.

Schedules use inclusive start and exclusive end dates. One-time events have one occurrence ID. An occurrence on an end boundary belongs to the following active interval, if any; it cannot appear in both intervals. Recurrences define an anchor date and a missing-day policy, proposed clamping to the last day of the month. Multiple occurrences in one month are ordered by scheduled date, explicit priority, then stable ID. Annual stream anchors must not drift after clamping a leap-day occurrence.

Quick mode is a constrained adapter into the same engine: zero inflation, a synthetic invested account with unrestricted access, and annual net-income/expense events every twelfth projection month. Twelve equivalent monthly growth factors produce the annual return; savings enter at the closing step of month 12. “Monthly savings” in quick mode is an average, not a monthly contribution schedule. The synthetic account has unknown actual tax treatment, not an assertion that assets are legally tax-free.

Expansion retains this schedule, real return, zero-inflation assumption, after-tax income tag, and all six inputs. The unchanged expanded plan must reproduce quick annual results. Converting to monthly salary, adding inflation, gross income, real accounts, or taxes is an explicit plan revision with an explanation of changed results. Do not reverse-engineer gross income from after-tax income. Detailed tax mode requires gross income or a clearly labeled residual after-tax stream excluded from tax calculation.

Annual reports identify their basis: calendar years for taxes and general reporting; projection-year anniversaries for the quick comparison. A partial calendar year is labeled as such.

## 4. Returns, inflation, and fees

For an effective annual nominal rate `q`, the equivalent monthly factor is `(1 + q)^(1/12)`. A supplied monthly market series is used directly, not converted from its arithmetic annual average. Rates of -100% in a historical period require explicit total-loss handling; rates below -100% are invalid for an unlevered asset.

Use `(1 + nominal return) = (1 + real return) × (1 + inflation)` when translating assumptions over the same period. Do not substitute simple subtraction as the defining rule. Let `CPI[t]` be the cumulative price index with `CPI[base] = 1`; a nominal amount at period `t` is displayed in base purchasing power as `nominal[t] / CPI[t]`.

Streams specify whether their amount is expressed at plan start or stream start. Growth above inflation compounds with inflation, using a stated effective rate. Custom curves state interpolation, endpoint, and price-basis conventions. Missing or nonpositive price indices invalidate a real conversion.

Each return source declares either total return including reinvested dividends, or price return plus separately booked dividends. It cannot supply both as independent growth. When a source is already net of a fee, the same fee cannot be charged again. For a separately specified annual proportional fee `f`, propose a monthly retained-value factor `(1 - f)^(1/12)`, charged after market growth and before closing cash flows. The fee basis and order appear in results; transaction costs are separate events.

## 5. Monthly event order and ledger

Proposed deterministic order:

1. Load opening balances, ownership, schedules, and jurisdiction state. Apply dated changes effective this month; latch portfolio-triggered changes from the preceding month.
2. Apply investment returns, dividends according to their convention, and asset appreciation. Accrue loan interest under the loan's documented convention.
3. Charge investment fees. Book due external income, property-sale transactions, and other scheduled events. An asset sale removes the asset and records cash proceeds, costs, and debt payoff separately.
4. Build required obligations: essential expenses, contractual debt payments, and tax payments. Include desired discretionary spending separately.
5. Allocate available income and cash, calculate permitted withdrawals, and settle required obligations before optional contributions. Apply remaining priorities in user order subject to eligibility and limits. Recompute coupled tax/withdrawal effects as specified below.
6. Apply scheduled rebalancing, recognizing any costs or taxable consequences through the same settlement process. Finalize the period only after it reconciles.
7. Record closing balances, unpaid obligations, goals, and diagnostics. Evaluate portfolio-threshold milestones on reconciled closing balances; newly met triggers apply next month.

A dated retirement or other milestone applies at its configured month; a threshold-triggered milestone is latched once unless explicitly configured as reversible. Combined conditions state AND/OR semantics, measurement currency/price basis, and which member's age is relevant. Cyclic event dependencies are rejected or reported as unresolved; an iteration must not fire an event twice.

For each account, record `closing = opening + investment gain + external deposits + transfers in - transfers out - withdrawals - fees`. Tax and expense payments from cash are withdrawals with category tags, not an additional subtraction from every source account. Aggregate internal transfers cancel. Loan principal reduces both cash and liability; loan interest is an expense. Net-worth reconciliation additionally includes property changes and liability changes. Every flow has one transaction ID and balanced source/use records.

## 6. Priorities, shortfalls, and coupled calculations

Required obligations outrank optional funding. If available money cannot cover all required obligations, allocate by an explicit user order with a visible deterministic default order; amounts within an equal-priority group are allocated proportionately. Record the unpaid remainder by obligation. The proposed default group order is essential expenses, contractual debt payments, then tax payments. This is a planning allocation convention, not a statement of legal creditor priority.

Account contributions require known eligibility and limits, or an explicit simplified assumption. Never silently claim “maximum permitted” for an unsupported jurisdiction. Withdrawal sources must respect modeled ownership, availability, access restrictions, and balance limits. An emergency fund is a target, not newly created money. No borrowing occurs without an explicit loan or credit facility.

Desired spending is the requested lifestyle amount; funded spending is actual payment; essential spending is the protected subset. A spending floor creates a need, not an automatic source of money. Unmet needs remain in results even when a strategy reduces later requests. Unpaid debt or tax obligations remain outstanding; treatment of arrears, interest, and penalties requires an explicit supported rule or a limitation diagnostic.

Treat tax, withdrawal, subsidy, and transaction effects as one deterministic settlement problem. Start every candidate evaluation from the same opening snapshot, not from the prior candidate's mutated balances. A proposed solver contract uses both monetary-residual tolerance and stable discrete decisions, a recorded iteration cap (proposed 100), cycle detection, and explicit non-convergence. The chosen tolerance and cap are part of run settings. A non-converged period has no valid final success metric; show diagnostics and the last valid period rather than publishing an approximation as settled.

Annual tax liability and payment cash flows are separate. A detailed module defines tax-year aggregation, withholding/estimated payments, reconciliation dates, and carryovers. A simple effective-rate module must name its taxable base and payment timing. Neither may tax an after-tax quick stream again. Detailed statutory rules, subsidies, and penalty formulas remain Stage 4 source-dependent work.

## 7. Worked verification examples

These fixtures verify proposed design arithmetic and semantics, not implemented software.

| Case | Inputs and timing | Expected result |
|---|---|---|
| Q1: zero-return FI | `A=100, I=60, E=40, r=0, w=0.04`; annual closing savings | `S=20`, average monthly savings `20/12`, rate `1/3`, target `1,000`; year 44 is 980, year 45 is 1,000 |
| Q2: already funded | Q1 but `A=1,000` | Zero years to target |
| Q3: unreachable | `A=100, I=40, E=40, r=0, w=0.04` | Target 1,000; balance stays 100; unreachable under constant assumptions |
| Q4: income zero | `A=100, I=0, E=40, r=0` | Savings -40; rate undefined; year 3 has 20 unfunded, assets zero |
| Q5: savings edit | `I=60`; change savings rate to 0.25 | Savings 15, expenses 45, target 1,125 at `w=0.04` |
| L1: monthly ledger | Cash 100, invested assets 1,000; invested growth 10, fee 2; income 50; expenses 40; cash-to-investment transfer 20; all closing flows | Cash 90; invested 1,028; total 1,118 = opening 1,100 + growth 10 + income 50 - expenses 40 - fees 2 |
| L2: shortage | Cash 30; essential expense 40; optional contribution 20; no available withdrawals | Essential funded 30, shortfall 10, contribution 0, cash 0 |
| L3: synthetic tax coupling | Gross withdrawal `W` funds expense 80 and synthetic tax `0.20W`; no other money | `W=100`, tax 20, expense 80, residual zero. This is an algebra fixture, not a statutory tax rate. |
| R1: rate conversion | Real return 0.04, inflation 0.02 over one year | Nominal return 0.0608; nominal 106.08 equals real 104 at index 1.02 |
| S1: schedule boundary | Stream active `[2030-01-01, 2031-01-01)` with occurrences each January 1 | One 2030 occurrence, no 2031 occurrence |

Acceptance requires quick/expanded parity at projection-year boundaries and the same ledger output from interactive and background execution under the same versions and settings.
