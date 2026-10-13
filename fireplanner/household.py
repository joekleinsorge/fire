"""Import a private household source without embedding personal data in code."""
from copy import deepcopy

from .engine import project


def import_household(source):
    """Return a planner document with the complete original source attached.

    This is a data-entry adapter, not a tax or retirement recommendation.
    Unknown debt terms cannot be amortized from an escrow-inclusive payment.
    """
    data = source['planner_inputs']
    assumptions = data['planner_assumptions']
    age = assumptions['current_age_years']
    horizon = assumptions['plan_through_age_years'] - age
    retirement = assumptions['retirement_age_years']
    retirement_month = (retirement - age) * 12 + 1
    rate = assumptions['real_portfolio_return_pct'] / 100
    warnings = [
        'Data collection draft; projections are incomplete illustrations, not retirement advice.',
        'Balances retain their source dates. Review stale values before using projections.',
        'Income uses the prior unverified take-home estimate; gross salary and bonus are retained in the source only.',
        'Debt balances are held constant for reference. Payments are already in observed spending; no additional amortization is modeled.',
        'Retirement spending uses the midpoint of the normal target range. Its tax basis and missing allowances remain unresolved.',
        'Retirement accounts remain restricted until a withdrawal-access plan is supplied.',
        'Home value uses the midpoint of the reported range; employer equity uses stated value, not realizable proceeds.',
        'Education assets remain restricted and unassigned. Child birth dates and beneficiary mapping have not been invented.',
        'Project costs are entered as disabled purchases until dates and funding are chosen; month 1 is only a disabled field placeholder.',
        'Contributions, taxes, healthcare, Social Security, and retirement debt payoff are not fully modeled. See the source profile.',
        'Zero real returns on cash, property, and other restricted assets are placeholders, not verified assumptions.',
    ]
    mapping = {'retirement': 'retirement', 'health_savings': 'other',
               'taxable_investment': 'investment', 'cash': 'cash',
               'employer_equity': 'other', 'property': 'property',
               'vehicle': 'other', 'education_restricted': 'other'}
    accounts = []
    for index, row in enumerate(data['accounts']):
        kind = mapping[row['type']]
        balance = row.get('balance_usd', row.get('stated_value_usd', row.get('carrying_value_usd')))
        if balance is None:
            bounds = row['estimated_value_range_usd']
            balance = (bounds['low'] + bounds['high']) / 2
        accounts.append(dict(id=f'import-account-{index}', name=row['name'], type=kind,
                             balance=balance, return_rate=rate if kind in ('investment', 'retirement') else 0,
                             fee_rate=0, available=row['type'] in ('cash', 'taxable_investment'),
                             source_details=deepcopy(row)))
    # Cash receives modeled surplus; preserve all source holdings separately.
    accounts.sort(key=lambda row: row['type'] != 'cash')
    debts = [dict(id=f'import-debt-{index}', name=row['name'], balance=row['balance_usd'],
                  annual_rate=row['apr_pct'] / 100, balance_only=True,
                  payment=row.get('monthly_payment_usd', row.get('reported_monthly_payment_usd')),
                  source_details=deepcopy(row)) for index, row in enumerate(data['debts'])]

    def stream(ident, name, kind, amount, start=1, end=None, essential=True, enabled=True):
        return dict(id=ident, name=name, kind=kind, amount=amount, start_month=start,
                    end_month=end or horizon * 12 + 1, every_months=12,
                    growth_rate=0, enabled=enabled, essential=essential)

    cashflow = data['cash_flow']
    target_range = data['retirement_goal']['normal_annual_spending_target_2026_usd']
    minimum = data['retirement_goal']['minimum_annual_spending_target_2026_usd']
    target = (target_range['low'] + target_range['high']) / 2
    floor = (minimum['low'] + minimum['high']) / 2
    estimate = data['income'].get('prior_net_monthly_estimate_usd')
    streams = [
        stream('import-income', 'Prior take-home estimate — UNVERIFIED', 'income',
               (estimate or 0) * 12, end=retirement_month, enabled=estimate is not None),
        stream('import-essentials', 'Observed essentials incl. debt payments — draft annual repeat',
               'expense', cashflow['recurring_essentials_annual_usd'], end=retirement_month),
        stream('import-other', 'Observed other / one-time spending — draft annual repeat',
               'expense', cashflow['other_and_one_time_residual_annual_usd'],
               end=retirement_month, essential=False),
        stream('import-retirement-minimum', 'Retirement minimum midpoint — tax basis unknown',
               'expense', floor, start=retirement_month),
        stream('import-retirement-lifestyle', 'Retirement normal midpoint above minimum',
               'expense', target - floor, start=retirement_month, essential=False),
    ]
    # Contributions are transfers excluded by the supplied non-transfer spending.
    education = data.get('education_goal', {}).get('observed_monthly_contribution_usd')
    if education:
        streams.append(stream('import-education', '529 funding — duration / beneficiaries unresolved',
                              'expense', education * 12, end=retirement_month, essential=False))
        warnings.append('529 funding is a draft household outflow through planned retirement; future education balances are not forecast until beneficiaries and timing are known.')
    plan = dict(name=data['plan_name'], valuation_date=data['valuation_date'], currency=source['source']['currency'],
                age=age, horizon=horizon, retirement_age=retirement, return_rate=rate,
                withdrawal_rate=assumptions['withdrawal_rate_pct'] / 100,
                accounts=accounts, debts=debts, streams=streams, members=[], child_accounts=[],
                future_purchases=[dict(id=f'import-project-{key}', name=key.replace('_', ' ').title(),
                                       amount=value['estimated_cost_usd'], month=1, enabled=False,
                                       annual_upkeep=0, source_details=deepcopy(value))
                                  for key, value in data['planned_home_projects'].items()],
                household_source=deepcopy(source), import_warnings=warnings,
                unresolved_inputs={key: None for key in data['unknowns_to_preserve_as_null']},
                scenario_assumptions={'status': 'unverified draft', 'real_return_pct': rate * 100})
    project(plan)
    return plan


def draft_scenarios(plan):
    """Explicit stress-test placeholders; source facts remain identical."""
    result = []
    for name, rate in [('Base', plan['return_rate']), ('Conservative', .03), ('Adverse', .01)]:
        candidate = deepcopy(plan)
        candidate['return_rate'] = rate
        candidate['scenario_assumptions'] = dict(status='unverified illustrative placeholder', real_return_pct=rate * 100)
        candidate['import_warnings'].append(f'{name}: {rate * 100:g}% real investment return is an illustrative placeholder, not a verified assumption. Income and spending uncertainties are unchanged.')
        for account in candidate['accounts']:
            if account['type'] in ('investment', 'retirement'):
                account['return_rate'] = rate
        result.append(dict(name=f'{name} — draft assumptions', plan=candidate))
    return result
