"""Structured, source-labeled household updates and independent purchase drafts."""

from copy import deepcopy
from datetime import date
from .taxes import value


def text(v, name, limit=200):
    if not isinstance(v, str) or not v.strip() or len(v) > limit:
        raise ValueError(f"{name} is required (up to {limit} characters)")
    return v.strip()


def day(v, name):
    try:
        d = date.fromisoformat(v)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be YYYY-MM-DD") from None
    if d > date.today():
        raise ValueError(f"{name} cannot be in the future")
    return d.isoformat()


def find(rows, ident, label):
    matches = [r for r in rows if r.get("id") == ident]
    if len(matches) != 1:
        raise ValueError(f"Choose an existing {label} ID")
    return matches[0]


def amount(d, key, low=0, high=1e15):
    return value(d.get(key), key, low, high)


def set_stream(plan, ident, amount_value, **extra):
    matches = [s for s in plan["streams"] if s.get("id") == ident]
    if not matches:
        raise ValueError(
            f"Modeled stream {ident} is missing; reconcile this plan first"
        )
    matches[0].update(amount=amount_value, **extra)


def completion(plan):
    f = plan.get("confirmed_inputs", {})
    reported = len(
        plan.get("household_source", {})
        .get("planner_inputs", {})
        .get("household", {})
        .get("children", {})
        .get("ages", [])
    )
    people = plan.get("members", [])
    kids = bool(people) and len(people) >= reported
    education = (
        kids
        and not any(
            a.get("source_details", {}).get("type") == "education_restricted"
            and a.get("balance", 0) > 0
            for a in plan.get("accounts", [])
        )
        and all(
            any(
                a.get("beneficiary_id") == m["id"]
                and a.get("education_annual_withdrawal") is not None
                for a in plan.get("child_accounts", [])
            )
            for m in people
        )
    )

    def fresh(a):
        snapshot = a.get("source_details", {}).get("latest_reported_snapshot", {})
        try:
            age = (
                date.today()
                - date.fromisoformat(snapshot.get("underlying_statement_date", ""))
            ).days
        except ValueError:
            return False
        return snapshot.get("confirmed") is True and 0 <= age <= (
            365 if a.get("type") in ("property", "other") else 45
        )

    recent = all(fresh(a) for a in plan.get("accounts", []))
    rows = [
        (
            "household",
            "Adult birth dates and ownership",
            bool(f.get("household")),
            "Confirm owner birth years for RMD and benefit timing.",
        ),
        (
            "payroll",
            "Actual pay and payroll deductions",
            bool(f.get("payroll")),
            "Use a paystub; target bonus remains uncertain.",
        ),
        (
            "mortgage",
            "Mortgage statement and escrow",
            bool(f.get("mortgage")),
            "Use current principal,remaining term,P&I and escrow.",
        ),
        (
            "balances",
            "Current balances and source dates",
            recent,
            "Refresh each account with its statement date; valuation date alone does not refresh it.",
        ),
        (
            "children",
            "Children and birth dates",
            kids,
            "Three reported children; names and exact birth dates are still needed for timing.",
        ),
        (
            "education",
            "529 mapping and college targets",
            education,
            "Allocate the restricted pool once; add per-child cost targets and Trump Account status.",
        ),
        (
            "healthcare",
            "Retirement healthcare and living budget",
            bool(f.get("healthcare")),
            "Confirm healthcare scope in the living target; provide a healthcare budget/quote.",
        ),
        (
            "insurance",
            "Insurance and estate records",
            bool(f.get("insurance"))
            and all(
                v is not None for v in f.get("insurance", {}).get("values", {}).values()
            ),
            "Record life/disability/umbrella limits,health exposure,wills,guardians and beneficiaries.",
        ),
        (
            "benefits",
            "Social Security and pension expectations",
            bool(f.get("benefits")),
            "Use statement estimates and claiming ages,or explicitly confirm no benefits assumed.",
        ),
        (
            "tax_basis",
            "Account tax character and cost basis",
            all(
                a.get("tax_basis_source", {}).get("confirmed")
                for a in plan.get("accounts", [])
                if a.get("tax_treatment") in ("pretax", "taxable", "roth_qualified")
            ),
            "Confirm pretax/Roth character and taxable basis; supplied basis uses a proportional long-term approximation.",
        ),
        (
            "investments",
            "Holdings,fees and employer equity",
            bool(f.get("employer_equity"))
            and all(
                a.get("source_details", {}).get("latest_holdings", {}).get("confirmed")
                for a in plan.get("accounts", [])
                if a.get("type") in ("investment", "retirement")
            ),
            "Statement holdings/fees and RSU vesting/liquidity remain needed.",
        ),
        (
            "second_home",
            "Second-home budget and costs",
            bool(f.get("second_home")),
            "Complete purchase price,date,financing and operating costs to save a calculated alternative.",
        ),
        (
            "project_quotes",
            "Roof,pool and window quotes",
            all(
                k in f.get("project_quotes", {}).get("values", {})
                for k in ("roof", "pool", "windows")
            ),
            "Keep estimates labeled until contractor quotes and dates are chosen.",
        ),
    ]
    return [dict(id=i, label=l, complete=bool(ok), next_step=n) for i, l, ok, n in rows]


