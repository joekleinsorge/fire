'use strict';
// Calendar months, ages and stream timing relative to the plan's valuation date.
// Projection month m (1-based) is the m-th calendar month after the valuation month.
function baselineParts(p = plan) {
  return String(p.valuation_date || valuationDate())
    .split('-')
    .map(Number);
}
function offsetToMonth(offset, p = plan) {
  const [y, m] = baselineParts(p),
    d = new Date(y, m - 1 + Number(offset), 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
function monthToOffset(value, p = plan) {
  const [y, m] = baselineParts(p),
    [vy, vm] = String(value).split('-').map(Number);
  return (vy - y) * 12 + (vm - m);
}
function monthLabel(offset, p = plan) {
  const [y, m] = baselineParts(p);
  return new Date(y, m - 1 + Number(offset), 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}
function ageAtOffset(offset, p = plan, row = null) {
  return personAge(row, p) + Math.floor((Number(offset) - 1) / 12);
}
// Streams keep engine month offsets (start inclusive, end exclusive) plus the user's intent:
// start_basis/end_basis is 'plan', 'age' or 'date', with start_age/start_date or end_age/end_date.
// Offsets are re-derived whenever age, horizon or the valuation date change.
function inferredBasis(which, row, p = plan) {
  if (which === 'start') return !row || (+row.start_month || 1) <= 1 ? 'plan' : 'date';
  return !row || row.end_month == null || +row.end_month >= +p.horizon * 12 + 1 ? 'plan' : 'date';
}
function streamOffsets(row, p = plan) {
  const fromAge = a => (Number(a) - personAge(row, p)) * 12 + 1,
    last = +p.horizon * 12 + 1;
  let start =
    row.start_basis === 'age'
      ? fromAge(row.start_age)
      : row.start_basis === 'date'
        ? monthToOffset(row.start_date, p)
        : row.start_basis === 'plan'
          ? 1
          : +row.start_month || 1;
  let end =
    row.end_basis === 'age'
      ? fromAge(row.end_age)
      : row.end_basis === 'date'
        ? monthToOffset(row.end_date, p) + 1
        : row.end_basis === 'plan'
          ? last
          : +row.end_month || last;
  start = Math.min(1801, Math.max(1, start));
  end = Math.min(1801, Math.max(start, end));
  return { start_month: start, end_month: end };
}
// Income that stops at the planned retirement age follows it when the retirement age changes.
function moveRetirement(p, age, who = 'self') {
  const current = who === 'partner' ? p.partner?.retirement_age : p.retirement_age;
  for (const s of p.streams || [])
    if (s.kind === 'income' && (s.owner || 'self') === who && s.end_basis === 'age' && +s.end_age === +current)
      s.end_age = age;
  if (who === 'partner') {
    if (p.partner) p.partner.retirement_age = age;
  } else p.retirement_age = age;
  resyncStreams(p);
}
// Age-based timing follows whoever the row belongs to; plan.age and partner.age are ages at valuation.
function personAge(row, p = plan) {
  return row?.owner === 'partner' && p.partner ? Number(p.partner.age) : Number(p.age);
}
function personName(owner, p = plan) {
  return owner === 'partner' ? p.partner?.name || 'Partner' : 'You';
}
function resyncStreams(p = plan) {
  for (const s of p.streams || []) if (s.start_basis || s.end_basis) Object.assign(s, streamOffsets(s, p));
}
function streamStartLabel(s, p = plan) {
  const m = +s.start_month || 1;
  return m <= 1
    ? 'Plan start'
    : `${monthLabel(m, p)}<small class="row-sub">${s.start_basis === 'age' ? `At age ${esc(s.start_age)}` : `Age ${ageAtOffset(m, p, s)}`}</small>`;
}
function streamEndLabel(s, p = plan) {
  const e = +s.end_month || +p.horizon * 12 + 1;
  if (e >= +p.horizon * 12 + 1) return 'End of plan';
  if (e <= (+s.start_month || 1)) return 'Never active';
  return `${s.end_basis === 'age' ? `Until age ${esc(s.end_age)}` : `Through ${monthLabel(e - 1, p)}`}<small class="row-sub">${s.end_basis === 'age' ? `Last payment by ${monthLabel(e - 1, p)}` : `Age ${ageAtOffset(e - 1, p, s)}`}</small>`;
}
function timingField(which, row) {
  const basis = row?.[`${which}_basis`] || inferredBasis(which, row),
    start = which === 'start',
    offset = start ? +row?.start_month || 1 : +row?.end_month || +plan.horizon * 12 + 1,
    month = row?.[`${which}_date`] || offsetToMonth(start ? offset : Math.max(1, offset - 1)),
    age =
      row?.[`${which}_age`] ?? (start ? ageAtOffset(offset, plan, row) : personAge(row) + Math.ceil((offset - 1) / 12)),
    options = start
      ? [
          ['plan', 'At plan start'],
          ['age', 'At age'],
          ['date', 'In month'],
        ]
      : [
          ['plan', 'At end of plan'],
          ['age', 'Until age'],
          ['date', 'Last payment in'],
        ];
  return `<fieldset class="timing-field"><legend>${start ? 'Starts' : 'Ends'}</legend><select name="${which}_basis" data-timing="${which}" aria-label="${start ? 'Start' : 'End'} timing">${options.map(([v, l]) => `<option value="${v}" ${v === basis ? 'selected' : ''}>${l}</option>`).join('')}</select><input name="${which}_age" type="number" min="0" max="150" step="1" value="${esc(age)}" aria-label="${start ? 'Start' : 'End'} age" ${basis === 'age' ? '' : 'hidden disabled'}><input name="${which}_date" type="month" value="${esc(month)}" aria-label="${start ? 'Start' : 'End'} month" ${basis === 'date' ? '' : 'hidden disabled'}></fieldset>`;
}
function syncTimingInputs() {
  for (const sel of $('dialog-fields').querySelectorAll('[data-timing]')) {
    const w = sel.dataset.timing;
    for (const [k, b] of [
      ['age', 'age'],
      ['date', 'date'],
    ]) {
      const input = $('dialog-fields').querySelector(`[name="${w}_${k}"]`);
      input.hidden = input.disabled = sel.value !== b;
    }
  }
}
function readTiming(row, data) {
  for (const w of ['start', 'end']) {
    const basis = data[`${w}_basis`];
    delete row[`${w}_age`];
    delete row[`${w}_date`];
    row[`${w}_basis`] = basis;
    if (basis === 'age') {
      const a = Number(data[`${w}_age`]);
      if (!Number.isInteger(a) || a < 0) throw Error(`Enter a whole-number ${w} age.`);
      row[`${w}_age`] = a;
    }
    if (basis === 'date') {
      if (!/^\d{4}-\d{2}$/.test(data[`${w}_date`] || '')) throw Error(`Choose a ${w} month.`);
      row[`${w}_date`] = data[`${w}_date`];
    }
    delete row[`${w}_month`];
  }
  const raw = { ...row };
  Object.assign(row, streamOffsets(row));
  const end =
    raw.end_basis === 'age'
      ? (raw.end_age - personAge(raw)) * 12 + 1
      : raw.end_basis === 'date'
        ? monthToOffset(raw.end_date) + 1
        : Infinity;
  if (end <= row.start_month) throw Error('The end must come after the start.');
}
