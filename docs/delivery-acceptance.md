# Delivery scope and acceptance

Status: target release gates for the product. The repository now contains a partial working implementation; each row below still requires evidence before its capability can be called accepted or complete.

The five stages in [product §17](product-and-architecture.md) are the remaining roadmap. Each stage preserves prior plan semantics and makes unsupported capabilities visible. Cross-cutting requirements become enforceable when the relevant surface first ships; privacy, reconciliation, and provenance are not postponed to Stage 5.

## 1. Stage 1 — Foundation

Proposed boundary: anonymous quick calculator, authenticated saved household plans, manual cash/investment balances, simplified fixed returns, after-tax income and expenses, elementary allocation of surplus/shortfall, and self-hosted operation. Detailed taxes, named advanced withdrawal methods, properties, loan amortization, and stochastic results remain deferred. A simple retirement spending schedule may be projected without claiming advanced tax or strategy support.

| Deliverable | Observable exit criterion | Required evidence |
|---|---|---|
| Self-hosting | Same images support both profiles on one machine; normal local-login operation works with internet and SMTP disabled | Compose install/upgrade/backup/restore instructions; offline operation and restore drill; measured benchmark baseline |
| Household isolation | Two households cannot read/write each other's plans, jobs, artifacts, exports, or membership | Negative authorization tests at each exposed boundary; role matrix matches behavior; operator view excludes plan values |
| Quick calculator | All six inputs, linked savings edits, charts, annual table, and edge-state messages follow calculation §2 | Independently computed Q1–Q5 and boundary tests; savings-rate chart semantics checked |
| Saved plans | Unsaved entry expands and saves into one household model; reopening preserves inputs and assumptions | Quick/expanded result parity; anonymous draft-to-household transition; stale-edit conflict and revision history checks |
| Fixed projections | Account ledger reconciles under visible nominal/real assumptions and defined event timing | L1–L3/R1/S1 fixtures plus multiple-account and same-period event tests; browser/worker parity where both execute |
| Basic accounts and cash flow | Manual balances, liquid/investable/net-worth distinctions, known tax status or explicit unknown, income, expenses, surplus allocation, and shortfalls are visible | A surplus and deficit plan; no double counting of transfers or after-tax income; unsupported access/tax assumptions shown |

Stage 1 must not describe a simplified effective-rate or after-tax plan as a complete US tax model. Synthetic unrestricted assets are a disclosed quick-mode assumption. Detailed scheduling controls and ordered priorities can arrive in Stage 3, but the foundational model must already preserve dates, units, and stable references.

## 2. Stage 2 — Retirement testing

| Deliverable | Observable exit criterion | Required evidence |
|---|---|---|
| Historical testing | Rolling, single-start, selected ranges, stress periods, allocation/glide paths, rebalancing, fees/dividends, and complete/incomplete distinctions work on installed data | Licensed/provenanced dataset manifest; missing-data and total-return fixtures; independently reproduced selected periods |
| Monte Carlo | Resampling, blocks, parametric models, correlations, custom distributions, seeds, and path inspection honor the analysis contract | Repeated seed/version runs, worker-count invariance, invalid-matrix handling, distribution and sampling checks |
| Withdrawal strategies | Every strategy offered has a completed versioned method sheet, source, formula, timing, constraints, and verified examples | Method-sheet gate for all product §8 strategies; unavailable entries labeled; stage cannot claim full strategy coverage while any are pending |
| Detailed results | Survival, essential/desired funding, cuts, first shortfalls, distributions, trial counts, and individual paths have explicit denominators | Analysis classification fixtures; unchanged desired baseline after cuts; incomplete/numerical-error reporting |
| Exports | Printable summary, PDF, annual CSV, simulation CSV, JSON plan backup, and methodology appendix identify versions and limitations | Round-trip JSON plan semantics; CSV/report values reconcile with stored run; exported source/seed/assumption metadata |

Taxes and net estate outcomes unavailable at this stage are marked unsupported or simplified, never fabricated. A published intermediate release may ship a documented strategy subset, but the full Stage 2 target remains incomplete until its strategy gate is met.

## 3. Stage 3 — Lifetime planning

