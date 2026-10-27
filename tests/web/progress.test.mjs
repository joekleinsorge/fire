import test from 'node:test';
import assert from 'node:assert/strict';
import {load} from './harness.mjs';

const run = load('core.js', 'timing.js', 'progress.js');
const parse = text => JSON.parse(run(`JSON.stringify(parseObservationsCsv(${JSON.stringify(text)}))`));

test('CSV import reads headers, quoting, currency and US dates', () => {
  const {rows, problems} = parse('Date,Balance,Note\n2026-11-15,"$302,500",first\n3/15/2027,318000,"quoted, comma"\nbad,1,\n');
  assert.deepEqual(rows, [
    {date: '2026-11-15', balance: 302500, note: 'first'},
    {date: '2027-03-15', balance: 318000, note: 'quoted, comma'},
  ]);
  assert.deepEqual(problems, [4]);
});

test('CSV import without a recognizable header uses the first two columns', () => {
  const {rows, problems} = parse('2026-11-15,1000\n2026-12-15,1100\n');
  assert.equal(rows.length, 2);
  assert.deepEqual(problems, []);
});

test('impossible dates and negative balances are rejected', () => {
  assert.equal(run("parseObservationDate('2027-02-30')"), null);
  assert.equal(run("parseObservationDate('13/01/2027')"), null);
  assert.equal(parse('date,balance\n2027-01-01,-5\n').rows.length, 0);
});
