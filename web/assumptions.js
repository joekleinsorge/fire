'use strict';
// Plan assumptions form.
function syncGuardrailFields() {
  const f = $('assumptions-form'),
    on = f.elements.spending_kind.value === 'guardrails';
  for (const l of f.querySelectorAll('.guardrail-field')) {
    l.hidden = !on;
    l.querySelector('input').disabled = !on;
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
  assumptionsPending = false;
  const f = $('assumptions-form');
  f.elements.age.value = plan.age;
  f.elements.end_age.value = +plan.age + +plan.horizon;
  f.elements.retirement_age.value = plan.retirement_age;
  f.elements.return_rate.value = (+plan.return_rate * 100).toFixed(1);
  f.elements.withdrawal_rate.value = (+plan.withdrawal_rate * 100).toFixed(1);
  f.elements.withdrawal_order.value = plan.withdrawal_order === 'tax_efficient' ? 'tax_efficient' : 'listed';
  const rule = plan.spending_strategy || {};
  f.elements.spending_kind.value = rule.kind === 'guardrails' ? 'guardrails' : 'fixed';
  f.elements.spending_floor.value = Math.round((rule.floor ?? 0.7) * 100);
  f.elements.spending_ceiling.value = Math.round((rule.ceiling ?? 1.2) * 100);
  syncGuardrailFields();
  const partner = plan.partner;
  f.elements.has_partner.checked = !!partner;
  f.elements.partner_name.value = partner?.name || '';
  f.elements.partner_age.value = partner?.age ?? '';
  f.elements.life_expectancy.value = plan.life_expectancy ?? '';
  f.elements.partner_life_expectancy.value = partner?.life_expectancy ?? '';
  f.elements.survivor_spending.value = Math.round((plan.survivor_spending ?? 0.7) * 100);
  syncPartnerFields();
  $('currency-display').value = plan.currency || 'USD';
}
async function applyAssumptions() {
  const f = $('assumptions-form');
  if (!f.reportValidity()) return false;
  const d = new FormData(f),
    age = +d.get('age'),
    endAge = +d.get('end_age'),
    retire = +d.get('retirement_age');
  if (endAge <= age || endAge - age > 150 || retire > endAge) {
    tell('Plan through age must be after your current age, within 150 years, and include retirement age.', true);
    return false;
  }
  const candidate = {
    ...structuredClone(plan),
    age,
    horizon: endAge - age,
    retirement_age: retire,
    return_rate: +d.get('return_rate') / 100,
    withdrawal_rate: +d.get('withdrawal_rate') / 100,
  };
  if (d.get('withdrawal_order') === 'tax_efficient') candidate.withdrawal_order = 'tax_efficient';
  else delete candidate.withdrawal_order;
  if (d.get('spending_kind') === 'guardrails')
    candidate.spending_strategy = {
      ...(plan.spending_strategy || {}),
      kind: 'guardrails',
      floor: +d.get('spending_floor') / 100,
      ceiling: +d.get('spending_ceiling') / 100,
    };
  else delete candidate.spending_strategy;
  const incomeMoved = d.get('move_income') ? moveRetirementIncome(candidate, plan.retirement_age, retire, plan.age) : [];
  let moved = 0;
  if (d.get('has_partner')) {
    if (d.get('partner_age') === '' || !(+d.get('partner_age') >= 0)) {
      tell('Enter your partner’s current age.', true);
      return false;
    }
    candidate.partner = {
      ...(plan.partner || {}),
      name: String(d.get('partner_name') || '').trim() || 'Partner',
      age: +d.get('partner_age'),
    };
    if (d.get('partner_life_expectancy')) candidate.partner.life_expectancy = +d.get('partner_life_expectancy');
    else delete candidate.partner.life_expectancy;
    if (d.get('life_expectancy')) candidate.life_expectancy = +d.get('life_expectancy');
    else delete candidate.life_expectancy;
    candidate.survivor_spending = +d.get('survivor_spending') / 100;
  } else if (candidate.partner) {
    // Removing the partner gives what they owned to you.
    for (const r of [...(candidate.streams || []), ...(candidate.social_security || [])])
      if (r.owner === 'partner') {
        r.owner = 'self';
        moved++;
      }
    delete candidate.partner;
    delete candidate.life_expectancy;
    delete candidate.survivor_spending;
  }
  try {
    const result = await projectPlan(candidate);
    plan = candidate;
    assumptionsPending = false;
    touch();
    projection = result;
    renderTables();
    tell(
      (moved
        ? `Assumptions applied. Partner removed; ${moved} item${moved === 1 ? '' : 's'} they owned now belong${moved === 1 ? 's' : ''} to you.`
        : 'Assumptions applied and projection updated. Save plan to keep changes.') +
        (incomeMoved.length ? ` ${incomeMoved.join(', ')} now end${incomeMoved.length === 1 ? 's' : ''} at ${retire}.` : ''),
    );
    return true;
  } catch (err) {
    tell(err.message, true);
    return false;
  }
}
$('assumptions-form').onsubmit = e => {
  e.preventDefault();
  applyAssumptions();
};
$('assumptions-form').elements.spending_kind.onchange = syncGuardrailFields;
$('assumptions-form').elements.has_partner.onchange = syncPartnerFields;
$('assumptions-form').oninput = () => {
  assumptionsPending = true;
  markDirty();
};
$('plan-name').oninput = e => {
  plan.name = e.target.value;
  touch();
};
$('valuation-date').onchange = e => {
  if (!e.target.value) return;
  plan.valuation_date = e.target.value;
  projection = null;
  touch();
  runProjection()
    .then(() => refreshObservations())
    .catch(err => tell(err.message, true));
  tell('Valuation baseline updated. Historical observations before this date will not be compared.');
};
