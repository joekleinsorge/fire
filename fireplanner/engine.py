"""Versioned, dependency-free planning arithmetic; amounts are constant purchasing power."""
import hashlib
import json
import math
import random
import statistics
from datetime import date
import re
from . import children as child_planning

VERSION = '2.0.0'


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


def _plan_inflation(plan):
    # Plan-wide expected inflation; debts and purchase loans use it unless they set their own.
    return number(plan.get('inflation_rate', 0), 'inflation_rate', -.5, 1)


def _purchases(plan):
    inflation = _plan_inflation(plan)
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
            upkeep_years=upkeep_years, loan_amount=loan,
            loan_rate=number(row.get('loan_rate', 0), 'loan_rate', 0, 10),
            # loan_rate is the quoted (nominal) rate; loan_inflation converts its fixed
            # payments into this engine's constant purchasing power.
            loan_inflation=number(row.get('loan_inflation', inflation), 'loan_inflation', -.5, 1),
            loan_months=number(row.get('loan_months', 360), 'loan_months', 1, 1800, True),
            adds_asset=adds_asset,
            asset_return=number(row.get('asset_return', 0), 'asset_return', -.99, 10),
            sell_account_id=row.get('sell_account_id'), sell_purchase_id=row.get('sell_purchase_id'),
            payoff_debt_id=row.get('payoff_debt_id'),
            sell_cost_rate=number(row.get('sell_cost_rate', .06), 'sell_cost_rate', 0, .5), sold_month=None))
    by_id = {item['id']: item for item in normalized}
    sold_accounts, sold_purchases = set(), set()
    for item in normalized:
        if not item['enabled']:
            continue
        if item['sell_account_id'] is not None and item['sell_purchase_id'] is not None:
            raise ValueError('a future purchase can sell one existing asset at a time')
        if item['sell_account_id'] is not None:
            if item['sell_account_id'] in sold_accounts:
                raise ValueError('an account can be sold by only one future purchase')
            sold_accounts.add(item['sell_account_id'])
        target = item['sell_purchase_id']
        if target is not None:
            asset = by_id.get(target) if isinstance(target, str) else None
            if asset is None or asset is item or not asset['enabled'] or not asset['adds_asset']:
                raise ValueError('future purchase sell_purchase_id must reference another included purchase kept as an asset')
            if asset['month'] >= item['month']:
                raise ValueError('a purchased asset can be sold only after the month it is bought')
            if target in sold_purchases:
                raise ValueError('a purchased asset can be sold by only one future purchase')
            sold_purchases.add(target)
            asset['sold_month'] = item['month']
    return normalized


def _upkeep_active(item, month):
    # Upkeep starts the month after purchase and runs for upkeep_years, or
    # indefinitely, and stops once the purchase is sold.
    if not item['enabled'] or month <= item['month']:
        return False
    if item['sold_month'] is not None and month >= item['sold_month']:
        return False
    return item['upkeep_years'] is None or month <= item['month'] + item['upkeep_years'] * 12


