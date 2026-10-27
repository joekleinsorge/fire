'use strict';
// Running projections and retirement simulations.
async function projectPlan(p = plan) {
  return api('/api/project', { plan: p });
}
async function runProjection(quiet = false) {
  clearTimeout(autoTimer);
  const requested = JSON.stringify(plan);
  const b = $('run-projection');
  b.disabled = true;
  b.textContent = 'Calculating…';
  try {
    const result = await projectPlan(JSON.parse(requested));
    if (requested !== JSON.stringify(plan)) return;
    projection = result;
    simulation = null;
    touchAfterRun();
    renderTables();
    if (quiet !== true) tell('Projection updated.');
  } catch (e) {
    if (quiet === true) {
      $('projection-note').textContent = `Projection not updated: ${e.message}`;
      $('health-status').textContent = 'Needs attention';
    } else tell(e.message, true);
  } finally {
    b.disabled = false;
    b.innerHTML = 'Update projection <span>↗</span>';
  }
}
function touchAfterRun() {
  showSaveState();
}
$('run-projection').onclick = () => runProjection();
$('run-retirement').onclick = () => runProjection();
$('nominal-toggle').onchange = () => {
  if (projection) renderSummary();
};
$('table-toggle').onclick = () => {
  const on = $('annual-wrap').hidden;
  $('annual-wrap').hidden = !on;
  $('table-toggle').textContent = on ? 'Hide annual figures ↑' : 'Show annual figures ↓';
  $('table-toggle').setAttribute('aria-expanded', String(on));
};
// Annual returns pasted by the user: numbers separated by commas, spaces or lines. A
// series containing any value above 1.5 in magnitude is read as percentages.
function parseReturns(text) {
  const values = String(text || '').split(/[\s,;]+/).filter(Boolean).map(v => Number(v.replace('%', '')));
  if (values.some(v => !Number.isFinite(v))) throw Error('Returns must be numbers, one per year.');
  const percent = /%/.test(text) || values.some(v => Math.abs(v) > 1.5);
  return values.map(v => (percent ? v / 100 : v));
}
function simulationSettings() {
  const mode = $('sim-mode').value,
    base = { trials: +$('trials').value, seed: +$('seed').value, mode };
  if (mode === 'parametric') return { ...base, volatility: +$('volatility').value / 100 };
  const returns = parseReturns($('sim-returns').value);
  if (!returns.length) throw Error('Paste a series of annual returns for this method.');
  if (mode === 'historical' && returns.length < +plan.horizon)
    throw Error(`Historical periods need at least ${plan.horizon} years of returns for this plan; ${returns.length} supplied.`);
  return { ...base, historical_returns: returns, ...(mode === 'block' ? { block_size: +$('sim-block').value } : {}) };
}
function syncSimulationFields() {
  const mode = $('sim-mode').value;
  for (const el of document.querySelectorAll('.sim-parametric')) el.hidden = mode !== 'parametric';
  for (const el of document.querySelectorAll('.sim-history')) el.hidden = mode === 'parametric' || (el.querySelector('#sim-block') && mode !== 'block');
  $('trials').disabled = mode === 'historical';
  $('trials-note').textContent = mode === 'historical' ? 'Set by the number of complete windows in your series.' : '';
  try {
    localStorage.setItem('openfi:sim', JSON.stringify({ mode, returns: $('sim-returns').value, block: $('sim-block').value }));
  } catch {}
}
try {
  const stored = JSON.parse(localStorage.getItem('openfi:sim') || 'null');
  if (stored) {
    $('sim-mode').value = stored.mode || 'parametric';
    $('sim-returns').value = stored.returns || '';
    $('sim-block').value = stored.block || 5;
  }
} catch {}
$('sim-mode').onchange = syncSimulationFields;
$('sim-returns').oninput = syncSimulationFields;
$('sim-block').oninput = syncSimulationFields;
syncSimulationFields();
async function runSimulation() {
  if (!user) {
    tell('Sign in and save this plan before running a simulation.', true);
    openAuth();
    return;
  }
  try {
    if (!(await ensureSaved())) return;
    const data = await api(`/api/plans/${saved.id}/run`, {
      kind: 'simulate',
      settings: simulationSettings(),
    });
    pollJob(data.job.id, JSON.stringify(plan));
  } catch (e) {
    tell(e.message, true);
  }
}
$('run-simulation').onclick = runSimulation;
async function pollJob(id, inputSnapshot, attempt = 0) {
  if (inputSnapshot !== JSON.stringify(plan)) return;
  $('simulation-result').innerHTML = '<span class="quiet-icon">⌁</span><p>Simulation running…</p>';
  try {
    const d = await api(`/api/jobs/${id}`),
      j = d.job;
    if (inputSnapshot !== JSON.stringify(plan)) return;
    if (['complete', 'completed', 'succeeded'].includes(j.status)) {
      simulation = j.result;
      renderSimulation(j.result);
      return;
    }
    if (['failed', 'cancelled', 'canceled'].includes(j.status)) throw Error(j.error || 'Simulation did not complete.');
    if (attempt >= 600) throw Error('The simulation is taking too long to finish. Try fewer trials.');
    setTimeout(() => pollJob(id, inputSnapshot, attempt + 1), 700);
  } catch (e) {
    $('simulation-result').textContent = e.message;
    tell(e.message, true);
  }
}
function renderSimulation(r) {
  const funded = r.outcomes?.essential_spending_funded,
    rate = funded?.rate == null ? '—' : pct(funded.rate),
    bands = r.annual_bands || [];
  const W = 500,
    H = 125,
    L = 38,
    R = 8,
    T = 8,
    B = 20,
    max = Math.max(1, ...bands.map(x => +x.p90 || 0)),
    x = i => L + (i / Math.max(1, bands.length - 1)) * (W - L - R),
    y = v => T + (1 - v / max) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Simulation median and tenth to ninetieth percentile range">`;
  for (let i = 0; i <= 2; i++) {
    const v = (max * i) / 2;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ece7"/><text x="${L - 4}" y="${y(v) + 3}" text-anchor="end" fill="#79837e" font-size="8">${compact(v)}</text>`;
  }
  if (bands.length) {
    const upper = bands.map((b, i) => `${x(i)},${y(b.p90)}`).join(' '),
      lower = bands
        .slice()
        .reverse()
        .map((b, j) => `${x(bands.length - 1 - j)},${y(b.p10)}`)
        .join(' '),
      median = bands.map((b, i) => `${x(i)},${y(b.median)}`).join(' ');
    svg += `<polygon points="${upper} ${lower}" fill="#dcece3"/><polyline points="${median}" fill="none" stroke="#28675e" stroke-width="2"/>`;
  }
  svg += '</svg>';
  $('simulation-result').innerHTML =
    `${r.status === 'no_complete_periods' ? '<p class="notice error">No complete historical periods cover the selected horizon. Shorter or incomplete windows were not counted as successes.</p>' : ''}<div class="sim-outcome"><span>ESSENTIAL SPENDING FUNDED</span><strong>${esc(rate)}</strong><small>${funded?.numerator == null || funded?.denominator == null ? 'Outcome data unavailable' : `${funded.numerator} of ${funded.denominator} modeled paths`}${funded?.excluded ? ` · ${funded.excluded} excluded` : ''}</small></div><div class="sim-stats"><div>Ending assets median <strong>${money(r.ending_assets?.median)}</strong></div><div>10th–90th percentile <strong>${money(r.ending_assets?.p10)} – ${money(r.ending_assets?.p90)}</strong></div><div>Portfolio survives <strong>${r.outcomes?.portfolio_survives?.rate == null ? '—' : pct(r.outcomes.portfolio_survives.rate)}</strong></div><div>Desired lifestyle funded <strong>${r.outcomes?.desired_lifestyle_funded?.rate == null ? '—' : pct(r.outcomes.desired_lifestyle_funded.rate)}</strong></div>${r.outcomes?.spending_cuts ? `<div>Paths that cut discretionary spending <strong>${pct(r.outcomes.spending_cuts.rate)}</strong></div><div>Median lowest discretionary spending <strong>${pct(r.outcomes.spending_cuts.median_lowest_factor)} of plan</strong></div>` : ''}</div>${bands.length ? `<div class="simulation-band-chart">${svg}<small>Year ${bands[0].year} through ${bands[bands.length - 1].year} · median with 10th–90th percentile range</small></div>` : ''}`;
}
