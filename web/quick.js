'use strict';
// Quick calculator and expansion into a full plan.
function fillQuick() {
  const form = $('quick-form');
  if (!form) return;
  for (const k of ['age', 'assets', 'income', 'expenses', 'return_rate', 'withdrawal_rate', 'horizon'])
    form.elements[k].value =
      k === 'return_rate' || k === 'withdrawal_rate' ? (quickState[k] * 100).toFixed(1) : quickState[k];
  syncQuickDerived();
}
function syncQuickDerived() {
  const f = $('quick-form');
  if (!f) return;
  const savings = quickState.income - quickState.expenses;
  f.elements.income.value = quickState.income;
  f.elements.expenses.value = quickState.expenses;
  f.elements.savings.value = savings.toFixed(2);
  f.elements.monthly_savings.value = (savings / 12).toFixed(2);
  f.elements.savings_rate.value = quickState.income ? ((savings / quickState.income) * 100).toFixed(1) : '';
  f.elements.savings_rate.disabled = quickState.income === 0;
}
$('quick-form').onsubmit = e => e.preventDefault();
$('quick-form').oninput = e => {
  const k = e.target.name;
  if (!k) return;
  const val = Number(e.target.value);
  if (!Number.isFinite(val)) return;
  if (k === 'savings') {
    if (val > quickState.income) {
      tell('Savings cannot exceed income because expenses cannot be negative.', true);
      syncQuickDerived();
      return;
    }
    quickState.expenses = quickState.income - val;
  } else if (k === 'monthly_savings') {
    const annual = val * 12;
    if (annual > quickState.income) {
      tell('Savings cannot exceed income because expenses cannot be negative.', true);
      syncQuickDerived();
      return;
    }
    quickState.expenses = quickState.income - annual;
  } else if (k === 'savings_rate') {
    const annual = (quickState.income * val) / 100;
    if (annual > quickState.income) {
      tell('Savings rate cannot exceed 100%.', true);
      syncQuickDerived();
      return;
    }
    quickState.expenses = quickState.income - annual;
  } else if (k === 'income') {
    quickState.income = val;
  } else if (k === 'expenses') quickState.expenses = val;
  else if (k === 'return_rate' || k === 'withdrawal_rate') quickState[k] = val / 100;
  else quickState[k] = val;
  if (k === 'income' || k === 'expenses' || k === 'savings' || k === 'monthly_savings' || k === 'savings_rate')
    syncQuickDerived();
  quickResult = null;
  $('save-state').textContent = 'Unsaved quick estimate';
  $('save-state').classList.add('dirty');
  runQuick();
};
async function runQuick() {
  const token = ++quickRequest;
  try {
    $('quick-status').textContent = 'Calculating…';
    $('quick-status').className = 'status-pill';
    const p = {
      age: quickState.age,
      assets: quickState.assets,
      income: quickState.income,
      expenses: quickState.expenses,
      return_rate: quickState.return_rate,
      withdrawal_rate: quickState.withdrawal_rate,
      horizon: quickState.horizon,
    };
    const r = await api('/api/quick', { plan: p });
    if (token !== quickRequest) return;
    quickResult = r;
    renderQuick(r);
  } catch (e) {
    if (token !== quickRequest) return;
    $('quick-status').textContent = 'Calculation unavailable';
    $('quick-chart').innerHTML = `<p class="chart-empty">${esc(e.message)}</p>`;
  }
}
function renderQuick(r) {
  $('quick-target').textContent = money(r.target);
  $('quick-target-note').textContent =
    `${money(quickState.expenses)} annual expenses ÷ ${pct(quickState.withdrawal_rate)}`;
  $('quick-savings').textContent = money(r.savings);
  $('quick-status').textContent =
    {
      already_at_target: 'Already at target',
      target_reached: 'Target reached',
      not_reached_within_horizon: 'Beyond horizon',
      funding_shortfall: 'Funding shortfall',
      unreachable: 'Unreachable under assumptions',
    }[r.status] || r.status;
  $('quick-years').textContent = r.years_to_target == null ? '—' : String(r.years_to_target);
  $('quick-age').textContent = r.retirement_age == null ? '—' : String(r.retirement_age);
  $('quick-status').className =
    'status-pill ' +
    (r.status === 'target_reached' || r.status === 'already_at_target'
      ? 'good'
      : r.status === 'funding_shortfall'
        ? 'alert'
        : '');
  const rows = r.annual || [],
    target = r.target,
    W = 680,
    H = 200,
    L = 58,
    R = 18,
    T = 16,
    B = 30,
    max = Math.max(target, ...rows.map(x => x.balance), 1) * 1.08,
    x = i => L + (i / Math.max(1, rows.length - 1)) * (W - L - R),
    y = v => T + (1 - v / max) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">`;
  for (let i = 0; i <= 4; i++) {
    const v = (max * i) / 4;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ece7"/><text x="${L - 7}" y="${y(v) + 3}" text-anchor="end" fill="#79837e" font-size="9">${compact(v)}</text>`;
  }
  svg += `<line x1="${L}" x2="${W - R}" y1="${y(target)}" y2="${y(target)}" stroke="#9aa891" stroke-dasharray="5 5"/><polyline points="${rows.map((v, i) => `${x(i)},${y(v.balance)}`).join(' ')}" fill="none" stroke="#28675e" stroke-width="3"/>`;
  [0, rows.length - 1].forEach(
    i =>
      (svg += `<text x="${x(i)}" y="${H - 7}" text-anchor="middle" fill="#79837e" font-size="9">Age ${rows[i]?.age ?? ''}</text>`),
  );
  $('quick-chart').innerHTML = svg + '</svg>';
  $('quick-annual').innerHTML = rows
    .map(
      v => `<tr><td>${v.year}</td><td>${v.age}</td><td>${money(v.balance)}</td><td>${money(v.unfunded || 0)}</td></tr>`,
    )
    .join('');
  renderQuickSavings(r.savings_curve || []);
}
function renderQuickSavings(points) {
  const W = 680,
    H = 170,
    L = 44,
    R = 14,
    T = 12,
    B = 32,
    max = Math.max(1, quickState.horizon),
    x = v => L + v * (W - L - R),
    y = v => T + (1 - Math.min(v, max) / max) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">`;
  for (let i = 0; i <= 4; i++) {
    const v = (max * i) / 4;
    s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ece7"/><text x="${L - 5}" y="${y(v) + 3}" text-anchor="end" fill="#79837e" font-size="9">${Math.round(v)}y</text>`;
  }
  let segment = [];
  const flush = () => {
    if (segment.length > 1)
      s += `<polyline points="${segment.join(' ')}" fill="none" stroke="#28675e" stroke-width="2"/>`;
    segment = [];
  };
  for (const p of points) {
    const valid =
      p.years_to_target !== null &&
      p.years_to_target !== undefined &&
      ['target_reached', 'already_at_target'].includes(p.status);
    if (valid) segment.push(`${x(p.savings_rate)},${y(p.years_to_target)}`);
    else flush();
  }
  flush();
  for (const p of points) {
    const valid =
        p.years_to_target !== null &&
        p.years_to_target !== undefined &&
        ['target_reached', 'already_at_target'].includes(p.status),
      yy = valid ? y(p.years_to_target) : y(max);
    s += `<circle cx="${x(p.savings_rate)}" cy="${yy}" r="3" fill="${valid ? '#28675e' : '#be805d'}"><title>${(p.savings_rate * 100).toFixed(0)}% savings: ${valid ? `${p.years_to_target} years` : p.status || 'not reached'}</title></circle>`;
  }
  s += `<text x="${L}" y="${H - 7}" fill="#79837e" font-size="9">0%</text><text x="${W - R}" y="${H - 7}" text-anchor="end" fill="#79837e" font-size="9">100% savings rate</text></svg>`;
  $('quick-savings-chart').innerHTML = s;
}
function expandQuick() {
  if (!discardOk('replace it with this quick estimate')) return false;
  const q = { ...quickState };
  scenarios = [];
  observations = [];
  plan = {
    name: 'Expanded quick estimate',
    age: q.age,
    horizon: q.horizon,
    retirement_age: Math.min(300, q.age + q.horizon),
    valuation_date: valuationDate(),
    return_rate: q.return_rate,
    withdrawal_rate: q.withdrawal_rate,
    inflation_rate: 0.025,
    currency: plan.currency || 'USD',
    accounts: [
      {
        id: uid(),
        name: 'Quick estimate portfolio',
        type: 'investment',
        balance: q.assets,
        return_rate: q.return_rate,
        fee_rate: 0,
        available: true,
      },
    ],
    streams: [
      {
        id: uid(),
        name: 'After-tax income (quick estimate)',
        kind: 'income',
        amount: q.income,
        every_months: 12,
        start_month: 12,
        end_month: q.horizon * 12 + 1,
        enabled: true,
        growth_rate: 0,
        essential: true,
      },
      {
        id: uid(),
        name: 'Expenses (quick estimate)',
        kind: 'expense',
        amount: q.expenses,
        every_months: 12,
        start_month: 12,
        end_month: q.horizon * 12 + 1,
        enabled: true,
        growth_rate: 0,
        essential: true,
      },
    ],
    debts: [],
  };
  saved = null;
  projection = null;
  $('saved-plans').value = '';
  $('plan-name').value = plan.name;
  $('valuation-date').value = plan.valuation_date;
  fillAssumptions();
  renderTables();
  go('accounts');
  touch();
  tell(
    'Expanded as a full plan. The portfolio, annual after-tax cash flows, constant real return, and horizon were carried over; adjust the retirement age and account details for your situation.',
  );
}
$('expand-quick').onclick = expandQuick;

