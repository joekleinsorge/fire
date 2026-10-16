import unittest
import test_api
from fireplanner.intake import apply, second_home
from fireplanner.engine import project


class IntakeTests(unittest.TestCase):
    def plan(self):
        return dict(
            age=34,
            retirement_age=48,
            horizon=30,
            valuation_date="2026-10-15",
            return_rate=0,
            accounts=[
                dict(
                    id="cash",
                    name="Cash",
                    type="cash",
                    balance=1000,
                    return_rate=0,
                    available=True,
                ),
                dict(
                    id="529",
                    name="529 pool",
                    type="other",
                    source_details={"type": "education_restricted"},
                    balance=100,
                    return_rate=0,
                    available=False,
                    household_contribution_monthly=20,
                    contribution_end_month=37,
                ),
            ],
            members=[
                dict(id="a", name="A", birth_date="2022-01-01"),
                dict(id="b", name="B", birth_date="2024-01-01"),
            ],
            child_accounts=[],
            streams=[],
            debts=[],
            metadata={"keep": None},
        )

    def payload(self, section, values):
        return dict(
            section=section,
            values=values,
            source="Synthetic statement",
            as_of="2026-10-01",
            confirmed=True,
        )

    def test_allocation_conserves_pool_and_rejects_duplicates(self):
        p = self.plan()
        values = dict(
            pool_account_id="529",
            adult_owner="Parent",
            allocations=[
                dict(
                    beneficiary_id="a",
                    balance=60,
                    monthly_contribution=10,
                    education_annual_withdrawal=1000,
                    education_years=4,
                ),
                dict(
                    beneficiary_id="b",
                    balance=40,
                    monthly_contribution=10,
                    education_annual_withdrawal=1000,
                    education_years=4,
                ),
            ],
        )
        q = apply(p, self.payload("education", values))
        self.assertEqual(q["accounts"][1]["balance"], 0)
        self.assertEqual(q["accounts"][1]["household_contribution_monthly"], 0)
        self.assertEqual(sum(a["balance"] for a in q["child_accounts"]), 100)
        self.assertIsNone(q["metadata"]["keep"])
        self.assertEqual(p["accounts"][1]["balance"], 100)
        values["allocations"][0]["balance"] = 70
        with self.assertRaises(ValueError):
            apply(p, self.payload("education", values))

    def test_source_date_and_unknown_are_preserved(self):
        p = self.plan()
        q = apply(p, self.payload("balance", dict(account_id="cash", balance=0)))
        self.assertEqual(q["accounts"][0]["balance"], 0)
        self.assertTrue(
            q["accounts"][0]["source_details"]["latest_reported_snapshot"]["confirmed"]
        )
        self.assertIsNone(q["metadata"]["keep"])
        x = self.payload("balance", dict(account_id="cash", balance=200))
        x["confirmed"] = False
        with self.assertRaises(ValueError):
            apply(p, x)

    def test_second_home_requires_full_inputs_and_cannot_create_free_rent(self):
        d = dict(
            price=200000,
            purchase_month="2027-01",
            price_basis="plan_start_real",
            down_payment_pct=20,
            mortgage_rate_pct=7,
            loan_years=30,
            closing_costs=6000,
            seller_credit=0,
            moving_costs=1000,
            property_tax_annual=3000,
            insurance_annual=5000,
            hoa_annual=0,
            maintenance_annual=2000,
            liquid_reserve=55000,
            net_rental_income_monthly=1000,
        )
        q = second_home(self.plan(), d)
        r = project(q)
        self.assertEqual(r["summary"]["blocked_purchases"], 1)
        self.assertEqual(sum(a["income"] for a in r["annual"]), 0)
        d.pop("insurance_annual")
        with self.assertRaises(ValueError):
            second_home(self.plan(), d)


class IntakeAPITests(unittest.TestCase):
    setUp = test_api.APITest.setUp
    tearDown = test_api.APITest.tearDown
    request = test_api.APITest.request
    register = test_api.APITest.register

    def test_versioned_update_logs_run_and_preserves_nulls(self):
        user, cookie = self.register("intake@example.test")
        p = IntakeTests().plan()
        status, saved, _ = self.request(
            "POST", "/api/plans", dict(name="Intake", plan=p), cookie
        )
        route = "/api/plans/" + saved["id"]
        payload = IntakeTests().payload(
            "balance", dict(account_id="cash", balance=2000)
        )
        payload["version"] = 1
        status, result, _ = self.request(
            "POST", route + "/complete-inputs", payload, cookie
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["plan"]["version"], 2)
        self.assertIsNone(result["plan"]["plan"]["metadata"]["keep"])
        self.assertEqual(result["job"]["status"], "queued")
        self.assertEqual(
            self.request("POST", route + "/complete-inputs", payload, cookie)[0], 409
        )
        _, other = self.register("other-intake@example.test")
        payload["version"] = 2
        self.assertEqual(
            self.request("POST", route + "/complete-inputs", payload, other)[0], 404
        )

    def test_second_home_saves_an_independent_scenario_and_run(self):
        user, cookie = self.register("home-intake@example.test")
        status, saved, _ = self.request(
            "POST", "/api/plans", dict(name="Home", plan=IntakeTests().plan()), cookie
        )
        d = dict(
            price=200000,
            purchase_month="2027-01",
            price_basis="plan_start_real",
            down_payment_pct=20,
            mortgage_rate_pct=7,
            loan_years=30,
            closing_costs=6000,
            seller_credit=0,
            moving_costs=1000,
            property_tax_annual=3000,
            insurance_annual=5000,
            hoa_annual=0,
            maintenance_annual=2000,
            liquid_reserve=55000,
            net_rental_income_monthly=0,
        )
        payload = IntakeTests().payload("second_home", d)
        payload["version"] = 1
        route = "/api/plans/" + saved["id"]
        status, result, _ = self.request(
            "POST", route + "/complete-inputs", payload, cookie
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["plan"]["plan"].get("future_purchases", []), [])
        rows = self.request("GET", route + "/scenarios", cookie=cookie)[1]["scenarios"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["data"]["plan"]["future_purchases"][0]["amount"], 200000
        )
        self.assertEqual(result["job"]["status"], "queued")
