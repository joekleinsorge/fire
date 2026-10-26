'use strict';
// What-if sliders: project an adjusted copy of the working plan and compare it with the
// current projection. The plan itself only changes when the user applies the result.

let whatIfFingerprint = null, whatIfTimer = null, whatIfRequest = 0, whatIfCandidate = null;

function whatIfSettings() {
  return {
    retire: Number($('whatif-retire').value),
    spend: Number($('whatif-spend').value) / 100,
    ret: Number($('whatif-return').value) / 100,
  };
}

function whatIfIsNeutral(s = whatIfSettings()) {
  return s.retire === Number(plan.retirement_age) && !s.spend && !s.ret;
}

function adjustedPlan({retire, spend, ret}) {
  const p = structuredClone(plan);
  moveRetirement(p, retire);
  for (const stream of p.streams || []) {
    if (stream.kind === 'expense') stream.amount = Math.round((+stream.amount || 0) * (1 + spend) * 100) / 100;
  }
  if (ret) {
    p.return_rate = (+p.return_rate || 0) + ret;
    for (const account of p.accounts || []) {
      if (['investment', 'retirement'].includes(account.type || 'investment')) {
        account.return_rate = (account.return_rate ?? plan.return_rate) + ret;
      }
    }
  }
  return p;
}

function showWhatIfLabels() {
  const s = whatIfSettings(), signed = (v, unit) => `${v > 0 ? '+' : ''}${v}${unit}`;
  $('whatif-retire-out').textContent = s.retire;
  $('whatif-spend-out').textContent = s.spend ? signed(Math.round(s.spend * 100), '%') : 'As planned';
  $('whatif-return-out').textContent = s.ret ? signed(+(s.ret * 100).toFixed(1), ' pts') : 'As planned';
}

// Called after the plan is re-rendered; resets the sliders only when the plan itself changed.
function syncWhatIf() {
  const fingerprint = JSON.stringify(plan);
  if (fingerprint === whatIfFingerprint) return;
  whatIfFingerprint = fingerprint;
  const retire = $('whatif-retire'), age = Number(plan.age), last = age + Number(plan.horizon);
  retire.min = String(age);
  retire.max = String(Math.max(Number(plan.retirement_age), Math.min(last, Math.max(age + 1, 80))));
  retire.value = String(plan.retirement_age);
  $('whatif-spend').value = '0';
  $('whatif-return').value = '0';
  whatIfCandidate = null;
  $('whatif-apply').disabled = true;
  $('whatif-result').innerHTML = '';
  showWhatIfLabels();
}

function compareCard(label, before, after, format, lowerIsBetter) {
  const changed = before !== after && before != null && after != null;
  const better = changed && (lowerIsBetter ? after < before : after > before);
  const tone = !changed ? '' : better ? 'better' : 'worse';
  return `<div class="${tone}">${label}<strong>${format(after)}</strong>${changed ? `<small>was ${format(before)}</small>` : '<small>no change</small>'}</div>`;
}

async function updateWhatIf() {
  showWhatIfLabels();
  const settings = whatIfSettings(), request = ++whatIfRequest, box = $('whatif-result');
  if (whatIfIsNeutral(settings)) {
    whatIfCandidate = null;
    $('whatif-apply').disabled = true;
    box.innerHTML = '';
    return;
  }
  const candidate = adjustedPlan(settings);
  try {
    const [base, next] = await Promise.all([projection || projectPlan(plan), projectPlan(candidate)]);
    if (request !== whatIfRequest) return;
    const age = v => v == null ? 'Not reached' : `Age ${v}`;
    const short = r => r.summary?.first_shortfall_age == null ? null : Math.floor(r.summary.first_shortfall_age);
    const shortLabel = v => v == null ? 'Never' : `Age ${v}`;
    box.innerHTML = [
      compareCard('FI at or after retirement', base.fi_age, next.fi_age, age, true),
      compareCard('Assets first reach target', base.earliest_fi_age, next.earliest_fi_age, age, true),
      compareCard('FI target', base.target, next.target, money, true),
      compareCard('Spendable at retirement', base.summary?.retirement_available_balance, next.summary?.retirement_available_balance, money, false),
      // A later shortfall (or none) is better; treat "never" as the best outcome.
      compareCard('Money first runs short', short(base) ?? Infinity, short(next) ?? Infinity, v => shortLabel(v === Infinity ? null : v), false),
    ].join('');
    whatIfCandidate = candidate;
    $('whatif-apply').disabled = false;
  } catch (err) {
    if (request === whatIfRequest) box.innerHTML = `<div class="worse">Could not test this change<strong>${esc(err.message)}</strong></div>`;
  }
}

for (const id of ['whatif-retire', 'whatif-spend', 'whatif-return']) {
  $(id).addEventListener('input', () => {
    showWhatIfLabels();
    clearTimeout(whatIfTimer);
    whatIfTimer = setTimeout(updateWhatIf, 250);
  });
}
$('whatif-reset').onclick = () => { whatIfFingerprint = null; syncWhatIf(); };
$('whatif-apply').onclick = () => {
  if (!whatIfCandidate) return;
  plan = whatIfCandidate;
  touch();
  fillAssumptions();
  renderTables();
  tell('What-if change applied to your working plan.');
};
syncWhatIf();
