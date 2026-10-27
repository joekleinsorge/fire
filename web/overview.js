'use strict';
// Overview: snapshot KPIs, the projected assets chart and the annual table.
function calcSnapshot() {
  let a = plan.accounts.reduce((s, x) => s + (+x.balance || 0), 0),
    available = plan.accounts.reduce((s, x) => s + (isAvailableAccount(x) ? +x.balance || 0 : 0), 0),
    d = plan.debts.reduce((s, x) => s + (+x.balance || 0), 0);
  let income = 0,
    expense = 0;
  plan.streams
    .filter(s => s.enabled !== false)
    .forEach(s => {
      let n = 0;
      for (let m = 1; m <= 12; m++) {
        const start = Number(s.start_month || 1),
          end = Number(s.end_month ?? 1801);
        if (start <= m && m < end && (m - start) % Number(s.every_months || 12) === 0)
          n += (+s.amount || 0) * Math.pow(1 + Number(s.growth_rate || 0), (m - start) / 12);
      }
      if (s.kind === 'income') income += n;
      else expense += n;
    });
  if (projection?.monthly?.length) {
    const next = projection.monthly.slice(0, 12);
    income = next.reduce((n, m) => n + m.income, 0);
    expense = next.reduce(
      (n, m) =>
        n + (m.expenses || 0) + (m.debt_due || 0) + (m.withdrawal_taxes || 0) + (m.account_contribution_due || 0),
      0,
    );
  }
  return {
    assets: a,
    available,
    debt: d,
    net: a - d,
    income,
    expense,
    target: expense / (+plan.withdrawal_rate || 0.04),
  };
}
function renderSummary() {
  const s = calcSnapshot();
  $('net-worth').textContent = money(s.net);
  $('net-worth-note').textContent = `${money(s.assets)} assets · ${money(s.debt)} debt`;
  $('fi-target').textContent = projection ? money(projection.target) : '—';
  const ratio = projection?.target ? Math.min(100, (s.available / projection.target) * 100) : 0;
  $('funded-progress').textContent = projection ? pct(ratio / 100) : '—';
  $('funded-bar').style.width = `${ratio}%`;
  $('funded-bar').parentElement.setAttribute('aria-valuenow', String(Math.round(ratio)));
  $('funded-bar').parentElement.setAttribute(
    'aria-valuetext',
    `${Math.round(ratio)} percent of target using available accounts`,
  );
  $('funded-progress').title = `Based on ${money(s.available)} in accounts available for spending`;
  $('accounts-total').textContent = money(
    plan.accounts.filter(a => !isPersonalAsset(a)).reduce((n, a) => n + (+a.balance || 0), 0),
  );
  $('debts-total').textContent = money(s.debt);
  $('income-total').textContent = money(s.income);
  $('spending-total').textContent = money(s.expense);
  $('surplus-total').textContent = money(s.income - s.expense);
  if (!projection) {
    $('fi-age').textContent = '—';
    $('fi-age-note').textContent = 'Run a projection to estimate';
    $('essential-health').textContent = '—';
    $('unfunded-health').textContent = '—';
    $('debt-health').textContent = money(s.debt);
    $('health-status').textContent = 'Awaiting projection';
    $('projection-note').textContent = 'Run a projection to see your estimated path.';
    $('chart').innerHTML = '<div class="chart-empty">Your forecast will appear here after you run a projection.</div>';
    return;
  }
  const rows = projection.annual || [];
  const years = projection.years_to_target;
  projection.target = projection.target ?? s.target;
  $('fi-target').textContent = money(projection.target);
  const progress = Math.min(100, (s.available / (projection.target || 1)) * 100);
  $('funded-progress').textContent = pct(progress / 100);
  $('funded-bar').style.width = `${progress}%`;
  $('funded-bar').parentElement.setAttribute('aria-valuenow', String(Math.round(progress)));
  $('funded-bar').parentElement.setAttribute(
    'aria-valuetext',
    `${Math.round(progress)} percent of target using available accounts`,
  );
  $('funded-progress').title = `Based on ${money(s.available)} in accounts available for spending`;
  $('fi-age').textContent = years == null ? '—' : String(+plan.age + years);
  $('fi-age-note').textContent =
    years == null
      ? projection.earliest_fi_age != null
        ? `Assets reach the target at ${projection.earliest_fi_age} but fall short by planned retirement`
        : 'Target not reached under these assumptions'
      : projection.earliest_fi_age != null && projection.earliest_fi_age < +plan.age + years
        ? `Assets reach the target at ${projection.earliest_fi_age}; planned retirement is ${+plan.age + years}`
        : `Estimated in ${years} years`;
  $('essential-health').textContent =
    projection.essential_spending_funded === false
      ? 'Shortfall expected'
      : projection.essential_spending_funded === true
        ? 'Funded in modeled years'
        : 'See annual details';
  $('unfunded-health').textContent = money(
    projection.summary?.total_unfunded ?? rows.reduce((t, r) => t + (+r.unfunded || 0), 0),
  );
  $('debt-health').textContent = money(rows[Math.min(9, (rows.length || 1) - 1)]?.debt_balance ?? 0);
  $('health-status').textContent = projection.first_shortfall_month ? 'Review shortfall' : 'On track in model';
  $('projection-note').textContent =
    `${rows.length} years modeled · fixed real return estimate · ${projection.metadata?.engine_version || 'projection'}`;
  renderChart(
    rows.map(r => ({ ...r, balance: availableValue(r) })),
    projection.target,
  );
  renderAnnual();
  if (!plan.streams.some(s => s.enabled !== false && s.kind === 'expense' && Number(s.amount) > 0)) {
    $('fi-age').textContent = '—';
    $('fi-age-note').textContent = 'Add spending to estimate FI';
    $('health-status').textContent = 'No spending entered';
    $('essential-health').textContent = 'Not modeled';
  }
}
function renderChart(rows, target, series) {
  if (!rows.length) {
    $('chart').innerHTML = '<div class="chart-empty">No annual projection data returned.</div>';
    return;
  }
  const W = 760,
    H = 250,
    L = 60,
    R = 20,
    T = 18,
    B = 34,
    max =
      Math.max(
        target || 0,
        ...rows.map(r => +r.balance || 0),
        ...(series || []).flatMap(a => a.map(r => +r.balance || 0)),
        1,
      ) * 1.08,
    x = i => L + (i / Math.max(1, rows.length - 1)) * (W - L - R),
    y = v => T + (1 - v / max) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">`;
  for (let i = 0; i <= 4; i++) {
    const val = (max * i) / 4;
    s += `<line x1="${L}" x2="${W - R}" y1="${y(val)}" y2="${y(val)}" stroke="#e9ece7"/><text x="${L - 8}" y="${y(val) + 4}" text-anchor="end" fill="#79837e" font-size="10">${compact(val)}</text>`;
  }
  s += `<line x1="${L}" x2="${W - R}" y1="${y(target)}" y2="${y(target)}" stroke="#9aa891" stroke-dasharray="5 5"/>`;
  for (let q = 0; q < (series || []).length; q++) {
    const pts = series[q].map((r, i) => `${x(i)},${y(r.balance)}`).join(' ');
    s += `<polyline points="${pts}" fill="none" stroke="${['#b9c9c4', '#d3c6ad', '#afc7ae'][q % 3]}" stroke-width="1" opacity=".45"/>`;
  }
  const points = rows.map((r, i) => `${x(i)},${y(r.balance)}`).join(' ');
  s += `<polyline points="${points}" fill="none" stroke="#28675e" stroke-width="3"/>`;
  [0, Math.floor((rows.length - 1) / 2), rows.length - 1].forEach(
    i =>
      (s += `<text x="${x(i)}" y="${H - 9}" text-anchor="middle" fill="#79837e" font-size="10">Age ${esc(rows[i].age ?? +plan.age + i + 1)}</text>`),
  );
  $('chart').innerHTML = s + '</svg>';
}
function compact(n) {
  return n >= 1e6
    ? '$' + (n / 1e6).toFixed(1) + 'm'
    : n >= 1000
      ? '$' + Math.round(n / 1000) + 'k'
      : '$' + Math.round(n);
}
function renderAnnual() {
  const rows = projection?.annual || [];
  $('annual-table').innerHTML = rows
    .map(
      r =>
        `<tr><td>${r.year}</td><td>${r.age}</td><td>${money(availableValue(r))}</td><td>${money(r.net_worth)}</td><td>${money(r.debt_balance || 0)}</td><td>${money(r.purchase_paid || 0)}</td><td>${money((r.child_contributions || 0) + (r.child_education || 0))}</td><td>${money(r.unfunded || 0)}</td></tr>`,
    )
    .join('');
}
