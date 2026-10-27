'use strict';
// Healthcare estimate: adds age-based expense streams for coverage before Medicare and
// on Medicare. Streams it creates are tagged so running it again replaces them.

const HEALTHCARE_TAG = 'healthcare-estimate';

function openHealthcare() {
  const existing = (plan.streams || []).filter(s => s.source === HEALTHCARE_TAG);
  const pre = existing.find(s => s.healthcare_phase === 'pre_medicare'), medicare = existing.find(s => s.healthcare_phase === 'medicare');
  const people = existing[0]?.healthcare_people || 1;
  $('hc-people').value = people;
  $('hc-start').value = pre?.start_age ?? plan.retirement_age;
  if (pre) $('hc-pre').value = Math.round(pre.amount * 12 / people);
  if (medicare) {
    $('hc-medicare').value = Math.round(medicare.amount * 12 / people);
    $('hc-medicare-age').value = medicare.start_age;
  }
  $('hc-growth').value = (((existing[0]?.growth_rate) ?? .01) * 100).toFixed(1);
  $('healthcare-dialog').showModal();
}

function healthcareStreams() {
  const people = Number($('hc-people').value), start = Number($('hc-start').value), medicareAge = Number($('hc-medicare-age').value);
  const growth = Number($('hc-growth').value) / 100, base = {kind: 'expense', every_months: 1, enabled: true, essential: true,
    growth_rate: growth, source: HEALTHCARE_TAG, healthcare_people: people};
  const rows = [];
  // Before Medicare only if coverage starts earlier; private coverage ends when Medicare begins.
  if (start < medicareAge) {
    rows.push({...base, id: uid(), name: 'Healthcare before Medicare', healthcare_phase: 'pre_medicare',
      amount: Math.round(Number($('hc-pre').value) * people / 12 * 100) / 100,
      start_basis: 'age', start_age: start, end_basis: 'age', end_age: medicareAge});
  }
  rows.push({...base, id: uid(), name: 'Healthcare on Medicare', healthcare_phase: 'medicare',
    amount: Math.round(Number($('hc-medicare').value) * people / 12 * 100) / 100,
    start_basis: 'age', start_age: Math.max(start, medicareAge), end_basis: 'plan'});
  for (const row of rows) Object.assign(row, streamOffsets(row));
  return rows;
}

$('add-healthcare').onclick = openHealthcare;
$('healthcare-form').onsubmit = e => {
  e.preventDefault();
  if (!$('healthcare-form').reportValidity()) return;
  const rows = healthcareStreams();
  plan.streams = (plan.streams || []).filter(s => s.source !== HEALTHCARE_TAG).concat(rows);
  $('healthcare-dialog').close();
  touch();
  renderTables();
  tell(`Healthcare estimate added as ${rows.length === 1 ? 'one expense stream' : 'two expense streams'}. Edit them like any other cash flow.`);
};
