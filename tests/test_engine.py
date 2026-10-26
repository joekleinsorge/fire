import math
import unittest
from fireplanner.engine import quick, project, simulate


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(age=30, income=60, expenses=40, assets=100, return_rate=0, withdrawal_rate=.04, horizon=100)

    def test_contract_fi(self):
        result = quick(self.plan)
        self.assertEqual(result['years_to_target'], 45)
        self.assertEqual(result['annual'][44]['balance'], 980)
        self.assertEqual(result['annual'][45]['balance'], 1000)
        self.assertAlmostEqual(result['savings_rate'], 1/3)

    def test_states(self):
        self.assertEqual(quick(dict(self.plan, assets=1000))['status'], 'already_at_target')
        self.assertEqual(quick(dict(self.plan, income=40))['status'], 'unreachable')
        result = quick(dict(self.plan, income=0))
        self.assertIsNone(result['savings_rate'])
        self.assertEqual(result['first_shortfall_year'], 3)
        self.assertEqual(result['annual'][3]['unfunded'], 20)
        self.assertEqual(quick(dict(self.plan, horizon=10))['status'], 'not_reached_within_horizon')

    def test_monthly_parity_and_reconciliation(self):
        result = project(dict(self.plan, return_rate=.047))
        reference = quick(dict(self.plan, return_rate=.047))
        for m in result['monthly']:
            self.assertAlmostEqual(m['opening'] + m['gain'] + m['income'] - m['expenses'] + m['unfunded'], m['closing'], places=7)
            if m['month'] % 12 == 0:
                self.assertEqual(m['closing'], reference['annual'][m['month']//12]['balance'])

    def test_obligations_and_boundary(self):
        result = project(dict(self.plan, horizon=1, accounts=[dict(balance=30,return_rate=0)], streams=[dict(kind='expense',amount=40,start_month=1,end_month=2)]))
        self.assertEqual(result['monthly'][0]['unfunded'], 10)
        self.assertEqual(result['monthly'][1]['expenses'], 0)
        self.assertEqual(result['first_shortfall_month'], 1)
        self.assertEqual(result['annual'][0]['unfunded'], 10)
        self.assertEqual(result['annual'][0]['expenses'], 40)

    def test_validation(self):
        for key, value in [('assets', -1), ('age', 1.5), ('income', math.nan), ('return_rate', -1), ('horizon', 1000), ('withdrawal_rate',0)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                quick(dict(self.plan, **{key:value}))
        with self.assertRaises(ValueError):
            simulate(self.plan, dict(mode='resampling'))
        with self.assertRaises(ValueError):
            simulate(self.plan, dict(mode='block', historical_returns=[0],block_size=2))
        with self.assertRaisesRegex(ValueError, 'real calendar date'):
            quick(dict(self.plan, valuation_date='2026-02-30'))
        dated = project(dict(self.plan, valuation_date='2026-09-30'))
        self.assertEqual(dated['metadata']['valuation_date'], '2026-09-30')

    def test_historical_reports_no_complete_period_as_unavailable(self):
        result = simulate(self.plan, {'mode': 'historical', 'historical_returns': [.02, .03]})
        self.assertEqual(result['status'], 'no_complete_periods')
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['paths'], [])
        self.assertIsNone(result['ending_assets'])
        self.assertEqual(len(result['incomplete_history']), 2)

    def test_seed_and_statistics(self):
        settings = dict(trials=10,seed=42)
        self.assertEqual(simulate(self.plan, settings), simulate(self.plan, settings))
        result = simulate(self.plan, dict(mode='resampling',historical_returns=[0], trials=3,retirement_year=99))
        self.assertAlmostEqual(result['ending_assets']['median'], 2040)
        self.assertEqual(result['ending_assets']['standard_deviation'], 0)
        self.assertEqual(result['outcomes']['portfolio_survives']['rate'], 1)

    def test_retirement_stops_income(self):
        result = simulate(dict(self.plan, horizon=3), dict(trials=1, volatility=0))
        self.assertEqual(result['paths'][0]['first_shortfall_year'], 3)
        self.assertEqual(result['outcomes']['desired_lifestyle_funded']['rate'], 0)
        self.assertEqual(result['outcomes']['portfolio_survives']['rate'], 0)

    def test_history_excludes_incomplete(self):
        result = simulate(dict(self.plan,horizon=2),dict(mode='historical',historical_returns=[0,0,0]))
        self.assertEqual(result['completed'],2)
        self.assertEqual(len(result['incomplete_history']),1)
        result = simulate(dict(self.plan,horizon=5),dict(mode='historical',historical_returns=[0]))
        self.assertIsNone(result['ending_assets'])

    def test_accumulation_failure_invalidates_feasibility(self):
        result = simulate(dict(self.plan, income=0, assets=0, horizon=3), dict(trials=1,volatility=0,retirement_year=1))
        self.assertEqual(result['paths'][0]['accumulation_shortfall'],40)
        self.assertFalse(result['paths'][0]['retirement_feasible'])
        self.assertEqual(result['paths'][0]['retirement_year'],1)

    def test_no_retirement_is_unavailable(self):
        result = simulate(dict(self.plan,income=40),dict(trials=2,volatility=0,retirement_year=100))
        self.assertIsNone(result['outcomes']['portfolio_survives']['rate'])
        self.assertEqual(result['outcomes']['portfolio_survives']['excluded'],2)

class FullEngineTests(unittest.TestCase):
    def plan(self, **changes):
        return dict(dict(age=40, retirement_age=41, horizon=2, return_rate=0,
            accounts=[dict(type='investment',balance=1200,return_rate=0)], streams=[]), **changes)

    def test_full_zero_volatility_matches_fixed_projection(self):
        plan = self.plan(return_rate=.04, accounts=[dict(type='investment',balance=10000,return_rate=.06,fee_rate=.01),dict(type='cash',balance=500,return_rate=.02)],
            streams=[dict(kind='income',amount=500,end_month=13),dict(kind='expense',amount=700)],
            debts=[dict(balance=400,annual_rate=.12,months=12)])
        fixed = project(plan)
        sampled = simulate(plan, dict(trials=3,volatility=0))
        for path in sampled['paths']:
            for actual, expected in zip(path['annual'], fixed['annual']):
                self.assertAlmostEqual(actual['balance'],expected['balance'],places=7)
                self.assertAlmostEqual(actual['net_worth'],expected['net_worth'],places=7)
                self.assertAlmostEqual(actual['unfunded'],expected['unfunded'],places=7)
        self.assertEqual(sampled['annual_bands'][0]['p10'],sampled['annual_bands'][0]['p90'])

    def test_full_simulation_uses_stream_essential_classification(self):
        plan = self.plan(streams=[dict(kind='expense', amount=50_000, essential=True)])
        result = simulate(plan, dict(trials=1, volatility=0))
        self.assertEqual(result['outcomes']['essential_spending_funded']['denominator'], 1)
        with self.assertRaisesRegex(ValueError, 'defined by expense streams'):
            simulate(plan, dict(trials=1, essential_expenses=20_000))

    def test_debt_only_plan_cannot_fall_back_to_quick_mode(self):
        plan = dict(age=40, horizon=1, debts=[dict(balance=100)])
        with self.assertRaisesRegex(ValueError, 'requires at least one account'):
            project(plan)
        with self.assertRaisesRegex(ValueError, 'requires at least one account'):
            simulate(plan, dict(trials=1))

    def test_retirement_does_not_truncate_explicit_streams(self):
        plan = self.plan(streams=[dict(kind='income',amount=100,end_month=13),
            dict(kind='income',amount=20,start_month=13), dict(kind='income',amount=999,enabled=False)])
        result = project(plan)
        self.assertEqual(result['annual'][0]['income'],1200)
        self.assertEqual(result['annual'][1]['income'],240)
        self.assertEqual(simulate(plan,dict(trials=1,volatility=0))['paths'][0]['ending_balance'],2640)
        self.assertEqual(result['summary']['retirement_balance'],2400)

    def test_fee_and_growth_arithmetic(self):
        result = project(self.plan(horizon=1, accounts=[dict(balance=1000,return_rate=.1,fee_rate=.02)]))
        self.assertAlmostEqual(result['annual'][0]['balance'],1078)
        for row in result['monthly']:
            self.assertAlmostEqual(row['closing'],row['opening']+row['gain']-row['fees'])
        growth = project(self.plan(streams=[dict(kind='income',amount=100,every_months=12,growth_rate=.1)]))
        self.assertAlmostEqual(growth['annual'][1]['income'],110)

    def test_unavailable_assets_and_essential_priority(self):
        result = project(self.plan(accounts=[dict(balance=1000,available=False,return_rate=0),dict(balance=100,return_rate=0)],
            streams=[dict(kind='expense',amount=90,essential=False,end_month=2),dict(kind='expense',amount=80,essential=True,end_month=2)]))
        row = result['monthly'][0]
        self.assertEqual(row['essential_unfunded'],0)
        self.assertEqual(row['unfunded'],70)
        self.assertEqual(row['closing'],1000)
        self.assertEqual(row['available_balance'],0)

    def test_retirement_feasibility_is_separate_from_pre_retirement_shortfall(self):
        plan = dict(age=30, horizon=3, retirement_age=31, return_rate=0, withdrawal_rate=.04,
            accounts=[dict(balance=0, return_rate=0)],
            streams=[dict(kind='expense', amount=10, every_months=1, start_month=1, end_month=37, essential=True),
                     dict(kind='income', amount=100, every_months=1, start_month=2, end_month=13, essential=True)])
        result = simulate(plan, {'trials':1,'seed':1,'mean':0,'volatility':0,'retirement_year':1})
        self.assertGreater(result['paths'][0]['accumulation_shortfall'], 0)
        self.assertTrue(result['paths'][0]['retirement_feasible'])

    def test_debt_ledger_and_unpaid_principal(self):
        result = project(self.plan(accounts=[dict(balance=0)],streams=[dict(kind='income',amount=110,end_month=2)],
            debts=[dict(balance=1200,annual_rate=.12,months=12,payment=100)]))
        row = result['monthly'][0]
        self.assertEqual(row['debt_interest'],12)
        self.assertEqual(row['debt_payment'],100)
        self.assertEqual(row['debt_principal'],88)
        self.assertEqual(row['debt_balance'],1112)
        self.assertEqual(row['net_worth'],-1102)
        next_row=result['monthly'][1]
        self.assertEqual(next_row['debt_payment'],10)
        self.assertAlmostEqual(next_row['debt_balance'],1113.12)
        self.assertEqual(next_row['debt_unfunded'],90)
        # A payment below accrued interest capitalizes the difference; it
        # cannot be reported as negative principal repayment.
        self.assertEqual(next_row['debt_principal'],0)
        self.assertEqual(next_row['debts'][0]['principal'],0)

    def test_surplus_without_available_accounts_remains_spendable(self):
        result=project(self.plan(accounts=[dict(balance=100,available=False)],streams=[dict(kind='income',amount=50,end_month=2),dict(kind='expense',amount=30,start_month=2,end_month=3)]))
        self.assertEqual(result['monthly'][1]['available_balance'],20)
        self.assertEqual(result['monthly'][1]['balance'],120)

    def test_unpaid_matured_debt_is_not_recounted_each_month(self):
        result=project(self.plan(accounts=[dict(balance=0)],debts=[dict(balance=1200,months=12)]))
        self.assertAlmostEqual(result['summary']['total_unfunded'],1200)
        self.assertAlmostEqual(result['monthly'][-1]['debt_balance'],1200)
        with_interest=project(self.plan(accounts=[dict(balance=0)],debts=[dict(balance=1200,months=12,annual_rate=.12)]))
        # Missed payments plus interest accrued on the unpaid balance; never the balance again each month.
        self.assertLess(with_interest['summary']['total_unfunded'],with_interest['monthly'][-1]['debt_balance']+1e-6)

    def test_monthly_and_annual_reconciliation(self):
        result=project(self.plan(accounts=[dict(balance=100,return_rate=.03,fee_rate=.01)],streams=[dict(kind='income',amount=30),dict(kind='expense',amount=40)],debts=[dict(balance=100,months=12)]))
        for row in result['monthly']:
            self.assertAlmostEqual(row['closing'],row['opening']+row['gain']-row['fees']+row['income']-row['funded_expenses']-row['debt_payment'])
            self.assertAlmostEqual(row['net_worth'],row['closing']-row['debt_balance'])
        self.assertAlmostEqual(sum(row['unfunded'] for row in result['annual']),result['summary']['total_unfunded'])


class FuturePurchaseTests(unittest.TestCase):
    def plan(self, **changes):
        return dict(dict(age=40, retirement_age=41, horizon=2, return_rate=0, withdrawal_rate=.04,
            accounts=[dict(type='investment', balance=200000, return_rate=0)],
            streams=[dict(kind='expense', amount=1000)]), **changes)

    def test_purchase_and_upkeep_reduce_assets_and_raise_target(self):
        baseline = project(self.plan())
        pool = project(self.plan(future_purchases=[dict(id='pool', name='Pool', amount=100000, month=6, annual_upkeep=1200)]))
        self.assertEqual(pool['monthly'][5]['purchase_due'], 100000)
        self.assertEqual(pool['monthly'][5]['purchase_upkeep'], 0)
        self.assertEqual(pool['monthly'][6]['purchase_upkeep'], 100)
        # 18 months of upkeep after the purchase month.
        self.assertAlmostEqual(baseline['summary']['ending_assets'] - pool['summary']['ending_assets'], 100000 + 1800)
        self.assertAlmostEqual(pool['target'] - baseline['target'], 1200 / .04)

    def test_unaffordable_purchase_is_unfunded_and_disabled_purchase_is_ignored(self):
        short = project(self.plan(future_purchases=[dict(id='home', name='Home', amount=300000, month=1)]))
        self.assertAlmostEqual(short['monthly'][0]['purchase_unfunded'], 300000 - 199000)
        self.assertEqual(short['first_shortfall_month'], 1)
        disabled = project(self.plan(future_purchases=[dict(id='home', name='Home', amount=200000, month=1, annual_upkeep=500, enabled=False)]))
        self.assertEqual(disabled['annual'], project(self.plan())['annual'])
        self.assertEqual(disabled['target'], project(self.plan())['target'])

    def test_earliest_fi_age_shows_purchase_delay_before_planned_retirement(self):
        plan = dict(age=30, retirement_age=60, horizon=40, return_rate=0, withdrawal_rate=.04,
            accounts=[dict(type='investment', balance=0, return_rate=0)],
            streams=[dict(kind='income', amount=5000, end_month=361), dict(kind='expense', amount=1000)])
        baseline = project(plan)
        # Target 12,000 / .04 = 300,000 at 4,000 saved a month: crossed at month 75.
        self.assertEqual(baseline['earliest_fi_age'], 37)
        self.assertEqual(baseline['fi_age'], 60)
        pool = project(dict(plan, future_purchases=[dict(id='pool', name='Pool', amount=48000, month=12)]))
        self.assertEqual(pool['earliest_fi_age'], 38)
        self.assertEqual(pool['fi_age'], baseline['fi_age'])

    def test_financed_home_creates_asset_and_loan(self):
        home = dict(id='home', name='Home', amount=400000, month=6, loan_amount=320000,
                    loan_rate=.06, loan_months=360, adds_asset=True, asset_return=.02)
        result = project(self.plan(future_purchases=[home]))
        before, bought, after = result['monthly'][4], result['monthly'][5], result['monthly'][6]
        self.assertAlmostEqual(bought['purchase_paid'], 80000)
        self.assertAlmostEqual(bought['debt_balance'], 320000)
        self.assertAlmostEqual(bought['purchase_asset_value'], 400000)
        # Swapping cash for an asset financed by a loan leaves net worth unchanged.
        self.assertAlmostEqual(bought['net_worth'], before['net_worth'] - 1000)
        self.assertAlmostEqual(bought['available_balance'], before['available_balance'] - 81000)
        payment = 320000 * .005 / (1 - 1.005 ** -360)
        self.assertAlmostEqual(after['debt_payment'], payment)
        self.assertAlmostEqual(after['purchase_asset_value'], 400000 * 1.02 ** (1 / 12))
        for row in result['monthly']:
            self.assertAlmostEqual(row['closing'], row['opening'] + row['gain'] - row['fees'] + row['income']
                                   - row['funded_expenses'] - row['debt_payment'] + row['purchase_asset_added'], places=6)
        self.assertAlmostEqual(result['annual'][0]['purchase_asset_value'], 400000 * 1.02 ** (6 / 12))

    def test_move_up_sells_current_home_and_pays_off_its_mortgage(self):
        plan = self.plan(
            accounts=[dict(id='invest', type='investment', balance=200000, return_rate=0),
                      dict(id='house', type='property', balance=300000, return_rate=0)],
            debts=[dict(id='mortgage', balance=150000, annual_rate=0, months=300)],
            future_purchases=[dict(id='new', name='New home', amount=500000, month=6, loan_amount=300000,
                                   loan_rate=0, loan_months=360, adds_asset=True,
                                   sell_account_id='house', payoff_debt_id='mortgage', sell_cost_rate=.06)])
        result = project(plan)
        before, moved = result['monthly'][4], result['monthly'][5]
        self.assertAlmostEqual(moved['purchase_sale_proceeds'], 282000)
        self.assertAlmostEqual(moved['purchase_sale_costs'], 18000)
        self.assertAlmostEqual(moved['purchase_debt_payoff'], 150000 - 6 * 500)
        self.assertAlmostEqual(moved['debt_balance'], 300000)
        self.assertEqual(moved['accounts'][1], 0)
        # Only the selling costs (and this month's spending and old mortgage payment) reduce net worth.
        self.assertAlmostEqual(moved['net_worth'], before['net_worth'] - 18000 - 1000)
        for row in result['monthly']:
            self.assertAlmostEqual(row['closing'], row['opening'] + row['gain'] - row['fees'] + row['income']
                                   - row['funded_expenses'] - row['debt_payment'] + row['purchase_asset_added']
                                   - row['purchase_sale_costs'], places=6)
        with self.assertRaisesRegex(ValueError, 'must reference one account'):
            plan['future_purchases'][0]['sell_account_id'] = 'missing'
            project(plan)

    def test_time_limited_upkeep_stops_and_only_its_retirement_part_joins_target(self):
        tuition = dict(id='school', name='School', amount=0, month=3, annual_upkeep=24000, upkeep_years=1)
        result = project(self.plan(future_purchases=[tuition]))
        baseline = project(self.plan())
        upkeep = [row['purchase_upkeep'] for row in result['monthly']]
        self.assertEqual(upkeep[:3], [0, 0, 0])
        self.assertEqual(upkeep[3:15], [2000] * 12)
        self.assertEqual(upkeep[15:], [0] * 9)
        # Retirement starts in month 13, so months 13-15 remain: a finite 6,000, not 24,000 / .04.
        self.assertEqual(result['annual_desired_spending'], baseline['annual_desired_spending'])
        self.assertAlmostEqual(result['retirement_obligations'], 6000)
        self.assertAlmostEqual(result['target'], baseline['target'] + 6000)

    def test_loan_rate_is_quoted_and_payments_shrink_with_inflation(self):
        home = dict(id='home', name='Home', amount=100000, month=1, loan_amount=100000,
                    loan_rate=.06, loan_inflation=.03, loan_months=24)
        result = project(self.plan(horizon=3, retirement_age=43, future_purchases=[home]))
        nominal = 100000 * .005 / (1 - 1.005 ** -24)
        deflator = 1.03 ** (1 / 12)
        payments = [row['debt_payment'] for row in result['monthly'][1:25]]
        for k, paid in enumerate(payments[:23], start=1):
            self.assertAlmostEqual(paid, nominal / deflator ** k, places=6)
        # The final payment clears the loan; in today's dollars it costs less than its quoted total.
        self.assertAlmostEqual(result['monthly'][24]['debt_balance'], 0, places=6)
        self.assertLess(sum(payments), nominal * 24)
        self.assertGreater(sum(payments), 100000)
        # Omitting loan_inflation keeps the earlier constant-payment behaviour.
        flat = project(self.plan(retirement_age=43, future_purchases=[dict(home, loan_inflation=0)]))
        self.assertAlmostEqual(flat['monthly'][5]['debt_payment'], nominal)

    def test_loan_payments_after_retirement_join_target_as_present_value(self):
        car = dict(id='car', name='Car', amount=24000, month=6, loan_amount=24000, loan_rate=0, loan_months=24)
        result = project(self.plan(horizon=4, future_purchases=[car]))
        baseline = project(self.plan(horizon=4))
        # Payments run months 7-30 at 1,000; months 13-30 fall after retirement starts.
        self.assertAlmostEqual(result['retirement_obligations'], 18000)
        self.assertAlmostEqual(result['target'] - baseline['target'], 18000)
        discounted = project(self.plan(horizon=4, return_rate=.05,
            accounts=[dict(type='investment', balance=200000, return_rate=0)], future_purchases=[car]))
        expected = sum(1000 / 1.05 ** ((m - 13) / 12) for m in range(13, 31))
        self.assertAlmostEqual(discounted['retirement_obligations'], expected)

    def test_debt_rate_is_quoted_and_payments_shrink_with_inflation(self):
        debt = dict(id='m', balance=12000, annual_rate=.06, months=12, inflation_rate=.03)
        result = project(self.plan(debts=[debt]))
        nominal = 12000 * .005 / (1 - 1.005 ** -12)
        deflator = 1.03 ** (1 / 12)
        for k, row in enumerate(result['monthly'][:11], start=1):
            self.assertAlmostEqual(row['debt_payment'], nominal / deflator ** k, places=6)
        self.assertAlmostEqual(result['monthly'][11]['debt_balance'], 0, places=6)
        # An entered payment is nominal too.
        fixed = project(self.plan(debts=[dict(debt, payment=500)]))
        self.assertAlmostEqual(fixed['monthly'][2]['debt_payment'], 500 / deflator ** 3)

    def test_plan_inflation_is_the_default_for_debts_and_loans(self):
        debt = dict(id='m', balance=12000, annual_rate=.06, months=12)
        loan = dict(id='car', name='Car', amount=10000, month=1, loan_amount=10000, loan_rate=.06, loan_months=12)
        planwide = project(self.plan(inflation_rate=.03, debts=[debt], future_purchases=[loan]))
        explicit = project(self.plan(debts=[dict(debt, inflation_rate=.03)],
                                     future_purchases=[dict(loan, loan_inflation=.03)]))
        self.assertEqual(planwide['annual'], explicit['annual'])
        # A row's own value wins over the plan's.
        override = project(self.plan(inflation_rate=.03, debts=[dict(debt, inflation_rate=0)]))
        self.assertAlmostEqual(override['monthly'][2]['debt_payment'], 12000 * .005 / (1 - 1.005 ** -12))
        with self.assertRaisesRegex(ValueError, 'inflation_rate'):
            project(self.plan(inflation_rate=2))

    def test_debt_payments_and_purchases_after_retirement_join_target(self):
        baseline = project(self.plan())
        # 24 months at 500 a month; retirement starts in month 13, so 12 payments remain.
        debt = project(self.plan(debts=[dict(id='m', balance=12000, annual_rate=0, months=24)]))
        self.assertAlmostEqual(debt['retirement_obligations'], 6000)
        self.assertAlmostEqual(debt['target'], baseline['target'] + 6000)
        car = project(self.plan(future_purchases=[dict(id='car', name='Car', amount=30000, month=18)]))
        self.assertAlmostEqual(car['target'], baseline['target'] + 30000)
        before = project(self.plan(future_purchases=[dict(id='car', name='Car', amount=30000, month=6)]))
        self.assertEqual(before['target'], baseline['target'])

    def test_downsizing_after_retirement_nets_sale_proceeds(self):
        plan = self.plan(accounts=[dict(id='invest', type='investment', balance=200000, return_rate=0),
                                   dict(id='house', type='property', balance=500000, return_rate=0)])
        baseline = project(plan)
        plan['future_purchases'] = [dict(id='condo', name='Condo', amount=300000, month=18, adds_asset=True,
                                         sell_account_id='house', sell_cost_rate=.06)]
        result = project(plan)
        # 470,000 of proceeds more than cover the 300,000 condo, so nothing is added.
        self.assertEqual(result['retirement_obligations'], 0)
        self.assertEqual(result['target'], baseline['target'])
        plan['future_purchases'][0]['amount'] = 520000
        self.assertAlmostEqual(project(plan)['retirement_obligations'], 50000)

    def test_disabled_purchase_with_stale_references_is_ignored(self):
        stale = dict(id='move', name='Move', amount=1, month=2, enabled=False,
                     sell_account_id='gone', payoff_debt_id='gone', sell_purchase_id='gone')
        self.assertEqual(project(self.plan(future_purchases=[stale]))['annual'], project(self.plan())['annual'])

    def test_an_asset_can_be_sold_only_once(self):
        plan = self.plan(accounts=[dict(id='invest', type='investment', balance=200000, return_rate=0),
                                   dict(id='house', type='property', balance=300000, return_rate=0)],
            future_purchases=[dict(id='a', name='A', amount=1, month=2, sell_account_id='house'),
                              dict(id='b', name='B', amount=1, month=3, sell_account_id='house')])
        with self.assertRaisesRegex(ValueError, 'only one future purchase'):
            project(plan)
        plan['future_purchases'][1]['enabled'] = False
        project(plan)
        homes = [dict(id='h', name='Home', amount=10, month=1, adds_asset=True),
                 dict(id='a', name='A', amount=1, month=2, sell_purchase_id='h'),
                 dict(id='b', name='B', amount=1, month=3, sell_purchase_id='h')]
        with self.assertRaisesRegex(ValueError, 'only one future purchase'):
            project(self.plan(future_purchases=homes))

    def test_later_purchase_sells_an_earlier_purchased_home_and_repays_its_loan(self):
        starter = dict(id='starter', name='Starter', amount=300000, month=2, loan_amount=200000, loan_rate=0,
                       loan_months=200, adds_asset=True, asset_return=0, annual_upkeep=1200)
        upsize = dict(id='upsize', name='Upsize', amount=500000, month=12, loan_amount=400000, loan_rate=0,
                      loan_months=400, adds_asset=True, sell_purchase_id='starter', sell_cost_rate=.05)
        result = project(self.plan(accounts=[dict(type='investment', balance=600000, return_rate=0)],
                                   future_purchases=[starter, upsize]))
        before, moved, after = result['monthly'][10], result['monthly'][11], result['monthly'][12]
        self.assertAlmostEqual(moved['purchase_sale_proceeds'], 285000)
        self.assertAlmostEqual(moved['purchase_sale_costs'], 15000)
        # Nine payments of 1,000 (months 3-11) and the regular month-12 payment precede the payoff.
        self.assertAlmostEqual(moved['purchase_debt_payoff'], 200000 - 10 * 1000)
        self.assertAlmostEqual(moved['purchase_asset_value'], 500000)
        self.assertAlmostEqual(moved['debt_balance'], 400000)
        self.assertAlmostEqual(moved['net_worth'], before['net_worth'] - 15000 - 1000)
        # The starter home's upkeep stops at the sale, so it never reaches the perpetual target.
        self.assertEqual([r['purchase_upkeep'] for r in result['monthly'][2:12]], [100] * 9 + [0])
        self.assertEqual(after['purchase_upkeep'], 0)
        self.assertEqual(result['annual_desired_spending'], 12000)
        for row in result['monthly']:
            self.assertAlmostEqual(row['closing'], row['opening'] + row['gain'] - row['fees'] + row['income']
                                   - row['funded_expenses'] - row['debt_payment'] + row['purchase_asset_added']
                                   - row['purchase_sale_costs'], places=6)
        with self.assertRaisesRegex(ValueError, 'only after the month'):
            project(self.plan(future_purchases=[dict(starter, month=12), dict(upsize, month=12)]))
        with self.assertRaisesRegex(ValueError, 'kept as an asset'):
            project(self.plan(future_purchases=[dict(starter, adds_asset=False), upsize]))

    def test_purchase_validation(self):
        with self.assertRaisesRegex(ValueError, 'cannot exceed'):
            project(self.plan(future_purchases=[dict(id='a', name='A', amount=1, month=1, loan_amount=2)]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            project(self.plan(future_purchases=[dict(id='a', name='A', amount=1, month=1)] * 2))
        with self.assertRaisesRegex(ValueError, 'month'):
            project(self.plan(future_purchases=[dict(id='a', name='A', amount=1, month=0)]))
        with self.assertRaisesRegex(ValueError, 'one existing asset'):
            project(self.plan(accounts=[dict(id='x', type='property', balance=1), dict(type='investment', balance=1)],
                future_purchases=[dict(id='h', name='H', amount=1, month=1, adds_asset=True),
                                  dict(id='a', name='A', amount=1, month=2, sell_account_id='x', sell_purchase_id='h')]))
        with self.assertRaisesRegex(ValueError, 'loan_inflation'):
            project(self.plan(future_purchases=[dict(id='a', name='A', amount=1, month=1, loan_inflation=2)]))


class ChildPlanningTests(unittest.TestCase):
    def base(self):
        return dict(age=40, income=60, expenses=40, assets=1000, return_rate=0,
                    withdrawal_rate=.04, horizon=3, valuation_date='2025-12-31',
                    members=[dict(id='kid-1', name='A', birth_date='2010-06-01')],
                    child_accounts=[])

    def test_child_forecasts_are_separate_and_use_year_end_real_ledger(self):
        plan = self.base()
        plan['child_accounts'] = [
            dict(id='college', name='Education', type='529', beneficiary_id='kid-1',
                 balance=100, return_rate=.1, fee_rate=.01, annual_contribution=100,
                 start_year=2026, end_year=2026, education_annual_withdrawal=200,
                 education_start_age=16, education_years=2),
            dict(id='future', name='Trump', type='trump', beneficiary_id='kid-1',
                 balance=1000, return_rate=0, annual_contribution=1000,
                 employer_contribution=500, employer_contributor_id='adult-a',
                 start_year=2026, end_year=2027, pilot_contribution=1000, pilot_year=2026),
        ]
        plan['assets'] = 10000
        result = project(plan)
        children = result['children']
        accounts = {row['id']: row for row in children['child_accounts']}
        college_2026, trump_2026 = accounts['college']['annual'][0], accounts['future']['annual'][0]
        self.assertEqual(college_2026['age'], 16)
        self.assertAlmostEqual(college_2026['return_amount'], 10)
        self.assertAlmostEqual(college_2026['education_withdrawal'], 200)
        self.assertAlmostEqual(college_2026['closing'], 8.9)
        self.assertEqual(trump_2026['contribution'], 2500)
        self.assertEqual(accounts['future']['annual'][2]['contribution'], 0)
        # Child balances stay outside the parent's assets and target; only
        # household-funded contributions reduce the parent's balance.
        parent_only = dict(plan)
        parent_only.pop('members')
        parent_only.pop('child_accounts')
        baseline = project(parent_only)
        # Retirement starts immediately here, so household-funded contributions are a finite
        # retirement obligation added to the target; the child balances themselves are not.
        self.assertAlmostEqual(result['retirement_obligations'], 2100)
        self.assertAlmostEqual(result['target'], baseline['target'] + 2100)
        self.assertAlmostEqual(baseline['annual'][-1]['balance'] - result['annual'][-1]['balance'], 2100)
        self.assertAlmostEqual(sum(row['child_contributions'] for row in result['annual']), 2100)
        for account in plan['child_accounts']:
            account['contribution_source'] = 'external'
        external = project(plan)
        baseline_by_year = {row['year']: row['balance'] for row in baseline['annual']}
        for row in external['annual']:
            self.assertAlmostEqual(row['balance'], baseline_by_year[row['year']])
        self.assertEqual(external['target'], baseline['target'])

    def test_child_year_end_falls_in_december_after_a_mid_year_valuation(self):
        plan = self.base()
        plan.update(valuation_date='2026-09-30', assets=10000)
        plan['child_accounts'] = [dict(id='c', name='529', type='529', beneficiary_id='kid-1', balance=1000,
                                      return_rate=.1, annual_contribution=100, start_year=2026, end_year=2027)]
        result = project(plan)
        months = [row['month'] for row in result['monthly'] if row['child_contributions']]
        # Month 1 is October, so December 2026 is month 3 and December 2027 is month 15.
        self.assertEqual(months, [3, 15])
        first = result['children']['child_accounts'][0]['annual'][0]
        self.assertEqual(first['year'], 2026)
        self.assertAlmostEqual(first['return_amount'], 1000 * (1.1 ** (3 / 12) - 1))
        # A December valuation has no months left in its year, so the first year-end is the next one.
        plan['valuation_date'] = '2025-12-31'
        years = [row['year'] for row in project(plan)['children']['child_accounts'][0]['annual']]
        self.assertEqual(years[0], 2026)

    def test_unaffordable_household_contribution_is_reported_unfunded(self):
        plan = self.base()
        plan['assets'] = 500
        plan['child_accounts'] = [dict(id='t1', name='Trump', type='trump', beneficiary_id='kid-1',
                                      annual_contribution=1000, start_year=2026, end_year=2026)]
        result = project(plan)
        first = result['children']['child_accounts'][0]['annual'][0]
        self.assertAlmostEqual(first['contribution'], 520)
        self.assertAlmostEqual(first['unfunded_contribution'], 480)
        self.assertAlmostEqual(result['annual'][0]['child_unfunded'], 480)
        self.assertEqual(result['first_shortfall_month'], 12)

    def test_trump_aggregate_caps_and_beneficiary_validation(self):
        plan = self.base()
        plan['members'].append(dict(id='kid-2', name='B', birth_date='2012-02-29'))
        plan['child_accounts'] = [dict(id='t1', name='One', type='trump', beneficiary_id='kid-1',
                 annual_contribution=5001, start_year=2026, end_year=2026)]
        with self.assertRaisesRegex(ValueError, 'aggregate annual cap'):
            project(plan)

    def test_only_one_trump_account_per_child(self):
        plan = self.base()
        plan['child_accounts'] = [
            dict(id='t1', name='One', type='trump', beneficiary_id='kid-1'),
            dict(id='t2', name='Two', type='trump', beneficiary_id='kid-1'),
        ]
        with self.assertRaisesRegex(ValueError, 'only one Trump Account'):
            project(plan)
        plan['child_accounts'][1]['beneficiary_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'must reference a member'):
            project(plan)

    def test_trump_contributions_stop_when_growth_period_ends(self):
        plan = self.base()
        plan['members'][0]['birth_date'] = '2009-06-01'  # Growth period ends Dec. 31, 2026.
        plan['child_accounts'] = [dict(id='t1', name='Trump', type='trump', beneficiary_id='kid-1',
                                      annual_contribution=1000, start_year=2026, end_year=2026)]
        self.assertEqual(project(plan)['children']['child_accounts'][0]['growth_period_end_year'], 2026)
        plan['child_accounts'][0]['end_year'] = 2027
        with self.assertRaisesRegex(ValueError, 'cannot continue after'):
            project(plan)

    def test_trump_contributions_default_through_age_seventeen(self):
        plan = self.base()
        plan['assets'] = 100000
        plan['horizon'] = 12
        plan['members'][0]['birth_date'] = '2019-04-10'
        plan['child_accounts'] = [dict(id='t1', name='Trump', type='trump', beneficiary_id='kid-1',
                                      annual_contribution=2000)]
        account = project(plan)['children']['child_accounts'][0]
        self.assertEqual((account['start_year'], account['end_year']), (2026, 2036))
        contributions = {row['year']: row['contribution'] for row in account['annual']}
        self.assertEqual(contributions[2036], 2000)
        self.assertEqual(contributions[2037], 0)
        self.assertEqual(sum(contributions.values()), 2000 * 11)
        # Later-year caps are the same real amount.
        plan['child_accounts'][0].update(annual_contribution=5001, start_year=2030, end_year=2030)
        with self.assertRaisesRegex(ValueError, 'aggregate annual cap'):
            project(plan)

    def test_trump_pilot_cannot_precede_account_start(self):
        plan = self.base()
        plan['child_accounts'] = [dict(id='t1', name='Trump', type='trump', beneficiary_id='kid-1',
                                      pilot_contribution=1000, pilot_year=2026, start_year=2027, end_year=2027)]
        with self.assertRaisesRegex(ValueError, 'cannot be before'):
            project(plan)

    def test_employer_cap_and_ssn_rejection(self):
        plan = self.base()
        plan['members'].append(dict(id='kid-2', name='B', birth_date='2012-02-29'))
        plan['child_accounts'] = [
            dict(id='t1', name='One', type='trump', beneficiary_id='kid-1',
                 employer_contribution=1500, employer_contributor_id='adult-a', start_year=2026, end_year=2026),
            dict(id='t2', name='Two', type='trump', beneficiary_id='kid-2',
                 employer_contribution=1001, employer_contributor_id='adult-a', start_year=2026, end_year=2026),
        ]
        with self.assertRaisesRegex(ValueError, 'per-employee annual cap'):
            project(plan)
        plan['members'][0]['ssn'] = '123-45-6789'
        with self.assertRaisesRegex(ValueError, 'Social Security numbers'):
            project(plan)

    def test_pilot_receipt_is_single_and_excluded_from_general_cap(self):
        plan = self.base()
        plan['assets'] = 10000
        plan['child_accounts'] = [dict(id='t1', name='One', type='trump', beneficiary_id='kid-1',
                 annual_contribution=5000, pilot_contribution=1000, pilot_year=2026,
                 start_year=2026, end_year=2026)]
        result = project(plan)
        account = result['children']['child_accounts'][0]
        self.assertEqual(account['annual'][0]['contribution'], 6000)


if __name__ == '__main__':
    unittest.main()
