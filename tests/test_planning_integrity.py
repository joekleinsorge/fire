"""Accounting checks for payroll deposits, spending access, and house closings."""
import unittest
from fireplanner.engine import project, simulate


class PlanningIntegrityTests(unittest.TestCase):
    def plan(self, **changes):
        return dict(dict(age=59, retirement_age=60, horizon=2, valuation_date='2026-10-15',
                         return_rate=0, accounts=[], streams=[], debts=[]), **changes)

    def test_payroll_deposits_do_not_spend_net_pay_twice(self):
        p = self.plan(accounts=[dict(type='cash', balance=0, return_rate=0),
                               dict(type='retirement', balance=0, available=False, return_rate=0,
                                    payroll_contribution_monthly=100, contribution_end_month=13)],
                      streams=[dict(kind='income', amount=900, end_month=13)])
        r = project(p)
        self.assertAlmostEqual(r['annual'][0]['accounts'][0], 10800)
        self.assertAlmostEqual(r['annual'][0]['accounts'][1], 1200)
        self.assertEqual(r['annual'][1]['payroll_contributions'], 0)
        for m in r['monthly']:
            self.assertAlmostEqual(m['opening'] + m['gain'] - m['fees'] + m['income'] +
                                   m['payroll_contributions'] - m['funded_expenses'] -
                                   m['withdrawal_taxes'], m['closing'])

    def test_age_access_and_withdrawal_tax_reconcile(self):
        p = self.plan(accounts=[dict(type='retirement', balance=1000, return_rate=0,
                                    available=False, available_from_age=59.5, withdrawal_tax_rate=.2)],
                      streams=[dict(kind='expense', amount=80)])
        r = project(p)
        self.assertTrue(all(m['unfunded']==80 for m in r['monthly'][:6]))
        self.assertEqual(r['monthly'][6]['unfunded'], 0)
        self.assertAlmostEqual(r['monthly'][6]['withdrawal_taxes'], 20)
        self.assertAlmostEqual(r['monthly'][6]['accounts'][0], 900)
        for m in r['monthly']:
            self.assertAlmostEqual(m['opening'] - m['funded_expenses'] - m['withdrawal_taxes'], m['closing'])
        with self.assertRaises(ValueError):
            project(self.plan(accounts=[dict(type='property', available_from_age=60)]))

    def house_plan(self, cash):
        return self.plan(age=40, accounts=[dict(id='cash',type='cash',balance=cash,return_rate=0),
                                          dict(id='old-house',type='property',balance=1000,return_rate=0)],
                         debts=[dict(id='old-loan',balance=800,balance_only=True)],
                         streams=[dict(kind='expense',amount=10,essential=True)],
                         future_purchases=[dict(id='move',name='Move',amount=2000,month=1,
                            loan_amount=1600,loan_rate=0,loan_months=20,adds_asset=True,
                            sell_account_id='old-house',payoff_debt_id='old-loan',sell_cost_rate=.1,
                            transaction_costs=50,require_full_funding=True,annual_upkeep=120,
                            replaces_expense_monthly=10,replaces_expense_end_month=25)])

    def test_failed_closing_preserves_home_cash_and_mortgage(self):
        r=project(self.house_plan(200));m=r['monthly'][0]
        self.assertEqual(m['purchase_blocked'],1)
        self.assertAlmostEqual(m['purchase_funding_gap'],160)
        self.assertEqual(m['purchase_loan_drawn'],0)
        self.assertEqual(m['purchase_sale_proceeds'],0)
        self.assertEqual(m['purchase_asset_added'],0)
        self.assertEqual(m['accounts'][1],1000)
        self.assertEqual(m['debt_balance'],800)
        self.assertEqual(m['accounts'][0],190)
        self.assertEqual(r['monthly'][1]['purchase_upkeep'],0)
        self.assertEqual(r['monthly'][1]['essential_expenses'],10)

    def test_funded_closing_pays_all_costs_and_starts_new_loan_next_month(self):
        r=project(self.house_plan(1000));m=r['monthly'][0]
        self.assertEqual(m['purchase_blocked'],0)
        self.assertEqual(m['purchase_sale_costs'],100)
        self.assertEqual(m['purchase_debt_payoff'],800)
        self.assertEqual(m['purchase_asset_added'],2000)
        self.assertEqual(m['purchase_paid'],450)
        self.assertEqual(m['accounts'][0],640)
        self.assertEqual(m['accounts'][1],0)
        self.assertEqual(m['debt_balance'],1600)
        self.assertEqual(r['monthly'][1]['debt_payment'],80)
        self.assertEqual(r['monthly'][1]['purchase_upkeep'],10)
        self.assertEqual(r['monthly'][1]['essential_expenses'],0)

    def test_fixed_nominal_loan_declines_in_real_dollars(self):
        p=self.house_plan(10000);p['inflation_rate']=.03;p['future_purchases'][0]['nominal_loan']=True
        r=project(p)
        self.assertAlmostEqual(r['monthly'][12]['debt_payment'],80/1.03)
        self.assertAlmostEqual(r['monthly'][20]['debt_balance'],0,places=7)
        fixed=simulate(p,dict(trials=1,volatility=0))
        for actual,expected in zip(fixed['paths'][0]['annual'],r['annual']):
            self.assertAlmostEqual(actual['net_worth'],expected['net_worth'])

    def test_reject_invalid_rates_and_flags(self):
        for field,value in [('withdrawal_tax_rate',1),('payroll_contribution_monthly',-1),('available_from_age','59')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                project(self.plan(accounts=[dict(type='retirement',**{field:value})]))
        p=self.house_plan(1000);p['future_purchases'][0]['require_full_funding']='yes'
        with self.assertRaises(ValueError):project(p)

    def test_surplus_fills_reserve_then_invests(self):
        p=self.plan(accounts=[dict(id='cash',type='cash',balance=90,return_rate=0),
                              dict(id='broker',type='investment',balance=0,return_rate=0)],
                    streams=[dict(kind='income',amount=30,end_month=2)],
                    reserve_account_id='cash',cash_reserve_target=100,surplus_account_id='broker')
        r=project(p)
        self.assertEqual(r['monthly'][0]['accounts'],[100,20])
        with self.assertRaises(ValueError):project(dict(p,surplus_account_id='missing'))

    def test_unfunded_standalone_debt_payoff_is_not_reported_as_success(self):
        p=self.plan(accounts=[dict(type='cash',balance=10)],debts=[dict(id='loan',balance=100,balance_only=True)],
                    future_purchases=[dict(id='payoff',name='Retirement payoff',month=1,amount=0,
                                          payoff_debt_id='loan',require_full_funding=True)])
        r=project(p);m=r['monthly'][0]
        self.assertEqual(m['purchase_funding_gap'],90)
        self.assertEqual(m['purchase_unfunded'],100)
        self.assertEqual(m['debt_balance'],100)
        self.assertEqual(m['closing'],10)
        self.assertGreater(r['accumulation_shortfall'],0)

    def test_education_pool_deposit_is_a_funded_transfer_not_lost_spending(self):
        p=self.plan(accounts=[dict(id='cash',type='cash',balance=150,return_rate=0),
                              dict(type='other',available=False,balance=100,return_rate=0,
                                   source_details={'type':'education_restricted'},household_contribution_monthly=100,
                                   contribution_end_month=3)])
        r=project(p)
        self.assertEqual(r['monthly'][0]['accounts'],[50,200])
        self.assertEqual(r['monthly'][1]['accounts'],[0,250])
        self.assertEqual(r['monthly'][1]['account_contribution_unfunded'],50)
        self.assertEqual(r['monthly'][1]['unfunded'],0)
        self.assertEqual(r['monthly'][1]['closing'],250)

    def test_project_upkeep_ends_only_after_successful_linked_move(self):
        for cash, expected in [(10000, 20), (100, 110)]:
            p = self.plan(accounts=[dict(type='cash', balance=cash, return_rate=0)],
                future_purchases=[dict(id='pool', name='Pool', amount=0, month=1,
                    annual_upkeep=120, upkeep_until_purchase_id='move'),
                    dict(id='move', name='Move', amount=1000, month=3,
                    require_full_funding=True)])
            r = project(p)
            self.assertAlmostEqual(r['annual'][0]['purchase_upkeep'], expected)
            self.assertEqual(r['summary']['blocked_purchases'], int(cash == 100))
        p['future_purchases'][0]['upkeep_until_purchase_id'] = 'missing'
        with self.assertRaises(ValueError): project(p)
