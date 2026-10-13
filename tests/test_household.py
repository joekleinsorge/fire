import json
from pathlib import Path
import tempfile
import unittest

from fireplanner.engine import project
from fireplanner.household import import_household, draft_scenarios
from fireplanner.store import Store


def source_fixture():
    return dict(source=dict(currency='USD'), planner_inputs=dict(
        plan_name='Synthetic household', valuation_date='2025-01-01',
        planner_assumptions=dict(current_age_years=40, plan_through_age_years=90,
                                 retirement_age_years=60, real_portfolio_return_pct=4,
                                 withdrawal_rate_pct=3.5),
        accounts=[dict(name='Cash', type='cash', balance_usd=10000),
                  dict(name='Restricted', type='employer_equity', stated_value_usd=20000,
                       vested_units=None, realizable_value=None),
                  dict(name='Education', type='education_restricted', balance_usd=5000)],
        debts=[dict(name='Escrow loan', balance_usd=80000, apr_pct=3,
                    reported_monthly_payment_usd=500, remaining_term_months=None)],
        cash_flow=dict(recurring_essentials_annual_usd=12000,
                       other_and_one_time_residual_annual_usd=3000),
        retirement_goal=dict(normal_annual_spending_target_2026_usd=dict(low=12000, high=16000),
                             minimum_annual_spending_target_2026_usd=dict(low=10000, high=12000)),
        income=dict(prior_net_monthly_estimate_usd=2000, verified_take_home_pay=None),
        planned_home_projects=dict(roof=dict(estimated_cost_usd=1000, timing='unknown')),
        unknowns_to_preserve_as_null=['verified_income', 'mortgage_term']),
        source_profile=dict(holdings=None, original_note='Keep this <exactly>'))


class HouseholdImportTests(unittest.TestCase):
    def test_full_source_round_trips_privately_with_unknowns(self):
        source = source_fixture()
        plan = import_household(source)
        self.assertEqual(plan['household_source'], source)
        self.assertTrue(all(value is None for value in plan['unresolved_inputs'].values()))
        self.assertEqual(sum(a['balance'] for a in plan['accounts'] if a['available']), 10000)
        self.assertFalse(plan['future_purchases'][0]['enabled'])
        self.assertEqual(plan['members'], [])
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'private.sqlite3')
            user = store.register('test@example.invalid', 'synthetic-password-only')
            saved = store.save(user, dict(name=plan['name'], plan=plan))
            self.assertEqual(store.plan(user, saved['id'])['plan']['household_source'], source)
            self.assertEqual(Path(store.path).stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(json.dumps(plan))['household_source'], source)

    def test_reference_debt_does_not_duplicate_spending_or_invent_payoff(self):
        plan = import_household(source_fixture())
        result = project(plan)
        for row in result['monthly']:
            self.assertEqual(row['debt_balance'], 80000)
            self.assertEqual(row['debt_payment'], 0)
            self.assertEqual(row['debt_interest'], 0)
        self.assertEqual(result['annual'][0]['expenses'], 15000)
        plan['debts'][0]['balance_only'] = False
        self.assertGreater(project(plan)['monthly'][0]['debt_payment'], 0)

    def test_scenarios_do_not_mutate_source_or_grant_asset_access(self):
        source = source_fixture()
        plan = import_household(source)
        scenarios = draft_scenarios(plan)
        self.assertEqual(len(scenarios), 3)
        for row in scenarios:
            self.assertEqual(row['plan']['household_source'], source)
            self.assertFalse(row['plan']['accounts'][1]['available'])
            project(row['plan'])
        self.assertEqual(plan['return_rate'], .04)
        self.assertEqual(source_fixture(), source)

    def test_reference_flag_rejects_non_boolean(self):
        plan = import_household(source_fixture())
        plan['debts'][0]['balance_only'] = 'yes'
        with self.assertRaises(ValueError):
            project(plan)
