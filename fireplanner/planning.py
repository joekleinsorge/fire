"""Bounded planning tools. No statutory or proprietary methods are implied."""
import math
from .engine import quick

VERSION = 'planning-2'

def number(value, name, minimum=0, maximum=1e15):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a number')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number') from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f'{name} outside supported range')
    return result

def integer(value, name, minimum, maximum):
    result = number(value, name, minimum, maximum)
    if result != int(result):
        raise ValueError(f'{name} must be an integer')
    return int(result)

def capabilities():
    return {'version': VERSION, 'available': ['quick', 'fixed_projection', 'saved_revisions', 'scenarios', 'durable_run_history', 'scenario_snapshot_runs', 'mcp_stdio', 'parametric_simulation', 'user_data_resampling', 'debt', 'sensitivity', 'bounded_search', 'effective_tax_fallback', 'gross_estate_arithmetic', 'user_supplied_survival', 'mfj_florida_2026_withdrawal_taxes', 'rmd_uniform_lifetime', 'source_labeled_intake', 'marketplace_2026_quote_arithmetic'], 'unavailable': {'full_statutory_taxes': 'Bounded2026 MFJ Florida standard-deduction module only; other jurisdictions,AMT,itemization and future law not installed', 'social_security_estimation': 'No reviewed benefit rules installed; enter manual income', 'full_ACA_Medicare': '2026 Marketplace quote arithmetic available; eligibility,Medicare IRMAA and future program changes require reviewed inputs', 'named_withdrawal_methods': 'Exact source-reviewed variants not installed', 'licensed_historical_data': 'Supply your own annual total-return series', 'mortality_tables': 'Supply a reviewed survival series; none bundled', 'international_rules': 'No reviewed country modules installed'}}

def analyze(payload):
    kind = payload.get('kind')
    if kind == 'healthcare':
        from .healthcare import estimate
        return {'kind':kind,**estimate(payload)}
    if kind == 'federal_tax':
        from .taxes import federal,SOURCES,VERSION as TAX_VERSION
        if payload.get('jurisdiction')!='US-MFJ-FL-2026':raise ValueError('Supported jurisdiction is US-MFJ-FL-2026')
        return {'kind':kind,'version':TAX_VERSION,'sources':SOURCES,**federal(**{key:payload[key] for key in ('ordinary','gains','social_security','exempt_interest','children') if key in payload})}
    if kind == 'debt':
        principal = number(payload.get('principal'), 'principal')
        rate = number(payload.get('annual_rate', 0), 'annual_rate', 0, 1) / 12
        months = integer(payload.get('months', 360), 'months', 1, 1200)
        extra = number(payload.get('extra_payment', 0), 'extra_payment')
        payment = principal / months if rate == 0 else principal * rate / (1 - (1 + rate) ** -months)
        balance, rows = principal, []
        for month in range(1, months + 1):
            interest = balance * rate
            paid = min(balance + interest, payment + extra)
            closing = max(0, balance + interest - paid)
            rows.append({'month': month, 'opening': balance, 'interest': interest, 'payment': paid, 'principal': paid - interest, 'closing': closing})
            balance = closing
            if balance <= 1e-8:
                break
        return {'kind': kind, 'monthly_payment': payment, 'months_to_payoff': len(rows), 'total_interest': sum(r['interest'] for r in rows), 'schedule': rows, 'assumption': 'Monthly interest, closing payment, fixed rate; no arrears, penalties, or fees.'}
    if kind in ('sensitivity', 'optimize'):
        plan = payload.get('plan', {})
        field = payload.get('field', 'expenses')
        if field not in ('assets', 'income', 'expenses', 'return_rate', 'withdrawal_rate'):
            raise ValueError('Unsupported search variable')
        lower = number(payload.get('minimum'), 'minimum', -0.99 if field == 'return_rate' else 0)
        upper = number(payload.get('maximum'), 'maximum', lower)
        count = integer(payload.get('steps', 11), 'steps', 2, 101)
        rows = []
        for i in range(count):
            value = lower + (upper - lower) * i / (count - 1)
            candidate = dict(plan, **{field: value})
            result = quick(candidate)
            rows.append({'value': value, 'years_to_target': result['years_to_target'], 'status': result['status'], 'target': result['target'], 'plan': candidate})
        reached = [r for r in rows if r['years_to_target'] is not None]
        best = min(reached, key=lambda r: r['years_to_target']) if reached else None
        return {'kind': kind, 'field': field, 'candidates': rows, 'best_evaluated': best if kind == 'optimize' else None, 'objective': 'minimum annual years to simple FI target', 'method': 'bounded equally spaced grid; first candidate wins ties', 'limitations': 'No global optimum or retirement funding guarantee. Fixed assumptions only. Save a chosen candidate as a separate scenario.'}
    if kind == 'effective_tax':
        gross = number(payload.get('gross_income', 0), 'gross_income')
        after = number(payload.get('after_tax_income', 0), 'after_tax_income')
        rate = number(payload.get('rate'), 'rate', 0, 1)
        return {'kind': kind, 'tax': gross * rate, 'available_income': gross * (1 - rate) + after, 'taxable_base': gross, 'excluded_after_tax_income': after, 'coverage': 'User-defined effective-rate fallback; annual closing payment. No statutory tax, benefits, deductions, or account access rules.'}
    if kind == 'estate':
        assets = number(payload.get('assets', 0), 'assets')
        debt = number(payload.get('debts', 0), 'debts')
        costs = number(payload.get('costs', 0), 'costs')
        tax = number(payload.get('manual_taxes', 0), 'manual_taxes')
        charity = number(payload.get('charitable_bequest', 0), 'charitable_bequest')
        residual = assets - debt - costs - tax
        funded_charity = min(max(0, residual), charity)
        return {'kind': kind, 'gross_estate': assets, 'net_before_bequests': max(0, residual), 'unfunded_obligations': max(0, -residual), 'funded_charity': funded_charity, 'unfunded_charity': charity - funded_charity, 'beneficiary_receipts': max(0, residual - charity), 'coverage': 'Arithmetic with user-entered tax/cost amounts. No estate law, basis step-up, ownership, or survivor calculation.'}
    if kind == 'longevity':
        series = payload.get('survival')
        if not isinstance(series, list) or not 1 <= len(series) <= 121:
            raise ValueError('Supply 1–121 annual survival probabilities')
        source = payload.get('source')
        if not isinstance(source, str) or not source.strip():
            raise ValueError('Survival source/version is required')
        funding = payload.get('funding_probability', 1)
        funding = number(funding, 'funding_probability', 0, 1)
        previous, rows = 1.0, []
        for year, item in enumerate(series):
            alive = number(item, 'survival probability', 0, previous)
            rows.append({'year': year, 'alive_funded': alive * funding, 'alive_shortfall': alive * (1 - funding), 'deceased': 1 - alive, 'funding_conditional_alive': funding if alive > 0 else None})
            previous = alive
        return {'kind': kind, 'source': source, 'annual': rows, 'assumption': 'User-supplied individual survival; funding independent of mortality. No joint-life or survivor cash-flow model.'}
    raise ValueError('Unknown analysis kind')
