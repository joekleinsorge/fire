import test from 'node:test';
import assert from 'node:assert/strict';
import {load} from './harness.mjs';

const run = load('core.js', 'timing.js');
const setPlan = plan => run(`plan = ${JSON.stringify(plan)}`);
const base = {valuation_date: '2026-09-30', age: 35, horizon: 60, retirement_age: 62, streams: []};

test('month 1 is the calendar month after the valuation month', () => {
  setPlan(base);
  assert.equal(run("offsetToMonth(1)"), '2026-10');
  assert.equal(run("offsetToMonth(3)"), '2026-12');
  assert.equal(run("monthToOffset('2026-10')"), 1);
  for (const m of [1, 2, 15, 120, 719]) assert.equal(run(`monthToOffset(offsetToMonth(${m}))`), m);
});

test('stream offsets follow age, calendar month and plan end', () => {
  setPlan(base);
  const offsets = row => run(`streamOffsets(${JSON.stringify(row)})`);
  assert.deepEqual({...offsets({start_basis: 'plan', end_basis: 'age', end_age: 62})}, {start_month: 1, end_month: 325});
  assert.deepEqual({...offsets({start_basis: 'age', start_age: 62, end_basis: 'plan'})}, {start_month: 325, end_month: 721});
  // A last payment in December 2031 ends (exclusively) the month after.
  assert.deepEqual({...offsets({start_basis: 'date', start_date: '2026-12', end_basis: 'date', end_date: '2031-12'})}, {start_month: 3, end_month: 64});
  // Ages already passed start at month 1, and an end before the start never runs.
  assert.deepEqual({...offsets({start_basis: 'age', start_age: 30, end_basis: 'age', end_age: 20})}, {start_month: 1, end_month: 1});
});

test('partner-owned timing uses the partner age', () => {
  setPlan({...base, partner: {name: 'Sam', age: 33, retirement_age: 60}});
  const row = {owner: 'partner', start_basis: 'plan', end_basis: 'age', end_age: 60};
  assert.equal(run(`streamOffsets(${JSON.stringify(row)}).end_month`), (60 - 33) * 12 + 1);
  assert.equal(run(`personName('partner')`), 'Sam');
});

test('resync moves plan-end streams with the horizon and keeps calendar months fixed', () => {
  setPlan({...base, streams: [
    {kind: 'expense', start_basis: 'plan', end_basis: 'plan', start_month: 1, end_month: 721},
    {kind: 'expense', start_basis: 'date', start_date: '2027-01', end_basis: 'plan', start_month: 4, end_month: 721},
  ]});
  run("plan.horizon = 65; plan.valuation_date = '2026-12-31'; resyncStreams()");
  assert.equal(run('plan.streams[0].end_month'), 781);
  assert.equal(run('plan.streams[1].start_month'), 1);
});

test('moving retirement moves only income that ended at the old retirement age', () => {
  setPlan({...base, streams: [
    {kind: 'income', end_basis: 'age', end_age: 62, start_month: 1, end_month: 325},
    {kind: 'income', end_basis: 'age', end_age: 65, start_month: 1, end_month: 361},
    {kind: 'expense', end_basis: 'age', end_age: 62, start_month: 1, end_month: 325},
  ]});
  run('moveRetirement(plan, 58)');
  assert.deepEqual(JSON.parse(run('JSON.stringify(plan.streams.map(s => s.end_age))')), [58, 65, 62]);
  assert.equal(run('plan.streams[0].end_month'), (58 - 35) * 12 + 1);
  assert.equal(run('plan.retirement_age'), 58);
});
