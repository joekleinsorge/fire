import test from 'node:test';
import assert from 'node:assert/strict';
import {load} from './harness.mjs';

const run = load('core.js', 'timing.js', 'checkup.js');
const setPlan = plan => run(`plan = ${JSON.stringify(plan)}`);
const stream = (kind, amount, extra = {}) => ({id: `${kind}${amount}`, kind, amount, every_months: 1, start_month: 1, end_month: 721, enabled: true, ...extra});
const base = {valuation_date: '2026-09-30', age: 35, horizon: 60, retirement_age: 62, withdrawal_rate: 0.04, currency: 'USD',
  accounts: [{id: 'c', type: 'cash', balance: 6000}, {id: 'b', type: 'investment', balance: 100000, fee_rate: 0.001, tax_treatment: 'taxable'}],
  streams: [stream('income', 6000), stream('expense', 3000, {essential: true}), stream('expense', 500)],
  debts: [], social_security: [{id: 's', pia_at_fra: 2000, claim_age_years: 67, claim_age_months: 0}]};
const checks = () => JSON.parse(run('JSON.stringify(planChecks(plan, null))'));
const find = (list, title) => list.find(c => c.title.startsWith(title));

test('flags a thin emergency fund and credits a strong savings rate', () => {
  setPlan(base);
  const list = checks();
  assert.equal(find(list, 'Build an emergency fund').tone, 'act');
  // (6000 - 3500) / 6000 is above 20%.
  assert.equal(find(list, 'Saving 41.7%').tone, 'good');
  assert.equal(find(list, 'Low investment fees').tone, 'good');
});

test('debt payments count toward essential costs and high rates need action', () => {
  setPlan({...base, accounts: [{id: 'c', type: 'cash', balance: 20000}],
    debts: [{id: 'd', name: 'Card', balance: 5000, annual_rate: 0.24, months: 24, payment: 500}]});
  const list = checks();
  // 20000 / (3000 + 500) is under six months but over three.
  assert.match(find(list, 'Emergency fund in place').detail, /5\.7 months/);
  assert.equal(find(list, 'Pay down high-interest debt').tone, 'act');
});

test('spending above income and missing Social Security are reported', () => {
  setPlan({...base, streams: [stream('income', 3000), stream('expense', 3500, {essential: true})], social_security: []});
  const list = checks();
  assert.equal(find(list, 'Spending exceeds').tone, 'act');
  assert.ok(find(list, 'No Social Security'));
});

test('candidates edit copies and leave the working plan alone', () => {
  setPlan({...base, accounts: [{id: 'c', type: 'cash', balance: 80000}, ...base.accounts.slice(1),
    {id: 'r', type: 'retirement', balance: 50000, fee_rate: 0.01, tax_treatment: 'pre_tax'}],
    debts: [{id: 'd', name: 'Car', balance: 10000, annual_rate: 0.08, months: 48}]});
  const before = run('JSON.stringify(plan)');
  const moves = JSON.parse(run('JSON.stringify(checkupCandidates())'));
  assert.equal(run('JSON.stringify(plan)'), before);
  const byId = Object.fromEntries(moves.map(m => [m.id, m.plan]));
  assert.deepEqual(Object.keys(byId).sort(), ['cut-fees', 'invest-cash', 'pay-debt', 'retire-later', 'save-more', 'ss-s', 'tax-order', 'trim-flexible'].sort());
  assert.equal(byId['save-more'].streams.at(-1).end_month, 27 * 12 + 1);
  assert.equal(byId['trim-flexible'].streams[2].amount, 400);
  assert.equal(byId['trim-flexible'].streams[1].amount, 3000);
  assert.equal(byId['retire-later'].retirement_age, 63);
  assert.equal(byId['cut-fees'].accounts[2].fee_rate, 0.0005);
  assert.ok(byId['pay-debt'].debts[0].extra_payment > 0);
  // Six months of essential costs (3000) and the car payment (244.13) stay in cash, rounded;
  // the rest moves to the taxable account.
  assert.equal(byId['invest-cash'].accounts[0].balance, 19500);
  assert.equal(byId['invest-cash'].accounts[1].balance, 160500);
  assert.equal(byId['tax-order'].withdrawal_order, 'tax_efficient');
  assert.equal(byId['ss-s'].social_security[0].claim_age_years, 70);
});

test('moves are ranked by fixing a shortfall, then years gained, then cushion', () => {
  setPlan(base);
  const r = (fi, bal, shortfall = null) => ({earliest_fi_age: fi, target: 1000, first_shortfall_month: shortfall, summary: {retirement_available_balance: bal}});
  const ranked = JSON.parse(run(`JSON.stringify(rankMoves(${JSON.stringify(r(50, 900, 400))}, ${JSON.stringify([
    {id: 'a', result: r(48, 950, 400)},
    {id: 'b', result: r(50, 1500, null)},
    {id: 'c', result: r(49, 2000, 400)},
    {id: 'none', result: r(50, 900, 400)},
    {id: 'worse', result: r(52, 800, 400)},
  ])}))`));
  assert.deepEqual(ranked.map(m => m.id), ['b', 'a', 'c']);
  assert.equal(ranked[1].gained, 2);
  // A plan that newly reaches the target gains the years to the horizon end.
  assert.equal(run(`yearsGained({earliest_fi_age: null}, {earliest_fi_age: 60})`), 35);
});
