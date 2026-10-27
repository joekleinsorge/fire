'use strict';
// Core assumptions: ages, returns, inflation, spending rule and partner.
function syncGuardrailFields() {
  const f = $('assumptions-form'),
    on = f.elements.spending_kind.value === 'guardrails';
  for (const l of f.querySelectorAll('.guardrail-field')) {
    l.hidden = !on;
    l.querySelector('input').disabled = !on;
  }
}
function syncTaxFields() {
  const f = $('assumptions-form'),
    on = f.elements.tax_model.value === 'federal_2026';
  for (const l of f.querySelectorAll('.tax-field')) {
    l.hidden = !on;
    l.querySelector('input,select').disabled = !on;
  }
}
function syncPartnerFields() {
  const f = $('assumptions-form'),
    on = f.elements.has_partner.checked;
  for (const l of f.querySelectorAll('.partner-field')) {
    l.hidden = !on;
    l.querySelector('input').disabled = !on;
  }
}
function fillAssumptions() {
  const f = $('assumptions-form');
  f.elements.age.value = plan.age;
  f.elements.end_age.value = +plan.age + +plan.horizon;
  f.elements.retirement_age.value = plan.retirement_age;
  f.elements.return_rate.value = (+plan.return_rate * 100).toFixed(1);
  {
    const r = plan.spending_strategy || {};
    f.elements.spending_kind.value = r.kind === 'guardrails' ? 'guardrails' : 'fixed';
    f.elements.spending_floor.value = Math.round((r.floor ?? 0.7) * 100);
    f.elements.spending_ceiling.value = Math.round((r.ceiling ?? 1.2) * 100);
    syncGuardrailFields();
  }
  {
    const q = plan.partner;
    f.elements.has_partner.checked = !!q;
    f.elements.partner_name.value = q?.name || '';
    f.elements.partner_age.value = q?.age ?? '';
    f.elements.partner_retirement_age.value = q?.retirement_age ?? '';
    f.elements.life_expectancy.value = plan.life_expectancy ?? '';
    f.elements.partner_life_expectancy.value = q?.life_expectancy ?? '';
    f.elements.survivor_spending.value = Math.round((plan.survivor_spending ?? 0.7) * 100);
    syncPartnerFields();
  }
  {
    const t = plan.tax || {};
    f.elements.tax_model.value = t.model === 'federal_2026' ? 'federal_2026' : 'flat';
    f.elements.filing_status.value = t.filing_status || (plan.partner ? 'married_joint' : 'single');
    f.elements.state_rate.value = ((t.state_rate ?? 0) * 100).toFixed(1);
    f.elements.gain_share.value = Math.round((t.gain_share ?? 0.5) * 100);
    f.elements.roth_fill.value = t.roth_conversion ? String(t.roth_conversion.fill_to) : '';
    f.elements.roth_start.value = t.roth_conversion?.start_age ?? plan.retirement_age;
    f.elements.roth_end.value = t.roth_conversion?.end_age ?? 72;
    syncTaxFields();
  }
  f.elements.inflation_rate.value = ((+plan.inflation_rate || 0) * 100).toFixed(1);
  f.elements.withdrawal_rate.value = (+plan.withdrawal_rate * 100).toFixed(1);
  $('currency-display').value = plan.currency || 'USD';
}
$('assumptions-form').elements.spending_kind.onchange = syncGuardrailFields;
$('assumptions-form').elements.has_partner.onchange = syncPartnerFields;
$('assumptions-form').elements.tax_model.onchange = syncTaxFields;
$('assumptions-form').onsubmit = e => {
  e.preventDefault();
  const d = new FormData(e.currentTarget),
    age = +d.get('age'),
    endAge = +d.get('end_age'),
    retire = +d.get('retirement_age');
  if (endAge <= age || retire > endAge) {
    tell('Plan through age must be after your current age, and retirement age must be within the plan horizon.', true);
    return;
  }
  for (const s of plan.streams || []) {
    if (!s.end_basis && +s.end_month >= +plan.horizon * 12 + 1) s.end_basis = 'plan';
    if (!s.start_basis && (+s.start_month || 1) <= 1) s.start_basis = 'plan';
  }
  if (d.get('has_partner')) {
    const pa = +d.get('partner_age'),
      pr = d.get('partner_retirement_age');
    if (!(d.get('partner_age') !== '' && pa >= 0)) {
      tell('Enter your partner’s current age.', true);
      return;
    }
    const prev = plan.partner;
    plan.partner = {
      ...(prev || {}),
      name: String(d.get('partner_name') || '').trim() || 'Partner',
      age: pa,
      retirement_age: pr === '' ? (prev?.retirement_age ?? retire) : +pr,
    };
    if (prev && pr !== '' && +pr !== +prev.retirement_age) {
      plan.partner.retirement_age = prev.retirement_age;
      moveRetirement(plan, +pr, 'partner');
    }
    const ple = d.get('partner_life_expectancy');
    if (ple) plan.partner.life_expectancy = +ple;
    else delete plan.partner.life_expectancy;
    const le = d.get('life_expectancy');
    if (le) plan.life_expectancy = +le;
    else delete plan.life_expectancy;
    plan.survivor_spending = +d.get('survivor_spending') / 100;
  } else if (plan.partner) {
    let moved = 0;
    for (const r of [...(plan.streams || []), ...(plan.social_security || [])])
      if (r.owner === 'partner') {
        r.owner = 'self';
        moved++;
      }
    delete plan.partner;
    delete plan.life_expectancy;
    delete plan.survivor_spending;
    if (moved)
      tell(
        `Partner removed; ${moved} item${moved === 1 ? '' : 's'} they owned now belong${moved === 1 ? 's' : ''} to you.`,
      );
  }
  plan.age = age;
  plan.horizon = endAge - age;
  resyncStreams();
  moveRetirement(plan, retire);
  renderTables();
  plan.return_rate = +d.get('return_rate') / 100;
  plan.withdrawal_rate = +d.get('withdrawal_rate') / 100;
  plan.inflation_rate = +d.get('inflation_rate') / 100;
  if (d.get('spending_kind') === 'guardrails')
    plan.spending_strategy = {
      ...(plan.spending_strategy || {}),
      kind: 'guardrails',
      floor: +d.get('spending_floor') / 100,
      ceiling: +d.get('spending_ceiling') / 100,
    };
  else delete plan.spending_strategy;
  if (d.get('tax_model') === 'federal_2026')
    plan.tax = {
      model: 'federal_2026',
      filing_status: d.get('filing_status'),
      state_rate: +d.get('state_rate') / 100,
      gain_share: +d.get('gain_share') / 100,
      ...(d.get('roth_fill')
        ? { roth_conversion: { fill_to: +d.get('roth_fill'), start_age: +d.get('roth_start'), end_age: +d.get('roth_end') } }
        : {}),
    };
  else delete plan.tax;
  touch();
  if (plan.tax?.roth_conversion && !(plan.accounts || []).some(a => a.tax_treatment === 'roth'))
    tell('Roth conversions need a Roth account to receive them. Add one under Accounts & debts.', true);
  else tell('Assumptions applied. Update the projection to recalculate.');
};
$('plan-name').oninput = e => {
  plan.name = e.target.value;
  touch();
};
$('valuation-date').onchange = e => {
  if (!e.target.value) return;
  plan.valuation_date = e.target.value;
  resyncStreams();
  projection = null;
  touch();
  renderTables();
  runProjection()
    .then(() => refreshObservations())
    .catch(err => tell(err.message, true));
  tell('Valuation baseline updated. Historical observations before this date will not be compared.');
};
