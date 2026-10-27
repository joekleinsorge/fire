"""2026 US federal income tax arithmetic for retirement withdrawals; not a tax return.

Sources (reviewed 2026-10-26):
- Rev. Proc. 2025-32, sections 4.01 (tax rate tables), 4.03 (maximum capital gains rate
  breakpoints) and 4.14 (standard deduction, additional amount for age 65 or older).
  https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- Taxable Social Security from provisional income: IRC section 86 base amounts ($25,000 /
  $32,000) and adjusted base amounts ($34,000 / $44,000), as in the IRS Publication 915
  worksheet. These amounts are not indexed for inflation.

Projections are in constant 2026 dollars. Brackets, deductions and capital gains
breakpoints are indexed for inflation, so they stay fixed in real terms; the Social
Security thresholds are not indexed, so callers shrink them by cumulative inflation.
Not modeled: the temporary 2025-2028 senior deduction, the net investment income tax,
itemized deductions, credits, AMT, and state tax beyond a flat rate.
"""
import math

RULES = dict(
    married_joint=dict(
        deduction=32200.0, aged_addition=1650.0,
        brackets=((24800.0, .10), (100800.0, .12), (211400.0, .22), (403550.0, .24),
                  (512450.0, .32), (768700.0, .35), (math.inf, .37)),
        capital_gains=(98900.0, 613700.0), social_security=(32000.0, 44000.0)),
    single=dict(
        deduction=16100.0, aged_addition=2050.0,
        brackets=((12400.0, .10), (50400.0, .12), (105700.0, .22), (201775.0, .24),
                  (256225.0, .32), (640600.0, .35), (math.inf, .37)),
        capital_gains=(49450.0, 545500.0), social_security=(25000.0, 34000.0)),
)
FILING_STATUSES = tuple(RULES)


def ordinary_tax(status, taxable):
    tax, floor = 0.0, 0.0
    for ceiling, rate in RULES[status]['brackets']:
        if taxable <= floor:
            break
        tax += (min(taxable, ceiling) - floor) * rate
        floor = ceiling
    return tax


def taxable_social_security(status, other_income, benefits, threshold_scale=1.0):
    """IRC section 86: the taxable part of benefits from provisional income."""
    base, adjusted = (amount * threshold_scale for amount in RULES[status]['social_security'])
    provisional = other_income + .5 * benefits
    if provisional <= base:
        return 0.0
    if provisional <= adjusted:
        return min(.5 * benefits, .5 * (provisional - base))
    return min(.85 * benefits, .85 * (provisional - adjusted) + min(.5 * benefits, .5 * (adjusted - base)))


def annual_tax(status, ordinary, gains, benefits, aged=0, state_rate=0.0, threshold_scale=1.0):
    """Federal tax plus a flat state rate on federal taxable income.

    ordinary: pre-tax withdrawals and other taxable income; gains: long-term capital gains;
    benefits: Social Security received; aged: filers 65 or older."""
    rules = RULES[status]
    ordinary_income = ordinary + taxable_social_security(status, ordinary + gains, benefits, threshold_scale)
    deduction = rules['deduction'] + aged * rules['aged_addition']
    taxable = max(0.0, ordinary_income + gains - deduction)
    ordinary_taxable = max(0.0, ordinary_income - deduction)
    # Gains stack on top of ordinary income: 0% to the first breakpoint, 15% to the second.
    zero_top, fifteen_top = rules['capital_gains']
    low, high = ordinary_taxable, taxable
    at_15 = max(0.0, min(high, fifteen_top) - max(low, zero_top))
    at_20 = max(0.0, high - max(low, fifteen_top))
    return ordinary_tax(status, ordinary_taxable) + .15 * at_15 + .20 * at_20 + state_rate * taxable


# IRS Publication 590-B, Appendix B, Table III (Uniform Lifetime), from age 72.
UNIFORM_LIFETIME = (27.4, 26.5, 25.5, 24.6, 23.7, 22.9, 22.0, 21.1, 20.2, 19.4, 18.5, 17.7, 16.8,
                    16.0, 15.2, 14.4, 13.7, 12.9, 12.2, 11.5, 10.8, 10.1, 9.5, 8.9, 8.4, 7.8, 7.3,
                    6.8, 6.4, 6.0, 5.6, 5.2, 4.9, 4.6, 4.3, 4.1, 3.9, 3.7, 3.5, 3.4, 3.3, 3.1,
                    3.0, 2.9, 2.8, 2.7, 2.5, 2.3, 2.0)


def rmd_start_age(birth_year):
    # SECURE 2.0 section 107: 73 for births 1951-1959 and 75 from 1960. The statute's
    # 1959 overlap is resolved as 73 here.
    return 75 if birth_year >= 1960 else 73


def rmd_divisor(age):
    return UNIFORM_LIFETIME[min(max(age, 72), 120) - 72]
