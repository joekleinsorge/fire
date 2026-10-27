"""Versioned, dependency-free planning arithmetic; amounts are constant purchasing power."""
import hashlib
import json
import math
import random
import statistics
from datetime import date
import re
from . import children as child_planning
from . import taxes
from . import social_security as ss_planning

VERSION = '2.4.0'


def is_personal_asset(account):
    """Recognize older imports that stored restricted financial holdings as other."""
    source = account.get('source_details')
    source_type = source.get('type') if isinstance(source, dict) else None
    return account.get('type') == 'property' or (
        account.get('type') == 'other' and source_type not in
        ('health_savings', 'employer_equity', 'education_restricted'))


def number(value, name, minimum=None, maximum=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f'{name} outside supported bounds')
    if integer and int(value) != value:
        raise ValueError(f'{name} must be an integer')
    return int(value) if integer else float(value)


def inputs(plan):
    if not isinstance(plan, dict):
        raise ValueError('plan must be an object')
    defaults = dict(age=30, income=60000, expenses=40000, assets=100000,
                    return_rate=.04, withdrawal_rate=.04, horizon=100)
    p = {k: plan.get(k, v) for k, v in defaults.items()}
    for k in ('income', 'expenses', 'assets'):
        p[k] = number(p[k], k, 0, 1e15)
    p['age'] = number(p['age'], 'age', 0, 150, True)
    p['horizon'] = number(p['horizon'], 'horizon', 1, 150, True)
    p['return_rate'] = number(p['return_rate'], 'return_rate', -.999999999, 10)
    p['withdrawal_rate'] = number(p['withdrawal_rate'], 'withdrawal_rate', 1e-12, 1)
    return p


