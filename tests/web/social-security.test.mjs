import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {load} from './harness.mjs';

const run = load('core.js', 'timing.js', 'social-security.js');

test('the live preview matches the engine for every claiming month', () => {
  const births = ['1955-06-15', '1958-01-01', '1960-01-02', '1960-07-01', '1975-11-20', '1990-03-01'];
  const claims = Array.from({length: 97}, (_, i) => 744 + i);
  // The engine computes the same factors; compare across birth dates and claim ages.
  const script = `
import json, sys
from datetime import date, timedelta
from fireplanner.social_security import full_retirement_age_months, benefit_factor, _months
out = {}
for birth in json.loads(sys.argv[1]):
    attained = date.fromisoformat(birth) - timedelta(days=1)
    late = attained.day != 1
    out[birth] = [benefit_factor(*_months(attained.year, c, late)) for c in json.loads(sys.argv[2])]
print(json.dumps(out))`;
  const engine = JSON.parse(execFileSync('python3', ['-c', script, JSON.stringify(births), JSON.stringify(claims)],
    {cwd: new URL('../../', import.meta.url)}));
  for (const birth of births) {
    const preview = JSON.parse(run(`JSON.stringify(${JSON.stringify(claims)}.map(c => ssOption(${JSON.stringify(birth)}, c).factor))`));
    preview.forEach((factor, i) => assert.ok(Math.abs(factor - engine[birth][i]) < 1e-12, `${birth} at ${claims[i]} months`));
  }
});

test('SSA published percentages for full retirement age 67', () => {
  // Born January 2, 1960: full retirement age 67, attains each age on the first of the month.
  const factor = months => run(`ssOption('1960-01-02', ${months}).factor`);
  assert.ok(Math.abs(factor(62 * 12) - .70) < 1e-12);
  assert.equal(factor(67 * 12), 1);
  assert.ok(Math.abs(factor(70 * 12) - 1.24) < 1e-12);
});
