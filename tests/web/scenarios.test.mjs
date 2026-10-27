import test from 'node:test';
import assert from 'node:assert/strict';
import {load} from './harness.mjs';

const run = load('plan-inputs.js', 'core.js', 'scenarios.js',
  {source: 'var planningRuns = () => [], archivedScenarioIds = () => new Set(), simulationSettings = () => ({}), refreshRuns = async () => {};'},
  'scenario-tests.js');
const stream = (name, kind, amount, extra = {}) => ({id: name, name, kind, amount, every_months: 1, start_month: 1, end_month: 721, ...extra});
const base = {age: 35, horizon: 60, retirement_age: 62, return_rate: 0.05,
  accounts: [{id: 'a', type: 'investment', balance: 1000, return_rate: 0.06}, {id: 'c', type: 'cash', balance: 10, return_rate: 0.01}],
  streams: [stream('Pay', 'income', 7000, {end_month: 325}), stream('Pension', 'income', 1500, {start_month: 325}),
    stream('Partner pay', 'income', 3000, {end_month: 325, owner: 'partner'}), stream('Living', 'expense', 4000)],
  social_security: [{id: 's', claim_age_years: 67, claim_age_months: 0}]};
const json = expr => JSON.parse(run(`JSON.stringify(${expr})`));

test('retirement moves only your income that ends when retirement starts', () => {
  run(`plan = ${JSON.stringify(base)}`);
  assert.deepEqual(json('moveRetirementIncome(plan, 62, 58)'), ['Pay']);
  const streams = json('plan.streams');
  assert.equal(streams[0].end_month, 23 * 12 + 1);
  assert.equal(streams[1].start_month, 325);
  assert.equal(streams[2].end_month, 325);
  assert.deepEqual(json('moveRetirementIncome(plan, 58, 58)'), []);
});

test('scenario changes apply to a copy and are summarized', () => {
  run(`plan = ${JSON.stringify(base)}`);
  const {plan, summary} = json(`applyScenarioChanges(plan, {retire: 58, spend: -10, save: 500, ret: -1, ss: 70})`);
  assert.equal(json('plan.retirement_age'), 62);
  assert.equal(plan.retirement_age, 58);
  assert.equal(plan.streams[0].end_month, 277);
  assert.equal(plan.streams[3].amount, 3600);
  const extra = plan.streams.at(-1);
  assert.equal(extra.amount, 500);
  assert.equal(extra.end_month, 23 * 12 + 1);
  assert.ok(Math.abs(plan.accounts[0].return_rate - 0.05) < 1e-12);
  assert.equal(plan.accounts[1].return_rate, 0.01);
  assert.equal(plan.social_security[0].claim_age_years, 70);
  assert.equal(summary.length, 5);
  assert.match(summary[0], /Retire at 58 \(Pay ends then\)/);
  assert.deepEqual(json('applyScenarioChanges(plan, {retire: 62, spend: 0, save: 0, ret: 0, ss: null}).summary'), []);
});

test('verdicts combine the fixed, random and bad-start tests', () => {
  const verdict = r => run(`scenarioVerdict(${JSON.stringify(r)})`);
  const ok = {summary: {}}, rate = v => ({outcomes: {essential_spending_funded: {rate: v}}});
  assert.equal(verdict({fixed: ok, random: rate(0.95), stress: rate(1)}), 'pass');
  assert.equal(verdict({fixed: ok, random: rate(0.8), stress: rate(1)}), 'watch');
  assert.equal(verdict({fixed: ok, random: rate(0.95), stress: rate(0)}), 'fail');
  assert.equal(verdict({fixed: ok, random: rate(0.7), stress: rate(1)}), 'fail');
  assert.equal(verdict({fixed: {summary: {first_retirement_shortfall_age: 80}}, random: rate(0.99), stress: rate(1)}), 'fail');
  assert.equal(verdict({fixed: ok, random: rate(0.95)}), null);
});
