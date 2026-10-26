'use strict';
// Progress: import balance observations from CSV and chart them against the projected
// spendable portfolio.

function parseCsvLine(line) {
  const cells = [];
  let cell = '', quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { cells.push(cell); cell = ''; }
    else cell += c;
  }
  cells.push(cell);
  return cells.map(v => v.trim());
}

// Accepts YYYY-MM-DD and M/D/YYYY; returns an ISO date or null.
function parseObservationDate(text) {
  let y, m, d;
  const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/), us = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (iso) [, y, m, d] = iso.map(Number);
  else if (us) [, m, d, y] = us.map(Number);
  else return null;
  const date = new Date(Date.UTC(y, m - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return null;
  return date.toISOString().slice(0, 10);
}

function parseObservationsCsv(text) {
  const lines = text.split(/\r?\n/).filter(l => l.trim());
  if (!lines.length) throw Error('The file is empty.');
  let header = parseCsvLine(lines[0]).map(h => h.toLowerCase());
  let dateCol = header.findIndex(h => h.includes('date')), balanceCol = header.findIndex(h => /balance|value|amount|total/.test(h));
  const noteCol = header.findIndex(h => /note|memo|comment/.test(h));
  let start = 1;
  if (dateCol < 0 || balanceCol < 0) { dateCol = 0; balanceCol = 1; start = 0; }
  const rows = [], problems = [];
  for (let i = start; i < lines.length; i++) {
    const cells = parseCsvLine(lines[i]), date = parseObservationDate(cells[dateCol] || '');
    const balance = Number(String(cells[balanceCol] || '').replace(/[$,\s]/g, ''));
    if (!date || !Number.isFinite(balance) || balance < 0) { problems.push(i + 1); continue; }
    rows.push({date, balance, note: noteCol >= 0 ? (cells[noteCol] || '').slice(0, 240) : ''});
  }
  if (problems.length && !start && problems[0] === 1) problems.shift(); // An unrecognized header row.
  return {rows, problems};
}

$('import-observations').onchange = async e => {
  const file = e.target.files?.[0];
  e.target.value = '';
  if (!file) return;
  try {
    const {rows, problems} = parseObservationsCsv(await file.text());
    const seen = new Set(observations.map(o => `${o.date}|${o.balance}`));
    const fresh = rows.filter(r => !seen.has(`${r.date}|${r.balance}`) && seen.add(`${r.date}|${r.balance}`));
    if (!fresh.length) throw Error(problems.length ? `No valid rows found; check lines ${problems.slice(0, 5).join(', ')}.` : 'Every row is already recorded.');
    const skipped = rows.length - fresh.length;
    const summary = `Import ${plural(fresh.length, 'observation')}${skipped ? `, skipping ${skipped} already recorded` : ''}${problems.length ? `, ignoring ${plural(problems.length, 'unreadable line')}` : ''}?`;
    if (!confirm(summary)) return;
    if (user) {
      if (!(await ensureSaved())) return;
      for (const row of fresh) await api(`/api/plans/${saved.id}/observations`, row);
    } else {
      for (const row of fresh) observations.push({id: uid(), local: true, ...row});
    }
    await refreshObservations();
    tell(`Imported ${plural(fresh.length, 'observation')}.`);
  } catch (err) {
    tell(err.message, true);
  }
};

function renderProgressChart() {
  const box = $('progress-chart');
  if (!box) return;
  const points = observations.map(o => ({...o, m: monthsSinceBaseline(o.date)})).filter(o => o.m != null && o.m >= 0).sort((a, b) => a.m - b.m);
  const monthly = projection?.monthly || [];
  if (!monthly.length) { box.innerHTML = '<p class="chart-empty">The projection is updating…</p>'; return; }
  if (!points.length) { box.innerHTML = '<p class="chart-empty">Record or import balances after your plan baseline to compare them with the projection.</p>'; return; }
  // Show at least two years, and a year past the latest observation.
  const span = Math.min(monthly.length, Math.max(24, points.at(-1).m + 12));
  const line = [{m: 0, v: projectedPortfolioAt(0)}].concat(monthly.slice(0, span).map((r, i) => ({m: i + 1, v: +r.available_balance || 0})));
  const W = 760, H = 220, L = 60, R = 20, T = 14, B = 30;
  const values = line.map(p => p.v).concat(points.map(p => p.balance));
  const lo = Math.min(...values) * .95, hi = Math.max(...values) * 1.05 || 1;
  const x = m => L + m / span * (W - L - R), y = v => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Recorded balances compared with the projected portfolio">`;
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ece7"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" fill="#79837e" font-size="10">${compact(v)}</text>`;
  }
  svg += `<polyline points="${line.map(p => `${x(p.m)},${y(p.v)}`).join(' ')}" fill="none" stroke="var(--green)" stroke-width="2"/>`;
  for (const p of points) {
    const projected = projectedPortfolioAt(p.m), diff = projected == null ? '' : ` · ${p.balance >= projected ? '+' : ''}${money(p.balance - projected)} vs projection`;
    svg += `<circle cx="${x(p.m)}" cy="${y(p.balance)}" r="5" fill="var(--orange)" stroke="#fff" stroke-width="2"><title>${esc(p.date)}: ${money(p.balance)}${diff}</title></circle>`;
  }
  [0, Math.round(span / 2), span].forEach(m => {
    svg += `<text x="${x(m)}" y="${H - 8}" text-anchor="middle" fill="#79837e" font-size="10">${esc(monthLabel(m))}</text>`;
  });
  box.innerHTML = svg + '</svg>';
}
