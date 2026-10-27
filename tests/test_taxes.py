import unittest
from fireplanner.taxes import federal
from fireplanner.engine import project
from fireplanner.healthcare import estimate


class TaxTests(unittest.TestCase):
    def test_brackets_gains_stacking_and_niit(self):
        self.assertEqual(federal(ordinary=50000)["total_tax"], 1780)
        self.assertEqual(federal(ordinary=100000)["total_tax"], 7640)
        self.assertEqual(federal(gains=50000)["total_tax"], 0)
        self.assertEqual(federal(ordinary=100000, gains=100000)["total_tax"], 17975)
        self.assertEqual(federal(ordinary=200000, gains=100000)["total_tax"], 43240)
        self.assertEqual(
            federal(ordinary=10000, social_security=40000)["taxable_social_security"], 0
        )
        self.assertEqual(
            federal(ordinary=50000, social_security=40000)["taxable_social_security"],
            28100,
        )
        self.assertEqual(federal(ordinary=50000, children=3)["total_tax"], 0)

    def plan(self, **extra):
        return dict(
            dict(
                age=60,
                retirement_age=60,
                horizon=1,
                valuation_date="2025-12-31",
                return_rate=0,
                inflation_rate=0,
                accounts=[],
                streams=[],
                debts=[],
                tax_model={
                    "enabled": True,
                    "jurisdiction": "US-MFJ-FL-2026",
                    "income_context": [],
                },
            ),
            **extra,
        )

    def test_progressive_gross_up_and_accounting(self):
        p = self.plan(
            accounts=[
                dict(
                    id="ira",
                    type="retirement",
                    balance=300000,
                    return_rate=0,
                    available=True,
                    tax_treatment="pretax",
                )
            ],
            streams=[dict(kind="expense", amount=8000)],
        )
        r = project(p)
        gross = 300000 - r["summary"]["ending_assets"]
        self.assertAlmostEqual(
            gross - federal(ordinary=gross)["total_tax"], 96000, places=4
        )
        self.assertAlmostEqual(
            r["summary"]["withdrawal_taxes"],
            federal(ordinary=gross)["total_tax"],
            places=4,
        )
        for row in r["monthly"]:
            self.assertAlmostEqual(
                row["opening"] - row["funded_expenses"] - row["withdrawal_taxes"],
                row["closing"],
                places=4,
            )

    def test_tax_efficient_order_defers_pretax_draws(self):
        accounts = [
            dict(id="ira", type="retirement", balance=200000, return_rate=0, available=True, tax_treatment="pretax"),
            dict(id="cash", type="cash", balance=30000, return_rate=0, available=True, tax_treatment="cash"),
        ]
        spend = [dict(kind="expense", amount=4000)]
        listed = project(self.plan(accounts=accounts, streams=spend))
        efficient = project(self.plan(accounts=accounts, streams=spend, withdrawal_order="tax_efficient"))
        # Cash covers the first seven months untaxed before the pre-tax account is drawn.
        self.assertEqual(efficient["monthly"][6]["accounts"][0], 200000)
        self.assertEqual(efficient["monthly"][6]["withdrawal_taxes"], 0)
        self.assertLess(efficient["summary"]["withdrawal_taxes"], listed["summary"]["withdrawal_taxes"])

    def test_claimed_social_security_is_taxed_as_benefit_income(self):
        accounts = [dict(id="ira", type="retirement", balance=500000, return_rate=0, available=True, tax_treatment="pretax")]
        benefit = dict(id="ss", name="Me", birth_year=1960, pia_at_fra=3000, claim_age_years=62)
        spend = [dict(kind="expense", amount=6000)]
        with_ss = project(self.plan(age=62, retirement_age=62, accounts=accounts, streams=spend, social_security=[benefit]))
        self.assertEqual(with_ss["social_security"][0]["start_month"], 1)
        manual = project(self.plan(age=62, retirement_age=62, accounts=accounts, streams=spend + [dict(
            id="manual", kind="income", amount=with_ss["social_security"][0]["monthly_benefit"],
            tax_kind="social_security")]))
        # The benefit is gross income in the tax model, taxed exactly like main's manual
        # Social Security stream, so the year's withdrawals and tax match.
        self.assertAlmostEqual(with_ss["summary"]["withdrawal_taxes"], manual["summary"]["withdrawal_taxes"], places=6)
        self.assertAlmostEqual(with_ss["summary"]["ending_assets"], manual["summary"]["ending_assets"], places=6)
        self.assertGreater(with_ss["tax_analysis"]["annual"][0]["taxable_social_security"], 0)

    def test_spousal_and_survivor_benefits_are_taxed_as_social_security(self):
        accounts = [dict(id="ira", type="retirement", balance=900000, return_rate=0, available=True, tax_treatment="pretax")]
        benefits = [dict(id="me", birth_year=1960, pia_at_fra=3000, claim_age_years=67, owner="self"),
                    dict(id="you", birth_year=1960, pia_at_fra=1000, claim_age_years=67, owner="partner")]
        plan = self.plan(age=67, retirement_age=67, horizon=2, partner=dict(age=67, life_expectancy=68),
                         accounts=accounts, streams=[dict(kind="expense", amount=7000)], social_security=benefits)
        result = project(plan)
        months = result["monthly"]
        # Both alive: 3000 + 1000 + 500 spousal excess; after the partner dies, the survivor keeps 3000.
        self.assertAlmostEqual(months[0]["income"] + months[0]["income_taxes"], 4500, places=6)
        self.assertAlmostEqual(months[13]["income"] + months[13]["income_taxes"], 3000, places=6)
        self.assertTrue(any("survivor filing status" in w for w in result["warnings"]))
        self.assertGreater(result["tax_analysis"]["annual"][0]["taxable_social_security"], 0)

    def fill_plan(self, rule, **extra):
        accounts = [
            dict(id="cash", type="cash", balance=200000, return_rate=0, available=True, tax_treatment="cash"),
            dict(id="ira", type="retirement", balance=500000, return_rate=0, available=True, tax_treatment="pretax"),
            dict(id="roth", type="retirement", balance=0, return_rate=0, available=True, tax_treatment="roth_qualified"),
        ]
        return self.plan(horizon=3, accounts=accounts, streams=[dict(kind="expense", amount=1000)],
                         tax_model=dict(self.plan()["tax_model"], roth_conversion_fill=rule), **extra)

    def test_roth_conversion_fills_the_chosen_bracket_each_december(self):
        rule = dict(source_account_id="ira", target_account_id="roth", fill_to=0.12, start_age=60, end_age=61)
        result = project(self.fill_plan(rule))
        events = result["summary"]["conversion_events"]
        # Valuation 2025-12-31: Decembers 2026-2028 fall at ages 61-63, so only 2026 is in the window.
        self.assertEqual([e["month"] for e in events], [12])
        # Cash pays the spending, so the conversion alone fills ordinary income to the
        # top of the 12% bracket plus the standard deduction.
        self.assertAlmostEqual(events[0]["amount"], 100800 + 32200, places=4)
        self.assertTrue(events[0]["executed"])
        year = result["tax_analysis"]["annual"][0]
        self.assertAlmostEqual(year["ordinary_taxable"], 100800, places=4)
        self.assertAlmostEqual(result["monthly"][11]["accounts"][2], 133000, places=4)
        self.assertAlmostEqual(result["summary"]["conversion_tax"], federal(ordinary=133000)["total_tax"], places=4)

    def test_roth_conversion_fill_skips_rmd_years_and_validates(self):
        rule = dict(source_account_id="ira", target_account_id="roth", fill_to=0.22, start_age=60, end_age=70)
        plan = self.fill_plan(rule)
        plan["accounts"][1].update(rmd_start_age=73, owner_birth_year=1953, prior_year_end_nominal_balance=500000)
        # Born 1953 with RMDs from 73: every year from 2026 is an RMD year, so nothing converts.
        self.assertEqual(project(plan)["summary"]["conversion_events"], [])
        with self.assertRaisesRegex(ValueError, "fill_to"):
            project(self.fill_plan(dict(rule, fill_to=0.37)))
        with self.assertRaisesRegex(ValueError, "pretax source"):
            project(self.fill_plan(dict(rule, source_account_id="cash")))

    def test_basis_deposits_and_tax_year_reset(self):
        p = self.plan(
            valuation_date="2026-10-15",
            accounts=[
                dict(
                    id="broker",
                    type="investment",
                    balance=100000,
                    return_rate=0,
                    available=True,
                    tax_treatment="taxable",
                    cost_basis=80000,
                    gain_method="proportional_long_term",
                )
            ],
            streams=[dict(kind="expense", amount=1000)],
        )
        r = project(p)
        self.assertEqual(r["summary"]["withdrawal_taxes"], 0)
        self.assertEqual([x["year"] for x in r["tax_analysis"]["annual"]], [2026, 2027])

    def test_rmd_is_internal_transfer_net_of_tax(self):
        p = self.plan(
            valuation_date="2025-12-31",
            accounts=[
                dict(
                    id="cash",
                    type="cash",
                    balance=0,
                    return_rate=0,
                    available=True,
                    tax_treatment="cash",
                ),
                dict(
                    id="ira",
                    type="retirement",
                    balance=984000,
                    return_rate=0,
                    available=True,
                    tax_treatment="pretax",
                    rmd_start_age=73,
                    owner_birth_year=1951,
                    prior_year_end_nominal_balance=984000,
                ),
            ],
            surplus_account_id="cash",
        )
        r = project(p)
        self.assertAlmostEqual(r["summary"]["rmd_gross"], 40000)
        self.assertAlmostEqual(r["summary"]["withdrawal_taxes"], 780)
        self.assertAlmostEqual(r["summary"]["ending_assets"], 983220)
        self.assertAlmostEqual(r["annual"][0]["accounts"][0], 39220)

    def test_gross_social_security_is_taxed_once(self):
        p = self.plan(
            valuation_date="2025-12-31",
            accounts=[
                dict(
                    type="cash",
                    balance=0,
                    return_rate=0,
                    available=True,
                    tax_treatment="cash",
                )
            ],
            streams=[
                dict(kind="income", amount=5000, tax_kind="ordinary"),
                dict(kind="income", amount=4000, tax_kind="social_security"),
            ],
        )
        r = project(p)
        expected = federal(ordinary=60000, social_security=48000)["total_tax"]
        self.assertAlmostEqual(r["annual"][0]["income_taxes"], expected)
        self.assertAlmostEqual(r["summary"]["ending_assets"], 108000 - expected)

    def test_dividend_taxes_and_basis_reconcile(self):
        p = self.plan(
            accounts=[
                dict(
                    id="b",
                    type="investment",
                    balance=1000000,
                    return_rate=0,
                    available=True,
                    tax_treatment="taxable",
                    cost_basis=1000000,
                    gain_method="proportional_long_term",
                    qualified_dividend_yield=0.02,
                )
            ],
            tax_model={
                "enabled": True,
                "jurisdiction": "US-MFJ-FL-2026",
                "income_context": [
                    dict(
                        kind="ordinary", amount=300000 / 12, start_month=1, end_month=13
                    )
                ],
            },
        )
        r = project(p)
        self.assertGreater(r["summary"]["withdrawal_taxes"], 3000)
        for row in r["monthly"]:
            self.assertAlmostEqual(
                row["opening"] - row["withdrawal_taxes"], row["closing"], places=5
            )

    def test_marketplace_requires_eligibility_and_cliff(self):
        d = dict(
            year=2026,
            family_size=5,
            magi=75300,
            benchmark_premium_annual=24000,
            selected_premium_annual=22000,
            out_of_pocket_budget_annual=5000,
        )
        self.assertIsNone(estimate(d)["premium_tax_credit"])
        d["eligibility_confirmed"] = True
        r = estimate(d)
        self.assertAlmostEqual(r["expected_household_contribution"], 75300 * 0.066)
        self.assertAlmostEqual(r["premium_tax_credit"], 24000 - 75300 * 0.066)
        d["magi"] = 150601
        self.assertEqual(estimate(d)["premium_tax_credit"], 0)

    def test_purchase_funding_uses_combined_progressive_tax(self):
        p = self.plan(
            accounts=[
                dict(
                    id="a",
                    type="retirement",
                    balance=50000,
                    return_rate=0,
                    available=True,
                    tax_treatment="pretax",
                ),
                dict(
                    id="b",
                    type="retirement",
                    balance=50000,
                    return_rate=0,
                    available=True,
                    tax_treatment="pretax",
                ),
            ],
            future_purchases=[
                dict(
                    id="buy",
                    name="Buy",
                    amount=95000,
                    month=1,
                    require_full_funding=True,
                )
            ],
        )
        r = project(p)
        self.assertEqual(r["summary"]["blocked_purchases"], 1)

    def test_blocked_rental_never_produces_income(self):
        p = self.plan(
            accounts=[
                dict(type="cash", balance=0, return_rate=0, tax_treatment="cash")
            ],
            future_purchases=[
                dict(
                    id="buy",
                    name="Home",
                    amount=100000,
                    month=1,
                    require_full_funding=True,
                )
            ],
            streams=[
                dict(
                    kind="income",
                    amount=1000,
                    start_month=2,
                    requires_purchase_id="buy",
                )
            ],
        )
        self.assertEqual(project(p)["annual"][0]["income"], 0)

    def test_conversion_is_internal_and_tax_paid_once(self):
        p = self.plan(
            accounts=[
                dict(
                    id="cash",
                    type="cash",
                    balance=10000,
                    return_rate=0,
                    available=True,
                    tax_treatment="cash",
                ),
                dict(
                    id="ira",
                    type="retirement",
                    balance=100000,
                    return_rate=0,
                    available=False,
                    available_from_age=59.5,
                    tax_treatment="pretax",
                ),
                dict(
                    id="roth",
                    type="retirement",
                    balance=0,
                    return_rate=0,
                    available=False,
                    available_from_age=59.5,
                    tax_treatment="roth_qualified",
                ),
            ],
            tax_model={
                "enabled": True,
                "jurisdiction": "US-MFJ-FL-2026",
                "conversions": [
                    dict(
                        month=1,
                        amount=40000,
                        source_account_id="ira",
                        target_account_id="roth",
                    )
                ],
            },
        )
        r = project(p)
        self.assertAlmostEqual(r["summary"]["conversion_tax"], 780)
        self.assertAlmostEqual(r["summary"]["ending_assets"], 109220)
        self.assertAlmostEqual(r["annual"][0]["accounts"][2], 40000)
        p["accounts"][0]["balance"] = 0
        p["age"] = 48
        p["retirement_age"] = 48
        r = project(p)
        self.assertEqual(r["summary"]["blocked_conversions"], 1)
        self.assertEqual(r["summary"]["conversion_gross"], 0)
        self.assertEqual(r["summary"]["ending_assets"], 100000)

    def test_explicit_gross_wages_recalculate_without_double_tax(self):
        config = {
            "enabled": True,
            "jurisdiction": "US-MFJ-FL-2026",
            "recalculate_wages": True,
            "child_credit_end_years": [2038, 2040, 2042],
            "income_context": [
                dict(
                    kind="ordinary",
                    role="base_wages",
                    stream_id="salary",
                    gross_amount=275000 / 12,
                    amount=253000 / 12,
                    start_month=1,
                    end_month=13,
                ),
                dict(
                    kind="ordinary",
                    role="bonus_wages",
                    stream_id="bonus",
                    gross_amount=55000 / 4,
                    amount=55000 / 4,
                    start_month=3,
                    end_month=13,
                    every_months=3,
                ),
            ],
        }
        p = self.plan(
            tax_model=config,
            accounts=[
                dict(type="cash", balance=0, return_rate=0, tax_treatment="cash")
            ],
            streams=[
                dict(id="salary", kind="income", amount=1),
                dict(
                    id="bonus", kind="income", amount=1, start_month=3, every_months=3
                ),
            ],
        )
        r = project(p)
        self.assertAlmostEqual(r["annual"][0]["income"], 246268, places=4)
        self.assertAlmostEqual(r["summary"]["ending_assets"], 246268, places=4)

    def test_pilot_requires_valid_birth_year_and_confirmation(self):
        p = self.plan(
            members=[dict(id="kid", name="Kid", birth_date="2024-01-01")],
            child_accounts=[
                dict(
                    id="trump",
                    name="Trump",
                    type="trump",
                    beneficiary_id="kid",
                    start_year=2026,
                    end_year=2027,
                    pilot_contribution=1000,
                    pilot_year=2026,
                    pilot_eligibility_confirmed=True,
                )
            ],
        )
        with self.assertRaisesRegex(ValueError, "born2025"):
            project(p)
        p["members"][0]["birth_date"] = "2025-01-01"
        p["child_accounts"][0]["pilot_eligibility_confirmed"] = False
        with self.assertRaisesRegex(ValueError, "Confirm all pilot"):
            project(p)

    def test_itemized_refund_follows_funded_closing_only(self):
        config = {
            "enabled": True,
            "jurisdiction": "US-MFJ-FL-2026",
            "income_context": [
                dict(kind="ordinary", amount=300000 / 12, start_month=1, end_month=25)
            ],
        }
        p = self.plan(
            horizon=2,
            tax_model=config,
            accounts=[
                dict(
                    id="cash",
                    type="cash",
                    balance=1000000,
                    return_rate=0,
                    tax_treatment="cash",
                )
            ],
            streams=[dict(kind="income", amount=15000)],
            future_purchases=[
                dict(
                    id="house",
                    name="House",
                    amount=800000,
                    loan_amount=700000,
                    loan_rate=0.06,
                    loan_months=360,
                    month=1,
                    require_full_funding=True,
                    annual_upkeep=12000,
                    property_tax_annual=12000,
                    qualified_home_mortgage=True,
                )
            ],
        )
        r = project(p)
        self.assertGreater(r["tax_analysis"]["annual"][0]["refund_due"], 0)
        self.assertEqual(r["monthly"][0]["tax_refund_income"], 0)
        self.assertGreater(r["monthly"][12]["tax_refund_income"], 0)
        p["accounts"][0]["balance"] = 0
        r = project(p)
        self.assertEqual(r["summary"]["blocked_purchases"], 1)
        self.assertEqual(r["summary"]["tax_refund_income"], 0)
