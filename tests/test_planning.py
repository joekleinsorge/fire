import unittest
from fireplanner.planning import analyze

class PlanningTests(unittest.TestCase):
    def test_zero_interest_payoff(self):
        result = analyze({'kind': 'debt', 'principal': 1200, 'months': 12})
        self.assertEqual(result['monthly_payment'], 100)
        self.assertEqual(result['schedule'][-1]['closing'], 0)
        self.assertEqual(result['total_interest'], 0)

    def test_independent_amortization(self):
        result = analyze({'kind': 'debt', 'principal': 1000, 'months': 2, 'annual_rate': .12})
        self.assertAlmostEqual(result['monthly_payment'], 507.51243781)
        self.assertAlmostEqual(result['schedule'][0]['closing'], 502.48756219)

    def test_tax_excludes_net_income(self):
        result = analyze({'kind': 'effective_tax', 'gross_income': 100, 'after_tax_income': 50, 'rate': .2})
        self.assertEqual(result['tax'], 20)
        self.assertEqual(result['available_income'], 130)

    def test_insolvent_estate(self):
        result = analyze({'kind': 'estate', 'assets': 100, 'debts': 120})
        self.assertEqual(result['unfunded_obligations'], 20)
        self.assertEqual(result['beneficiary_receipts'], 0)

    def test_mortality_partition(self):
        result = analyze({'kind': 'longevity', 'survival': [.75, 0], 'source': 'synthetic fixture', 'funding_probability': .8})
        row = result['annual'][0]
        self.assertAlmostEqual(row['alive_funded'], .6)
        self.assertAlmostEqual(sum(row[k] for k in ('alive_funded', 'alive_shortfall', 'deceased')), 1)
        self.assertIsNone(result['annual'][1]['funding_conditional_alive'])
        with self.assertRaises(ValueError):
            analyze({'kind': 'longevity', 'source': 'test', 'survival': [.5, .6]})
