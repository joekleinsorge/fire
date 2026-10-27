import unittest
from fireplanner import federal_tax as tax


class FederalTaxTests(unittest.TestCase):
    def test_bracket_tax_matches_rev_proc_2025_32_tables(self):
        # "The Tax Is" column at each threshold of Tables 1 and 3.
        for status, points in (
            ('married_joint', ((24800, 2480), (100800, 11600), (211400, 35932), (403550, 82048),
                               (512450, 116896), (768700, 206583.50))),
            ('single', ((12400, 1240), (50400, 5800), (105700, 17966), (201775, 41024),
                        (256225, 58448), (640600, 192979.25)))):
            for income, expected in points:
                self.assertAlmostEqual(tax.ordinary_tax(status, income), expected, places=2, msg=(status, income))
        self.assertAlmostEqual(tax.ordinary_tax('single', 700600), 192979.25 + .37 * 60000)

    def test_standard_deduction_and_age_addition(self):
        self.assertEqual(tax.annual_tax('single', 16100, 0, 0), 0)
        self.assertAlmostEqual(tax.annual_tax('single', 18150, 0, 0), 205)
        self.assertEqual(tax.annual_tax('single', 18150, 0, 0, aged=1), 0)
        self.assertEqual(tax.annual_tax('married_joint', 32200 + 2 * 1650, 0, 0, aged=2), 0)

    def test_capital_gains_stack_on_ordinary_income(self):
        # All gains within the 0% band.
        self.assertEqual(tax.annual_tax('single', 16100, 49450, 0), 0)
        # Ordinary income fills the 0% band, so every gain dollar is taxed at 15%.
        ordinary = 16100 + 49450
        self.assertAlmostEqual(tax.annual_tax('single', ordinary, 10000, 0) - tax.annual_tax('single', ordinary, 0, 0), 1500)
        # Gains above the second breakpoint pay 20%.
        top = 16100 + 545500
        self.assertAlmostEqual(tax.annual_tax('single', top, 1000, 0) - tax.annual_tax('single', top, 0, 0), 200)

    def test_taxable_social_security_tiers(self):
        self.assertEqual(tax.taxable_social_security('single', 0, 40000), 0)
        # Provisional 30,000: half of the excess over 25,000.
        self.assertAlmostEqual(tax.taxable_social_security('single', 10000, 40000), 2500)
        # Provisional 60,000: 85% of the excess over 34,000 plus the 4,500 middle tier, capped at 85% of benefits.
        self.assertAlmostEqual(tax.taxable_social_security('single', 40000, 40000), min(34000, .85 * 26000 + 4500))
        self.assertAlmostEqual(tax.taxable_social_security('married_joint', 200000, 40000), 34000)
        # Unindexed thresholds shrink in real terms.
        self.assertGreater(tax.taxable_social_security('single', 10000, 40000, threshold_scale=.8), 2500)

    def test_state_rate_applies_to_federal_taxable_income(self):
        self.assertAlmostEqual(tax.annual_tax('single', 26100, 0, 0, state_rate=.05) - tax.annual_tax('single', 26100, 0, 0), 500)

    def test_rmd_rules(self):
        self.assertEqual(tax.rmd_start_age(1955), 73)
        self.assertEqual(tax.rmd_start_age(1959), 73)
        self.assertEqual(tax.rmd_start_age(1960), 75)
        # Publication 590-B examples: 26.5 at 73 and 24.6 at 75.
        self.assertEqual(tax.rmd_divisor(73), 26.5)
        self.assertEqual(tax.rmd_divisor(75), 24.6)
        self.assertEqual(tax.rmd_divisor(125), 2.0)