| Deliverable | Observable exit criterion | Required evidence |
|---|---|---|
| Properties | Purchases, sales, appreciation, rental flows, carrying costs, transaction costs, and linked loans reconcile | Purchase/sale fixtures remove assets and liabilities once and create correct cash flows |
| Debts | Supported loan types model interest, contractual payments, extra payments, and payoff events | Independent amortization examples, zero-interest boundary, early payoff, and shortfall/arrears behavior |
| Scheduled events | All product §5 stream types and frequencies, recurrence, growth curves, inflation origin, and disable controls appear on the timeline | Date/age/milestone scheduling; leap-day and interval-boundary checks; disabled stream leaves no cash flow |
| Priorities | Ordered fixed/percentage/limit/target instructions allocate one shared cash pool and honor availability | Competing priorities, equal-priority shortage, emergency-fund target, and unsupported-contribution-limit cases |
| Milestones | Date, age, portfolio, and combined triggers fire consistently and explain movements | Threshold latch, next-period effect, AND/OR, dependency-cycle rejection, and member-specific age examples |
| Scenario comparison | Forked plans show changed assumptions alongside comparable results | Parent immutability, fair shared-path comparisons, no silent change in inflation/currency basis |
| Progress tracking | Manual/CSV observations, corrections, actual history, notes, forecast overlays, and revision history preserve provenance | Duplicate-import handling; observations do not become income; rebasing leaves original forecast available |

Inheritance/windfalls, pensions, annuities, RSU events, education, and charitable spending may be scheduled at this stage with explicit simplified tax treatment; detailed statutory behavior waits for reviewed modules.

## 4. Stage 4 — Tax-aware planning

| Deliverable | Observable exit criterion | Required evidence |
|---|---|---|
| US taxes | Published federal/state/year/circumstance coverage includes the selected target rules; unsupported cells visibly fall back or block | Authoritative sources and module sheets; bracket/threshold/rounding boundary cases; independent reference calculations |
| Account access | Supported contribution, RMD, inherited-account, penalty/exception, Roth, backdoor/mega-backdoor, and SEPP behaviors use required historical data | Eligibility and access fixtures; missing-basis/history diagnostics; no unsupported maximum-contribution assertion |
| Social Security | Manual/estimated benefits, claiming, earnings, spousal/survivor behavior, and reduction scenarios are clearly distinguished | Sourced benefit fixtures and claiming comparisons; survivor transitions; earnings-history limitations |
| ACA | Premiums, eligibility, subsidies, and reconciliation interact with income and withdrawals consistently | Boundary/history cases; subsidy/withdrawal convergence; non-converged results cannot claim success |
| Medicare | Premiums, IRMAA lookback, enrollment assumptions, and independent healthcare growth are explicit | Missing-history behavior, lookback transitions, source-year identification, and independent growth tests |
| Tax analytics | Annual/lifetime taxes, conversions, gains, and withdrawal effects reconcile to the cash ledger | Liability versus payment timing, withholding/reconciliation, no tax on already-after-tax streams, account and household totals |

Initial tax years, states, future-law policy, and complete supported circumstances must be selected before Stage 4 implementation; the broad coverage list is not a claim of nationwide completeness. Professional review requirements and independent reference ownership must be assigned at that gate.

## 5. Stage 5 — Advanced analysis

| Deliverable | Observable exit criterion | Required evidence |
|---|---|---|
| Optimization | Every product §12 search has explicit variables, objectives, constraints, stopping rules, alternatives, and scenario adoption | Feasibility and budget limits; independent validation paths; no unproved global-optimum claim; source plan preserved |
| Longevity | Fixed and mortality-based individual/joint analyses separate alive/shortfall/deceased states from financial rates | Licensed mortality data; probabilities reconcile; joint survivor state; conditional-denominator fixtures |
| Estate planning | Gross estate, debts/costs, taxes, beneficiary receipts, basis, bequests, survivor changes, and conversion effects use supported jurisdiction rules | Death-event fixtures; assets counted once; net beneficiary ledger; unsupported-rule labels |
| International modules | Canada, UK, Australia, Germany, and Netherlands capabilities use published per-country coverage and explicit FX assumptions | Module sources and fixtures; mixed-currency aggregation; account/pension/estate limitations; no display-only conversion |
| Professional collaboration | Explicit per-household grants control any multi-client workflow, exports, and support access | Cross-household negative tests, grant expiry/revocation, audit review, and scoped export tests |

An intermediate international release may cover a subset but cannot claim this full target complete. Professional collaboration does not authorize regulated workflows beyond separately specified scope.

## 6. Cross-cutting product acceptance