def apply(plan, payload):
    if not isinstance(payload, dict) or payload.get("confirmed") is not True:
        raise ValueError("Confirm the supplied facts or chosen budget before applying")
    section = payload.get("section")
    d = payload.get("values")
    if not isinstance(d, dict):
        raise ValueError("values must be an object")
    source = text(payload.get("source"), "Statement or budget source")
    as_of = day(payload.get("as_of"), "Source date")
    q = deepcopy(plan)
    q.setdefault("streams", [])
    q.setdefault("accounts", [])
    q.setdefault("debts", [])
    q.setdefault("confirmed_inputs", {})[section] = dict(
        values=deepcopy(d),
        source=source,
        as_of=as_of,
        recorded_on=date.today().isoformat(),
        status="user_confirmed",
    )
    if section == "household":
        primary = day(d.get("primary_birth_date"), "Primary birth date")
        spouse = day(d.get("spouse_birth_date"), "Spouse birth date")
        q["household_birth_dates"] = {"primary": primary, "spouse": spouse}
        if q.get("tax_model", {}).get("enabled"):
            q["tax_model"]["adult_birth_years"] = [int(primary[:4]), int(spouse[:4])]
        for a in q["accounts"]:
            if a.get("rmd_start_age") is not None:
                a["owner_birth_year"] = int(
                    (spouse if a.get("owner_role") == "spouse" else primary)[:4]
                )
    elif section == "payroll":
        base = amount(d, "net_base_monthly")
        set_stream(q, "income-net-base-2026", base)
        if d.get("net_bonus_quarterly") is not None:
            set_stream(q, "income-net-bonus-2026", amount(d, "net_bonus_quarterly"))
        pretax = amount(d, "pretax_retirement_monthly")
        roth = amount(d, "roth_retirement_monthly")
        a = find(q["accounts"], d.get("retirement_account_id"), "retirement account")
        a["payroll_contribution_monthly"] = pretax
        if roth:
            matches = [a for a in q["accounts"] if a.get("id") == "future-roth-payroll"]
            bucket = (
                matches[0]
                if matches
                else dict(
                    id="future-roth-payroll",
                    name="Future Roth payroll contributions",
                    type="retirement",
                    balance=0,
                    return_rate=q.get("return_rate", 0.05),
                    available=False,
                    available_from_age=59.5,
                    tax_treatment="roth_qualified",
                    withdrawal_tax_rate=0,
                )
            )
            bucket.update(
                payroll_contribution_monthly=roth,
                contribution_start_month=1,
                contribution_end_month=a.get("contribution_end_month", 1),
            )
            if not matches:
                q["accounts"].append(bucket)
        for context in q.get("tax_model", {}).get("income_context", []):
            if context.get("role") == "base_wages":
                context["amount"] = context["gross_amount"] - pretax
                # Current after-tax estimate is retained as a source; the user-entered net
                # pay difference is an explicit forecast adjustment,not an extra expense.
                from .taxes import TaxLedger

                context["net_adjustment_per_payment"] = 0
                estimate = TaxLedger(q, q["accounts"]).wage_net(1)[0]
                context["net_adjustment_per_payment"] = estimate - base
        c = q.setdefault("compensation_summary", {})
        c.update(
            net_base_monthly=base,
            payroll_retirement_annual=(pretax + roth) * 12,
            notes=f"Net base supplied from {source},as of {as_of}. Bonus remains a target unless confirmed; payroll deductions are already included in net pay.",
        )
        if d.get("net_bonus_quarterly") is not None:
            c["net_bonus_quarterly"] = d["net_bonus_quarterly"]
    elif section == "mortgage":
        debt = find(q["debts"], d.get("debt_id"), "debt")
        balance = amount(d, "balance")
        apr = amount(d, "apr_pct", 0, 100) / 100
        months = amount(d, "remaining_months", 1, 1200)
        if int(months) != months:
            raise ValueError("remaining_months must be a whole number")
        debt.update(
            balance=balance,
            annual_rate=apr,
            months=int(months),
            payment=amount(d, "principal_interest_monthly"),
            nominal=True,
            balance_only=False,
            notes=f"User-supplied statement: {source}, {as_of}; escrow modeled separately.",
        )
        debt["source_details"] = {
            **debt.get("source_details", {}),
            "confirmed_statement": dict(source=source, as_of=as_of, **deepcopy(d)),
        }
        set_stream(q, "current-escrow", amount(d, "escrow_monthly"))
    elif section == "balance":
        a = find(q["accounts"], d.get("account_id"), "account")
        a["balance"] = amount(d, "balance")
        a.setdefault("source_details", {})["latest_reported_snapshot"] = dict(
            balance_usd=a["balance"],
            reported_on=date.today().isoformat(),
            underlying_statement_date=as_of,
            source=source,
            confirmed=True,
        )
        # A balance entry does not certify its tax basis or holdings.
    elif section == "children":
        children = d.get("children")
        if not isinstance(children, list) or not children or len(children) > 20:
            raise ValueError("Supply child profiles")
        members = q.setdefault("members", [])
        for child in children:
            ident = text(child.get("id"), "child ID", 80)
            birth = day(child.get("birth_date"), "Birth date")
            name = text(child.get("name"), "Child name", 120)
            if child.get("relationship", "Child") != "Child":
                raise ValueError("This form accepts child profiles")
            current = next((m for m in members if m["id"] == ident), None)
            row = {
                **(current or {}),
                **child,
                "id": ident,
                "name": name,
                "birth_date": birth,
                "relationship": "Child",
                "source": source,
                "as_of": as_of,
            }
            if current:
                members[members.index(current)] = row
            else:
                members.append(row)
        if q.get("tax_model", {}).get("enabled"):
            q["tax_model"]["child_credit_end_years"] = [
                int(m["birth_date"][:4]) + 17 for m in members
            ]
    elif section == "education":
        pool = find(
            q["accounts"], d.get("pool_account_id"), "restricted education pool"
        )
        if pool.get("source_details", {}).get("type") != "education_restricted":
            raise ValueError("Select the existing restricted education pool")
        rows = d.get("allocations")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Supply beneficiary allocations")
        if abs(sum(amount(r, "balance") for r in rows) - pool["balance"]) > 0.01:
            raise ValueError(
                "Child balances must equal the existing pool balance; this prevents duplication"
            )
        ids = set()
        accounts = q.setdefault("child_accounts", [])
        for r in rows:
            beneficiary = find(q.get("members", []), r.get("beneficiary_id"), "child")[
                "id"
            ]
            if beneficiary in ids:
                raise ValueError("One allocation per child in this mapping form")
            ids.add(beneficiary)
            ident = "mapped-529-" + beneficiary
            existing = next((a for a in accounts if a.get("id") == ident), None)
            if existing:
                raise ValueError(
                    "This pool is already mapped; edit the existing child accounts"
                )
            monthly = amount(r, "monthly_contribution")
            cost = amount(r, "education_annual_withdrawal")
            years = amount(r, "education_years", 1, 10)
            if years != int(years):
                raise ValueError("Education years must be an integer")
            accounts.append(
                dict(
                    id=ident,
                    name="529 — " + find(q["members"], beneficiary, "child")["name"],
                    type="529",
                    beneficiary_id=beneficiary,
                    adult_owner=text(d.get("adult_owner"), "Adult owner", 120),
                    balance=r["balance"],
                    return_rate=pool.get("return_rate", 0.04),
                    fee_rate=pool.get("fee_rate", 0),
                    annual_contribution=monthly * 12,
                    start_year=int(q["valuation_date"][:4]),
                    end_year=int(
                        find(q["members"], beneficiary, "child")["birth_date"][:4]
                    )
                    + 17,
                    education_start_age=18,
                    education_years=int(years),
                    education_annual_withdrawal=cost,
                    cover_education_shortfall=r.get("cover_education_shortfall", False),
                    contribution_source="household",
                    source=source,
                    as_of=as_of,
                )
            )
        pool.update(
            balance=0,
            household_contribution_monthly=0,
            notes=f"Balance and future deposits allocated exactly once to named child accounts on {as_of}. Original source retained.",
        )
    elif section == "healthcare":
        scope = d.get("living_target_includes_healthcare")
        if scope not in (True, False):
            raise ValueError(
                "Confirm whether living targets already include healthcare"
            )
        normal = amount(d, "normal_living_annual")
        minimum = amount(d, "minimum_living_annual")
        if minimum > normal:
            raise ValueError("Minimum budget cannot exceed normal budget")
        set_stream(q, "import-retirement-minimum", minimum / 12)
        set_stream(q, "import-retirement-lifestyle", (normal - minimum) / 12)
        set_stream(
            q,
            "retirement-health-pre",
            0 if scope else amount(d, "pre_medicare_annual") / 12,
        )
        set_stream(
            q,
            "retirement-health-post",
            0 if scope else amount(d, "post_medicare_annual") / 12,
        )
        set_stream(q, "retirement-home-reserve", amount(d, "home_capital_annual") / 12)
        set_stream(
            q,
            "retirement-vehicle-reserve",
            amount(d, "vehicle_replacement_annual") / 12,
        )
    elif section == "insurance":
        for key in (
            "life_primary",
            "life_spouse",
            "disability_monthly",
            "disability_waiting_days",
            "umbrella",
            "health_out_of_pocket_max",
        ):
            if d.get(key) is not None:
                amount(d, key)
        for key in (
            "wills",
            "guardians",
            "beneficiaries_reviewed",
            "powers_of_attorney",
        ):
            if d.get(key) is not None and not isinstance(d[key], bool):
                raise ValueError(f"{key} must be yes,no or unknown")
        required = (
            "life_primary",
            "life_spouse",
            "disability_monthly",
            "disability_waiting_days",
            "umbrella",
            "health_out_of_pocket_max",
            "wills",
            "guardians",
            "beneficiaries_reviewed",
            "powers_of_attorney",
        )
        q["confirmed_inputs"][section]["values"] = {key: d.get(key) for key in required}
    elif section == "benefits":
        if d.get("none_assumed") is not True:
            gross = amount(d, "monthly_gross")
            age = amount(d, "claim_age", 62, 75)
            offset = amount(d, "owner_age_offset", 0, 40)
            ident = "manual-social-security-" + text(d.get("id"), "Benefit label", 50)
            month = max(1, round((age + offset - q["age"]) * 12) + 1)
            row = dict(
                id=ident,
                name=text(d.get("name"), "Benefit name", 120),
                kind="income",
                amount=gross,
                start_month=month,
                end_month=q["horizon"] * 12 + 1,
                every_months=1,
                growth_rate=0,
                enabled=True,
                tax_kind="social_security",
                source=source,
                as_of=as_of,
            )
            q["streams"] = [s for s in q["streams"] if s["id"] != ident] + [row]
    elif section == "tax_basis":
        a = find(q["accounts"], d.get("account_id"), "account")
        kind = d.get("tax_treatment")
        if kind not in (
            "cash",
            "pretax",
            "taxable",
            "roth_qualified",
            "restricted",
            "property",
        ):
            raise ValueError("Choose account tax treatment")
        a["tax_treatment"] = kind
        if kind == "taxable":
            a.update(
                cost_basis=amount(d, "cost_basis"), gain_method="proportional_long_term"
            )
        a["tax_basis_source"] = dict(
            source=source,
            as_of=as_of,
            confirmed=True,
            method="User-entered tax character; taxable sales use proportional long-term approximation",
        )
    elif section == "investments":
        a = find(q["accounts"], d.get("account_id"), "account")
        holdings = d.get("holdings")
        if not isinstance(holdings, list) or len(holdings) > 200:
            raise ValueError("Supply a bounded holdings list")
        for h in holdings:
            text(h.get("symbol"), "Holding symbol", 30)
            amount(h, "market_value")
        if abs(sum(h["market_value"] for h in holdings) - a["balance"]) > 1:
            raise ValueError(
                "Holdings must reconcile to the entered account balance; include cash as a holding"
            )
        a["fee_rate"] = amount(d, "annual_fee_pct", 0, 20) / 100
        a.setdefault("source_details", {})["latest_holdings"] = dict(
            holdings=deepcopy(holdings), source=source, as_of=as_of, confirmed=True
        )
    elif section == "employer_equity":
        a = find(q["accounts"], d.get("account_id"), "employer equity account")
        if a.get("source_details", {}).get("type") != "employer_equity":
            raise ValueError("Choose the existing employer-equity holding")
        status = d.get("liquidity_status")
        if status not in ("restricted", "tradable"):
            raise ValueError(
                "Confirm restricted or tradable status; unknown cannot become spendable"
            )
        amount(d, "vested_units")
        amount(d, "unvested_units")
        a.setdefault("source_details", {})["vesting_record"] = dict(
            source=source, as_of=as_of, **deepcopy(d)
        )
        if status == "tradable":
            vested = amount(d, "vested_market_value")
            basis = amount(d, "vested_cost_basis")
            if vested > a["balance"] + 0.01:
                raise ValueError(
                    "Vested value cannot exceed the full entered employer-equity balance"
                )
            ident = a["id"] + "-tradable"
            if any(x.get("id") == ident for x in q["accounts"]):
                raise ValueError(
                    "Tradable shares already split; update their existing account"
                )
            a["balance"] -= vested
            q["accounts"].append(
                dict(
                    id=ident,
                    name="Tradable employer shares",
                    type="investment",
                    balance=vested,
                    return_rate=a.get("return_rate", 0),
                    fee_rate=0,
                    available=True,
                    tax_treatment="taxable",
                    cost_basis=basis,
                    gain_method="proportional_long_term",
                    short_term_gain_fraction=amount(
                        d, "short_term_gain_fraction", 0, 1
                    ),
                    source_details={
                        "type": "employer_equity",
                        "original_account_id": a["id"],
                        "vesting_record": deepcopy(
                            a["source_details"]["vesting_record"]
                        ),
                    },
                )
            )
    elif section == "project_quotes":
        key = d.get("project")
        if key not in ("roof", "pool", "windows"):
            raise ValueError("Choose roof,pool or windows")
        amount(d, "cost")
        amount(d, "annual_upkeep")
        text(d.get("target_month"), "Project month", 7)
        accumulated = deepcopy(
            plan.get("confirmed_inputs", {}).get("project_quotes", {}).get("values", {})
        )
        accumulated[key] = dict(d, source=source, as_of=as_of)
        q["confirmed_inputs"][section]["values"] = accumulated
    elif section == "second_home":
        second_home(
            q, d
        )  # Validation only; the alternative is saved separately by the endpoint.
    else:
        raise ValueError("Unsupported guided input section")
    mapping = {
        "payroll": ["current_verified_take_home_pay"],
        "mortgage": ["mortgage_remaining_term", "mortgage_payment_escrow_split"],
        "children": ["child_names_birth_dates_and_education_targets"],
        "education": ["529_beneficiary_mapping_and_holdings"],
        "healthcare": [
            "retirement_spending_tax_basis",
            "pre_medicare_healthcare_cost",
            "vehicle_replacement_reserve",
            "home_capital_reserve",
        ],
        "benefits": ["social_security_estimates"],
        "second_home": ["second_home_budget_date_funding_and_costs"],
        "project_quotes": ["pool_date_quote_upkeep_and_funding"],
    }
    for key in mapping.get(section, []):
        if key in q.get("unresolved_inputs", {}):
            q["unresolved_inputs"][key] = {
                "source": source,
                "as_of": as_of,
                "guided_section": section,
                "values": deepcopy(d),
            }
    q["completion_status"] = completion(q)
    review = q.setdefault("planning_review", {})
    review["blockers"] = [
        r["label"] + ": " + r["next_step"]
        for r in q["completion_status"]
        if not r["complete"]
    ]
    review["reviewed_on"] = date.today().isoformat()
    return q


