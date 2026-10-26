'use strict';
// Overview: FI milestones and a stacked area of year-end balances by account, with net
// worth as a line on the same dollar axis. Colors follow the account's position in the
// plan (fixed order, never cycled); accounts past the sixth fold into "Other".

const WEALTH_SLOTS = 6;

function wealthSeries(rows) {
  const accounts = plan.accounts || [], series = [];
  const value = (row, i) => +(row.accounts?.[i]) || 0;
  accounts.slice(0, WEALTH_SLOTS).forEach((a, i) => series.push({
    name: a.name || `Account ${i + 1}`, color: `var(--series-${i + 1})`, values: rows.map(r => value(r, i)),
  }));
  // Later accounts, the engine's overflow cash ledger, and purchased property share "Other".
  const extra = rows.map(r => (r.accounts || []).slice(Math.min(WEALTH_SLOTS, accounts.length)).reduce((s, v) => s + (+v || 0), 0));
  const other = rows.map((r, i) => extra[i] + (+r.purchase_asset_value || 0));
  if (other.some(v => v > 0)) {
    const label = extra.some(v => v > 0) ? 'Other assets' : 'Purchased property';
    series.push({name: label, color: 'var(--series-other)', values: other});
  }
  return series;
}

// Milestones use the same target and spendable balances as the headline FI age.
function milestoneCards(rows) {
  const target = +projection.target || 0, retire = +plan.retirement_age, rate = +plan.return_rate || 0;
  const first = test => rows.find(test)?.age ?? null;
  const ageText = v => v == null ? 'Not reached' : `Age ${v}`;
  const cards = [
    ['Coast FI', first(r => r.age < retire && r.available_balance * (1 + rate) ** (retire - r.age) >= target),
      `Growth alone reaches the target by ${retire}, with no more saving`],
    ['Lean FI', first(r => r.available_balance >= target * .75), '75% of your FI target'],
    ['FI', projection.earliest_fi_age ?? null, 'Spendable assets reach the target'],
    ['Fat FI', first(r => r.available_balance >= target * 1.5), '150% of your FI target'],
  ];
  return cards.map(([label, age, note]) =>
    `<div class="${age != null && age <= +plan.age ? 'reached' : ''}">${label}<strong>${ageText(age)}</strong><small>${note}</small></div>`).join('');
}

function renderWealth() {
  const rows = projection?.annual || [];
  if (!rows.length) { $('wealth-chart').innerHTML = ''; $('wealth-legend').innerHTML = ''; $('milestones').innerHTML = ''; return; }
  $('milestones').innerHTML = milestoneCards(rows);
  const k = rows.map(r => futureFactor(r.year)), series = wealthSeries(rows).map(s => ({...s, values: s.values.map((v, i) => v * k[i])}));
  const net = rows.map((r, i) => (+r.net_worth || 0) * k[i]);
  const tops = rows.map((_, i) => series.reduce((s, x) => s + x.values[i], 0));
  const W = 760, H = 240, L = 60, R = 20, T = 14, B = 30;
  const max = Math.max(1, ...tops, ...net) * 1.06, min = Math.min(0, ...net);
  const x = i => L + i / Math.max(1, rows.length - 1) * (W - L - R), y = v => T + (1 - (v - min) / (max - min)) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Year-end balances by account with net worth">`;
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ece7"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" fill="#79837e" font-size="10">${compact(Math.max(0, v))}</text>`;
  }
  // Bands stack bottom-up; a white edge keeps adjacent fills visibly separate.
  const base = rows.map(() => 0);
  for (const s of series) {
    const upper = s.values.map((v, i) => base[i] + v);
    const top = upper.map((v, i) => `${x(i)},${y(v)}`), bottom = base.map((v, i) => `${x(i)},${y(v)}`).reverse();
    svg += `<polygon points="${top.join(' ')} ${bottom.join(' ')}" fill="${s.color}" fill-opacity=".85" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>`;
    upper.forEach((v, i) => { base[i] = v; });
  }
  svg += `<polyline points="${net.map((v, i) => `${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="var(--ink)" stroke-width="2"/>`;
  [0, Math.floor((rows.length - 1) / 2), rows.length - 1].forEach(i => {
    svg += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" fill="#79837e" font-size="10">Age ${esc(rows[i].age)}</text>`;
  });
  svg += `<line class="wealth-cross" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="#79837e" stroke-dasharray="3 3" visibility="hidden"/>`;
  svg += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" class="wealth-hit"/></svg>`;
  const chart = $('wealth-chart');
  chart.innerHTML = svg + '<div class="wealth-tip" hidden></div>';
  const last = rows.length - 1;
  $('wealth-legend').innerHTML = series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}<strong>${money(s.values[last])}</strong></span>`).join('')
    + `<span><i class="line-key"></i>Net worth<strong>${money(net[last])}</strong></span>`;
  $('wealth-basis').textContent = `${$('nominal-toggle')?.checked ? 'Future dollars' : 'Today’s dollars'} · values in the key are at age ${rows[last].age}`;

  const svgEl = chart.querySelector('svg'), tip = chart.querySelector('.wealth-tip'), cross = chart.querySelector('.wealth-cross');
  const show = evt => {
    const box = svgEl.getBoundingClientRect(), px = (evt.clientX - box.left) / box.width * W;
    const i = Math.max(0, Math.min(last, Math.round((px - L) / (W - L - R) * Math.max(1, last))));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    tip.innerHTML = `<b>Age ${esc(rows[i].age)}</b>` + series.slice().reverse().map(s => `<span><em><i style="background:${s.color}"></i>${esc(s.name)}</em>${money(s.values[i])}</span>`).join('')
      + `<span><em>Net worth</em><strong>${money(net[i])}</strong></span>`;
    tip.hidden = false;
    const left = x(i) / W * box.width;
    tip.style.left = `${Math.min(box.width - tip.offsetWidth, Math.max(0, left + (left > box.width / 2 ? -tip.offsetWidth - 12 : 12)))}px`;
    tip.style.top = '8px';
  };
  const hide = () => { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); };
  const hit = chart.querySelector('.wealth-hit');
  hit.addEventListener('pointermove', show);
  hit.addEventListener('pointerleave', hide);
}
