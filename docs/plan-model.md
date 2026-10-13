# Conceptual plan model

Status: proposed specification conventions, pending product acceptance before implementation. This is a domain dictionary, not a database schema or API design. Addresses R03 and supports the [calculation contract](calculation-contract.md).

## 1. Identity and ownership

| Entity | Identity and relationship | Required meaning |
|---|---|---|
| User | Stable user ID; zero or more household memberships | Authentication identity; distinct from a person modeled financially |
| Household | Stable household ID | Authorization boundary; all private plans, revisions, observations, runs, jobs, and artifacts belong to exactly one household |
| Membership | User ID plus household ID | Role and lifecycle; a modeled spouse need not be an application user |
| Plan | Stable plan ID within a household | Planning project with a root scenario; no separate financial data format for quick mode |
| Scenario | Stable scenario ID within a plan | Named branch with a current revision; optional parent scenario and fork revision |
| Plan revision | Immutable revision ID, parent revision ID, content digest, schema version | Complete resolved planning state, including assumptions; prior revisions never change in place |
| Member | Stable member ID within a plan | Financially modeled person with birth-date precision and lifespan/retirement settings |
| Account, asset, liability | Separate stable object IDs within a plan | Economic holdings and obligations; same IDs survive revisions unless the objects are replaced |
| Stream, milestone, priority | Stable object IDs and references within a plan | Scheduled economic intent and funding rules; no ownership inferred from labels |
| Observation | Stable observation ID and valuation date | Actual reported balance or transaction; distinct from projection output |
| Run | Stable run ID and immutable manifest | Evaluation of one revision under an explicit mode and settings |
| Job | Stable job ID referencing one run | Scheduling and execution state; retries are attempts, not new plan revisions |
| Artifact | Stable artifact ID referencing run or export | Result table, report, import evidence, or backup with type, digest, ownership, and retention policy |

Stable IDs are opaque and must not serve as authorization. A scenario fork retains the same economic object IDs within the plan while creating a new scenario/revision identity. Cross-household copying assigns new household and object identities and strips grants and source artifacts.

Anonymous quick entry is an unsaved draft using the same input model, not a persisted private plan without an owner. It runs locally where feasible and does not require registration or a household database record. Saving requires an authenticated household and creates the plan/revision identities above. Expansion can remain an unsaved draft until that point. If an anonymous server calculation is later introduced, its retention, abuse limits, and isolation must be specified before use; draft values must not enter normal logs.

## 2. Field dictionary

All monetary fields use a currency code and explicit nominal date or purchasing-power base date. All rates name period, effective/arithmetic interpretation, price basis, fee inclusion, and dividend inclusion. No locale-specific display format may become the storage meaning.

| Record | Essential fields and constraints |
|---|---|
| Revision header | Household/plan/scenario/revision IDs; creation time; valuation month-end; planning end; base currency; schema version; assumption references |
| Member | Birth date or year with precision flag; assumed birthday if needed; relationship; retirement rules; Social Security assumptions; horizon; survivor settings |
| Ownership | Owner IDs and shares summing to 1; legal/tax ownership distinct from beneficiary shares; unsupported ownership forms flagged |
| Location interval | Person/household scope; jurisdiction IDs; start inclusive/end exclusive; currency assumptions; ambiguity or overlap rejected for the same residency dimension |
| Account | Type/module ID; owner references; observed opening balance; currency; tax treatment including unknown; liquidity/access rules; allocation; fee/return assumptions; contribution and beneficiary rules |
| Basis record | Amount, basis kind, currency, effective date, covered account/lot/contribution/conversion, supporting rule version, confidence/source; unknown is distinct from zero |
| Allocation | Asset-class IDs and weights summing to 1; dated changes/glide path; return-series references; cash remains an explicit class |
| Property/other asset | Value at date; ownership; appreciation; purchase/sale schedule; carrying expenses; associated liabilities; income streams; spendability classification |
| Liability | Principal; creditor/type; rate convention; payment schedule; maturity; linked collateral; extra-payoff events; arrears and unsupported-rule status |
| Stream | Kind; signed economic direction; positive amount; currency/price basis; owner/payee; tax character; gross/after-tax status; schedule; enable flag; essential/desired classification where applicable |
| Schedule | Date/age/milestone anchor; inclusive start/exclusive end; recurrence; frequency; end-day policy; price-growth origin; curve/interpolation; occurrence IDs |
| Milestone | Trigger expression; referenced members/assets; measurement basis; date/age/threshold; AND/OR; latched/reversible behavior; dependent events |
| Priority | Ordered position/group; destination or obligation ID; fixed amount/percentage/limit/target mode; percentage base; cap; eligibility source; residual handling |
| Observation | Object ID; effective valuation date; recorded-at date; amount/currency; import batch/source; correction/supersession reference; reconciliation note |
| Assumption | Key; value/unit; source kind; provenance; effective dates; user override; confidence; supported/fallback/unsupported state |

Multiple basis records can be needed for an account; a single aggregate balance cannot stand in for cost basis, Roth contribution basis, conversion cohorts, and inherited-account dates. Stages may accept partial basis records with explicit limitations; missing data cannot be guessed to maximize apparent tax efficiency.

## 3. Assumptions and defaults

