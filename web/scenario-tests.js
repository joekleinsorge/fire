'use strict';
// Test every scenario: the saved plan and each current scenario get the same three tests
// (fixed projection, random markets, bad start to retirement). Runs are logged with one
// batch id, so the table always compares results made with identical settings, and it can
// be rebuilt from run history after a reload.

let scenarioTestBatch = null, scenarioTestRunning = false;

const SCENARIO_TESTS = [
  ['fixed', 'project', () => ({})],
  ['random', 'simulate', () => ({ mode: 'parametric', trials: +$('trials').value, seed: +$('seed').value, volatility: +$('volatility').value / 100 })],
  ['stress', 'simulate', () => ({ mode: 'sequence', shock_returns: [-0.15, -0.13, -0.24] })],
];

function testableScenarios() {
  const archived = archivedScenarioIds();
  return scenarios.filter(s => s.data && !archived.has(s.id) && s.data.metadata?.status !== 'needs_inputs');
}

// Pass/watch/fail from the three tests. Thresholds are rules of thumb, shown in the panel.
function scenarioVerdict(r) {
  if (!r.fixed || !r.random || !r.stress) return null;
  const fixedShort = r.fixed.summary?.first_retirement_shortfall_age ?? r.fixed.summary?.first_shortfall_age,
    random = r.random.outcomes?.essential_spending_funded?.rate,
    stress = r.stress.outcomes?.essential_spending_funded?.rate === 1;
  if (fixedShort != null || random == null || random < 0.75 || !stress) return 'fail';
  return random >= 0.9 ? 'pass' : 'watch';
}

function latestTestBatch() {
  return planningRuns().find(r => r.metadata?.scenario_test && (!saved || r.plan_id === saved.id))?.metadata.scenario_test;
}

function scenarioTestRows(batch) {
  const runs = planningRuns().filter(r => r.metadata?.scenario_test === batch && r.status === 'completed');
  const targets = [{ key: null, name: 'Saved plan', retire: saved?.plan?.retirement_age, note: 'Baseline' },
    ...testableScenarios().map(s => ({ key: s.id, name: scenarioName(s), retire: scenarioPlan(s).retirement_age, note: s.data.metadata?.rationale || '' }))];
  return targets.map(t => {
    const row = { ...t };
    for (const [test] of SCENARIO_TESTS)
      row[test] = runs.find(r => (r.scenario_id ?? null) === t.key && r.metadata.test === test)?.result;
    row.verdict = scenarioVerdict(row);
    return row;
  });
}

function renderScenarioTests() {
  let panel = $('scenario-tests');
  if (!panel) {
    panel = document.createElement('article');
    panel.id = 'scenario-tests';
    panel.className = 'panel scenario-tests';
    $('view-scenarios').querySelector('.page-head').after(panel);
  }
  const batch = scenarioTestBatch || latestTestBatch(),
    rows = batch ? scenarioTestRows(batch) : [],
    tested = rows.some(r => r.fixed || r.random || r.stress),
    label = { pass: 'Holds up', watch: 'Review', fail: 'At risk' };
  const settings = `${+$('trials').value} random paths at ${+$('volatility').value}% volatility, seed ${+$('seed').value}`;
  panel.innerHTML = `<div class="panel-head"><div><p class="eyebrow">STRESS-TEST EVERY PLAN</p><h2>Test your plan and every scenario</h2><p class="small-note">Runs the same three tests on your saved plan and each scenario: the fixed projection, random markets (${esc(settings)}, set under Retirement tests) and a bad start to retirement (−15%, −13%, −24% real in the first three retirement years). Every run is logged.</p></div><button class="button primary" id="run-scenario-tests" ${scenarioTestRunning || !saved ? 'disabled' : ''}>${scenarioTestRunning ? 'Testing…' : 'Test all'}</button></div>` +
    (!saved
      ? '<p class="small-note">Sign in and save your plan to test it and its scenarios.</p>'
      : !tested && !scenarioTestRunning
        ? '<p class="small-note">No tests yet. Create scenarios, then test them all together.</p>'
        : `<div class="table-scroll"><table class="scenario-test-table"><thead><tr><th>Plan</th><th>Fixed projection</th><th>Random markets</th><th>Bad start</th><th>Result</th></tr></thead><tbody>${rows
            .map(r => {
              const fixed = r.fixed, random = r.random?.outcomes?.essential_spending_funded, stress = r.stress;
              const stressHeld = stress?.outcomes?.essential_spending_funded?.rate === 1;
              return `<tr><td><strong>${esc(r.name)}</strong><small class="row-sub">Retire at ${esc(r.retire ?? '—')}${r.note ? ` · ${esc(r.note)}` : ''}</small></td><td>${fixed ? `${money(fixed.summary?.retirement_available_balance)} at retirement<small class="row-sub">${fixed.earliest_fi_age == null ? 'Target not reached' : `Target reached at ${fixed.earliest_fi_age}`}</small>` : '…'}</td><td>${random ? `${pct(random.rate)} fund essentials<small class="row-sub">Weak case ends with ${money(r.random.ending_assets?.p10)}</small>` : '…'}</td><td>${stress ? (stressHeld ? 'Holds' : 'Runs short') + `<small class="row-sub">Ends with ${money(stress.ending_assets?.median)}</small>` : '…'}</td><td>${r.verdict ? `<span class="verdict ${r.verdict}">${label[r.verdict]}</span>` : '…'}</td></tr>`;
            })
            .join('')}</tbody></table></div><p class="small-note">Weak case is the 10th percentile. Holds up: essentials funded in at least 90% of random paths and through the bad start, with no shortfall in the fixed projection. At risk: below 75%, short in the bad start, or short in the fixed projection. These are rules of thumb on your own assumptions, not a guarantee.</p>`);
  $('run-scenario-tests').onclick = testEveryScenario;
}

async function waitForJob(id) {
  for (;;) {
    const { job } = await api(`/api/jobs/${encodeURIComponent(id)}?summary=true`);
    if (!['queued', 'running'].includes(job.status)) return job;
    await new Promise(r => setTimeout(r, 700));
  }
}

async function testEveryScenario() {
  if (!saved) return openAuth();
  if (workingDirty && !confirm('Tests use your saved plan and saved scenarios, not unsaved edits. Test anyway?')) return;
  scenarioTestRunning = true;
  scenarioTestBatch = uid();
  renderScenarioTests();
  try {
    // One target at a time keeps the shared work queue well under its limit.
    for (const target of [null, ...testableScenarios().map(s => s.id)]) {
      const jobs = [];
      for (const [test, kind, settings] of SCENARIO_TESTS) {
        const body = { kind, settings: settings(), metadata: { origin: 'planner UI', scenario_test: scenarioTestBatch, test } };
        const url = target ? `/api/plans/${saved.id}/scenarios/${encodeURIComponent(target)}/run` : `/api/plans/${saved.id}/run`;
        if (!target) body.version = saved.version;
        jobs.push((await api(url, body)).job.id);
      }
      await Promise.all(jobs.map(waitForJob));
      await refreshRuns();
    }
    tell('Every plan tested with the same markets; results are logged in Calculation history.');
  } catch (e) {
    tell(e.message, true);
  } finally {
    scenarioTestRunning = false;
    renderScenarioTests();
  }
}

const testsRenderScenarios = renderScenarios;
renderScenarios = function () {
  testsRenderScenarios();
  renderScenarioTests();
};
renderScenarioTests();