| Product area or requirement | Acceptance gate |
|---|---|
| Overview and guided setup | Users can skip optional details, see assumed values and supported coverage, and understand why a date or outcome changes |
| Timeline and cash-flow presentation | Charts, tables, and Sankey flows reconcile with the same ledger; tables provide a nonvisual way to inspect values |
| Retirement spending and results | Essential/desired needs, strategy request, funded spending, and legacy are distinguishable; no unqualified success from unacceptable cuts |
| Responsive and accessible interaction | Quick entry, guided setup, errors, charts, and reports support keyboard operation, explicit labels, visible focus, non-color outcome cues, and usable narrow/wide layouts; formal accessibility target remains a design decision |
| Scenario/sensitivity UI | All product §12 sensitivity dimensions use named units/ranges and preserve their baseline; invalid ranges and unreachable results are explained |
| Private/guest sharing | Per the access matrix, links are scoped/revocable/expiring; public scenarios use reviewed synthetic content, separate storage, and disclosure previews |
| Reports | Exported and on-screen values identify the same revision, engine, data, rule versions, assumptions, and price basis |
| Operations | Quotas, progress, cancellation, bounded retries, protected backups/secrets, independent reviewed updates, health checks, and deletion are tested when their surfaces ship |
| Scientific validity | Independent calculations, ledger invariants, boundary cases, deterministic replay, and explicit model limitations accompany each new capability |

Sharing beyond core membership has no explicit stage in the original roadmap. Proposed placement is Stage 2 for read-only result grants and Stage 3 for sanitized public-scenario publishing; private owner/editor/viewer membership is Stage 1. Sensitivity analysis is proposed for Stage 3 alongside scenario comparison. These placements require acceptance and must not disappear from the roadmap by omission.

## 7. Review disposition

“Specified” below means a proposed contract now exists and has been reviewed as documentation. It does not mean the behavior is approved, implemented, independently scientifically validated, or production-tested.

| Finding | Proposed resolution | Remaining decision or gate |
|---|---|---|
| R01 | Calculation §§2–3: equations, edits, boundaries, expansion parity | Accept annual quick timing, monthly full clock, and visible 100-year horizon default before Stage 1 |
| R02 | Calculation §§1, 3–5: units, timing, inflation, fees, ledger | Select numerical representation and tolerances; accept date/fee conventions before Stage 1 |
| R03 | Plan model §§1–8: identity, immutable revisions, observations, run manifests | Select persistence/schema strategy and licensed dependency-retention approach before implementation |
| R04 | Calculation §§5–7: priority order, shortfalls, settlement | Accept priority defaults; choose/test solver and convergence thresholds; reviewed legal behavior gates Stage 4 |
| R05 | Analysis §§1–3, 9: metrics, populations, reproducibility | Accept outcome definitions, including exact-zero depletion; select data/model settings before Stage 2 |
| R06 | Analysis §4: method-sheet and integration contract | Source and validate every named strategy before enabling it |
| R07 | Analysis §§5–6, 8: coverage, history, longevity, source gates | Select rule years/states, mortality sources, authoritative reviewers, and joint-life method before relevant stages |
| R08 | Access §§1–3: roles, grants, sharing, trust boundary | Accept download/publication rights and signed-link policy; test isolation before exposed surfaces ship |
| R09 | Access §§5–7: retention, deletion, offline recovery, restores | Set retention/RPO/RTO; define recovery and deletion-marker storage; execute restore drill before production |
| R10 | Access §4: states, attempts, quotas, publication race | Select queue/lease/storage implementation and benchmark quota defaults before production |
| R11 | This document §§1–6: stage and cross-cutting acceptance | Accept proposed placement for sharing/sensitivity and formal accessibility target; record measured capacity |
| R12 | Analysis §§7–8 and this document §5: bounded searches, professional grants, source register | Supply missing references; bound any expanded professional workflow before Stage 5 |

## 8. Implementation boundary

Implementation is underway as a local, bounded application. The current build exposes supported calculations and limitations directly; it does not claim acceptance of every proposed convention or completion of the five-stage roadmap. Continue in reversible increments with contract fixtures and runnable verification. Before adding jurisdiction rules, mortality-based claims, licensed data, sharing, or production operations, resolve the corresponding source, policy, and acceptance gates above. Do not describe an unimplemented roadmap capability as complete.

The original product specification is the scope source; the contracts are proposed behavior; this acceptance document is the release checklist; the [review handoff](spec-review-handoff.md) records what was actually reviewed. Future implementation reports must distinguish code tests, reference validation, operational drills, and documentation checks.
