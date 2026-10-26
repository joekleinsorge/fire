"""Social Security claiming-age arithmetic from a user-entered PIA; no benefit estimation.

Rules (SSA Office of the Chief Actuary, reviewed 2026-10-25):
- Full (normal) retirement age by year of birth: 66 for 1943-1954, plus 2 months per
  year for 1955-1959, and 67 for 1960 and later. People born on January 1 use the prior
  year. https://www.ssa.gov/oact/quickcalc/earlyretire.html
- Early reduction: 5/9 of 1% per month for the first 36 months before full retirement
  age and 5/12 of 1% for each additional month; a person must be the claiming age
  throughout the first month of a reduced benefit. (same page)
- Delayed retirement credits for births in 1943 or later: 8% per year (2/3 of 1% per
  month) after full retirement age, up to age 70.
  https://www.ssa.gov/oact/ProgData/ar_drc.html
SSA treats a person as attaining an age the day before the birthday, which is where
the January 1 rule comes from. Benefits are held constant in today's dollars, i.e. the
cost-of-living adjustment is assumed to match inflation.
"""
from datetime import date, timedelta
import re

EARLIEST_CLAIM = 62 * 12
LATEST_CLAIM = 70 * 12
FIRST_BIRTH_YEAR = 1943  # the 8%-per-year delayed credit applies from this year of birth


def full_retirement_age_months(birth_year):
    if birth_year <= 1954:
        return 66 * 12
    if birth_year <= 1959:
        return 66 * 12 + 2 * (birth_year - 1954)
    return 67 * 12


def benefit_factor(reduction_months, credit_months):
    """Share of the PIA payable after early reduction months or delayed credit months."""
    if reduction_months > 0:
        first = min(reduction_months, 36)
        return 1 - (first * 5 / 9 + (reduction_months - first) * 5 / 12) / 100
    return 1 + credit_months * 2 / 3 / 100


def _months(birth_year, claim, late_attainer=False):
    # A late attainer (age attained after the 1st of a month) is not yet the claiming age
    # throughout that month, so a reduced benefit starts one month later and one month
    # closer to full retirement age (earlyretire.html note b: 60 reduction months at 62
    # only for births on the 2nd, otherwise 59).
    fra = full_retirement_age_months(birth_year)
    reduction = max(0, fra - claim)
    return max(0, reduction - late_attainer), max(0, claim - fra)


def comparison(birth_year, pia, late_attainer=False):
    fra = full_retirement_age_months(birth_year)
    rows = []
    for label, claim in (('earliest', EARLIEST_CLAIM), ('full_retirement_age', fra), ('latest', LATEST_CLAIM)):
        factor = benefit_factor(*_months(birth_year, claim, late_attainer))
        rows.append(dict(label=label, claim_age_years=claim // 12, claim_age_months=claim % 12,
                         factor=factor, monthly_benefit=pia * factor))
    return rows


def normalize(plan, age, horizon_months, valuation, number):
    """Validate plan['social_security'] and return rows with their projection start month.

    Month 1 is the calendar month after the valuation month. With a birth_date the
    benefit starts in the first month the person has attained the claiming age (for a
    reduced benefit, the first month they are that age throughout). With only a
    birth_year the person is taken to be exactly their age at valuation (plan age, or the
    result of `age` when it is a function of the row), matching how retirement_age maps to
    projection months.
    """
    age_of = age if callable(age) else (lambda row: age)
    rows = plan.get('social_security', [])
    if not isinstance(rows, list) or len(rows) > 10 or any(not isinstance(row, dict) for row in rows):
        raise ValueError('social_security must be a bounded list of objects')
    result, identifiers = [], set()
    for row in rows:
        ident = row.get('id')
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 80 or ident in identifiers:
            raise ValueError('social security ids must be unique non-empty identifiers')
        identifiers.add(ident)
        enabled = row.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValueError('social security enabled must be a boolean')
        birth_date, birth_year = row.get('birth_date'), row.get('birth_year')
        if (birth_date is None) == (birth_year is None):
            raise ValueError('social security needs exactly one of birth_date or birth_year')
        attained = None
        if birth_date is not None:
            if not isinstance(birth_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', birth_date):
                raise ValueError('social security birth_date must be an ISO calendar date (YYYY-MM-DD)')
            try:
                attained = date.fromisoformat(birth_date) - timedelta(days=1)
            except ValueError:
                raise ValueError('social security birth_date must be a real calendar date') from None
            birth_year = attained.year
        birth_year = number(birth_year, 'social security birth_year', FIRST_BIRTH_YEAR, valuation.year, True)
        claim = (number(row.get('claim_age_years'), 'claim_age_years', 62, 70, True) * 12
                 + number(row.get('claim_age_months', 0), 'claim_age_months', 0, 11, True))
        if claim > LATEST_CLAIM:
            raise ValueError('social security claim age cannot be after 70')
        pia = number(row.get('pia_at_fra'), 'pia_at_fra', 0, 1e7)
        late = attained is not None and attained.day != 1
        reduction, credits = _months(birth_year, claim, late)
        if attained is not None:
            # Months counted from the valuation month, which is projection month 0.
            offset = (attained.year - valuation.year) * 12 + attained.month - valuation.month
            start = offset + claim + (late and claim < full_retirement_age_months(birth_year))
        else:
            start = claim - age_of(row) * 12 + 1
        start = min(max(1, start), horizon_months + 1)
        factor = benefit_factor(reduction, credits)
        result.append(dict(id=ident, name=row.get('name') if isinstance(row.get('name'), str) else None,
            enabled=enabled, birth_year=birth_year, pia_at_fra=pia,
            claim_age_years=claim // 12, claim_age_months=claim % 12,
            full_retirement_age_years=full_retirement_age_months(birth_year) // 12,
            full_retirement_age_months=full_retirement_age_months(birth_year) % 12,
            reduction_months=reduction, credit_months=credits, factor=factor,
            monthly_benefit=pia * factor, start_month=start, comparison=comparison(birth_year, pia, late)))
    return result
