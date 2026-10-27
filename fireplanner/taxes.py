"""Reviewed 2026 MFJ/Florida planning rules, not a tax-return preparation engine.

Indexed thresholds remain in plan-start dollars. Non-indexed SS/NIIT/credit
phaseout thresholds decline with entered inflation. Other jurisdictions fail
closed. Account basis and income contexts must be entered explicitly.
"""

import math
from datetime import date

VERSION = "us-mfj-fl-2026-v1"
SOURCES = [
    "https://www.irs.gov/irb/2025-45_IRB",
    "https://www.irs.gov/publications/p915",
    "https://www.irs.gov/taxtopics/tc559",
    "https://www.irs.gov/publications/p590b",
    "https://www.irs.gov/irb/2024-33_IRB",
    "https://www.irs.gov/irb/2025-32_IRB",
    "https://www.irs.gov/publications/p936",
    "https://www.irs.gov/forms-pubs/correction-to-state-and-local-income-tax-deduction-amount-in-the-2026-form-1040-es",
]
LIMITS = [
    (24800, 0.10),
    (100800, 0.12),
    (211400, 0.22),
    (403550, 0.24),
    (512450, 0.32),
    (768700, 0.35),
    (math.inf, 0.37),
]
RMD_FACTORS = dict(
    zip(
        range(72, 121),
        [
            27.4,
            26.5,
            25.5,
            24.6,
            23.7,
            22.9,
            22.0,
            21.1,
            20.2,
            19.4,
            18.5,
            17.7,
            16.8,
            16.0,
            15.2,
            14.4,
            13.7,
            12.9,
            12.2,
            11.5,
            10.8,
            10.1,
            9.5,
            8.9,
            8.4,
            7.8,
            7.3,
            6.8,
            6.4,
            6.0,
            5.6,
            5.2,
            4.9,
            4.6,
            4.3,
            4.1,
            3.9,
            3.7,
            3.5,
            3.4,
            3.3,
            3.1,
            3.0,
            2.9,
            2.8,
            2.7,
            2.5,
            2.3,
            2.0,
        ],
    )
)


def value(v, name, low=0, high=1e15):
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not low <= v <= high
    ):
        raise ValueError(f"{name} must be a finite number between {low} and {high}")
    return v


def federal(
    ordinary=0,
    gains=0,
    social_security=0,
    exempt_interest=0,
    children=0,
    fixed_threshold_factor=1,
    deduction=32200,
    investment_ordinary=0,
):
    """Ordinary/LTCG stacking, taxable Social Security, CTC and NIIT in real dollars.

    No loss carryovers, AMT, QBI, itemization, surtaxes on special gains, refundable
    credits, payroll taxes, or state tax outside Florida. SS is the ordinary
    worksheet case; special exclusions and lump-sum benefit elections excluded.
    """
    for name, v in [
        ("ordinary", ordinary),
        ("gains", gains),
        ("social_security", social_security),
        ("exempt_interest", exempt_interest),
        ("deduction", deduction),
    ]:
        value(v, name)
    value(investment_ordinary, "investment ordinary income", 0, ordinary)
    value(children, "children", 0, 20)
    if int(children) != children:
        raise ValueError("children must be an integer")
    value(fixed_threshold_factor, "fixed threshold factor", 0, 100)
    lower, upper = 32000 * fixed_threshold_factor, 44000 * fixed_threshold_factor
    combined = ordinary + gains + exempt_interest + social_security / 2
    if combined <= lower:
        taxable_ss = 0
    elif combined <= upper:
        taxable_ss = min(social_security * 0.5, (combined - lower) * 0.5)
    else:
        taxable_ss = min(
            social_security * 0.85,
            (combined - upper) * 0.85
            + min(social_security * 0.5, (upper - lower) * 0.5),
        )
    agi = ordinary + gains + taxable_ss
    ordinary_taxable = max(0, ordinary + taxable_ss - deduction)
    taxable_gains = max(0, gains - max(0, deduction - ordinary - taxable_ss))
    tax = 0
    last = 0
    for top, rate in LIMITS:
        tax += max(0, min(ordinary_taxable, top) - last) * rate
        last = top
    zero = min(taxable_gains, max(0, 98900 - ordinary_taxable))
    middle = min(taxable_gains - zero, max(0, 613700 - max(ordinary_taxable, 98900)))
    gains_tax = middle * 0.15 + max(0, taxable_gains - zero - middle) * 0.20
    phaseout = max(0, agi - 400000 * fixed_threshold_factor)
    # $50 per started $1,000, both statutory non-indexed amounts.
    credit = max(
        0,
        children * 2200
        - (
            50
            * fixed_threshold_factor
            * math.ceil(phaseout / (1000 * fixed_threshold_factor))
            if phaseout and fixed_threshold_factor
            else 0
        ),
    )
    income_tax = max(0, tax + gains_tax - credit)
    niit = 0.038 * min(
        gains + investment_ordinary, max(0, agi - 250000 * fixed_threshold_factor)
    )
    return dict(
        federal_income_tax=income_tax,
        net_investment_income_tax=niit,
        total_tax=income_tax + niit,
        agi=agi,
        aca_magi=ordinary + gains + social_security + exempt_interest,
        taxable_social_security=taxable_ss,
        ordinary_taxable=ordinary_taxable,
        taxable_gains=taxable_gains,
        child_credit_used=min(credit, tax + gains_tax),
    )


