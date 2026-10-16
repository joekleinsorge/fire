"""2026 Marketplace premium-credit arithmetic with explicit eligibility inputs."""

from .taxes import value


def estimate(data):
    if data.get("year") != 2026:
        raise ValueError(
            "Reviewed Marketplace reference year is2026; future subsidies are not assumed"
        )
    size = value(data.get("family_size"), "family_size", 1, 20)
    if int(size) != size:
        raise ValueError("Family size must be an integer")
    magi = value(data.get("magi"), "household MAGI")
    benchmark = value(data.get("benchmark_premium_annual"), "benchmark premium")
    premium = value(data.get("selected_premium_annual"), "selected premium")
    oop = value(data.get("out_of_pocket_budget_annual"), "out-of-pocket budget")
    fpl = 15650 + 5500 * (size - 1)
    ratio = magi / fpl
    eligibility = data.get("eligibility_confirmed")
    if eligibility is not True:
        return dict(
            status="needs_eligibility_confirmation",
            premium_tax_credit=None,
            net_premium=None,
            source="https://www.irs.gov/affordable-care-act/individuals-and-families/eligibility-for-the-premium-tax-credit",
            note="Confirm Marketplace eligibility,MFJ status,coverage months,and lack of disqualifying employer/government coverage. No credit applied.",
        )
    percentage = None
    for lower, upper, initial, final in [
        (1, 1.33, 0.021, 0.021),
        (1.33, 1.5, 0.0314, 0.0419),
        (1.5, 2, 0.0419, 0.066),
        (2, 2.5, 0.066, 0.0844),
        (2.5, 3, 0.0844, 0.0996),
        (3, 4.000000001, 0.0996, 0.0996),
    ]:
        if lower <= ratio < upper:
            percentage = initial + (final - initial) * (ratio - lower) / (upper - lower)
            break
    expected = magi * percentage if percentage is not None else None
    credit = min(premium, max(0, benchmark - expected)) if expected is not None else 0
    return dict(
        status="2026_reference_estimate",
        family_size=size,
        poverty_level=fpl,
        fpl_ratio=ratio,
        expected_household_contribution=expected,
        premium_tax_credit=credit,
        net_premium=premium - credit,
        total_healthcare_budget=premium - credit + oop,
        source="https://www.irs.gov/irb/2025-32_IRB",
        poverty_source="https://www.healthcare.gov/glossary/federal-poverty-level-fpl/",
        note="Full-year2026 reference arithmetic,not an eligibility determination. Uses2025 poverty guidelines for2026 Marketplace coverage. Income outside100–400% gets no credit here; special exceptions,Medicaid/CHIP,mixed eligibility and partial-year coverage are excluded. Enter actual benchmark/plan quotes. Repayment limits for excess advance credits were eliminated beginning2026.",
    )
