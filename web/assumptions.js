'use strict';
// Plan assumptions form.
function fillAssumptions() {
  assumptionsPending = false;
  const f = $('assumptions-form');
  f.elements.age.value = plan.age;
  f.elements.end_age.value = +plan.age + +plan.horizon;
  f.elements.retirement_age.value = plan.retirement_age;
  f.elements.return_rate.value = (+plan.return_rate * 100).toFixed(1);
  f.elements.withdrawal_rate.value = (+plan.withdrawal_rate * 100).toFixed(1);
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
  try {
    const result = await projectPlan(candidate);
    plan = candidate;
    assumptionsPending = false;
    touch();
    projection = result;
    renderTables();
    tell('Assumptions applied and projection updated. Save plan to keep changes.');
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