Resolve all defaults into the immutable revision or run manifest before calculation. Record whether a value was entered, imported, derived, or defaulted, and record the default policy version. Later changes to application defaults must not modify an existing revision or change its rerun implicitly.

Calculations may derive values, but every derived value references its inputs and formula version. Preserve raw imported data separately where permitted, with import mapping and validation status. Updating a dataset or module offers a new run with a changed manifest; it does not rewrite an old result.

A revision may be saved as incomplete. A run requires that its selected mode's prerequisites are satisfied or an explicit supported fallback is selected. Validation distinguishes errors blocking calculation, warnings requiring visible assumptions, and deferred unsupported capabilities.

## 4. Scenario and revision behavior

Editing a plan creates a new revision. A scenario is a pointer to its latest revision plus lineage, not a mutable bag of values secretly shared by all scenarios. An edit made after a run is queued cannot affect that run's snapshot.

A scenario fork records its parent revision and the changed assumptions. Comparisons use immutable revision IDs and display input differences. Branch edits must not mutate their parent or siblings. Concurrent edits require an expected-base revision; a stale save produces a conflict requiring an explicit merge or new branch rather than silent last-write-wins loss.

Deletion semantics are governed by the [access and operations contract](access-and-operations.md). Reproducibility does not override a user's deletion policy. If required artifacts have expired or been deleted, show that a retained result cannot be rerun; never silently substitute current dependencies.

## 5. Run manifest and result provenance

Every manifest contains household, plan, scenario, and revision IDs; resolved input digest; schema version; engine build/version; calculation-convention version; jurisdiction modules and effective tax years; market-series IDs, versions, and digests; mortality source where used; withdrawal method/version; currency and exchange-rate assumptions; simulation mode/settings; seed and random-generator version where relevant; numerical tolerance; and creation timestamp.

For stochastic execution, include path-generation algorithm, trial-index mapping, ordering rules, and reproducibility environment. Define bitwise versus tolerance-based repeatability in the [analysis contracts](analysis-contracts.md). Engine version plus seed alone is insufficient if defaults, data, or random-number assignment changed.

Results retain period ledgers, outcome definitions/version, diagnostic codes with object IDs and periods, and artifact digests. A report references the original manifest and states whether it is complete, partial, invalid, or no longer reproducible. Regenerating a report from stored results records the renderer version without changing the financial run.

Dependency bundles used by retained reproducible runs remain available subject to licensing and retention policy. If legal redistribution or preservation is unavailable, identify that limitation before describing a run as fully restorable.

## 6. Actuals and projected balances

Actual observations are append-only records with explicit corrections. Importing a duplicate source row must not add the same economic amount twice. A balance observation replaces the valuation at its date for a new baseline; it is not income or a contribution. A transfer recorded at both accounts is one transfer with two legs.

Rebasing a plan selects an observation set and a new valuation date, producing a new revision. Prior projections stay attached to their original revision and valuation date. An actual-versus-projected overlay identifies which forecast vintage is being compared and aligns currency, valuation dates, and price basis. Do not join revised actuals to old forecasts without identifying the correction.

Notes explain changes without altering economic records. A plan's net worth includes qualifying assets less liabilities once; investable assets and available withdrawal assets are separately derived views, with reasons for exclusions.

## 7. Currency and ownership boundaries

Display currency changes formatting only when amounts are already in that currency. Converting economic values requires dated exchange-rate assumptions and a direction convention, proposed units of base currency per unit of foreign currency. FX scenarios and return paths are versioned inputs; missing FX coverage blocks a cross-currency aggregate rather than assuming parity.

A joint asset's full economic value is included once in household totals; ownership shares allocate tax and beneficiary treatment. A mortgage links to its property but is counted once as a liability, not also subtracted from the property value unless that display is explicitly labeled equity. Inheritance and sale proceeds cannot coexist with the transferred asset as a new independent balance after the event.

## 8. Trace verification

The following is a conceptual trace, not evidence of implemented persistence:

| Step | New identity/state | Invariant |
|---|---|---|
| Quick entry | Household H, plan P, scenario S, revision V1; synthetic account A=100, after-tax income 60, expenses 40 | No gross income or taxable basis inferred; inputs use the quick schedule |
| Baseline run | Run U1 pins V1 and dependency bundle D1 | Year 45 reaches 1,000 under the zero-return fixture |
| Expand without edits | Same plan P; revision V2, parent V1, retains identical economic inputs | Annual results match U1; full UI visibility does not itself change money |
| Duplicate and edit spending | Scenario S2 forked from V2; revision V3, expenses 45 | S remains at V2; V3 target is 1,125, savings 15; same economic account ID within P |
| Record actual balance | Observation O1 says A=130 at a later month-end | No 130 income entry; V1–V3 and U1 unchanged |
| Rebase main scenario | Revision V4 references O1 and new valuation date | Opening A is 130, not 230; U2 pins V4 |
| Install data D2 | New optional run U3 with its own manifest | U1 still references D1; replacing D1 silently is forbidden |
| Attempt foreign-household result read | Household X requests U1 | Authorization denies access regardless of knowing U1's ID |

Review checks: V1–V4 lineage is explicit; no balance observation is a cash-flow event; expansion preserves after-tax semantics; comparison identifies revision pairs; all run dependencies and economic references remain addressable until their declared deletion or expiry.