def _real_rate(nominal, deflator):
    # Monthly real rate; exact when there is no inflation so real-dollar inputs are unchanged.
    return nominal if deflator == 1 else (1 + nominal) / deflator - 1


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
    if not accounts:
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
    accessible = [flag(a, 'available', a.get('type', 'investment') not in ('property', 'other')) for a in accounts]
    for a in accounts:
        if a.get('type', 'investment') not in ('cash', 'investment', 'retirement', 'property', 'other'):
            raise ValueError('unsupported account type')
    normalized = []
    for stream in streams:
        if stream.get('kind') not in ('income', 'expense'):
            raise ValueError('stream kind must be income or expense')
        row = dict(kind=stream['kind'], amount=number(stream.get('amount'), 'stream amount', 0, 1e15),
            start=number(stream.get('start_month', 1), 'start_month', 1, 1801, True),
            end=number(stream.get('end_month', p['horizon'] * 12 + 1), 'end_month', 1, 1801, True),
            every=number(stream.get('every_months', 1), 'every_months', 1, 1200, True),
            growth=number(stream.get('growth_rate', 0), 'growth_rate', -.99, 10),
            enabled=flag(stream, 'enabled', True), essential=flag(stream, 'essential', True))
        if row['end'] < row['start']:
            raise ValueError('stream end must follow start')
        normalized.append(row)
    debt_rows = []
    # annual_rate is the quoted (nominal) rate and payments are fixed in nominal terms. In
    # constant purchasing power they shrink with inflation_rate, and interest accrues at the
    # real rate. Without inflation_rate both are taken as already real, as before.
    for debt in debts:
        balance = number(debt.get('balance', 0), 'debt balance', 0, 1e15)
        nominal = number(debt.get('annual_rate', 0), 'debt annual_rate', 0, 10) / 12
        months = number(debt.get('months', 360), 'debt months', 1, 1800, True)
        payment = balance * nominal / (1 - (1 + nominal) ** -months) if nominal else balance / months
        if debt.get('payment') is not None:
            payment = number(debt['payment'], 'debt payment', 0, 1e15)
        deflator = (1 + number(debt.get('inflation_rate', _plan_inflation(plan)), 'debt inflation_rate', -.5, 1)) ** (1 / 12)
        debt_rows.append(dict(balance=balance, rate=_real_rate(nominal, deflator), payment=payment, deflator=deflator,
            extra=number(debt.get('extra_payment', 0), 'extra_payment', 0, 1e15), months=months, origin=0, principal=balance))
    initial_debt = sum(d['balance'] for d in debt_rows)
    # Financed purchases originate a debt in the purchase month; payments start the month after.
    # The quoted rate sets a fixed nominal payment; in constant purchasing power both the
    # payment and the balance shrink with inflation, so interest accrues at the real rate.
    purchase_loans = {}
    for item in purchases:
        if item['enabled'] and item['loan_amount']:
            nominal = item['loan_rate'] / 12
            loan, months = item['loan_amount'], item['loan_months']
            payment = loan * nominal / (1 - (1 + nominal) ** -months) if nominal else loan / months
            deflator = (1 + item['loan_inflation']) ** (1 / 12)
            purchase_loans[item['id']] = dict(balance=0.0, rate=_real_rate(nominal, deflator), payment=payment,
                deflator=deflator, extra=0.0, months=months, origin=item['month'], principal=loan)
            debt_rows.append(purchase_loans[item['id']])
    def resolve(rows, key, label):
        for item in purchases:
            ident = item[key]
            # Disabled purchases are ignored, so a stale reference must not break the plan.
            if ident is None or not item['enabled']:
                item[key + '_index'] = None
                continue
            matches = [i for i, row in enumerate(rows) if row.get('id') == ident]
            if not isinstance(ident, str) or len(matches) != 1:
                raise ValueError(f'future purchase {key} must reference one {label} in this plan')
            item[key + '_index'] = matches[0]
    resolve(accounts, 'sell_account_id', 'account')
    resolve(debts, 'payoff_debt_id', 'debt')
    purchase_assets = {item['id']: dict(month=item['month'], value=0.0, rate=item['asset_return'], amount=item['amount'])
                       for item in purchases if item['enabled'] and item['adds_asset']}
    # Income is available immediately; withdrawals follow the user's account order.
    available_indices = [i for i, available in enumerate(accessible) if available]
    monthly, annual = [], []
    first_shortfall = None
    total_unfunded = 0.0
    retirement_age = number(plan.get('retirement_age', p['age']), 'retirement_age', 0, 300, True)
    retirement_month = max(0, round((retirement_age - p['age']) * 12))
    retirement_balance = initial if retirement_month == 0 else None
    retirement_start = retirement_month + 1
    retirement_streams = [row for row in normalized if row['enabled'] and row['start'] <= retirement_start < row['end']]
    def annualized_stream(row):
        return row['amount'] * (1 + row['growth']) ** ((retirement_start - row['start']) / 12) * 12 / row['every']
    annual_desired_spending = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'expense')
    annual_retirement_income = sum(annualized_stream(row) for row in retirement_streams if row['kind'] == 'income')
    if plan.get('_quick_adapter'):
        annual_desired_spending, annual_retirement_income = p['expenses'], 0.0
    # Open-ended upkeep is permanent retirement spending. Costs that end (debt and loan
    # payments, purchases, upkeep with a term or a sale, household child funding) are added
    # after the projection as the present value of what falls after retirement starts.
    perpetual_upkeep = lambda row: row['upkeep_years'] is None and row['sold_month'] is None
    annual_desired_spending += sum(row['annual_upkeep'] for row in purchases
                                   if row['enabled'] and perpetual_upkeep(row) and row['month'] <= p['horizon'] * 12)
    annual_net_spending = max(0.0, annual_desired_spending - annual_retirement_income)
    spending_target = annual_net_spending / p['withdrawal_rate']
    if not all(math.isfinite(value) for value in (annual_desired_spending, annual_retirement_income, spending_target)):
        raise ValueError('retirement target exceeds numerical range')
    obligation_discount = (1 + p['return_rate']) ** (1 / 12)
    retirement_obligations = 0.0
    initial_available = sum(balances[i] for i in available_indices)
    retirement_available_balance = initial_available if retirement_month == 0 else None
    retirement_survives = True
    retirement_essential = True
    retirement_desired = True
    accumulation_shortfall = 0.0
    fields = ('income', 'expenses', 'essential_expenses', 'funded_expenses', 'unfunded',
              'essential_unfunded', 'desired_expenses', 'desired_unfunded', 'debt_payment', 'debt_due', 'debt_unfunded', 'debt_interest', 'debt_principal', 'gain', 'fees', 'purchase_due', 'purchase_paid', 'purchase_unfunded', 'purchase_upkeep', 'purchase_asset_added', 'purchase_loan_drawn', 'purchase_sale_proceeds', 'purchase_sale_costs', 'purchase_debt_payoff', 'child_contributions', 'child_contribution_due', 'child_education', 'child_education_due', 'child_unfunded')
    for month in range(1, p['horizon'] * 12 + 1):
        opening = sum(balances) + sum(a['value'] for a in purchase_assets.values())
        gain = fee = 0.0
        for asset in purchase_assets.values():
            earned = asset['value'] * ((1 + asset['rate']) ** (1 / 12) - 1)
            asset['value'] += earned
            gain += earned
        for i, account in enumerate(accounts):
            rate = account_rates[i]
            if rates is not None and account.get('type', 'investment') in ('investment', 'retirement'):
                rate = max(-1, rate + rates[(month - 1) // 12] - p['return_rate'])
            earned = balances[i] * ((1 + rate) ** (1 / 12) - 1)
            balances[i] += earned
            charged = balances[i] * (1 - (1 - fees[i]) ** (1 / 12))
            balances[i] -= charged
            gain += earned
            fee += charged
        due = [row for row in normalized if row['enabled'] and row['start'] <= month < row['end'] and (month-row['start']) % row['every'] == 0]
        amounts = [(row, row['amount'] * (1 + row['growth']) ** ((month-row['start']) / 12)) for row in due]
        income = sum(value for row, value in amounts if row['kind'] == 'income')
        essential = sum(value for row, value in amounts if row['kind'] == 'expense' and row['essential'])
        desired = sum(value for row, value in amounts if row['kind'] == 'expense' and not row['essential'])
        cash = income
        def pay(amount):
            nonlocal cash
            from_income = min(cash, amount)
            cash -= from_income
            remaining = amount - from_income
            for i in available_indices:
                taken = min(balances[i], remaining)
                balances[i] -= taken
                remaining -= taken
            return amount - remaining, remaining
        essential_paid, essential_unfunded = pay(essential)
        debt_payment = debt_due = debt_unfunded = debt_interest = debt_principal = 0.0
        debt_ledger = []
        for debt in debt_rows:
            if month <= debt['origin']:
                continue
            debt_open = debt['balance']
            interest = debt_open * debt['rate']
            debt['balance'] += interest
            required = min(debt['balance'], (debt['payment'] + debt['extra']) / debt['deflator'] ** (month - debt['origin']))
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
            # Payments settle accrued interest first. If cash is insufficient even
            # for interest, the unpaid interest is capitalized above; it is not
            # negative principal repayment.
            principal_paid = max(0.0, paid - interest)
            debt_principal += principal_paid
            debt_ledger.append(dict(opening=debt_open, interest=interest, due=required, payment=paid,
                                    principal=principal_paid, unfunded=unpaid, balance=debt['balance']))
        desired_paid, desired_unfunded = pay(desired)
        child_cash = dict(contributions=0.0, contribution_due=0.0, education=0.0, education_due=0.0, unfunded=0.0)
        # The valuation is a month-end and month 1 is the following calendar month, so
        # December closes when valuation.month + month is a multiple of 12.
        if (valuation.month + month) % 12 == 0:
            year = valuation.year + (valuation.month + month - 1) // 12
            child_cash = child_planning.advance(children, year, pay,
                year_fraction=month / 12 if not children['annual'] else 1)
        # Selling an existing asset and retiring its debt happen before the new purchase is paid.
        sale_proceeds = sale_costs = payoff = 0.0
        for item in purchases:
            if not item['enabled'] or item['month'] != month:
                continue
            proceeds = 0.0
            if item['sell_account_id_index'] is not None:
                value = balances[item['sell_account_id_index']]
                balances[item['sell_account_id_index']] = 0.0
                sale_costs += value * item['sell_cost_rate']
                proceeds = value * (1 - item['sell_cost_rate'])
                sale_proceeds += proceeds
                cash += proceeds
            if item['sell_purchase_id'] is not None:
                # Selling a purchased asset also repays the loan that financed it.
                asset = purchase_assets[item['sell_purchase_id']]
                sale_costs += asset['value'] * item['sell_cost_rate']
                proceeds = asset['value'] * (1 - item['sell_cost_rate'])
                asset['value'] = 0.0
                sale_proceeds += proceeds
                cash += proceeds
                loan = purchase_loans.get(item['sell_purchase_id'])
                if loan is not None:
                    paid, _ = pay(min(loan['balance'], proceeds))
                    loan['balance'] -= paid
                    payoff += paid
                    proceeds -= paid
            if item['payoff_debt_id_index'] is not None:
                debt = debt_rows[item['payoff_debt_id_index']]
                paid, _ = pay(min(debt['balance'], proceeds))
                debt['balance'] -= paid
                payoff += paid
        debt_payment += payoff
        debt_principal += payoff
        purchase_due = sum(item['amount'] - item['loan_amount'] for item in purchases if item['enabled'] and item['month'] == month)
        upkeep = sum(item['annual_upkeep'] / 12 for item in purchases if _upkeep_active(item, month))
        finite_upkeep = sum(item['annual_upkeep'] / 12 for item in purchases
                            if _upkeep_active(item, month) and not perpetual_upkeep(item))
        purchase_paid, purchase_unfunded = pay(purchase_due + upkeep)
        purchase_asset_added = 0.0
        for asset in purchase_assets.values():
            if asset['month'] == month:
                asset['value'] = asset['amount']
                purchase_asset_added += asset['amount']
        for debt in debt_rows:
            if debt['origin'] and debt['origin'] == month:
                debt['balance'] = debt['principal']
        purchase_loan_drawn = sum(item['loan_amount'] for item in purchases if item['enabled'] and item['month'] == month)
        asset_value = sum(a['value'] for a in purchase_assets.values())
        # If every account is unavailable, keep surplus in an explicit liquid cash ledger.
        if available_indices:
            balances[available_indices[0]] += cash
        else:
            if len(balances) == len(accounts):
                balances.append(0.0)
                available_indices.append(len(accounts))
            balances[-1] += cash
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
            purchase_due=purchase_due, purchase_paid=purchase_paid, purchase_unfunded=purchase_unfunded, purchase_upkeep=upkeep,
            purchase_asset_added=purchase_asset_added, purchase_loan_drawn=purchase_loan_drawn, purchase_asset_value=asset_value,
            purchase_sale_proceeds=sale_proceeds, purchase_sale_costs=sale_costs, purchase_debt_payoff=payoff,
            child_contributions=child_cash['contributions'], child_contribution_due=child_cash['contribution_due'],
            child_education=child_cash['education'], child_education_due=child_cash['education_due'], child_unfunded=child_cash['unfunded'],
            funded_expenses=essential_paid+desired_paid+purchase_paid+child_cash['contributions']+child_cash['education'], unfunded=unfunded, essential_unfunded=essential_unfunded,
            desired_expenses=desired, desired_unfunded=desired_unfunded,
            debt_payment=debt_payment, debt_due=debt_due, debt_unfunded=debt_unfunded, debt_balance=debt_balance,
            debt_interest=debt_interest, debt_principal=debt_principal, debts=debt_ledger, accounts=list(balances))
        if month >= retirement_start:
            # Sale proceeds offset the costs they fund; payoffs from them are counted as paid.
            finite = (debt_payment + debt_unfunded + purchase_due + finite_upkeep - sale_proceeds
                      + child_cash['contribution_due'] + child_cash['education_due'])
            retirement_obligations += finite / obligation_discount ** (month - retirement_start)
        if month <= retirement_month:
            accumulation_shortfall += unfunded
        else:
            retirement_survives = retirement_survives and row['available_balance'] > 1e-8
            retirement_essential = retirement_essential and essential_unfunded + debt_unfunded <= 1e-8
            retirement_desired = retirement_desired and desired_unfunded + purchase_unfunded + child_cash['unfunded'] <= 1e-8
        if month == retirement_month:
            retirement_balance = closing
            retirement_available_balance = row['available_balance']
        if (month - 1) % 12 == 0:
            year_row = dict(year=(month-1)//12+1, age=p['age']+(month-1)//12+1, opening=opening, **{key:0.0 for key in fields})
        for key in fields:
            year_row[key] += row[key]
        if month % 12 == 0:
            year_row.update({key:row[key] for key in ('balance','available_balance','net_worth','debt_balance','accounts','purchase_asset_value')})
            annual.append(year_row)
        if retain_monthly:
            monthly.append(row)
    retirement_obligations = max(0.0, retirement_obligations)
    target = spending_target + retirement_obligations
    if not math.isfinite(target):
        raise ValueError('retirement target exceeds numerical range')
    has_window = retirement_month < p['horizon'] * 12
    years_to_target = 0 if p['age'] >= retirement_age and initial_available >= target else next(
        (row['year'] for row in annual if row['age'] >= retirement_age and row['available_balance'] >= target), None)
    # Unlike fi_age, this ignores the planned retirement age, so trade-offs that
    # move the crossing earlier or later stay visible.
    earliest_fi_age = p['age'] if initial_available >= target else next(
        (row['age'] for row in annual if row['available_balance'] >= target), None)
    target_fields = dict(target=target, annual_desired_spending=annual_desired_spending, retirement_obligations=retirement_obligations,
        annual_retirement_income=annual_retirement_income, annual_net_spending=annual_net_spending,
        years_to_target=years_to_target, retirement_age=retirement_age,
        fi_age=p['age'] + years_to_target if years_to_target is not None else None,
        earliest_fi_age=earliest_fi_age)
    target_metadata = dict(
        basis='Enabled after-tax streams active at the start of retirement, annualized by recurrence at their retirement-start purchasing-power amounts; plus open-ended upkeep for enabled, unsold purchases within the horizon. Costs that end and fall after retirement starts (debt and purchase loan payments, one-time purchases net of sale proceeds, upkeep with a term or a later sale, and household child funding) are added as retirement_obligations, their present value at retirement start discounted at the plan return.',
        target_label='FI target from annualized retirement spending less income',
        balance_label='Available account assets',
        crossing_label='First year-end at or after retirement with available assets at the FI target',
        annual_desired_spending_label='Annualized retirement expenses',
        annual_net_spending_label='Annualized retirement expenses less income')
    summary = dict(initial_assets=initial, initial_debt=initial_debt, ending_assets=closing,
        ending_net_worth=closing-debt_balance, total_unfunded=total_unfunded,
        first_shortfall_age=p['age']+(first_shortfall / 12) if first_shortfall else None,
        retirement_balance=retirement_balance, retirement_available_balance=retirement_available_balance, **target_fields)
    return dict(**target_fields, children=children, future_purchases=purchases, target_metadata=target_metadata, monthly=monthly, annual=annual, summary=summary, first_shortfall_month=first_shortfall,
        accumulation_shortfall=accumulation_shortfall,
        portfolio_survives=retirement_survives if has_window else None,
        essential_spending_funded=retirement_essential if has_window else None,
        desired_lifestyle_funded=retirement_desired if has_window else None,
        metadata=metadata(plan, 'full'), warnings=['Streams are after tax. Unavailable accounts cannot fund spending.',
            'Debt interest uses annual rate divided by 12; any balance is due at the end of its term.',
            'Property and other asset values use fixed assumed returns, default to unavailable for spending, and have no automatic sale or linked debt.'])


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
    if mode not in ('parametric', 'resampling', 'block', 'historical'):
        raise ValueError('unsupported simulation mode')
    mean = number(settings.get('mean', p['return_rate']), 'mean', -.99, 10)
    volatility = number(settings.get('volatility', .15), 'volatility', 0, 3)
    history = settings.get('historical_returns', [])
    if mode != 'parametric':
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
                # Lognormal gross returns: mean is expected arithmetic annual return.
                sigma = math.sqrt(math.log1p((volatility / (1 + mean)) ** 2))
                rates.append(math.exp(rng.gauss(math.log1p(mean) - sigma * sigma / 2, sigma)) - 1)
            elif mode == 'historical':
                rates = history[trial:trial + p['horizon']]
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
                cumulative_unfunded=summary['total_unfunded'],
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
    meta = metadata(original_plan, mode)
    setting_metadata = dict(settings, trials=trials, seed=seed, mode=mode, retirement_year=retirement_year)
    if essential is not None:
        setting_metadata['essential_expenses'] = essential
    meta.update(settings=setting_metadata, random_generator='python.Random MT19937; per-trial string seed v1',
        distribution='lognormal gross return, arithmetic mean and standard deviation' if mode == 'parametric' else ('annual supplied returns, rolling consecutive complete windows; incomplete windows excluded' if mode == 'historical' else 'annual supplied returns with replacement; overlapping non-wrapping blocks for block mode'),
        history_digest=hashlib.sha256(json.dumps(history).encode()).hexdigest())
    incomplete = [dict(start_index=i, available_years=len(history)-i, required_years=p['horizon']) for i in range(trials, len(history))] if mode == 'historical' else []
    annual_bands = [dict(year=year+1, age=p['age']+year+1, **{name: _percentile([path['annual'][year]['balance'] for path in paths], fraction) for name, fraction in (('p10',.1),('median',.5),('p90',.9))}) for year in range(p['horizon'])] if full and paths else []
    return dict(status='complete' if paths else 'no_complete_periods', annual_bands=annual_bands, incomplete_history=incomplete, requested=trials, completed=len(paths), outcomes=outcomes, paths=paths,
        unreached_retirement=sum(x['retirement_year'] >= p['horizon'] for x in paths),
        ending_assets=dict(p10=_percentile(endings,.1), median=_percentile(endings,.5), p90=_percentile(endings,.9),
                           mean=statistics.mean(endings), standard_deviation=statistics.pstdev(endings)) if endings else None,
        legacy=dict(status='net_legacy_unsupported', gross_ending_asset_proxy=True), metadata=meta)
