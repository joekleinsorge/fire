import unittest
from fireplanner.engine import project
from fireplanner.social_security import benefit_factor, full_retirement_age_months


def plan(**changes):
    base = dict(age=60, retirement_age=62, horizon=12, return_rate=0, withdrawal_rate=.04,
                valuation_date='2026-12-31',
                accounts=[dict(type='investment', balance=500000, return_rate=0)],
                streams=[dict(kind='expense', amount=4000)])
    return dict(base, **changes)


def benefit(**changes):
    return dict(dict(id='ss', birth_year=1966, pia_at_fra=2000, claim_age_years=67, claim_age_months=0), **changes)


class SocialSecurityRuleTests(unittest.TestCase):
    def test_full_retirement_age_by_birth_year(self):
        # SSA OACT earlyretire.html table.
        self.assertEqual(full_retirement_age_months(1954), 66 * 12)
        self.assertEqual(full_retirement_age_months(1955), 66 * 12 + 2)
        self.assertEqual(full_retirement_age_months(1959), 66 * 12 + 10)
        self.assertEqual(full_retirement_age_months(1960), 67 * 12)

    def test_factors_match_ssa_tables(self):
        # SSA OACT ar_drc.html: percent of PIA at 62 / 70 by year of birth.
        self.assertAlmostEqual(benefit_factor(60, 0), .70)    # 1960+, age 62
        self.assertAlmostEqual(benefit_factor(48, 0), .75)    # 1943-54, age 62
        self.assertAlmostEqual(benefit_factor(54, 0), .725)   # 1957, age 62
        self.assertAlmostEqual(benefit_factor(36, 0), 1 - .20)
        self.assertAlmostEqual(benefit_factor(0, 0), 1)
        self.assertAlmostEqual(benefit_factor(0, 36), 1.24)   # 1960+, age 70
        self.assertAlmostEqual(benefit_factor(0, 42), 1.28)   # 1957, age 70

    def test_projection_reports_claim_ages(self):
        for years, expected in ((62, .70), (67, 1.0), (70, 1.24)):
            row = project(plan(social_security=[benefit(claim_age_years=years)]))['social_security'][0]
            self.assertAlmostEqual(row['factor'], expected)
            self.assertAlmostEqual(row['monthly_benefit'], 2000 * expected)
        comparison = row['comparison']
        self.assertEqual([c['claim_age_years'] for c in comparison], [62, 67, 70])
        self.assertAlmostEqual(comparison[0]['monthly_benefit'], 1400)

    def test_january_first_birth_uses_prior_year(self):
        row = project(plan(social_security=[dict(benefit(), birth_year=None, birth_date='1960-01-01')]))['social_security'][0]
        self.assertEqual(row['birth_year'], 1959)
        self.assertEqual((row['full_retirement_age_years'], row['full_retirement_age_months']), (66, 10))
        self.assertAlmostEqual(row['factor'], 1 + 2 * 2 / 300)


class SocialSecurityLedgerTests(unittest.TestCase):
    def test_start_month_from_plan_age(self):
        # Age 60 at valuation; age 62 starts month 25 (as retirement_age does), so 62y3m is month 28.
        result = project(plan(social_security=[benefit(claim_age_years=62, claim_age_months=3)]))
        income = [row['income'] for row in result['monthly']]
        self.assertEqual(result['social_security'][0]['start_month'], 28)
        self.assertEqual(income[26], 0)
        self.assertAlmostEqual(income[27], 2000 * (1 - (36 * 5 / 9 + 21 * 5 / 12) / 100))
        self.assertAlmostEqual(income[-1], income[27])

    def test_start_month_from_birth_date(self):
        # Born 1964-06-15 (attains ages on the 14th). Valuation 2026-12-31, month 1 = Jan 2027.
        # Attains 67 (full retirement age) in June 2031 = month 54.
        late = dict(benefit(), birth_year=None, birth_date='1964-06-15')
        row = project(plan(social_security=[late]))['social_security'][0]
        self.assertEqual(row['start_month'], 54)
        self.assertAlmostEqual(row['factor'], 1)
        early = project(plan(social_security=[dict(late, claim_age_years=64)]))['social_security'][0]
        # Attains 64 in June 2028 (month 18); first full month is July (month 19), 35 reduction months.
        self.assertEqual(early['start_month'], 19)
        self.assertEqual(early['reduction_months'], 35)
        on_second = project(plan(social_security=[dict(late, birth_date='1964-06-02', claim_age_years=64)]))['social_security'][0]
        self.assertEqual((on_second['start_month'], on_second['reduction_months']), (18, 36))

    def test_target_counts_benefit_active_at_retirement(self):
        base = project(plan())
        claimed = project(plan(social_security=[benefit(claim_age_years=62)]))
        self.assertAlmostEqual(claimed['annual_retirement_income'], 1400 * 12)
        self.assertAlmostEqual(claimed['target'], base['target'] - 1400 * 12 / .04)
        later = project(plan(social_security=[benefit(claim_age_years=67)]))
        self.assertEqual(later['annual_retirement_income'], 0)
        self.assertAlmostEqual(later['target'], base['target'])
        paused = project(plan(social_security=[benefit(claim_age_years=62, enabled=False)]))
        self.assertEqual(paused['annual_retirement_income'], 0)
        self.assertEqual(sum(row['income'] for row in paused['monthly']), 0)

    def test_plans_without_field_unchanged(self):
        result = project(plan())
        self.assertEqual(result['social_security'], [])
        self.assertFalse(any('Social Security' in w for w in result['warnings']))

    def test_validation(self):
        bad = [benefit(claim_age_years=61), benefit(claim_age_years=70, claim_age_months=1),
               benefit(claim_age_months=12), benefit(pia_at_fra=-1), benefit(birth_year=1942),
               benefit(birth_year=1966.5), dict(benefit(), birth_date='1966-01-01'),
               dict(benefit(), birth_year=None), benefit(enabled='yes'), benefit(id='')]
        for row in bad:
            with self.assertRaises(ValueError, msg=row):
                project(plan(social_security=[row]))
        with self.assertRaises(ValueError):
            project(plan(social_security=[benefit(), benefit()]))
        with self.assertRaises(ValueError):
            project(plan(social_security={}))


if __name__ == '__main__':
    unittest.main()