def metadata(plan, mode):
    valuation_date = plan.get('valuation_date')
    if valuation_date is not None:
        if not isinstance(valuation_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', valuation_date):
            raise ValueError('valuation_date must be an ISO calendar date (YYYY-MM-DD)')
        try:
            date.fromisoformat(valuation_date)
        except ValueError:
            raise ValueError('valuation_date must be a real calendar date') from None
    return dict(engine_version=VERSION, calculation_version='monthly-end-v1',
                outcome_version='separate-outcomes-v1', mode=mode, currency=plan.get('currency', 'USD'),
                valuation_date=valuation_date, price_basis='constant purchasing power at plan start',
                input_digest=hashlib.sha256(json.dumps(plan, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                limitations=['No statutory taxes, benefits, healthcare, or net estate calculation.'])


def _annual(p, rates=None):
    balance = p['assets']
    target = p['expenses'] / p['withdrawal_rate']
    savings = p['income'] - p['expenses']
    crossing = 0 if balance >= target else None
    first_shortfall = None
    annual = [dict(year=0, age=p['age'], balance=balance, unfunded=0.0)]
    for year in range(1, p['horizon'] + 1):
        raw = balance * (1 + (rates[year - 1] if rates is not None else p['return_rate'])) + savings
        if not math.isfinite(raw):
            raise ValueError('projection exceeds numerical range')
        unfunded = max(0.0, -raw)
        balance = max(0.0, raw)
        if unfunded and first_shortfall is None:
            first_shortfall = year
        if crossing is None and first_shortfall is None and balance >= target:
            crossing = year
        annual.append(dict(year=year, age=p['age'] + year, balance=balance, unfunded=unfunded))
    if crossing == 0:
        status = 'already_at_target'
    elif first_shortfall is not None and crossing is None:
        status = 'funding_shortfall'
    elif crossing is not None:
        status = 'target_reached'
    elif rates is None and balance <= p['assets']:
        status = 'unreachable'
    else:
        status = 'not_reached_within_horizon'
    return dict(status=status, target=target, savings=savings, monthly_savings=savings / 12,
                savings_rate=savings / p['income'] if p['income'] else None,
                years_to_target=crossing, retirement_age=p['age'] + crossing if crossing is not None else None,
                first_shortfall_year=first_shortfall, annual=annual)


def quick(plan):
    p = inputs(plan)
    result = _annual(p)
    result['savings_curve'] = []
    if p['income']:
        for i in range(21):
            rate = i / 20
            sample = _annual(dict(p, expenses=p['income'] * (1 - rate)))
            result['savings_curve'].append(dict(savings_rate=rate, status=sample['status'],
                years_to_target=sample['years_to_target'], retirement_age=sample['retirement_age']))
    result['metadata'] = metadata(plan, 'quick')
    result['warnings'] = ['Zero expenses make the target zero.'] if p['expenses'] == 0 else []
    return result


def project(plan):
    """Quick adapter or simplified accounts/streams. Full streams use month indexes [start,end)."""
    p = inputs(plan)
    if _has_family_costs(plan) and not any(key in plan for key in ('accounts', 'streams', 'debts')):
        adapted = _family_adapter(plan, p)
        result = _full_projection(adapted, p)
        result['metadata'] = metadata(plan, 'expanded_quick_family')
        return result
    if not any(key in plan for key in ('accounts', 'streams', 'debts')):
        result = quick(plan)
        monthly = []
        factor = (1 + p['return_rate']) ** (1 / 12)
        balance = p['assets']
        for month in range(1, p['horizon'] * 12 + 1):
            opening = balance
            gain = balance * (factor - 1)
            income = p['income'] if month % 12 == 0 else 0
            expenses = p['expenses'] if month % 12 == 0 else 0
            raw = opening + gain + income - expenses
            balance = max(0.0, raw)
            # Pin anniversaries to the reference recurrence to eliminate accumulated rounding drift.
            if month % 12 == 0:
                balance = result['annual'][month // 12]['balance']
                gain = balance + max(0, -raw) - opening - income + expenses
            monthly.append(dict(month=month, opening=opening, gain=gain, income=income,
                                expenses=expenses, closing=balance, unfunded=max(0, -raw)))
        result['monthly'] = monthly
        result['metadata'] = metadata(plan, 'expanded_quick')
        if 'members' in plan or 'child_accounts' in plan:
            result['children'] = child_planning.project(plan, p['horizon'])
        return result
    result = _full_projection(plan, p)
    return result


def _has_family_costs(plan):
    return bool(plan.get('child_accounts') or plan.get('future_purchases')) or ('future_purchases' in plan and not isinstance(plan['future_purchases'], list))


def _family_adapter(plan, p, retirement_year=None):
    # Preserve quick mode's annual cash timing while sharing the funded monthly ledger.
    income_end = p['horizon'] * 12 + 1 if retirement_year is None else retirement_year * 12 + 1
    return dict(plan, _quick_adapter=True,
        accounts=[dict(type='investment', balance=p['assets'], return_rate=p['return_rate'])],
        streams=[dict(kind='income', amount=p['income'], start_month=12, end_month=max(12, income_end), every_months=12),
                 dict(kind='expense', amount=p['expenses'], start_month=12, every_months=12)])


def _purchases(plan):
    rows = plan.get('future_purchases', [])
    if not isinstance(rows, list) or len(rows) > 200 or any(not isinstance(row, dict) for row in rows):
        raise ValueError('future_purchases must be a bounded list of objects')
    normalized, identifiers = [], set()
    for row in rows:
        ident, name = row.get('id'), row.get('name')
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 80 or ident in identifiers:
            raise ValueError('future purchase ids must be unique non-empty identifiers')
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError('future purchase name must be a non-empty string')
        identifiers.add(ident)
        enabled = row.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValueError('future purchase enabled must be a boolean')
        amount = number(row.get('amount'), 'future purchase amount', 0, 1e15)
        upkeep_years = row.get('upkeep_years')
        if upkeep_years is not None:
            upkeep_years = number(upkeep_years, 'upkeep_years', 1, 150, True)
        loan = number(row.get('loan_amount', 0), 'loan_amount', 0, 1e15)
        if loan > amount:
            raise ValueError('future purchase loan_amount cannot exceed the purchase amount')
        adds_asset = row.get('adds_asset', False)
        if not isinstance(adds_asset, bool):
            raise ValueError('future purchase adds_asset must be a boolean')
        normalized.append(dict(id=ident, name=name, enabled=enabled, amount=amount,
            month=number(row.get('month'), 'future purchase month', 1, 1800, True),
            annual_upkeep=number(row.get('annual_upkeep', 0), 'annual_upkeep', 0, 1e15),
            qualified_home_mortgage=row.get('qualified_home_mortgage',False),property_tax_annual=number(row.get('property_tax_annual',0),'property tax annual',0,1e15),
            upkeep_years=upkeep_years, upkeep_until_purchase_id=row.get('upkeep_until_purchase_id'), loan_amount=loan,
            loan_rate=number(row.get('loan_rate', 0), 'loan_rate', 0, 10),
            loan_months=number(row.get('loan_months', 360), 'loan_months', 1, 1800, True),
            adds_asset=adds_asset,
            asset_return=number(row.get('asset_return', 0), 'asset_return', -.99, 10),
            sell_account_id=row.get('sell_account_id'), payoff_debt_id=row.get('payoff_debt_id'),
            sell_cost_rate=number(row.get('sell_cost_rate', .06), 'sell_cost_rate', 0, .5),
            transaction_costs=number(row.get('transaction_costs', 0), 'transaction_costs', 0, 1e15),
            minimum_cash_reserve=number(row.get('minimum_cash_reserve', 0), 'minimum_cash_reserve', 0, 1e15),
            require_full_funding=row.get('require_full_funding', False),
            nominal_loan=row.get('nominal_loan', False),
            replaces_expense_monthly=number(row.get('replaces_expense_monthly', 0), 'replaces_expense_monthly', 0, 1e15),
            replaces_retirement_expense_monthly=number(row.get('replaces_retirement_expense_monthly', 0), 'replaces_retirement_expense_monthly', 0, 1e15),
            replaces_expense_end_month=number(row.get('replaces_expense_end_month', 1801), 'replaces_expense_end_month', 1, 1801, True)))
        for key in ('require_full_funding', 'nominal_loan','qualified_home_mortgage'):
            if not isinstance(normalized[-1][key], bool):
                raise ValueError(f'{key} must be a boolean')
    for item in normalized:
        stop = item.get('upkeep_until_purchase_id')
        if stop is not None and (not isinstance(stop, str) or stop not in identifiers or stop == item['id']):
            raise ValueError('upkeep_until_purchase_id must reference another saved purchase')
    return normalized


def _household(plan, p):
    """People in the plan and when each planned lifetime ends.

    Without a partner the plan is one person and nothing changes. With a partner, each
    person may set a life expectancy; the first person to reach it ends their owned income
    and Social Security from the month after, and household spending continues at
    survivor_spending of plan. Ages are at the valuation date, like plan age.
    """
    partner = plan.get('partner')
    if partner is None:
        return dict(couple=False, ages=dict(self=p['age']), deaths={}, first_death=None, survivor_spending=1.0)
    if not isinstance(partner, dict):
        raise ValueError('partner must be an object')
    ages = dict(self=p['age'], partner=number(partner.get('age'), 'partner age', 0, 150, True))
    expectancies = dict(self=plan.get('life_expectancy'), partner=partner.get('life_expectancy'))
    deaths = {}
    for who, value in expectancies.items():
        if value is None:
            continue
        value = number(value, f'{who} life_expectancy', 0, 150, True)
        if value <= ages[who]:
            raise ValueError('life expectancy must be after current age')
        month = (value - ages[who]) * 12 + 1
        if month <= p['horizon'] * 12:
            deaths[who] = month
    first = min(((m, who) for who, m in deaths.items()), default=None)
    return dict(couple=True, ages=ages, deaths=deaths, first_death=first,
                survivor_spending=number(plan.get('survivor_spending', 1), 'survivor_spending', 0, 1.5))


def _owner(row, household, label):
    owner = row.get('owner', 'self')
    if owner not in ('self', 'partner') or (owner == 'partner' and not household['couple']):
        raise ValueError(f'{label} owner must be self, or partner when the plan has one')
    return owner


def _household_streams(plan, p, streams, valuation, taxed):
    """Owned income, Social Security, and lifetimes as plain stream rows.

    Returns (streams, social_security, household). Claimed benefits become level monthly
    income in today's dollars from the claim month. For a couple, each spouse may get a
    spousal excess on the other's record while both are alive; at the first death that
    person's owned income and benefit stop and the survivor keeps the larger benefit,
    as a top-up to their own. With the tax model every benefit row is gross Social
    Security income; otherwise benefits are after tax like any other stream.
    """
    household = _household(plan, p)
    for stream in streams:
        _owner(stream, household, 'stream')
    if plan.get('_quick_adapter'):
        return streams, [], household
    end = p['horizon'] * 12 + 1
    # Benefits given only a birth year are timed from their owner's age at valuation.
    owner_age = lambda row: household['ages'][_owner(row, household, 'social security')]
    social_security = ss_planning.normalize(plan, owner_age, p['horizon'] * 12, valuation, number)
    raw = {row.get('id'): row for row in plan.get('social_security', [])}
    for row in social_security:
        row['owner'] = _owner(raw[row['id']], household, 'social security')
    def benefit(ident, row_name, amount, start, stop, owner, enabled=True):
        return dict(id=ident, name=row_name, kind='income', amount=amount, start_month=start, end_month=stop,
                    every_months=1, growth_rate=0.0, enabled=enabled, essential=True, owner=owner,
                    tax_kind='social_security' if taxed else None)
    rows = list(streams) + [benefit('social-security:' + r['id'], r['name'], r['monthly_benefit'], r['start_month'], end,
                                    r['owner'], r['enabled']) for r in social_security]
    # A person's owned income (streams and their benefit) stops when their planned lifetime ends.
    for i, row in enumerate(rows):
        death = household['deaths'].get(row.get('owner', 'self'))
        if death is not None and row.get('kind') == 'income' and death < row.get('end_month', end):
            rows[i] = dict(row, end_month=max(row.get('start_month', 1), death))
    first_death = household['first_death']
    paid = lambda who: [r for r in social_security if r['enabled'] and r['owner'] == who]
    if household['couple']:
        for spouse, worker in (('self', 'partner'), ('partner', 'self')):
            if not paid(spouse) or not paid(worker):
                continue
            amount, start = ss_planning.spousal_excess(paid(spouse)[0], paid(worker)[0])
            stop = first_death[0] if first_death else end
            if amount > 0 and start < stop:
                rows.append(benefit('social-security-spousal:' + spouse, 'Spousal benefit', amount, start, stop, spouse))
    if first_death:
        died, survivor = first_death[1], 'partner' if first_death[1] == 'self' else 'self'
        if paid(died) and paid(survivor):
            gap = max(r['monthly_benefit'] for r in paid(died)) - max(r['monthly_benefit'] for r in paid(survivor))
            start = max(first_death[0], min(r['start_month'] for r in paid(survivor)))
            stop = household['deaths'].get(survivor, end)
            if gap > 0 and start < stop:
                rows.append(benefit('social-security-survivor:' + survivor, 'Survivor benefit', gap, start, stop, survivor))
    return rows, social_security, household


def _spending_strategy(plan):
    """Optional retirement spending rule; None means fixed spending (the default).

    Guardrails: at each retirement anniversary the planned withdrawal rate is compared with
    the rate at retirement start. Above (1 + band) times that rate, discretionary spending
    is cut by `adjustment`; below (1 - band), it is raised by the same proportion. The
    multiplier stays within [floor, ceiling] and never touches essential spending.
    """
    rule = plan.get('spending_strategy')
    if rule is None:
        return None
    if not isinstance(rule, dict) or rule.get('kind', 'fixed') not in ('fixed', 'guardrails'):
        raise ValueError('spending_strategy kind must be fixed or guardrails')
    if rule.get('kind', 'fixed') == 'fixed':
        return None
    return dict(band=number(rule.get('band', .2), 'guardrail band', .01, .9),
                adjustment=number(rule.get('adjustment', .1), 'guardrail adjustment', .01, .5),
                floor=number(rule.get('floor', .7), 'spending floor', 0, 1),
                ceiling=number(rule.get('ceiling', 1.2), 'spending ceiling', 1, 3))


def _upkeep_active(item, month, purchases=()):
    # Upkeep starts the month after purchase and runs for upkeep_years, or indefinitely.
    if not item['enabled'] or item.get('failed') or month <= item['month']:
        return False
    if any(other['id'] == item.get('upkeep_until_purchase_id') and other.get('closed') and month > other['month'] for other in purchases):
        return False
    return item['upkeep_years'] is None or month <= item['month'] + item['upkeep_years'] * 12


def _full_projection(plan, p, rates=None, retain_monthly=True):
    purchases = _purchases(plan)
    children = child_planning.project(plan, p['horizon'], initialize_only=True)
    valuation = date.fromisoformat(plan['valuation_date']) if plan.get('valuation_date') else date.today()
    accounts = plan.get('accounts', [])
    streams = plan.get('streams', [])
    debts = plan.get('debts', [])
    for rows, name, cap in ((accounts, 'accounts', 100), (streams, 'streams', 500), (debts, 'debts', 100)):
        if not isinstance(rows, list) or len(rows) > cap or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{name} must be a bounded list of objects')
    if not accounts and 'accounts' not in plan:
        raise ValueError('full mode requires at least one account')
    def flag(row, key, default):
        value = row.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f'{key} must be a boolean')
        return value
    balances = [number(a.get('balance', 0), 'account balance', 0, 1e15) for a in accounts]
    initial = sum(balances)
    account_rates = [number(a.get('return_rate', p['return_rate']), 'account return', -.999999999, 10) for a in accounts]
    fees = [number(a.get('fee_rate', 0), 'fee_rate', 0, .99) for a in accounts]
    accessible = [flag(a, 'available', not is_personal_asset(a)) and not is_personal_asset(a) for a in accounts]
    access_ages = [number(a['available_from_age'], 'available_from_age', 0, 150) if a.get('available_from_age') is not None else None for a in accounts]
    withdrawal_rates = [number(a.get('withdrawal_tax_rate', 0), 'withdrawal_tax_rate', 0, .95) for a in accounts]
    payroll_deposits = [number(a.get('payroll_contribution_monthly', 0), 'payroll_contribution_monthly', 0, 1e15) for a in accounts]
    household_deposits = [number(a.get('household_contribution_monthly', 0), 'household_contribution_monthly', 0, 1e15) for a in accounts]
    contribution_starts = [number(a.get('contribution_start_month', 1), 'contribution_start_month', 1, 1801, True) for a in accounts]
    contribution_ends = [number(a.get('contribution_end_month', 1), 'contribution_end_month', 1, 1801, True) for a in accounts]
    inflation = number(plan.get('inflation_rate', 0), 'inflation_rate', 0, .5)
    inflation_monthly = (1 + inflation) ** (1 / 12)
    tax_config = plan.get('tax_model') or {}
    taxed = isinstance(tax_config, dict) and tax_config.get('enabled') is True
    streams, social_security, household = _household_streams(plan, p, streams, valuation, taxed)
    survivor_from = household['first_death'][0] if household['first_death'] else None
    tax_ledger = taxes.TaxLedger(dict(plan, streams=streams), accounts)
    for i, a in enumerate(accounts):
        if is_personal_asset(a) and (access_ages[i] is not None or payroll_deposits[i] or household_deposits[i]):
            raise ValueError('personal assets cannot have spending access or payroll contributions')
        if contribution_ends[i] < contribution_starts[i]:
            raise ValueError('contribution end must follow start')
    for a in accounts:
        if a.get('type', 'investment') not in ('cash', 'investment', 'retirement', 'property', 'other'):
            raise ValueError('unsupported account type')
    normalized = []
    for stream in streams:
        if stream.get('kind') not in ('income', 'expense'):
            raise ValueError('stream kind must be income or expense')
        row = dict(id=stream.get('id'),kind=stream['kind'], amount=number(stream.get('amount'), 'stream amount', 0, 1e15),
            start=number(stream.get('start_month', 1), 'start_month', 1, 1801, True),
            end=number(stream.get('end_month', p['horizon'] * 12 + 1), 'end_month', 1, 1801, True),
            every=number(stream.get('every_months', 1), 'every_months', 1, 1200, True),
            growth=number(stream.get('growth_rate', 0), 'growth_rate', -.99, 10),
            enabled=flag(stream, 'enabled', True), essential=flag(stream, 'essential', True),
            requires_purchase_id=stream.get('requires_purchase_id'),tax_kind=stream.get('tax_kind'))
        if row['requires_purchase_id'] is not None and row['requires_purchase_id'] not in {p['id'] for p in purchases}:
            raise ValueError('Stream requires_purchase_id must reference a saved purchase')
        if row['tax_kind'] not in (None,'ordinary','social_security'):
            raise ValueError('Unsupported income stream tax_kind')
        if row['tax_kind'] and not tax_ledger.enabled:
            raise ValueError('Gross taxable income streams require the supported tax model; otherwise enter after-tax income')
        if row['end'] < row['start']:
            raise ValueError('stream end must follow start')
        normalized.append(row)
    debt_rows = []
    for debt in debts:
        balance = number(debt.get('balance', 0), 'debt balance', 0, 1e15)
        balance_only = flag(debt, 'balance_only', False)
        rate = number(debt.get('annual_rate', 0), 'debt annual_rate', 0, 10) / 12
        months = number(debt.get('months', 360), 'debt months', 1, 1800, True)
        payment = balance * rate / (1 - (1 + rate) ** -months) if rate else balance / months
        if debt.get('payment') is not None:
            payment = number(debt['payment'], 'debt payment', 0, 1e15)
        debt_rows.append(dict(balance=balance, rate=rate, payment=payment,
            extra=number(debt.get('extra_payment', 0), 'extra_payment', 0, 1e15), months=months, origin=0, principal=balance,
            balance_only=balance_only, nominal=flag(debt, 'nominal', False),qualified_home_mortgage=flag(debt,'qualified_home_mortgage',False)))
    initial_debt = sum(d['balance'] for d in debt_rows)
    def allocation_index(key):
        ident = plan.get(key)
        if ident is None:
            return None
        matches = [i for i, a in enumerate(accounts) if a.get('id') == ident]
        if len(matches) != 1 or not accessible[matches[0]] or accounts[matches[0]].get('type') not in ('cash', 'investment'):
            raise ValueError(f'{key} must reference one currently available cash or investment account')
        return matches[0]
    order = plan.get('withdrawal_order', 'listed')
    if order not in ('listed', 'tax_efficient'):
        raise ValueError('withdrawal_order must be listed or tax_efficient')
    # A tax-efficient order spends cash first, then taxable, then pre-tax, then Roth, and
    # restricted holdings last, keeping the listed order within each group. Accounts without
    # a tax_treatment rank by type: cash, investment as taxable, retirement as pre-tax.
    # Surplus deposits still go to the first listed account. The overflow cash bucket
    # (index len(accounts)) is cash.
    treatment_rank = dict(cash=0, taxable=1, pretax=2, roth_qualified=3, restricted=4)
    type_rank = dict(cash=0, investment=1, retirement=2)
    def order_key(i):
        if i >= len(accounts):
            return 0
        treatment = accounts[i].get('tax_treatment')
        if treatment is None:
            return type_rank.get(accounts[i].get('type', 'investment'), 1)
        return treatment_rank.get(treatment, 4)
    def withdrawal_sequence(indices):
        return indices if order == 'listed' else sorted(indices, key=order_key)
    surplus_index = allocation_index('surplus_account_id')
    reserve_index = allocation_index('reserve_account_id')
    reserve_target = number(plan.get('cash_reserve_target', 0), 'cash_reserve_target', 0, 1e15)
    if reserve_target and reserve_index is None:
        raise ValueError('cash_reserve_target requires reserve_account_id')
    # Financed purchases originate a debt in the purchase month; payments start the month after.
    for item in purchases:
        if item['enabled'] and item['loan_amount']:
            rate = item['loan_rate'] / 12
            loan, months = item['loan_amount'], item['loan_months']
            payment = loan * rate / (1 - (1 + rate) ** -months) if rate else loan / months
            debt_rows.append(dict(balance=0.0, rate=rate, payment=payment, extra=0.0, months=months,
                                  origin=item['month'], principal=loan, purchase_id=item['id'], nominal=item['nominal_loan'],qualified_home_mortgage=item['qualified_home_mortgage']))
    def resolve(rows, key, label):
        for item in purchases:
            ident = item[key]
            if ident is None:
                item[key + '_index'] = None
                continue
            matches = [i for i, row in enumerate(rows) if row.get('id') == ident]
            if not isinstance(ident, str) or len(matches) != 1:
                raise ValueError(f'future purchase {key} must reference one {label} in this plan')
            item[key + '_index'] = matches[0]
    resolve(accounts, 'sell_account_id', 'account')
    resolve(debts, 'payoff_debt_id', 'debt')
    purchase_assets = [dict(id=item['id'], month=item['month'], value=0.0, rate=item['asset_return'], amount=item['amount'])
                       for item in purchases if item['enabled'] and item['adds_asset']]
    # Income is available immediately; withdrawals follow the user's account order.
    available_indices = [i for i, available in enumerate(accessible) if available or
                         (not is_personal_asset(accounts[i]) and access_ages[i] is not None and p['age'] >= access_ages[i])]
    monthly, annual, purchase_events, conversion_events = [], [], [], []
    first_shortfall = None
    total_unfunded = 0.0
    retirement_age = number(plan.get('retirement_age', p['age']), 'retirement_age', 0, 300, True)
    retirement_month = max(0, round((retirement_age - p['age']) * 12))
    retirement_balance = initial if retirement_month == 0 else None
    retirement_start = retirement_month + 1
    retirement_streams = [row for row in normalized if row['enabled'] and row['start'] <= retirement_start < row['end']]
    # Spending is already at the survivor level if the first death precedes retirement.
    survivor_at_retirement = household['survivor_spending'] if survivor_from is not None and survivor_from <= retirement_start else 1.0
    def annualized_stream(row):
        return row['amount'] * (survivor_at_retirement if row['kind'] == 'expense' else 1.0) * (1 + row['growth']) ** ((retirement_start - row['start']) / 12) * 12 / row['every']
    annual_desired_spending = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'expense')
    annual_retirement_income = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'income')
    if plan.get('_quick_adapter'):
        annual_desired_spending, annual_retirement_income = p['expenses'], 0.0
    # Open-ended upkeep is permanent retirement spending; time-limited upkeep is temporary, like child funding.
    annual_desired_spending += sum(row['annual_upkeep'] for row in purchases
                                   if row['enabled'] and row['upkeep_years'] is None and row['month'] <= p['horizon'] * 12)
    annual_desired_spending = max(0.0, annual_desired_spending - sum(row['replaces_retirement_expense_monthly'] * 12 for row in purchases
                                   if row['enabled'] and row['month'] <= p['horizon'] * 12))
    annual_net_spending = max(0.0, annual_desired_spending - annual_retirement_income)
    strategy = _spending_strategy(plan)
    retirement_essential_spending = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'expense' and row['essential'])
    retirement_discretionary_spending = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'expense' and not row['essential'])
    spending_factor = lowest_spending_factor = 1.0
    initial_withdrawal_rate = None
    target = annual_net_spending / p['withdrawal_rate']
    if not all(math.isfinite(value) for value in (annual_desired_spending, annual_retirement_income, target)):
        raise ValueError('retirement target exceeds numerical range')
    initial_available = sum(balances[i] for i in available_indices)
    retirement_available_balance = initial_available if retirement_month == 0 else None
    retirement_survives = True
    retirement_essential = True
    retirement_desired = True
    accumulation_shortfall = 0.0
    first_retirement_shortfall = None
    retirement_shortfall_months = longest_retirement_shortfall_months = consecutive_retirement_shortfall = 0
    retirement_essential_unfunded = retirement_desired_unfunded = 0.0
    fields = ('tax_refund_income', 'conversion_gross', 'conversion_tax', 'income_taxes', 'rmd_gross', 'income', 'expenses', 'essential_expenses', 'funded_expenses', 'unfunded', 'payroll_contributions', 'household_account_contributions', 'account_contribution_due', 'account_contribution_unfunded', 'withdrawal_taxes', 'debt_inflation_adjustment', 'purchase_funding_gap', 'purchase_blocked',
              'essential_unfunded', 'desired_expenses', 'desired_unfunded', 'debt_payment', 'debt_due', 'debt_unfunded', 'debt_interest', 'debt_principal', 'gain', 'fees', 'purchase_due', 'purchase_paid', 'purchase_unfunded', 'purchase_upkeep', 'purchase_asset_added', 'purchase_loan_drawn', 'purchase_sale_proceeds', 'purchase_sale_costs', 'purchase_debt_payoff', 'child_contributions', 'child_contribution_due', 'child_education', 'child_education_due', 'child_unfunded')
    for month in range(1, p['horizon'] * 12 + 1):
        tax_ledger.begin_month()
        # Age is measured at the beginning of each month. An access assumption
        # never unlocks a property, HSA, or education holding implicitly.
        available_indices = [i for i, a in enumerate(accounts) if not is_personal_asset(a) and
                             (accessible[i] or (access_ages[i] is not None and p['age'] + (month - 1) / 12 >= access_ages[i]))]
        if len(balances) > len(accounts):
            available_indices.append(len(accounts))
        opening = sum(balances) + sum(a['value'] for a in purchase_assets)
        gain = fee = investment_taxes = 0.0
        for asset in purchase_assets:
            earned = asset['value'] * ((1 + asset['rate']) ** (1 / 12) - 1)
            asset['value'] += earned
            gain += earned
        for i, account in enumerate(accounts):
            account_open=balances[i]
            rate = account_rates[i]
            if rates is not None and account.get('type', 'investment') in ('investment', 'retirement'):
                rate = max(-1, rate + rates[(month - 1) // 12] - p['return_rate'])
            earned = balances[i] * ((1 + rate) ** (1 / 12) - 1)
            balances[i] += earned
            charged = balances[i] * (1 - (1 - fees[i]) ** (1 / 12))
            balances[i] -= charged
            gain += earned
            fee += charged
            if tax_ledger.enabled:
                tax=tax_ledger.investment_income(i,account_open,month)
                if tax>balances[i]+1e-8:raise ValueError('Entered investment income yield/tax exceeds available holding')
                balances[i]-=tax;investment_taxes+=tax
        payroll_contributions = 0.0
        for i in range(len(accounts)):
            if contribution_starts[i] <= month < contribution_ends[i]:
                balances[i] += payroll_deposits[i]
                payroll_contributions += payroll_deposits[i]
                tax_ledger.deposit(i,payroll_deposits[i])
        due = [row for row in normalized if row['enabled'] and row['start'] <= month < row['end'] and (month-row['start']) % row['every'] == 0 and (not row['requires_purchase_id'] or any(p['id']==row['requires_purchase_id'] and p.get('closed') for p in purchases))]
        amounts = [(row, row['amount'] * (1 + row['growth']) ** ((month-row['start']) / 12)) for row in due]
        if survivor_from is not None and month >= survivor_from:
            amounts = [(row, value * household['survivor_spending'] if row['kind'] == 'expense' else value) for row, value in amounts]
        gross_taxable_income=sum(value for row,value in amounts if row['kind']=='income' and row['tax_kind'])
        income_taxes=tax_ledger.income_tax(month,gross_taxable_income) if tax_ledger.enabled else 0.0
        wage_net,wage_ids=tax_ledger.wage_net(month) if tax_ledger.enabled else (None,set())
        tax_refund_income=tax_ledger.refund(month) if tax_ledger.enabled else 0.0
        income = sum(value for row, value in amounts if row['kind'] == 'income' and row['id'] not in wage_ids)-income_taxes+(wage_net or 0)+tax_refund_income
        essential = sum(value for row, value in amounts if row['kind'] == 'expense' and row['essential'])
        essential = max(0.0, essential - sum(item['replaces_expense_monthly'] for item in purchases
                        if item.get('closed') and item['month'] < month < item['replaces_expense_end_month']) -
                        sum(item['replaces_retirement_expense_monthly'] for item in purchases
                            if item.get('closed') and item['month'] < month and month >= retirement_start))
        desired = sum(value for row, value in amounts if row['kind'] == 'expense' and not row['essential'])
        if strategy and month >= retirement_start:
            if (month - retirement_start) % 12 == 0:
                available_now = sum(balances[i] for i in available_indices)
                planned = max(0.0, retirement_essential_spending + retirement_discretionary_spending * spending_factor
                              - annual_retirement_income)
                if available_now > 0:
                    rate = planned / available_now
                    if initial_withdrawal_rate is None:
                        initial_withdrawal_rate = rate
                    elif rate > initial_withdrawal_rate * (1 + strategy['band']):
                        spending_factor = max(strategy['floor'], spending_factor * (1 - strategy['adjustment']))
                    elif rate < initial_withdrawal_rate * (1 - strategy['band']):
                        spending_factor = min(strategy['ceiling'], spending_factor * (1 + strategy['adjustment']))
                lowest_spending_factor = min(lowest_spending_factor, spending_factor)
            desired *= spending_factor
        cash = income
        withdrawal_taxes = investment_taxes
        def pay(amount,allowed_indices=None):
            nonlocal cash, withdrawal_taxes
            from_income = min(cash, amount)
            cash -= from_income
            remaining = amount - from_income
            for i in withdrawal_sequence(available_indices if allowed_indices is None else allowed_indices):
                if tax_ledger.enabled and i < len(accounts):
                    taken,withheld = tax_ledger.draw(i,remaining,balances[i],month)
                else:
                    tax_rate = withdrawal_rates[i] if i < len(withdrawal_rates) else 0.0
                    taken = min(balances[i], remaining / (1 - tax_rate))
                    withheld = taken * tax_rate
                balances[i] -= taken
                withdrawal_taxes += withheld
                remaining = max(0.0, remaining - (taken - withheld))
            return amount - remaining, remaining
        conversion_gross=conversion_tax=0.0
        if tax_ledger.enabled:
            for conversion in tax_ledger.conversions:
                if conversion['month']!=month:continue
                source,target=conversion['source_index'],conversion['target_index'];state=tax_ledger.state(month)
                amount=conversion['amount'] if conversion['amount'] is not None else tax_ledger.fill_amount(conversion,state,balances[source])
                if amount<=0:continue
                cost=tax_ledger.increment(state,amount,0)
                allowed=[i for i in available_indices if i<len(accounts) and accounts[i]['tax_treatment'] in ('cash','taxable') and i not in (source,target)]
                state['ordinary']+=amount
                liquid=cash+tax_ledger.liquidity(allowed,balances,month)
                reserve=number(conversion.get('minimum_liquid_reserve',0),'conversion reserve',0,1e15)
                funded=balances[source]+1e-8>=amount and liquid+1e-8>=cost+reserve
                event=dict(month=month,source_account_id=accounts[source].get('id'),target_account_id=accounts[target].get('id'),amount=amount,tax=cost,executed=funded,funding_gap=max(0,cost+reserve-liquid),source_balance_gap=max(0,amount-balances[source]))
                conversion_events.append(event)
                if not funded:state['ordinary']-=amount;continue
                state['tax']+=cost;state['surcharge']+=amount*tax_ledger.surcharge
                balances[source]-=amount;balances[target]+=amount
                paid,unpaid=pay(cost,allowed)
                if unpaid>1e-4:raise ValueError('Conversion tax funding failed after preflight; no result accepted')
                withdrawal_taxes+=paid;conversion_gross+=amount;conversion_tax+=paid
        essential_paid, essential_unfunded = pay(essential)
        debt_payment = debt_due = debt_unfunded = debt_interest = debt_principal = debt_inflation_adjustment = 0.0
        debt_ledger = []
        qualified_interest=0.0
        qualified_debt=sum(d['balance'] for d in debt_rows if d.get('qualified_home_mortgage'))
        debt_limit_factor=min(1,750000/tax_ledger.price(month)/qualified_debt) if tax_ledger.enabled and qualified_debt else 1.0
        for debt in debt_rows:
            if debt.get('balance_only'):
                debt_ledger.append(dict(opening=debt['balance'], interest=0, due=0, payment=0,
                                        principal=0, unfunded=0, balance=debt['balance'], balance_only=True))
                continue
            if month <= debt['origin']:
                continue
            debt_open = debt['balance']
            if debt.get('nominal'):
                deflation = debt['balance'] * (1 - 1 / inflation_monthly)
                debt['balance'] -= deflation
                debt_inflation_adjustment += deflation
            interest = debt['balance'] * debt['rate']
            debt['balance'] += interest
            payment_factor = (1 + inflation) ** (-(month - debt['origin']) / 12) if debt.get('nominal') else 1.0
            required = min(debt['balance'], (debt['payment'] + debt['extra']) * payment_factor)
            matured = month - debt['origin'] >= debt['months']
            if matured:
                required = debt['balance']
            paid, unpaid = pay(required)
            debt['balance'] -= paid
            debt_payment += paid
            debt_due += required
            # Missed scheduled payments are capitalized and reported once. After
            # maturity the whole balance is due each month, so only the part not
            # already reported (mostly new interest) is a new shortfall.
            arrears = debt.setdefault('arrears', 0.0)
            if matured:
                debt_unfunded += max(0.0, unpaid - arrears)
                debt['arrears'] = unpaid
            else:
                debt_unfunded += unpaid
                debt['arrears'] = arrears + unpaid
            debt_interest += interest
            if debt.get('qualified_home_mortgage'):qualified_interest+=min(paid,interest)*debt_limit_factor
            # Payments settle accrued interest first. If cash is insufficient even
            # for interest, the unpaid interest is capitalized above; it is not
            # negative principal repayment.
            principal_paid = max(0.0, paid - interest)
            debt_principal += principal_paid
            debt_ledger.append(dict(opening=debt_open, interest=interest, due=required, payment=paid,
                                    principal=principal_paid, unfunded=unpaid, balance=debt['balance']))
        desired_paid, desired_unfunded = pay(desired)
        household_account_contributions = account_contribution_due = account_contribution_unfunded = 0.0
        for i in range(len(accounts)):
            if contribution_starts[i] <= month < contribution_ends[i] and household_deposits[i]:
                paid, unpaid = pay(household_deposits[i])
                balances[i] += paid
                tax_ledger.deposit(i,paid)
                household_account_contributions += paid
                account_contribution_due += household_deposits[i]
                account_contribution_unfunded += unpaid
        child_cash = dict(contributions=0.0, contribution_due=0.0, education=0.0, education_due=0.0, unfunded=0.0)
        if (valuation.month + month) % 12 == 0:
            year = valuation.year + (valuation.month + month - 1) // 12
            child_cash = child_planning.advance(children, year, pay,
                year_fraction=month / 12 if not children['annual'] else 1)
        # Selling an existing asset and retiring its debt happen before the new purchase is paid.
        sale_proceeds = sale_costs = payoff = purchase_funding_gap = 0.0
        purchase_blocked = 0
        for item in purchases:
            if not item['enabled'] or item['month'] != month:
                continue
            proceeds = 0.0
            if item['require_full_funding']:
                sale_index, debt_index = item['sell_account_id_index'], item['payoff_debt_id_index']
                expected_sale = balances[sale_index] * (1 - item['sell_cost_rate']) if sale_index is not None else 0.0
                expected_payoff = debt_rows[debt_index]['balance'] if debt_index is not None else 0.0
                required = item['amount'] - item['loan_amount'] + item['transaction_costs'] + expected_payoff + item['minimum_cash_reserve']
                funding_indices=[i for i in available_indices if i != sale_index]
                if tax_ledger.enabled:
                    liquidity = cash + expected_sale + tax_ledger.liquidity([i for i in funding_indices if i < len(accounts)],balances,month) + sum(balances[i] for i in funding_indices if i >= len(accounts))
                else:
                    liquidity = cash + expected_sale + sum(balances[i] * (1 - (withdrawal_rates[i] if i < len(withdrawal_rates) else 0)) for i in funding_indices)
                event=dict(id=item['id'], name=item['name'], month=month,
                           required_cash_after_sale=required-item['minimum_cash_reserve']-expected_sale,
                           liquid_reserve_required=item['minimum_cash_reserve'],
                           funding_gap=max(0.0, required-liquidity), executed=liquidity+1e-8>=required)
                purchase_events.append(event)
                if liquidity + 1e-8 < required:
                    item['failed'] = True
                    item['blocked_debt_payoff'] = expected_payoff if sale_index is None else 0.0
                    purchase_blocked += 1
                    purchase_funding_gap += required - liquidity
                    continue
            item['closed'] = True
            if item['sell_account_id_index'] is not None:
                value = balances[item['sell_account_id_index']]
                balances[item['sell_account_id_index']] = 0.0
                sale_costs += value * item['sell_cost_rate']
                proceeds = value * (1 - item['sell_cost_rate'])
                sale_proceeds += proceeds
                cash += proceeds
            if item['payoff_debt_id_index'] is not None:
                debt = debt_rows[item['payoff_debt_id_index']]
                paid, _ = pay(debt['balance'] if item['require_full_funding'] else min(debt['balance'], proceeds))
                debt['balance'] -= paid
                payoff += paid
        debt_payment += payoff
        debt_principal += payoff
        purchase_due = sum(item['amount'] - item['loan_amount'] + item['transaction_costs'] + item.get('blocked_debt_payoff', 0) for item in purchases if item['enabled'] and item['month'] == month)
        blocked_due = sum(item['amount'] - item['loan_amount'] + item['transaction_costs'] + item.get('blocked_debt_payoff', 0) for item in purchases if item.get('failed') and item['month'] == month)
        upkeep = sum(item['annual_upkeep'] / 12 for item in purchases if _upkeep_active(item, month, purchases))
        purchase_paid, purchase_unfunded = pay(purchase_due - blocked_due + upkeep)
        purchase_unfunded += blocked_due
        # Allocate funded purchase cash in input order, before upkeep. Missing
        # cash is an explicit shortfall, never a free addition to net worth.
        funded_cash = min(purchase_paid, purchase_due)
        funded_values = {}
        for item in purchases:
            if item['enabled'] and item['month'] == month:
                if item.get('failed'):
                    funded_values[item['id']] = 0.0
                    continue
                paid = min(funded_cash, item['amount'] - item['loan_amount'] + item['transaction_costs'])
                funded_cash -= paid
                funded_values[item['id']] = min(paid, item['amount'] - item['loan_amount']) + item['loan_amount']
        purchase_asset_added = 0.0
        for asset in purchase_assets:
            if asset['month'] == month:
                asset['value'] = funded_values[asset['id']]
                purchase_asset_added += asset['value']
        for debt in debt_rows:
            if debt['origin'] and debt['origin'] == month:
                item = next(item for item in purchases if item['id'] == debt['purchase_id'])
                debt['balance'] = 0.0 if item.get('failed') else debt['principal']
        purchase_loan_drawn = sum(item['loan_amount'] for item in purchases if item['enabled'] and not item.get('failed') and item['month'] == month)
        asset_value = sum(a['value'] for a in purchase_assets)
        # If every account is unavailable, keep surplus in an explicit liquid cash ledger.
        rmd_gross=0.0
        if tax_ledger.enabled:
            rmd_gross,rmd_net,rmd_tax=tax_ledger.rmd(month,balances)
            cash+=rmd_net;withdrawal_taxes+=rmd_tax
        if reserve_index is not None:
            reserve_deposit = min(cash, max(0.0, reserve_target - balances[reserve_index]))
            balances[reserve_index] += reserve_deposit
            tax_ledger.deposit(reserve_index,reserve_deposit)
            cash -= reserve_deposit
        if surplus_index is not None:
            balances[surplus_index] += cash
            tax_ledger.deposit(surplus_index,cash)
        elif available_indices:
            balances[available_indices[0]] += cash
            tax_ledger.deposit(available_indices[0],cash)
        else:
            if len(balances) == len(accounts):
                balances.append(0.0)
                available_indices.append(len(accounts))
            balances[-1] += cash
        if tax_ledger.enabled:
            property_tax=sum(item['property_tax_annual']/12 for item in purchases if item.get('closed') and item['month']<month)
            tax_ledger.record_home_deductions(month,qualified_interest,property_tax)
            tax_ledger.settle_year(month)
        tax_ledger.finish_month(month,balances)
        closing = sum(balances) + asset_value
        if not math.isfinite(closing):
            raise ValueError('projection exceeds numerical range')
        unfunded = essential_unfunded + desired_unfunded + debt_unfunded + child_cash['unfunded'] + purchase_unfunded
        total_unfunded += unfunded
        if unfunded > 1e-8 and first_shortfall is None:
            first_shortfall = month
        debt_balance = sum(d['balance'] for d in debt_rows)
        if not all(math.isfinite(value) for value in (debt_balance, total_unfunded, income, essential, desired)):
            raise ValueError('projection exceeds numerical range')
        row = dict(month=month, opening=opening, closing=closing, balance=closing,
            available_balance=sum(balances[i] for i in available_indices), net_worth=closing-debt_balance,
            gain=gain, fees=fee, income=income, expenses=essential+desired+purchase_due+upkeep+child_cash['contribution_due']+child_cash['education_due'], essential_expenses=essential,
            tax_refund_income=tax_refund_income,conversion_gross=conversion_gross,conversion_tax=conversion_tax,income_taxes=income_taxes,rmd_gross=rmd_gross, payroll_contributions=payroll_contributions, withdrawal_taxes=withdrawal_taxes, debt_inflation_adjustment=debt_inflation_adjustment,
            household_account_contributions=household_account_contributions, account_contribution_due=account_contribution_due, account_contribution_unfunded=account_contribution_unfunded,
            purchase_funding_gap=purchase_funding_gap, purchase_blocked=purchase_blocked,
            purchase_due=purchase_due, purchase_paid=purchase_paid, purchase_unfunded=purchase_unfunded, purchase_upkeep=upkeep,
            purchase_asset_added=purchase_asset_added, purchase_loan_drawn=purchase_loan_drawn, purchase_asset_value=asset_value,
            purchase_sale_proceeds=sale_proceeds, purchase_sale_costs=sale_costs, purchase_debt_payoff=payoff,
            child_contributions=child_cash['contributions'], child_contribution_due=child_cash['contribution_due'],
            child_education=child_cash['education'], child_education_due=child_cash['education_due'], child_unfunded=child_cash['unfunded'],
            funded_expenses=essential_paid+desired_paid+purchase_paid+child_cash['contributions']+child_cash['education'], unfunded=unfunded, essential_unfunded=essential_unfunded,
            desired_expenses=desired, desired_unfunded=desired_unfunded,
            debt_payment=debt_payment, debt_due=debt_due, debt_unfunded=debt_unfunded, debt_balance=debt_balance,
            debt_interest=debt_interest, debt_principal=debt_principal, debts=debt_ledger, accounts=list(balances),
            spending_factor=spending_factor)
        if month <= retirement_month:
            accumulation_shortfall += unfunded
        else:
            retirement_essential_unfunded += essential_unfunded + debt_unfunded
            retirement_desired_unfunded += desired_unfunded + purchase_unfunded + child_cash['unfunded'] + account_contribution_unfunded
            if unfunded - blocked_due + account_contribution_unfunded > 1e-8:
                if first_retirement_shortfall is None:first_retirement_shortfall=month
                retirement_shortfall_months+=1;consecutive_retirement_shortfall+=1
                longest_retirement_shortfall_months=max(longest_retirement_shortfall_months,consecutive_retirement_shortfall)
            else:consecutive_retirement_shortfall=0
            retirement_survives = retirement_survives and row['available_balance'] > 1e-8
            retirement_essential = retirement_essential and essential_unfunded + debt_unfunded <= 1e-8
            retirement_desired = retirement_desired and desired_unfunded + purchase_unfunded + child_cash['unfunded'] + account_contribution_unfunded <= 1e-8
        if month == retirement_month:
            retirement_balance = closing
            retirement_available_balance = row['available_balance']
        if (month - 1) % 12 == 0:
            year_row = dict(year=(month-1)//12+1, age=p['age']+(month-1)//12+1, opening=opening, **{key:0.0 for key in fields})
        for key in fields:
            year_row[key] += row[key]
        if month % 12 == 0:
            year_row.update({key:row[key] for key in ('balance','available_balance','net_worth','debt_balance','accounts','purchase_asset_value','spending_factor')})
            annual.append(year_row)
        if retain_monthly:
            monthly.append(row)
    has_window = retirement_month < p['horizon'] * 12
    years_to_target = 0 if p['age'] >= retirement_age and initial_available >= target else next(
        (row['year'] for row in annual if row['age'] >= retirement_age and row['available_balance'] >= target), None)
    # Unlike fi_age, this ignores the planned retirement age, so trade-offs that
    # move the crossing earlier or later stay visible.
    earliest_fi_age = p['age'] if initial_available >= target else next(
        (row['age'] for row in annual if row['available_balance'] >= target), None)
    target_fields = dict(target=target, annual_desired_spending=annual_desired_spending,
        annual_retirement_income=annual_retirement_income, annual_net_spending=annual_net_spending,
        years_to_target=years_to_target, retirement_age=retirement_age,
        fi_age=p['age'] + years_to_target if years_to_target is not None else None,
        earliest_fi_age=earliest_fi_age)
    target_metadata = dict(
        basis='Enabled after-tax streams active at the start of retirement, annualized by recurrence at their retirement-start purchasing-power amounts; debt payments and one-time purchases excluded. Open-ended upkeep for enabled purchases within the horizon is included; time-limited upkeep, purchase loan payments, and temporary child funding are excluded.',
        target_label='FI target from annualized retirement spending less income',
        balance_label='Available account assets',
        crossing_label='First year-end at or after retirement with available assets at the FI target',
        annual_desired_spending_label='Annualized retirement expenses',
        annual_net_spending_label='Annualized retirement expenses less income')
    summary = dict(initial_assets=initial, initial_debt=initial_debt, ending_assets=closing,
        ending_net_worth=closing-debt_balance, total_unfunded=total_unfunded,
        payroll_contributions=sum(r['payroll_contributions'] for r in annual),
        household_account_contributions=sum(r['household_account_contributions'] for r in annual),
        account_contribution_unfunded=sum(r['account_contribution_unfunded'] for r in annual),
        withdrawal_taxes=sum(r['withdrawal_taxes'] for r in annual),
        purchase_funding_gap=sum(r['purchase_funding_gap'] for r in annual),
        blocked_purchases=sum(r['purchase_blocked'] for r in annual),
        purchase_events=purchase_events,conversion_events=conversion_events,
        conversion_gross=sum(r['conversion_gross'] for r in annual),conversion_tax=sum(r['conversion_tax'] for r in annual),blocked_conversions=sum(not e['executed'] for e in conversion_events),
        first_shortfall_age=p['age']+(first_shortfall / 12) if first_shortfall else None,
        first_retirement_shortfall_age=p['age']+(first_retirement_shortfall/12) if first_retirement_shortfall else None,
        retirement_shortfall_months=retirement_shortfall_months,longest_retirement_shortfall_months=longest_retirement_shortfall_months,
        retirement_essential_unfunded=retirement_essential_unfunded,retirement_desired_unfunded=retirement_desired_unfunded,
        rmd_gross=sum(r['rmd_gross'] for r in annual),tax_refund_income=sum(r['tax_refund_income'] for r in annual),
        retirement_balance=retirement_balance, retirement_available_balance=retirement_available_balance,
        spending_strategy=strategy, lowest_spending_factor=lowest_spending_factor, **target_fields)
    return dict(**target_fields, tax_analysis=tax_ledger.report(), children=children, future_purchases=purchases, social_security=social_security, target_metadata=target_metadata, monthly=monthly, annual=annual, summary=summary, first_shortfall_month=first_shortfall,
        accumulation_shortfall=accumulation_shortfall,
        portfolio_survives=retirement_survives if has_window else None,
        essential_spending_funded=retirement_essential if has_window else None,
        desired_lifestyle_funded=retirement_desired if has_window else None,
        metadata=metadata(plan, 'full'), warnings=['Income streams are entered after tax. Withdrawal taxes use the explicitly selected 2026 MFJ Florida module or entered effective rates. Tax module assumptions and exclusions appear in tax_analysis.',
            'Payroll contributions are deposits already excluded from take-home income. Do not deduct them again as expenses.',
            'Purchases marked require_full_funding do not sell assets, originate loans or incur upkeep when funding including the entered reserve is insufficient.',
            'Nominal loans use entered inflation to express future payments and balances in plan-start purchasing power.',
            'Underfunded purchases add only funded cost to asset value; a partial value does not mean a purchase can close.',
            'Debt interest uses annual rate divided by 12; any balance is due at the end of its term.',
            'Property and other asset values use fixed assumed returns, are unavailable for spending, and have no automatic sale or linked debt.']
            + (['Social Security uses the entered full-retirement-age benefit adjusted for claiming age, level in today\'s dollars. With the tax model it is taxed as Social Security income; otherwise it is treated as after tax. Spousal excess benefits are included for couples while both are alive and the survivor keeps the larger benefit; the earnings test, family maximum and survivor-benefit reductions are not modeled.'] if social_security else [])
            + (['After a planned death the tax model still files jointly; survivor filing status is not modeled.'] if taxed and survivor_from is not None else []))


def _percentile(values, p):
    values = sorted(values)
    index = (len(values) - 1) * p
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def simulate(plan, settings=None):
    p = inputs(plan)
    settings = {} if settings is None else settings
    if not isinstance(settings, dict):
        raise ValueError('settings must be an object')
    original_plan = plan
    family_quick = _has_family_costs(plan) and not any(key in plan for key in ('accounts', 'streams', 'debts'))
    if family_quick:
        stop = number(settings.get('retirement_year', max(0, min(p['horizon'], plan.get('retirement_age', p['age']) - p['age']))), 'retirement_year', 0, p['horizon'], True)
        plan = _family_adapter(plan, p, stop)
    full = any(key in plan for key in ('accounts', 'streams', 'debts'))
    if full:
        _full_projection(plan, p, retain_monthly=False)
    trials = number(settings.get('trials', 500), 'trials', 1, 5000, True)
    if trials * p['horizon'] > 500000:
        raise ValueError('simulation exceeds 500000 annual observations')
    seed = number(settings.get('seed', 0), 'seed', 0, 2**53 - 1, True)
    mode = settings.get('mode', 'parametric')
    if mode not in ('parametric', 'resampling', 'block', 'historical', 'sequence'):
        raise ValueError('unsupported simulation mode')
    mean = number(settings.get('mean', p['return_rate']), 'mean', -.99, 10)
    volatility = number(settings.get('volatility', .15), 'volatility', 0, 3)
    # Plan and account returns compound like a growth rate, so by default the simulated
    # median annual return equals `mean` and the fixed projection is the median path for a
    # single portfolio. 'arithmetic' instead makes `mean` the expected (average) annual
    # return, whose median compounds about volatility**2 / 2 lower.
    return_basis = settings.get('return_basis', 'geometric')
    if return_basis not in ('geometric', 'arithmetic'):
        raise ValueError('return_basis must be geometric or arithmetic')
    if return_basis == 'geometric':
        spread = volatility / (1 + mean)
        sigma = math.sqrt(math.log((1 + math.sqrt(1 + 4 * spread * spread)) / 2))
        log_mean = math.log1p(mean)
    else:
        sigma = math.sqrt(math.log1p((volatility / (1 + mean)) ** 2))
        log_mean = math.log1p(mean) - sigma * sigma / 2
    history = settings.get('historical_returns', [])
    if mode not in ('parametric', 'sequence'):
        if not isinstance(history, list) or not history or len(history) > 10000:
            raise ValueError('resampling requires supplied annual historical_returns')
        history = [number(x, 'historical return', -1, 10) for x in history]
    block = number(settings.get('block_size', 5), 'block_size', 1, 150, True)
    if mode == 'block' and block > len(history):
        raise ValueError('block_size exceeds supplied history')
    retirement_year = number(settings.get('retirement_year', min(p['horizon'], max(0, plan.get('retirement_age', p['age']) - p['age'])) if full else 0), 'retirement_year', 0, p['horizon'], True)
    if full and 'essential_expenses' in settings:
        raise ValueError('full-mode essential spending is defined by expense streams')
    essential = (None if full else
        number(settings.get('essential_expenses', p['expenses']), 'essential_expenses', 0, p['expenses']))
    if mode == 'sequence':
        # One deterministic path: the plan return every year except shock_returns, which
        # start in the first year of retirement (or shock_start_year) and replace it.
        shock = settings.get('shock_returns', [-.15, -.13, -.24])
        if not isinstance(shock, list) or not 1 <= len(shock) <= 30:
            raise ValueError('shock_returns must list 1-30 annual returns')
        shock = [number(x, 'shock return', -.99, 10) for x in shock]
        shock_start = number(settings.get('shock_start_year', min(retirement_year, p['horizon'] - 1)), 'shock_start_year', 0, p['horizon'] - 1, True)
        trials = 1
    if mode == 'historical':
        trials = max(0, len(history) - p['horizon'] + 1)
        if trials > 5000 or trials * p['horizon'] > 500000:
            raise ValueError('historical run exceeds observation cap')
    if full and trials * p['horizon'] * 12 * max(1, len(plan.get('accounts', [])) + len(plan.get('streams', [])) + len(plan.get('debts', []))) > 30000000:
        raise ValueError('simulation exceeds monthly operation cap; reduce trials or horizon')
    paths = []
    for trial in range(trials):
        rng = random.Random(f'{seed}:{trial}:v1')
        rates = []
        while len(rates) < p['horizon']:
            if mode == 'parametric':
                # Lognormal gross returns with standard deviation `volatility`.
                rates.append(math.exp(rng.gauss(log_mean, sigma)) - 1)
            elif mode == 'historical':
                rates = history[trial:trial + p['horizon']]
            elif mode == 'sequence':
                rates = [mean] * p['horizon']
                rates[shock_start:shock_start + len(shock)] = shock[:p['horizon'] - shock_start]
            elif mode == 'resampling':
                rates.append(rng.choice(history))
            else:
                start = rng.randrange(len(history) - block + 1)
                rates.extend(history[start:start + block])
        if full:
            simulation_plan = dict(plan, retirement_age=p['age'] + retirement_year) if 'retirement_year' in settings else plan
            projected = _full_projection(simulation_plan, p, rates=rates, retain_monthly=False)
            summary = projected['summary']
            first_month = projected['first_shortfall_month']
            paths.append(dict(trial=trial, ending_balance=summary['ending_assets'],
                retirement_year=retirement_year, retirement_age=summary['retirement_age'], retirement_balance=summary['retirement_balance'], accumulation_shortfall=projected['accumulation_shortfall'],
                retirement_feasible=projected['essential_spending_funded'] is True,
                first_shortfall_year=math.ceil(first_month/12) if first_month else None,
                cumulative_unfunded=summary['total_unfunded'], lowest_spending_factor=summary['lowest_spending_factor'],
                annual=[{key: row[key] for key in ('year','age','balance','net_worth','unfunded')} for row in projected['annual']],
                **{key:projected[key] for key in ('portfolio_survives','essential_spending_funded','desired_lifestyle_funded')}))
            continue
        balance = p['assets']
        first_shortfall = None
        survives = True
        essential_funded = True
        desired_funded = True
        cumulative_unfunded = 0.0
        accumulation_shortfall = 0.0
        for month in range(1, p['horizon'] * 12 + 1):
            factor = (1 + rates[(month - 1)//12]) ** (1/12)
            balance *= factor
            unfunded = 0.0
            if month % 12 == 0:
                year = month // 12
                income = p['income'] if year <= retirement_year else 0.0
                available = balance + income
                unfunded = max(0.0, p['expenses'] - available)
                if unfunded and first_shortfall is None:
                    first_shortfall = year
                balance = max(0.0, available - p['expenses'])
                cumulative_unfunded += unfunded
                if year <= retirement_year:
                    accumulation_shortfall += unfunded
                if month > retirement_year * 12:
                    essential_funded = essential_funded and available >= essential
                    desired_funded = desired_funded and unfunded == 0
            if month > retirement_year * 12:
                survives = survives and balance > 0
            if not math.isfinite(balance):
                raise ValueError('simulation exceeds numerical range')
        has_window = retirement_year < p['horizon']
        paths.append(dict(trial=trial, ending_balance=balance, retirement_year=retirement_year,
            accumulation_shortfall=accumulation_shortfall, retirement_feasible=has_window and essential_funded,
            first_shortfall_year=first_shortfall, cumulative_unfunded=cumulative_unfunded,
            portfolio_survives=survives if has_window else None,
            essential_spending_funded=essential_funded if has_window else None,
            desired_lifestyle_funded=desired_funded if has_window else None))
    outcomes = {}
    for key in ('portfolio_survives', 'essential_spending_funded', 'desired_lifestyle_funded'):
        evaluated = [x[key] for x in paths if x[key] is not None]
        outcomes[key] = dict(numerator=sum(evaluated), denominator=len(evaluated), excluded=trials-len(evaluated),
            rate=sum(evaluated)/len(evaluated) if evaluated else None, excluded_reason='Retirement not reached before horizon')
    endings = [x['ending_balance'] for x in paths]
    strategy = _spending_strategy(plan) if full else None
    if strategy and paths:
        lows = [x['lowest_spending_factor'] for x in paths]
        cut = [v for v in lows if v < 1 - 1e-9]
        outcomes['spending_cuts'] = dict(numerator=len(cut), denominator=len(lows), rate=len(cut) / len(lows),
            median_lowest_factor=_percentile(lows, .5), p10_lowest_factor=_percentile(lows, .1),
            definition='Paths where the guardrail rule cut discretionary spending below plan at least once')
    meta = metadata(original_plan, mode)
    setting_metadata = dict(settings, trials=trials, seed=seed, mode=mode, retirement_year=retirement_year)
    if mode == 'parametric':
        setting_metadata['return_basis'] = return_basis
    if mode == 'sequence':
        setting_metadata.update(shock_returns=shock, shock_start_year=shock_start)
    if essential is not None:
        setting_metadata['essential_expenses'] = essential
    meta.update(settings=setting_metadata, random_generator='python.Random MT19937; per-trial string seed v1',
        distribution=('lognormal gross return; median annual return equals mean (compound/geometric basis)' if return_basis == 'geometric' else 'lognormal gross return; mean is the expected arithmetic annual return') + ', standard deviation volatility' if mode == 'parametric' else ('one path at the plan return with shock_returns from shock_start_year' if mode == 'sequence' else 'annual supplied returns, rolling consecutive complete windows; incomplete windows excluded' if mode == 'historical' else 'annual supplied returns with replacement; overlapping non-wrapping blocks for block mode'),
        history_digest=hashlib.sha256(json.dumps(history).encode()).hexdigest())
    incomplete = [dict(start_index=i, available_years=len(history)-i, required_years=p['horizon']) for i in range(trials, len(history))] if mode == 'historical' else []
    annual_bands = [dict(year=year+1, age=p['age']+year+1, **{name: _percentile([path['annual'][year]['balance'] for path in paths], fraction) for name, fraction in (('p10',.1),('median',.5),('p90',.9))}) for year in range(p['horizon'])] if full and paths else []
    return dict(status='complete' if paths else 'no_complete_periods', annual_bands=annual_bands, incomplete_history=incomplete, requested=trials, completed=len(paths), outcomes=outcomes, paths=paths,
        unreached_retirement=sum(x['retirement_year'] >= p['horizon'] for x in paths),
        ending_assets=dict(p10=_percentile(endings,.1), median=_percentile(endings,.5), p90=_percentile(endings,.9),
                           mean=statistics.mean(endings), standard_deviation=statistics.pstdev(endings)) if endings else None,
        legacy=dict(status='net_legacy_unsupported', gross_ending_asset_proxy=True), metadata=meta)