class TaxLedger:
    def __init__(self, plan, accounts):
        config = plan.get("tax_model") or {}
        if not isinstance(config, dict):
            raise ValueError("tax_model must be an object")
        self.enabled = config.get("enabled", False)
        if not isinstance(self.enabled, bool):
            raise ValueError("tax_model enabled must be a boolean")
        self.accounts = accounts
        self.plan = plan
        self.config = config
        self.years = {}
        self.previous_december = {}
        self.pending_refunds = {}
        self.basis = [a.get("cost_basis") for a in accounts]
        if not self.enabled:
            return
        if config.get("jurisdiction") != "US-MFJ-FL-2026":
            raise ValueError("Supported tax jurisdiction is US-MFJ-FL-2026 only")
        self.valuation = date.fromisoformat(plan["valuation_date"])
        self.inflation = value(plan.get("inflation_rate", 0), "inflation", 0, 0.5)
        self.surcharge = value(
            config.get("additional_withdrawal_tax_rate", 0),
            "additional withdrawal tax",
            0,
            0.2,
        )
        self.incomes = list(config.get("income_context", []))
        self.gross_streams = [
            r
            for r in plan.get("streams", [])
            if r.get("kind") == "income"
            and r.get("tax_kind") in ("ordinary", "social_security")
            and r.get("enabled", True)
        ]
        self.incomes += [
            dict(r, kind=r["tax_kind"], gross_stream=True) for r in self.gross_streams
        ]
        if not isinstance(self.incomes, list) or len(self.incomes) > 100:
            raise ValueError("income_context must be a bounded list")
        for row in self.incomes:
            if not isinstance(row, dict):
                raise ValueError("Tax income contexts must be objects")
            if row.get("kind") not in (
                "ordinary",
                "gains",
                "social_security",
                "exempt_interest",
            ):
                raise ValueError("Unsupported tax income context")
            if row.get("role") in ("base_wages", "new_job_wages", "bonus_wages"):
                value(row.get("gross_amount"), "gross wage amount")
                if not isinstance(row.get("stream_id"), str):
                    raise ValueError(
                        "Wage contexts require the corresponding net income stream ID"
                    )
            value(row.get("amount"), "tax context amount")
            value(row.get("start_month", 1), "tax context start", 1, 1801)
            value(row.get("end_month", 1801), "tax context end", 1, 1801)
            value(row.get("every_months", 1), "tax context recurrence", 1, 1200)
        raw_conversions = config.get("conversions", [])
        if (
            not isinstance(raw_conversions, list)
            or len(raw_conversions) > 100
            or any(not isinstance(r, dict) for r in raw_conversions)
        ):
            raise ValueError("Bound conversion schedules to100 objects")
        for years_key in ("adult_birth_years", "child_credit_end_years"):
            years = config.get(years_key, [])
            if (
                not isinstance(years, list)
                or len(years) > 20
                or any(type(y) is not int or not 1900 <= y <= 2300 for y in years)
            ):
                raise ValueError(f"{years_key} must contain entered calendar years")
        self.conversions = [dict(r) for r in raw_conversions]
        for conversion in self.conversions:
            value(conversion.get("amount"), "conversion amount")
            value(conversion.get("month"), "conversion month", 1, 1800)
            source = next(
                (
                    i
                    for i, a in enumerate(accounts)
                    if a.get("id") == conversion.get("source_account_id")
                ),
                None,
            )
            target = next(
                (
                    i
                    for i, a in enumerate(accounts)
                    if a.get("id") == conversion.get("target_account_id")
                ),
                None,
            )
            if source is None or target is None or source == target:
                raise ValueError(
                    "Conversion source and destination must reference different accounts"
                )
            if (
                accounts[source].get("tax_treatment") != "pretax"
                or accounts[target].get("tax_treatment") != "roth_qualified"
            ):
                raise ValueError(
                    "Conversion requires pretax source and Roth destination"
                )
            a = accounts[source]
            if (
                a.get("rmd_start_age")
                and self.calendar(conversion["month"])[0] - a.get("owner_birth_year", 0)
                >= a["rmd_start_age"]
            ):
                raise ValueError(
                    "RMD-year conversion ordering is not supported; separately satisfy RMD before planning a conversion"
                )
            conversion["source_index"] = source
            conversion["target_index"] = target
        self.conversions += self.fill_schedule(config.get("roth_conversion_fill"), accounts)
        for i, a in enumerate(accounts):
            treatment = a.get("tax_treatment")
            if treatment not in (
                "cash",
                "pretax",
                "taxable",
                "roth_qualified",
                "restricted",
                "property",
            ):
                raise ValueError(
                    "Every account needs an explicit tax_treatment when the tax model is enabled"
                )
            if treatment == "taxable":
                value(self.basis[i], "taxable account cost_basis")
                if a.get("gain_method") != "proportional_long_term":
                    raise ValueError(
                        "Taxable gain_method must explicitly be proportional_long_term; actual lot treatment requires review"
                    )
            if a.get("rmd_start_age") is not None:
                value(a["rmd_start_age"], "rmd_start_age", 72, 75)
                value(a.get("owner_birth_year"), "owner_birth_year", 1900, 2200)
                if treatment != "pretax":
                    raise ValueError("RMD schedule requires a pretax account")
            if (
                a.get("available_from_age") is not None
                and treatment in ("pretax", "roth_qualified")
                and a["available_from_age"] < 59.5
            ):
                raise ValueError(
                    "Tax model requires a separately reviewed early-access rule before age59.5"
                )

    def fill_schedule(self, rule, accounts):
        """December conversions that fill a bracket between two ages.

        Each December from start_age through end_age (the plan owner's age in that
        calendar year) converts from the pre-tax source to the Roth target the largest
        amount that keeps ordinary taxable income within the top of the fill_to bracket,
        after the year's income and withdrawals so far. Years when the source owes an RMD
        are skipped, as RMD-year ordering is not supported.
        """
        if rule is None:
            return []
        if not isinstance(rule, dict):
            raise ValueError("roth_conversion_fill must be an object")
        tops = {rate: top for top, rate in LIMITS if math.isfinite(top)}
        if rule.get("fill_to") not in tops:
            raise ValueError("roth_conversion_fill fill_to must be a bracket rate from 10% to 35%")
        ids = [a.get("id") for a in accounts]
        source = ids.index(rule.get("source_account_id")) if rule.get("source_account_id") in ids else None
        target = ids.index(rule.get("target_account_id")) if rule.get("target_account_id") in ids else None
        if (source is None or target is None or accounts[source].get("tax_treatment") != "pretax"
                or accounts[target].get("tax_treatment") != "roth_qualified"):
            raise ValueError("roth_conversion_fill requires a pretax source and Roth destination account")
        age = self.plan.get("age", 0)
        start = value(rule.get("start_age", age), "roth_conversion_fill start_age", 0, 150)
        end = value(rule.get("end_age", 74), "roth conversion end_age", start, 150)
        reserve = value(rule.get("minimum_liquid_reserve", 0), "conversion reserve")
        a = accounts[source]
        schedule = []
        for month in range(1, int(self.plan.get("horizon", 0)) * 12 + 1):
            year, calendar_month = self.calendar(month)
            owner_age = age + year - self.valuation.year
            if calendar_month != 12 or not start <= owner_age <= end:
                continue
            if a.get("rmd_start_age") and year - a.get("owner_birth_year", 0) >= a["rmd_start_age"]:
                continue
            schedule.append(dict(month=month, amount=None, fill_to=rule["fill_to"], fill_top=tops[rule["fill_to"]],
                                 source_index=source, target_index=target,
                                 source_account_id=rule["source_account_id"], target_account_id=rule["target_account_id"],
                                 minimum_liquid_reserve=reserve))
        return schedule

    def fill_amount(self, conversion, state, available):
        """Largest conversion up to `available` keeping ordinary taxable income in the bracket."""
        fits = lambda amount: self.liability(state, state["ordinary"] + amount, state["gains"])["ordinary_taxable"] <= conversion["fill_top"]
        if available <= 0 or not fits(0.0):
            return 0.0
        if fits(available):
            return available
        low, high = 0.0, available
        for _ in range(60):
            middle = (low + high) / 2
            low, high = (middle, high) if fits(middle) else (low, middle)
        return low

    def calendar(self, month):
        total = self.valuation.month - 1 + month
        return self.valuation.year + total // 12, total % 12 + 1

    def price(self, month):
        return (1 + self.inflation) ** (month / 12)

    def state(self, month):
        year, _ = self.calendar(month)
        if year not in self.years:
            base = dict(ordinary=0, gains=0, social_security=0, exempt_interest=0)
            wages = dict(
                base_gross=0.0, base_ordinary=0.0, bonus_gross=0.0, bonus_ordinary=0.0
            )
            gross_base = dict(ordinary=0, social_security=0)
            for m in range(1, int(self.plan["horizon"]) * 12 + 1):
                if self.calendar(m)[0] != year:
                    continue
                for row in self.incomes:
                    start = row.get("start_month", 1)
                    if (
                        start <= m < row.get("end_month", 1801)
                        and (m - start) % row.get("every_months", 1) == 0
                    ):
                        amount = row["amount"] * (1 + row.get("growth_rate", 0)) ** (
                            (m - start) / 12
                        )
                        base[row["kind"]] += amount
                        if row.get("gross_stream"):
                            gross_base[row["kind"]] += amount
                        if row.get("role") in (
                            "base_wages",
                            "new_job_wages",
                            "bonus_wages",
                        ):
                            prefix = "bonus" if row["role"] == "bonus_wages" else "base"
                            wages[prefix + "_ordinary"] += amount
                            wages[prefix + "_gross"] += row["gross_amount"] * (
                                1 + row.get("growth_rate", 0)
                            ) ** ((m - start) / 12)
            # Pre-baseline earned income is required only for the first partial tax year.
            prior = (
                self.config.get("first_year_income_before_baseline", {})
                if year == self.valuation.year
                else {}
            )
            for kind in base:
                base[kind] += value(prior.get(kind, 0), "pre-baseline tax income")
            if year == self.valuation.year:
                for key in wages:
                    wages[key] += value(
                        self.config.get("first_year_wages_before_baseline", {}).get(
                            key, 0
                        ),
                        "pre-baseline wages",
                    )
            children = sum(
                year < y for y in self.config.get("child_credit_end_years", [])
            )
            factor = (1 + self.inflation) ** (-(year - self.valuation.year))
            self.years[year] = dict(
                base=base,
                wages=wages,
                gross_base=gross_base,
                nii_ordinary=0.0,
                deduction=32200
                + 1650
                * sum(year - b >= 65 for b in self.config.get("adult_birth_years", [])),
                ordinary=0.0,
                gains=0.0,
                tax=0.0,
                surcharge=0.0,
                distributions={},
                mortgage_interest=0.0,
                property_tax=0.0,
                refund_due=0.0,
                salt_deduction=0.0,
                factor=factor,
                children=children,
            )
        return self.years[year]

    def liability(self, state, ordinary=0, gains=0, investment_ordinary=None):
        b = state["base"]
        return federal(
            b["ordinary"] + ordinary,
            b["gains"] + gains,
            b["social_security"],
            b["exempt_interest"],
            state["children"],
            state["factor"],
            deduction=state["deduction"],
            investment_ordinary=state["nii_ordinary"]
            if investment_ordinary is None
            else investment_ordinary,
        )

    def wage_net(self, month):
        if self.config.get("recalculate_wages") is not True:
            return None, set()
        state = self.state(month)
        w = state["wages"]
        factor = state["factor"]

        def payroll(gross):
            return (
                min(gross, 184500) * 0.062
                + gross * 0.0145
                + max(0, gross - 250000 * factor) * 0.009
            )

        base_tax = federal(
            ordinary=w["base_ordinary"],
            children=state["children"],
            fixed_threshold_factor=factor,
            deduction=state["deduction"],
        )["total_tax"]
        total_tax = federal(
            ordinary=w["base_ordinary"] + w["bonus_ordinary"],
            children=state["children"],
            fixed_threshold_factor=factor,
            deduction=state["deduction"],
        )["total_tax"]
        base_deductions = base_tax + payroll(w["base_gross"])
        bonus_deductions = (
            total_tax
            - base_tax
            + payroll(w["base_gross"] + w["bonus_gross"])
            - payroll(w["base_gross"])
        )
        net = 0.0
        ids = set()
        for row in self.incomes:
            if row.get("role") not in ("base_wages", "new_job_wages", "bonus_wages"):
                continue
            start = row.get("start_month", 1)
            if not start <= month < row.get("end_month", 1801) or (
                month - start
            ) % row.get("every_months", 1):
                continue
            prefix = "bonus" if row["role"] == "bonus_wages" else "base"
            gross = row["gross_amount"] * (1 + row.get("growth_rate", 0)) ** (
                (month - start) / 12
            )
            deductions = (
                (bonus_deductions if prefix == "bonus" else base_deductions)
                * gross
                / w[prefix + "_gross"]
                if w[prefix + "_gross"]
                else 0
            )
            net += (
                row["amount"]
                * (1 + row.get("growth_rate", 0)) ** ((month - start) / 12)
                - deductions
                - row.get("net_adjustment_per_payment", 0)
            )
            ids.add(row["stream_id"])
        return net, ids

    def income_tax(self, month, gross):
        state = self.state(month)
        b = state["base"]
        g = state["gross_base"]
        total = sum(g.values())
        if not total:
            return 0.0
        full = self.liability(state)["total_tax"]
        without = federal(
            b["ordinary"] - g["ordinary"],
            b["gains"],
            b["social_security"] - g["social_security"],
            b["exempt_interest"],
            state["children"],
            state["factor"],
            deduction=state["deduction"],
        )["total_tax"]
        return max(0, full - without) * gross / total

    def increment(self, state, ordinary, gains, investment_ordinary=0):
        before = self.liability(state, state["ordinary"], state["gains"])["total_tax"]
        after = self.liability(
            state,
            state["ordinary"] + ordinary,
            state["gains"] + gains,
            state["nii_ordinary"] + investment_ordinary,
        )["total_tax"]
        return max(0, after - before) + ordinary * self.surcharge

    def components(self, i, gross, balance):
        kind = self.accounts[i]["tax_treatment"]
        if kind == "pretax":
            return gross, 0.0
        if kind == "taxable":
            profit = (
                gross * max(0, 1 - (self.basis[i] or 0) / balance) if balance else 0.0
            )
            short = value(
                self.accounts[i].get("short_term_gain_fraction", 0),
                "short-term gain fraction",
                0,
                1,
            )
            return profit * short, profit * (1 - short)
        return 0.0, 0.0

    def quote(self, i, gross, balance, month):
        ordinary, gains = self.components(i, gross, balance)
        if not ordinary and not gains:
            return 0.0
        return self.increment(
            self.state(month),
            ordinary,
            gains,
            ordinary if self.accounts[i]["tax_treatment"] == "taxable" else 0,
        )

    def draw(self, i, net_needed, balance, month):
        if self.accounts[i]["tax_treatment"] in (
            "cash",
            "roth_qualified",
            "restricted",
            "property",
        ):
            return min(net_needed, balance), 0.0
        if net_needed <= balance and self.quote(i, net_needed, balance, month) == 0:
            return net_needed, self.commit(i, net_needed, balance, month)
        maximum = max(0, balance - self.quote(i, balance, balance, month))
        if net_needed >= maximum:
            gross = balance
        else:
            lo, hi = 0.0, balance
            for _ in range(45):
                mid = (lo + hi) / 2
                if mid - self.quote(i, mid, balance, month) < net_needed:
                    lo = mid
                else:
                    hi = mid
            gross = hi
        tax = self.commit(i, gross, balance, month)
        return gross, tax

    def commit(self, i, gross, balance, month):
        state = self.state(month)
        ordinary, gains = self.components(i, gross, balance)
        tax = self.increment(
            state,
            ordinary,
            gains,
            ordinary if self.accounts[i]["tax_treatment"] == "taxable" else 0,
        )
        state["ordinary"] += ordinary
        state["gains"] += gains
        if self.accounts[i]["tax_treatment"] == "taxable":
            state["nii_ordinary"] += ordinary
        state["tax"] += tax
        state["surcharge"] += ordinary * self.surcharge
        state["distributions"][i] = (
            state["distributions"].get(i, 0) + gross * self.price(month)
            if self.accounts[i]["tax_treatment"] == "pretax"
            else state["distributions"].get(i, 0)
        )
        if self.accounts[i]["tax_treatment"] == "taxable" and balance:
            self.basis[i] *= max(0, 1 - gross / balance)
        return tax

    def investment_income(self, i, opening, month):
        a = self.accounts[i]
        if a["tax_treatment"] not in ("cash", "taxable"):
            return 0.0
        ordinary = (
            opening
            * value(a.get("ordinary_income_yield", 0), "ordinary income yield", 0, 0.2)
            / 12
        )
        gains = (
            opening
            * value(
                a.get("qualified_dividend_yield", 0), "qualified dividend yield", 0, 0.2
            )
            / 12
        )
        if not ordinary and not gains:
            return 0.0
        state = self.state(month)
        tax = self.increment(state, ordinary, gains, ordinary)
        state["nii_ordinary"] += ordinary
        state["ordinary"] += ordinary
        state["gains"] += gains
        state["tax"] += tax
        state["surcharge"] += ordinary * self.surcharge
        self.deposit(i, max(0, ordinary + gains - tax))
        return tax

    def liquidity(self, indices, balances, month):
        state = self.state(month)
        ordinary = gains = gross = nii = 0.0
        for i in indices:
            o, g = self.components(i, balances[i], balances[i])
            ordinary += o
            gains += g
            gross += balances[i]
            if self.accounts[i]["tax_treatment"] == "taxable":
                nii += o
        return max(0, gross - self.increment(state, ordinary, gains, nii))

    def deposit(self, i, amount):
        if (
            self.enabled
            and i < len(self.accounts)
            and self.accounts[i]["tax_treatment"] == "taxable"
        ):
            self.basis[i] += amount

    def begin_month(self):
        if self.enabled:
            for i, b in enumerate(self.basis):
                if b is not None:
                    self.basis[i] = b / (1 + self.inflation) ** (1 / 12)

    def rmd(self, month, balances):
        year, calendar_month = self.calendar(month)
        if calendar_month != 12:
            return 0.0, 0.0, 0.0
        state = self.state(month)
        gross = net = tax = 0.0
        for i, a in enumerate(self.accounts):
            if a.get("rmd_start_age") is None:
                continue
            age = year - a["owner_birth_year"]
            if age < a["rmd_start_age"]:
                continue
            prior = self.previous_december.get(
                i, a.get("prior_year_end_nominal_balance")
            )
            if prior is None:
                raise ValueError(
                    "RMD requires the prior December31 balance for the first modeled distribution year"
                )
            needed = max(
                0,
                prior / RMD_FACTORS[min(120, int(age))]
                - state["distributions"].get(i, 0),
            ) / self.price(month)
            drawn = min(balances[i], needed)
            withheld = self.commit(i, drawn, balances[i], month)
            balances[i] -= drawn
            gross += drawn
            tax += withheld
            net += drawn - withheld
        return gross, net, tax

    def record_home_deductions(self, month, interest, property_tax):
        state = self.state(month)
        state["mortgage_interest"] += interest
        state["property_tax"] += property_tax

    def refund(self, month):
        year, calendar_month = self.calendar(month)
        return (
            self.pending_refunds.pop(year, 0) / (1 + self.inflation) ** (1 / 12)
            if calendar_month == 1
            else 0.0
        )

    def settle_year(self, month):
        year, calendar_month = self.calendar(month)
        if calendar_month != 12:
            return
        state = self.state(month)
        before = self.liability(state, state["ordinary"], state["gains"])
        # Statutory SALT increase expires after2029 under the reviewed law.
        index = 1.01 ** max(0, year - 2026)
        cap = (40400 * index if year <= 2029 else 10000) * state["factor"]
        if year <= 2029:
            cap = max(
                10000 * state["factor"],
                cap - 0.30 * max(0, before["agi"] - 505000 * index * state["factor"]),
            )
        state["salt_deduction"] = min(state["property_tax"], cap)
        itemized = state["mortgage_interest"] + state["salt_deduction"]
        if itemized > state["deduction"]:
            # The37%-bracket itemized limitation and AMT are outside this module.
            if before["ordinary_taxable"] > 768700:
                raise ValueError(
                    "High-income itemized limitation/AMT requires a reviewed tax projection"
                )
            state["deduction"] = itemized
            after = self.liability(state, state["ordinary"], state["gains"])
            state["refund_due"] = max(0, before["total_tax"] - after["total_tax"])
            self.pending_refunds[year + 1] = state["refund_due"]

    def finish_month(self, month, balances):
        if self.enabled and self.calendar(month)[1] == 12:
            self.previous_december = {
                i: b * self.price(month)
                for i, b in enumerate(balances[: len(self.accounts)])
            }

    def report(self):
        if not self.enabled:
            return {
                "enabled": False,
                "method": "Entered effective withdrawal tax rates",
            }
        rows = []
        for year, s in sorted(self.years.items()):
            full = self.liability(s, s["ordinary"], s["gains"])
            base = self.liability(s)
            rows.append(
                dict(
                    year=year,
                    ordinary_distributions=s["ordinary"],
                    realized_long_term_gains=s["gains"],
                    incremental_withdrawal_tax=s["tax"],
                    additional_tax_stress=s["surcharge"],
                    base_context_tax=base["total_tax"],
                    mortgage_interest_deduction=s["mortgage_interest"],
                    salt_deduction=s["salt_deduction"],
                    deduction_used=s["deduction"],
                    refund_due=s["refund_due"],
                    **full,
                )
            )
        return dict(
            enabled=True,
            version=VERSION,
            annual=rows,
            sources=SOURCES,
            method="2026 MFJ Florida ordinary/LTCG/SS/NIIT rules; indexed thresholds held in real dollars; non-indexed thresholds deflated. Wage net pay is recalculated from declared gross schedules when enabled; explicit residual deductions are retained. Investment/withdrawal taxes are charged once; no second charge for baseline wage/context taxes.",
            limitations=[
                "Planning rules held constant, not forecasts of future legislation. Standard or entered eligible mortgage/property-tax itemization with modeled annual refunds; no AMT,QBI,other itemization,foreign income,loss carryovers or special gains.",
                "Taxable gains use proportional basis and an entered short-term fraction; actual lot selection is not modeled. Entered investment income yields are part of total return and taxed once; unknown yields are not inferred.",
                "Qualified Roth access and all-pretax account treatment require confirmation; no early Roth basis or five-year conversion access inferred.",
                "RMDs use Uniform Lifetime Table and entered owner birth year, paid by December31; inherited accounts,working-employer exceptions and spouses over10years younger excluded.",
                "Mortgage interest uses monthly qualified-debt caps as a planning approximation; mixed grandfathered debt,points,rental use and actual escrow tax-disbursement timing require review. Itemized benefit is settled the followingJanuary,not free closing cash.",
                "ACA credits,Medicare IRMAA,estate taxes and survivor filing transitions require separate reviewed inputs.",
            ],
        )
