"""Separate, simplified education-account forecasts for child beneficiaries.

These balances are informational and never enter a parent's FIRE assets.
Amounts use constant plan-start purchasing power and year-end event timing.
"""
from datetime import date
import math
import re


# Statutory caps for 2026–2027. Later caps are indexed for inflation; because
# forecasts are in constant plan-start dollars, they are assumed to stay at the
# same real amount.
TRUMP_GENERAL_CAP = {2026: 5000.0, 2027: 5000.0}
TRUMP_EMPLOYER_CAP = {2026: 2500.0, 2027: 2500.0}


def trump_general_cap(year):
    return TRUMP_GENERAL_CAP.get(year, TRUMP_GENERAL_CAP[2027])


def trump_employer_cap(year):
    return TRUMP_EMPLOYER_CAP.get(year, TRUMP_EMPLOYER_CAP[2027])
TRUMP_PILOT_YEARS = {2026, 2027, 2028}


def _number(value, field, low=0, high=1e15, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{field} must be a finite number')
    if value < low or value > high or (integer and int(value) != value):
        raise ValueError(f'{field} outside supported bounds')
    return int(value) if integer else float(value)


def _id(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise ValueError(f'{field} must be a non-empty identifier of at most 80 characters')
    return value.strip()


def _text(value, field, default=None):
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
        raise ValueError(f'{field} must be a non-empty string of at most 120 characters')
    return value.strip()


def _no_sensitive_ids(row):
    # Reject common SSN field spellings before the plan is hashed or persisted.
    if isinstance(row, dict):
        for key, value in row.items():
            normalized = re.sub(r'[^a-z0-9]', '', str(key).lower())
            if normalized in {'ssn', 'socialsecuritynumber', 'socialsecurityno'}:
                raise ValueError('Social Security numbers are not accepted in child profiles or accounts')
            _no_sensitive_ids(value)
    elif isinstance(row, list):
        for value in row:
            _no_sensitive_ids(value)


def project(plan, horizon, initialize_only=False):
    """Return a separate child-account forecast; does not mutate ``plan``."""
    raw_members = plan.get('members', [])
    raw_accounts = plan.get('child_accounts', [])
    if not isinstance(raw_members, list) or len(raw_members) > 100:
        raise ValueError('members must be a bounded list')
    if not isinstance(raw_accounts, list) or len(raw_accounts) > 200:
        raise ValueError('child_accounts must be a bounded list')
    if any(not isinstance(row, dict) for row in raw_members + raw_accounts):
        raise ValueError('members and child_accounts must contain objects')

    members = []
    member_ids = set()
    for raw in raw_members:
        _no_sensitive_ids(raw)
        member_id = _id(raw.get('id'), 'member id')
        if member_id in member_ids:
            raise ValueError('member ids must be unique')
        member_ids.add(member_id)
        name = _text(raw.get('name'), 'member name')
        birth_date = raw.get('birth_date')
        if not isinstance(birth_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', birth_date):
            raise ValueError('member birth_date must be an ISO calendar date (YYYY-MM-DD)')
        try:
            born = date.fromisoformat(birth_date)
        except ValueError:
            raise ValueError('member birth_date must be a real calendar date') from None
        if born.year < 1900 or born > date.today():
            raise ValueError('member birth_date is outside supported bounds')
        members.append(dict(id=member_id, name=name,
                            relationship=_text(raw.get('relationship'), 'member relationship', 'child'),
                            birth_date=birth_date))
    members_by_id = {row['id']: row for row in members}

    valuation_date = plan.get('valuation_date')
    if valuation_date is None:
        first_year = date.today().year
    else:
        if not isinstance(valuation_date, str):
            raise ValueError('valuation_date must be an ISO calendar date')
        try:
            first_year = date.fromisoformat(valuation_date).year
        except ValueError:
            raise ValueError('valuation_date must be a real calendar date') from None
    years = range(first_year, first_year + horizon)

    accounts = []
    account_ids = set()
    trump_beneficiaries = set()
    for raw in raw_accounts:
        _no_sensitive_ids(raw)
        account_id = _id(raw.get('id'), 'child account id')
        if account_id in account_ids:
            raise ValueError('child account ids must be unique')
        account_ids.add(account_id)
        account_type = raw.get('type')
        if account_type not in ('529', 'trump'):
            raise ValueError('child account type must be 529 or trump')
        beneficiary_id = _id(raw.get('beneficiary_id'), 'beneficiary_id')
        if beneficiary_id not in members_by_id:
            raise ValueError('child account beneficiary_id must reference a member')
        if account_type == 'trump' and beneficiary_id in trump_beneficiaries:
            raise ValueError('only one Trump Account may be modeled per child beneficiary')
        if account_type == 'trump':
            trump_beneficiaries.add(beneficiary_id)
        opening = _number(raw.get('balance', 0), 'child account balance')
        return_rate = _number(raw.get('return_rate', 0), 'child account return', -.999999999, 10)
        fee_rate = _number(raw.get('fee_rate', 0), 'child account fee', 0, .99)
        ordinary = _number(raw.get('annual_contribution', 0), 'annual_contribution')
        source = raw.get('contribution_source', 'household')
        if source not in ('household', 'external'):
            raise ValueError('contribution_source must be household or external')
        cover = raw.get('cover_education_shortfall', False)
        if not isinstance(cover, bool):
            raise ValueError('cover_education_shortfall must be a boolean')
        row = dict(id=account_id, name=_text(raw.get('name'), 'child account name'), type=account_type,
                   beneficiary_id=beneficiary_id, balance=opening, return_rate=return_rate,
                   fee_rate=fee_rate, annual_contribution=ordinary, contribution_source=source,
                   cover_education_shortfall=cover, annual=[])
        if account_type == '529':
            if raw.get('employer_contribution', 0) or raw.get('pilot_contribution', 0):
                raise ValueError('employer and pilot contributions apply only to Trump Accounts')
            start = _number(raw.get('start_year', first_year), '529 start_year', 1900, 9998, True)
            end = _number(raw.get('end_year', first_year + horizon - 1), '529 end_year', 1900, 9999, True)
            if end < start:
                raise ValueError('529 end_year must be at or after start_year')
            education_amount = _number(raw.get('education_annual_withdrawal', 0), 'education_annual_withdrawal')
            education_start_age = raw.get('education_start_age')
            if education_start_age is not None:
                education_start_age = _number(education_start_age, 'education_start_age', 0, 99, True)
            education_years = _number(raw.get('education_years', 4), 'education_years', 1, 20, True)
            if education_amount and education_start_age is None:
                raise ValueError('education_start_age is required when education withdrawals are configured')
            row.update(start_year=start, end_year=end, education_annual_withdrawal=education_amount,
                       education_start_age=education_start_age, education_years=education_years)
        else:
            if raw.get('education_annual_withdrawal', 0):
                raise ValueError('education withdrawals are modeled only for 529 accounts')
            growth_period_end_year = date.fromisoformat(members_by_id[beneficiary_id]['birth_date']).year + 17
            start = _number(raw.get('start_year', max(2026, first_year)), 'Trump start_year', 2026, 9998, True)
            end = _number(raw.get('end_year', growth_period_end_year), 'Trump end_year', 2026, 9999, True)
            if end < start:
                raise ValueError('Trump end_year must be at or after start_year')
            employer = _number(raw.get('employer_contribution', 0), 'employer_contribution')
            pilot = _number(raw.get('pilot_contribution', 0), 'pilot_contribution', 0, 1000)
            if pilot not in (0, 1000):
                raise ValueError('pilot_contribution must be 0 or 1000')
            pilot_year = raw.get('pilot_year')
            if pilot:
                pilot_year = _number(pilot_year, 'pilot_year', 2026, 2028, True)
            elif pilot_year is not None:
                pilot_year = _number(pilot_year, 'pilot_year', 2026, 2028, True)
            employer_contributor_id = raw.get('employer_contributor_id')
            if employer and employer_contributor_id is None:
                raise ValueError('employer_contributor_id is required for employer contributions')
            if employer_contributor_id is not None:
                employer_contributor_id = _id(employer_contributor_id, 'employer_contributor_id')
            if start > growth_period_end_year:
                raise ValueError('Trump Account contribution schedule starts after the beneficiary growth period ends')
            if end > growth_period_end_year:
                raise ValueError('Trump Account contributions cannot continue after the beneficiary growth period ends')
            if pilot and pilot_year < start:
                raise ValueError('pilot contribution year cannot be before the Trump Account start year')
            row.update(start_year=start, end_year=end, employer_contribution=employer,
                       pilot_contribution=pilot, pilot_year=pilot_year,
                       employer_contributor_id=employer_contributor_id,
                       growth_period_end_year=growth_period_end_year)
        accounts.append(row)

    # Validate contribution limits on aggregated accounts. Pilot amounts are
    # user-entered hypothetical receipts, not eligibility determinations.
    beneficiary_contributions = {}
    employer_contributions = {}
    pilot_receipts = {}
    for account in accounts:
        if account['type'] != 'trump':
            continue
        contributor = account['employer_contributor_id']
        if account['pilot_contribution']:
            key = account['beneficiary_id']
            pilot_receipts[key] = pilot_receipts.get(key, 0.0) + account['pilot_contribution']
        for year in range(account['start_year'], account['end_year'] + 1):
            total = account['annual_contribution'] + account['employer_contribution']
            key = account['beneficiary_id'], year
            beneficiary_contributions[key] = beneficiary_contributions.get(key, 0.0) + total
            if contributor and account['employer_contribution']:
                key = contributor, year
                employer_contributions[key] = employer_contributions.get(key, 0.0) + account['employer_contribution']
    if any(total > trump_general_cap(year) for (_, year), total in beneficiary_contributions.items()):
        raise ValueError('Trump Account contributions exceed the $5,000 aggregate annual cap (in today\'s dollars)')
    if any(total > trump_employer_cap(year) for (_, year), total in employer_contributions.items()):
        raise ValueError('employer Trump Account contributions exceed the $2,500 per-employee annual cap (in today\'s dollars)')
    if any(total > 1000 for total in pilot_receipts.values()):
        raise ValueError('pilot contribution may be entered only once per beneficiary')

    annual_rows = []
    totals = dict(initial_balance=sum(account['balance'] for account in accounts),
                  ending_balance=0.0, contributions=0.0, education_withdrawals=0.0,
                  education_shortfall=0.0, household_contributions=0.0, unfunded_contributions=0.0,
                  household_education=0.0, total_need=0.0, total_funded=0.0,
                  total_unfunded=0.0)
    totals['ending_balance'] = sum(account['balance'] for account in accounts)
    warnings = [
        'Child accounts are forecast separately and excluded from parent investable assets, net worth, and FI target.',
        'Year-end real-dollar approximation: annual return and fee, contributions, and education withdrawals are applied at year end; first-year growth is prorated to December; inflation is not modeled.',
        '529 contribution limits, qualified-expense rules, state tax treatment, and plan-specific caps are not evaluated; education withdrawals are user-entered estimates.',
        'Trump Account eligibility, tax treatment, investment eligibility, and pilot eligibility are not determined. General ($5,000) and employer ($2,500) caps are checked every year through the year the child turns 17; caps after 2027 are indexed for inflation and assumed to stay at the same amount in today’s dollars.',
    ]
    result = dict(members=members, child_accounts=accounts, annual=annual_rows, summary=totals,
                coverage='Simplified year-end real-dollar forecast; no eligibility or tax determinations.',
                warnings=warnings)

    if not initialize_only:
        for year in years:
            advance(result, year)
    return result


def advance(result, year, pay=None, year_fraction=1):
    """Advance child ledgers; pay returns (funded, unfunded) household dollars."""
    accounts, totals = result['child_accounts'], result['summary']
    members_by_id = {row['id']: row for row in result['members']}
    household = dict(contributions=0.0, contribution_due=0.0, education=0.0, education_due=0.0, unfunded=0.0)
    year_accounts = []
    for account in accounts:
        opening = account['balance']
        gross_return = opening * ((1 + account['return_rate']) ** year_fraction - 1)
        after_growth = opening + gross_return
        fees = after_growth * (1 - (1 - account['fee_rate']) ** year_fraction)
        contribution = pilot = employer = 0.0
        if account['start_year'] <= year <= account['end_year']:
            contribution = account['annual_contribution']
            if account['type'] == 'trump':
                employer = account['employer_contribution']
        if account['type'] == 'trump' and account['pilot_year'] == year:
            pilot = account['pilot_contribution']
        if account['type'] == '529':
            member = members_by_id[account['beneficiary_id']]
            age = year - date.fromisoformat(member['birth_date']).year
            start_age = account['education_start_age']
            requested = (account['education_annual_withdrawal']
                         if start_age is not None and start_age <= age < start_age + account['education_years'] else 0.0)
        else:
            age = year - date.fromisoformat(members_by_id[account['beneficiary_id']]['birth_date']).year
            requested = 0.0
        contribution_due = contribution if account['contribution_source'] == 'household' else 0.0
        missing_contribution = 0.0
        if contribution_due and pay is not None:
            contribution, missing_contribution = pay(contribution_due)
        household_contribution = contribution if account['contribution_source'] == 'household' else 0.0
        household['contributions'] += household_contribution
        household['contribution_due'] += contribution_due
        household['unfunded'] += missing_contribution
        pre_withdrawal = max(0.0, after_growth - fees + contribution + employer + pilot)
        withdrawal = min(pre_withdrawal, requested)
        shortfall = requested - withdrawal
        household_education = 0.0
        if account['cover_education_shortfall']:
            household['education_due'] += shortfall
            household_education, unpaid_education = pay(shortfall) if pay is not None else (shortfall, 0.0)
            household['education'] += household_education
            household['unfunded'] += unpaid_education
        closing = pre_withdrawal - withdrawal
        if not math.isfinite(closing):
            raise ValueError('child account forecast exceeds numerical range')
        account['balance'] = closing
        row = dict(year=year, age=age, opening=opening, **{'return': gross_return}, return_amount=gross_return, fees=fees,
                   contribution=contribution + employer + pilot, regular_contribution=contribution,
                   employer_contribution=employer, pilot_contribution=pilot,
                   education_withdrawal=withdrawal, education_need=requested,
                   unfunded_education=shortfall, education_requested=requested,
                   education_shortfall=shortfall, household_education=household_education,
                   household_contribution=household_contribution, unfunded_contribution=missing_contribution,
                   remaining_education_shortfall=shortfall-household_education, closing=closing)
        account['annual'].append(row)
        year_accounts.append(dict(account_id=account['id'], **row))
        totals['contributions'] += contribution + employer + pilot
        totals['education_withdrawals'] += withdrawal
        totals['education_shortfall'] += shortfall
        totals['total_need'] += requested
        totals['household_contributions'] += household_contribution
        totals['unfunded_contributions'] += missing_contribution
        totals['household_education'] += household_education
        totals['total_funded'] += withdrawal + household_education
        totals['total_unfunded'] += shortfall - household_education
    result['annual'].append(dict(year=year, accounts=year_accounts,
                            closing_balance=sum(account['balance'] for account in accounts)))
    totals['ending_balance'] = sum(account['balance'] for account in accounts)
    return household
