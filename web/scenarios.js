'use strict';
// Scenarios and scenario comparison.
function scenarioPlan(s) {
  return s.data ? s.data.plan : s.plan;
}
function scenarioName(s) {
  return s.data?.name || s.name || 'Scenario';
}
async function refreshScenarios() {
  if (saved) {
    const id = saved.id,
      d = await api(`/api/plans/${id}/scenarios`);
    if (saved?.id !== id) return;
    scenarios = d.scenarios || [];
  }
  await refreshRuns();
  renderScenarios();
}
function renderScenarios() {
  const wrap = $('scenario-list');
  wrap.innerHTML = '';
  if (!scenarios.length) {
    wrap.innerHTML =
      '<div class="panel empty-state">No scenarios saved. Create a named alternative to log its assumptions and results.</div>';
    return;
  }
  for (const scenario of scenarios) {
    const p = scenarioPlan(scenario),
      latest = runHistory.find(r => r.scenario_id === scenario.id),
      result = latest?.result,
      tag = latest
        ? `${latest.kind === 'simulate' ? 'Simulation' : 'Projection'} · ${latest.status}`
        : 'No saved calculation yet',
      currency = p.currency || 'USD';
    const el = document.createElement('article');
    el.className = 'panel scenario-card';
    el.innerHTML = `<div class="panel-head"><div><span class="scenario-tag">SAVED SCENARIO</span><h2>${esc(scenarioName(scenario))}</h2></div><button class="icon-button danger-text" data-remove-scenario="${esc(scenario.id)}" aria-label="Remove ${esc(scenarioName(scenario))}">×</button></div><p class="small-note">Retire at ${p.retirement_age}; ${p.accounts?.length || 0} holdings · ${p.streams?.length || 0} cash flows</p><p class="small-note">${esc(scenario.data?.metadata?.rationale || scenario.data?.metadata?.notes || '')}</p><div class="scenario-result">${esc(tag)}${result?.target != null ? ` · Target ${runMoney(result.target, currency)}` : ''}</div><div class="button-row"><button class="button secondary" data-run-scenario="${esc(scenario.id)}">Log projection</button><button class="button text-button" data-run-scenario="${esc(scenario.id)}" data-run-kind="simulate">Log simulation</button></div><div class="button-row"><button class="button secondary" data-compare="${esc(scenario.id)}">Log comparison</button><button class="button text-button" data-open-scenario="${esc(scenario.id)}">Open inputs</button></div>`;
    wrap.append(el);
  }
}
async function saveScenario() {
  const name = $('scenario-name').value.trim();
  if (!name) {
    $('scenario-name').focus();
    return;
  }
  try {
    if (!user) {
      openAuth();
      return;
    }
    if (!(await savePlan()) || workingDirty) return;
    const reply = await api(`/api/plans/${saved.id}/scenarios`, {
        name,
        plan: structuredClone(plan),
        baseline_plan: saved.plan,
        base_version: saved.version,
        metadata: { origin: 'planner UI' },
      }),
      scenario = reply.scenario;
    $('scenario-dialog').close();
    await refreshScenarios();
    await startScenarioRun(scenario.id);
    tell('Scenario saved; its projection has been queued and logged.');
  } catch (e) {
    tell(e.message, true);
  }
}
$('save-scenario').onclick = $('new-scenario').onclick = () => (user ? $('scenario-dialog').showModal() : openAuth());
$('scenario-form').onsubmit = e => {
  e.preventDefault();
  saveScenario();
};
$('scenario-close').onclick = $('scenario-cancel').onclick = () => $('scenario-dialog').close();
$('scenario-list').onclick = async e => {
  const comp = e.target.closest('[data-compare]'),
    open = e.target.closest('[data-open-scenario]'),
    remove = e.target.closest('[data-remove-scenario]');
  if (remove) {
    try {
      if (saved && scenarios.find(s => s.id === remove.dataset.removeScenario)?.data)
        await api(`/api/plans/${saved.id}/scenarios/${remove.dataset.removeScenario}`, {}, 'DELETE');
      else scenarios = scenarios.filter(s => s.id !== remove.dataset.removeScenario);
      await refreshScenarios();
    } catch (err) {
      tell(err.message, true);
    }
  }
  if (open) {
    const scenario = scenarios.find(s => s.id === open.dataset.openScenario),
      p = scenarioPlan(scenario);
    if (scenario) {
      if (workingDirty && !confirm('Open the saved scenario and replace your unsaved edits?')) return;
      plan = structuredClone(p);
      plan.name = scenarioName(scenario);
      saved = null;
      observations = [];
      scenarios = [];
      renderScenarios();
      simulation = null;
      projection = null;
      $('saved-plans').value = '';
      $('plan-name').value = plan.name;
      $('valuation-date').value = plan.valuation_date;
      fillAssumptions();
      renderTables();
      touch();
      go('inputs');
      tell('Scenario opened as an independent working copy. Save plan to keep further edits.');
    }
  }
  if (comp) {
    const scenario = scenarios.find(s => s.id === comp.dataset.compare);
    if (scenario) {
      const latest = runHistory.find(
        r => r.scenario_id === scenario.id && r.kind === 'project' && r.status === 'completed',
      );
      if (latest) {
        const { job } = await api(`/api/jobs/${latest.id}`);
        renderSavedRun(job);
        $('run-detail').scrollIntoView({ behavior: 'smooth' });
      } else await startScenarioRun(scenario.id);
    }
  }
};
function chartForCompare(results) {
  const currencies = results.map(r => r.metadata?.currency || 'USD'),
    bases = results.map(r => r.metadata?.price_basis || 'unknown');
  if (currencies[0] !== currencies[1] || bases[0] !== bases[1])
    return '<p class="chart-empty">These plans use different currencies or price bases. Convert them with explicit assumptions before comparing their asset paths.</p>';
  const maps = results.map(r => new Map((r.annual || []).map(row => [row.age, availableValue(row)]))),
    ages = [...maps[0].keys()].filter(age => maps[1].has(age)).sort((a, b) => a - b);
  if (!ages.length)
    return '<p class="chart-empty">These plan horizons have no ages in common, so their asset paths cannot be aligned.</p>';
  const vals = ages.flatMap(age => maps.map(m => m.get(age))),
    targets = results.map(r => +r.target || 0),
    W = 760,
    H = 250,
    L = 60,
    R = 20,
    T = 18,
    B = 34,
    max = Math.max(...targets, ...vals, 1) * 1.08,
    x = i => L + (i / Math.max(1, ages.length - 1)) * (W - L - R),
    y = v => T + (1 - v / max) * (H - T - B);
  let out = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Available assets aligned by age for the current plan and scenario">`;
  for (let i = 0; i <= 4; i++) {
    const val = (max * i) / 4;
    out += `<line x1="${L}" x2="${W - R}" y1="${y(val)}" y2="${y(val)}" stroke="#e9ece7"/><text x="${L - 8}" y="${y(val) + 4}" text-anchor="end" fill="#79837e" font-size="10">${compact(val)}</text>`;
  }
  results.forEach((r, j) => {
    out += `<line x1="${L}" x2="${W - R}" y1="${y(targets[j])}" y2="${y(targets[j])}" stroke="${j ? '#be805d' : '#28675e'}" stroke-dasharray="4 5" opacity=".7"/>`;
    const pts = ages.map((age, i) => `${x(i)},${y(maps[j].get(age))}`).join(' ');
    out += `<polyline points="${pts}" fill="none" stroke="${j ? '#be805d' : '#28675e'}" stroke-width="2.5"/>`;
  });
  [0, Math.floor((ages.length - 1) / 2), ages.length - 1].forEach(
    i =>
      (out += `<text x="${x(i)}" y="${H - 9}" text-anchor="middle" fill="#79837e" font-size="10">Age ${ages[i]}</text>`),
  );
  return (
    out +
    '</svg><p class="small-note">Available asset paths aligned by age. Each plan target and FI age are shown separately.</p>'
  );
}
$('clear-comparison').onclick = () => ($('comparison-panel').hidden = true);