def second_home(plan, d):
    q = deepcopy(plan)
    price = amount(d, "price")
    down = amount(d, "down_payment_pct", 0, 100) / 100
    rate = amount(d, "mortgage_rate_pct", 0, 30) / 100
    years = amount(d, "loan_years", 1, 50)
    if not price:
        raise ValueError("Second-home price must be greater than zero")
    try:
        y, m = map(int, d["purchase_month"].split("-"))
        date(y, m, 1)
    except (KeyError, ValueError, TypeError):
        raise ValueError("Choose a purchase month") from None
    vy, vm = map(int, q["valuation_date"][:7].split("-"))
    month = (y - vy) * 12 + m - vm
    if month < 1:
        raise ValueError("Purchase month must follow valuation month")
    costs = sum(
        amount(d, k)
        for k in (
            "property_tax_annual",
            "insurance_annual",
            "hoa_annual",
            "maintenance_annual",
        )
    )
    closing = amount(d, "closing_costs")
    moving = amount(d, "moving_costs")
    credit = amount(d, "seller_credit")
    if credit > closing:
        raise ValueError(
            "Seller credit cannot exceed entered buyer closing costs; lender limits still require confirmation"
        )
    nominal = d.get("price_basis") == "future_nominal"
    if d.get("price_basis") not in ("future_nominal", "plan_start_real"):
        raise ValueError("Choose the price dollar basis")
    factor = (1 + q.get("inflation_rate", 0)) ** (month / 12) if nominal else 1
    price /= factor
    costs /= factor
    closing /= factor
    moving /= factor
    credit /= factor
    item = dict(
        id="guided-second-home",
        name="Second home",
        amount=price,
        month=month,
        loan_amount=price * (1 - down),
        loan_rate=rate,
        loan_months=int(years * 12),
        nominal_loan=True,
        adds_asset=True,
        asset_return=0,
        annual_upkeep=costs,
        transaction_costs=closing + moving - credit,
        minimum_cash_reserve=amount(d, "liquid_reserve"),
        require_full_funding=True,
        enabled=True,
        source_details=deepcopy(d),
    )
    q.setdefault("future_purchases", []).append(item)
    rent = amount(d, "net_rental_income_monthly")
    if rent:
        q.setdefault("streams", []).append(
            dict(
                id="second-home-net-rent",
                name="Second-home net rent — after costs and taxes",
                kind="income",
                amount=rent / factor,
                start_month=month + 1,
                end_month=q["horizon"] * 12 + 1,
                every_months=1,
                growth_rate=0,
                enabled=True,
                requires_purchase_id=item["id"],
            )
        )
    return q


def quoted_project(plan, d):
    q = deepcopy(plan)
    key = d.get("project")
    if key not in ("roof", "pool", "windows"):
        raise ValueError("Choose a recognized project")
    try:
        y, m = map(int, d["target_month"].split("-"))
        date(y, m, 1)
    except (ValueError, KeyError, TypeError):
        raise ValueError("Choose a valid project month") from None
    vy, vm = map(int, q["valuation_date"][:7].split("-"))
    month = (y - vy) * 12 + m - vm
    if month < 1:
        raise ValueError("Project month must follow plan valuation")
    q.setdefault("future_purchases", []).append(
        dict(
            id=f"quoted-{key}-{month}",
            name=key.title() + " — supplied quote/budget",
            amount=amount(d, "cost"),
            month=month,
            annual_upkeep=amount(d, "annual_upkeep"),
            enabled=True,
            require_full_funding=True,
            minimum_cash_reserve=q.get("cash_reserve_target", 0),
            source_details=deepcopy(d),
        )
    )
    return q
