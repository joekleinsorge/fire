'use strict';
let purchaseEditId = null, purchaseMode = 'fork', purchaseBase = null, purchaseBaseFingerprint = null;

// Purchases store a month offset from the plan baseline; the dialog edits it as a calendar month.
// offsetToMonth, monthToOffset and monthLabel are shared from app.js.
const purchaseMonthLabel = (month, p = plan) => monthLabel(month, p);
function plural(n, word) {
  return `${n} ${word}${Math.abs(n) === 1 ? '' : 's'}`;
}

// ---- Purchases table ----

function purchaseSaleLabel(row, p = plan) {
  if (row.sell_account_id) {
    return `Sells ${esc((p.accounts || []).find(a => a.id === row.sell_account_id)?.name || 'an asset')}`;
  }
  if (row.sell_purchase_id) {
    return `Sells ${esc((p.future_purchases || []).find(r => r.id === row.sell_purchase_id)?.name || 'an earlier purchase')}`;
  }
  return '';
}

function renderPurchases() {
  const rows = plan.future_purchases || [];
  $('purchase-baseline').textContent = `Baseline ${plan.valuation_date || valuationDate()}. Month 1 is ${purchaseMonthLabel(1)}; all dates move with the baseline.`;
  $('purchase-table').innerHTML = rows.map(row => {
    const sub = text => `<small class="row-sub">${text}</small>`;
    const cost = [money(row.amount)];
    if (row.loan_amount) cost.push(sub(`${money(row.amount - row.loan_amount)} cash · ${money(row.loan_amount)} borrowed`));
    if (row.adds_asset) cost.push(sub('Kept as an asset'));
    const sale = purchaseSaleLabel(row);
    if (sale) cost.push(sub(sale));
    const upkeep = [money(row.annual_upkeep || 0)];
    if (row.annual_upkeep) upkeep.push(sub(row.upkeep_years ? `For ${plural(row.upkeep_years, 'year')}` : 'Ongoing'));
    return `<tr>
      <td><strong>${esc(row.name)}</strong></td>
      <td>${esc(purchaseMonthLabel(row.month))}${sub(`Month ${row.month}`)}</td>
      <td>${cost.join('')}</td>
      <td>${upkeep.join('')}</td>
      <td data-purchase-effect="${esc(row.id)}"><span class="muted-text">Calculating…</span></td>
      <td>${row.enabled === false ? 'Excluded' : 'Included'}</td>
      <td class="row-actions"><button class="link-button" data-edit-purchase="${esc(row.id)}">Edit</button><button class="link-button danger-text" data-remove-purchase="${esc(row.id)}">Remove</button></td>
    </tr>`;
  }).join('');
  $('purchase-empty').hidden = rows.length > 0;
  schedulePurchaseEffects();
}

// A copy of plan p with one purchase included or left out. Leaving a purchase out also
// drops later sales of the asset it created, which would otherwise have nothing to sell.
function planWithPurchase(p, id, include) {
  const copy = structuredClone(p);
  for (const row of copy.future_purchases || []) {
    if (row.id === id) row.enabled = include;
    else if (!include && row.sell_purchase_id === id) { delete row.sell_purchase_id; delete row.payoff_debt_id; }
  }
  return copy;
}

function effectSummary(without, withIt, included) {
  const parts = [], a = without.earliest_fi_age, b = withIt.earliest_fi_age;
  if (b == null && a != null) parts.push('<strong class="danger-text">FI no longer reached</strong>');
  else if (b != null && a == null) parts.push('<strong>FI now reached</strong>');
  else if (a === b) parts.push('FI age unchanged');
  else parts.push(`<strong>FI ${plural(Math.abs(b - a), 'year')} ${b > a ? 'later' : 'sooner'}</strong>`);
  const before = without.summary?.retirement_available_balance, after = withIt.summary?.retirement_available_balance;
  if (before != null && after != null && Math.round(after - before)) {
    parts.push(`<small class="row-sub">${after > before ? '+' : ''}${money(after - before)} at planned retirement</small>`);
  }
  const short = r => r.summary?.first_shortfall_age == null ? null : Math.floor(r.summary.first_shortfall_age);
  if (short(withIt) != null && short(without) == null) {
    parts.push(`<small class="row-sub danger-text">Money runs short at age ${short(withIt)}</small>`);
  }
  return (included ? '' : '<small class="row-sub">If included</small>') + parts.join('');
}

// Effects re-project the plan once, plus once per purchase with that purchase toggled.
// Results are cached for the current plan and stale runs are discarded.
let effectTimer = null, effectRequest = 0, effectCache = {fingerprint: null, cells: new Map()};
function schedulePurchaseEffects() {
  clearTimeout(effectTimer);
  effectTimer = setTimeout(() => updatePurchaseEffects().catch(() => {}), 400);
}
function setEffectCell(id, html) {
  const cell = document.querySelector(`[data-purchase-effect="${CSS.escape(id)}"]`);
  if (cell) cell.innerHTML = html;
}
async function updatePurchaseEffects() {
  if (!$('view-purchases').classList.contains('active')) return;
  const rows = plan.future_purchases || [], fingerprint = JSON.stringify(plan), request = ++effectRequest;
  if (effectCache.fingerprint !== fingerprint) effectCache = {fingerprint, cells: new Map()};
  const pending = rows.filter(row => {
    if (!effectCache.cells.has(row.id)) return true;
    setEffectCell(row.id, effectCache.cells.get(row.id));
    return false;
  });
  if (!pending.length) return;
  const snapshot = JSON.parse(fingerprint), current = projectPlan(snapshot);
  await Promise.all(pending.map(async row => {
    const included = row.enabled !== false;
    let html;
    try {
      const [base, other] = await Promise.all([current, projectPlan(planWithPurchase(snapshot, row.id, !included))]);
      html = included ? effectSummary(other, base, true) : effectSummary(base, other, false);
    } catch (err) {
      html = `<span class="muted-text" title="${esc(err.message)}">Unavailable</span>`;
    }
    if (request !== effectRequest || JSON.stringify(plan) !== fingerprint) return;
    effectCache.cells.set(row.id, html);
    setEffectCell(row.id, html);
  }));
}

// ---- Dialog ----

function purchaseSaleOptions(p, currentId) {
  const accounts = (p.accounts || []).filter(a => a.id)
    .map(a => `<option value="account:${esc(a.id)}">${esc(a.name)} · ${money(a.balance)}</option>`);
  const assets = (p.future_purchases || []).filter(r => r.id && r.id !== currentId && r.adds_asset && r.enabled !== false)
    .map(r => `<option value="purchase:${esc(r.id)}">${esc(r.name)} · bought ${esc(purchaseMonthLabel(r.month, p))}</option>`);
  return '<option value="">Nothing</option>'
    + (accounts.length ? `<optgroup label="Current assets">${accounts.join('')}</optgroup>` : '')
    + (assets.length ? `<optgroup label="Earlier purchases">${assets.join('')}</optgroup>` : '');
}

function openPurchase(mode, id) {
  purchaseMode = mode;
  purchaseEditId = id || null;
  purchaseBase = structuredClone(plan);
  purchaseBaseFingerprint = JSON.stringify(plan);
  const row = (plan.future_purchases || []).find(p => p.id === id), fork = mode === 'fork';
  $('purchase-dialog-title').textContent = fork ? 'Try a purchase scenario' : row ? 'Edit future purchase' : 'Add to current plan';

  $('purchase-name').value = row?.name || '';
  $('purchase-amount').value = row?.amount ?? '';
  $('purchase-month').value = offsetToMonth(row?.month ?? Math.min(24, plan.horizon * 12));
  $('purchase-month').min = offsetToMonth(1);
  $('purchase-month').max = offsetToMonth(plan.horizon * 12);
  $('purchase-upkeep').value = row?.annual_upkeep ?? 0;
  $('purchase-upkeep-years').value = row?.upkeep_years ?? '';
  $('purchase-enabled').checked = row?.enabled !== false;

  $('purchase-loan').value = row?.loan_amount ?? 0;
  $('purchase-loan-rate').value = ((row?.loan_rate ?? .06) * 100).toFixed(2);
  // Loans saved before inflation was asked for were modelled with none; new loans default to 2.5%.
  $('purchase-loan-inflation').value = ((row?.loan_amount ? row.loan_inflation ?? 0 : .025) * 100).toFixed(1);
  $('purchase-loan-years').value = Math.round((row?.loan_months ?? 360) / 12);
  $('purchase-sell').innerHTML = purchaseSaleOptions(plan, row?.id);
  $('purchase-sell').value = row?.sell_account_id ? `account:${row.sell_account_id}` : row?.sell_purchase_id ? `purchase:${row.sell_purchase_id}` : '';
  $('purchase-sell-cost').value = ((row?.sell_cost_rate ?? .06) * 100).toFixed(1);
  $('purchase-payoff').innerHTML = '<option value="">None</option>' + (plan.debts || []).filter(d => d.id)
    .map(d => `<option value="${esc(d.id)}">${esc(d.name)} · ${money(d.balance)}</option>`).join('');
  $('purchase-payoff').value = row?.payoff_debt_id || '';
  $('purchase-asset').checked = !!row?.adds_asset;
  $('purchase-asset-return').value = ((row?.asset_return ?? 0) * 100).toFixed(1);

  $('purchase-scenario-label').hidden = !fork;
  $('purchase-scenario-name').required = fork;
  $('purchase-scenario-name').value = '';
  $('purchase-submit').textContent = fork ? 'Save scenario & compare' : 'Apply & recalculate';
  $('purchase-mode-note').textContent = fork
    ? 'Save a full independent plan and its starting baseline. Your current plan stays as it is. Signed-in scenarios persist with the saved plan; signed-out scenarios last only in this tab.'
    : 'Apply this expense to your working plan. The forecast will be recalculated before the change is accepted.';
  $('purchase-advanced').open = !!(row?.loan_amount || row?.sell_account_id || row?.sell_purchase_id || row?.adds_asset);

  updatePurchaseTiming();
  previewBase = null;
  previewRequest++;
  $('purchase-dialog').showModal();
  updatePurchasePreview();
}

function updatePurchaseTiming() {
  const p = purchaseBase || plan, offset = monthToOffset($('purchase-month').value, p);
  $('purchase-timing').textContent = Number.isFinite(offset) && offset >= 1
    ? `${plural(offset, 'month')} after your ${p.valuation_date} baseline`
    : `Choose a month after your ${p.valuation_date} baseline`;
}
$('purchase-month').oninput = updatePurchaseTiming;
$('add-purchase').onclick = () => openPurchase('current');
$('fork-purchase').onclick = () => openPurchase('fork');
$('purchase-close').onclick = $('purchase-cancel').onclick = () => $('purchase-dialog').close();

function readPurchaseRow(forPreview = false) {
  const row = {
    id: purchaseEditId || uid(),
    name: $('purchase-name').value.trim(),
    amount: Number($('purchase-amount').value),
    month: monthToOffset($('purchase-month').value, purchaseBase),
    annual_upkeep: Number($('purchase-upkeep').value),
    enabled: $('purchase-enabled').checked,
  };
  const years = $('purchase-upkeep-years').value.trim(), loan = Number($('purchase-loan').value || 0);
  if (years) row.upkeep_years = Number(years);
  if (loan) {
    row.loan_amount = loan;
    row.loan_rate = Number($('purchase-loan-rate').value) / 100;
    row.loan_inflation = Number($('purchase-loan-inflation').value) / 100;
    row.loan_months = Number($('purchase-loan-years').value) * 12;
  }
  const sale = $('purchase-sell').value, split = sale.indexOf(':');
  if (sale) {
    row[sale.slice(0, split) === 'purchase' ? 'sell_purchase_id' : 'sell_account_id'] = sale.slice(split + 1);
    row.sell_cost_rate = Number($('purchase-sell-cost').value) / 100;
  }
  if ($('purchase-payoff').value) {
    if (!sale) throw Error('Choose an asset to sell before paying off a debt from the sale.');
    row.payoff_debt_id = $('purchase-payoff').value;
  }
  if ($('purchase-asset').checked) {
    row.adds_asset = true;
    row.asset_return = Number($('purchase-asset-return').value) / 100;
  }
  if (!row.name) {
    if (!forPreview) throw Error('Enter a purchase name.');
    row.name = 'Preview';
  }
  if (!Number.isInteger(row.month) || row.month < 1) throw Error('Choose a purchase month after the plan baseline.');
  if (loan > row.amount) throw Error('The amount borrowed cannot exceed the purchase cost.');
  return row;
}

function purchaseCandidate(row) {
  const candidate = structuredClone(purchaseBase), rows = candidate.future_purchases || [];
  const index = rows.findIndex(p => p.id === row.id);
  if (index < 0) rows.push(row); else rows[index] = row;
  candidate.future_purchases = rows;
  return candidate;
}

// ---- Live preview: re-project the candidate as the dialog changes; stale responses are dropped ----

let previewTimer = null, previewRequest = 0, previewBase = null;
function previewAge(value) {
  return value == null ? 'not reached' : `age ${value}`;
}
function previewDelta(before, after, unit) {
  if (before == null || after == null || before === after) return '';
  const d = after - before;
  return ` (${d > 0 ? '+' : ''}${unit === 'years' ? plural(d, 'year') : money(d)})`;
}
async function updatePurchasePreview() {
  const box = $('purchase-preview'), request = ++previewRequest;
  const idle = text => { box.className = 'purchase-preview muted'; box.textContent = text; };
  let row;
  try {
    row = readPurchaseRow(true);
  } catch (err) {
    idle($('purchase-amount').value ? err.message : 'Enter a cost and month to preview the effect on your plan.');
    return;
  }
  if (!$('purchase-amount').value) { idle('Enter a cost and month to preview the effect on your plan.'); return; }
  idle('Updating preview…');
  try {
    const [base, next] = await Promise.all([previewBase || (previewBase = projectPlan(purchaseBase)), projectPlan(purchaseCandidate(row))]);
    if (request !== previewRequest) return;
    const short = r => r.summary?.first_shortfall_age == null ? null : Math.floor(r.summary.first_shortfall_age);
    const lines = [
      next.earliest_fi_age == null
        ? `Assets <strong>never reach</strong> your FI target${base.earliest_fi_age != null ? ` (now ${previewAge(base.earliest_fi_age)})` : ''}`
        : `Assets reach your FI target at <strong>${previewAge(next.earliest_fi_age)}</strong>${previewDelta(base.earliest_fi_age, next.earliest_fi_age, 'years')}`,
      `FI target <strong>${money(next.target)}</strong>${previewDelta(base.target, next.target)}`,
      `Spendable at planned retirement <strong>${money(next.summary?.retirement_available_balance)}</strong>${previewDelta(base.summary?.retirement_available_balance, next.summary?.retirement_available_balance)}`,
    ];
    if (next.retirement_obligations) lines.push(`<small>Target includes ${money(next.retirement_obligations)} for loan payments, purchases and other costs that end after you retire</small>`);
    if (short(next) != null) lines.push(`<span class="danger-text">Money first runs short at age ${short(next)}</span>`);
    box.className = 'purchase-preview' + (short(next) != null ? ' warn' : '');
    box.innerHTML = `<span class="eyebrow">PREVIEW · NOT SAVED</span>${lines.map(l => `<span>${l}</span>`).join('')}`;
  } catch (err) {
    if (request === previewRequest) idle(err.message);
  }
}
$('purchase-form').addEventListener('input', () => { clearTimeout(previewTimer); previewTimer = setTimeout(updatePurchasePreview, 350); });
$('purchase-form').addEventListener('change', () => { clearTimeout(previewTimer); previewTimer = setTimeout(updatePurchasePreview, 150); });

// ---- Scenario comparison ----

function purchaseMetrics(p, r) {
  const short = r.summary?.first_shortfall_age;
  return [r.earliest_fi_age, r.fi_age ?? (r.years_to_target == null ? null : Number(p.age) + r.years_to_target),
    short == null ? null : Math.floor(short), r.target, r.summary?.retirement_available_balance,
    r.summary?.ending_assets, r.summary?.ending_net_worth, r.summary?.total_unfunded];
}
function purchaseComparisonHTML(left, right, results, leftName, rightName) {
  const currency = p => p.currency || 'USD';
  const format = (n, p) => n == null ? '—' : new Intl.NumberFormat(undefined, {style: 'currency', currency: currency(p), maximumFractionDigits: 0}).format(n);
  const values = [purchaseMetrics(left, results[0]), purchaseMetrics(right, results[1])];
  const labels = ['Age assets first reach FI target', 'FI age (at or after planned retirement)', 'Age money first runs short', 'FI target',
    'Spendable assets at planned retirement', 'End-of-plan assets', 'End-of-plan net worth', 'Total unfunded spending'];
  const compatible = currency(left) === currency(right) && results[0].metadata?.price_basis === results[1].metadata?.price_basis;
  const body = labels.map((label, i) => {
    const a = values[0][i], b = values[1][i], age = i < 3;
    const cell = (v, p) => age ? (v == null ? (i === 2 ? 'Never' : 'Not reached') : String(v)) : format(v, p);
    const delta = a == null || b == null || !compatible ? '—'
      : age ? (b === a ? 'No change' : `${b - a > 0 ? '+' : ''}${plural(b - a, 'year')}`)
      : `${b - a > 0 ? '+' : ''}${format(b - a, right)}`;
    return `<tr><th>${label}</th><td>${cell(a, left)}</td><td>${cell(b, right)}</td><td>${delta}</td></tr>`;
  }).join('');
  return `<div class="table-scroll"><table class="purchase-comparison"><thead><tr><th>Outcome</th><th>${esc(leftName)}</th><th>${esc(rightName)}</th><th>Change</th></tr></thead><tbody>${body}</tbody></table></div>`
    + `<p class="small-note">Planned retirement ages: ${left.age == null ? '—' : left.retirement_age} / ${right.retirement_age}. A one-time purchase reduces assets; ongoing upkeep, and loan payments or upkeep that continue after retirement, can also increase your FI target. “Age assets first reach FI target” is the first modeled year-end with spendable assets at the target, even before your planned retirement. FI age is the first such year-end at or after planned retirement; neither is an optimized retirement date.</p>`;
}
async function comparePurchaseScenario(s, precomputed) {
  const data = s.data || s, left = structuredClone(data.baseline_plan || plan), right = structuredClone(data.plan);
  const results = precomputed || await Promise.all([projectPlan(left), projectPlan(right)]);
  $('comparison-panel').hidden = false;
  $('comparison-chart').innerHTML = chartForCompare(results);
  $('comparison-cards').innerHTML = purchaseComparisonHTML(left, right, results, data.baseline_plan ? 'Saved starting baseline' : left.name || 'Current plan', scenarioName(s));
  $('comparison-cards').classList.add('purchase-comparison-wrap');
  $('comparison-panel').scrollIntoView({behavior: 'smooth'});
}

// ---- Applying changes ----

async function acceptPurchasePlan(candidate, startingFingerprint) {
  const result = await projectPlan(candidate);
  if (JSON.stringify(plan) !== startingFingerprint) throw Error('Your working plan changed during calculation. Try again using the updated plan.');
  plan = candidate;
  touch();
  projection = result;
  simulation = null;
  renderTables();
  showSaveState();
}

$('purchase-form').onsubmit = async e => {
  e.preventDefault();
  if (!$('purchase-form').reportValidity()) return;
  const button = $('purchase-submit');
  button.disabled = true;
  try {
    const candidate = purchaseCandidate(readPurchaseRow());
    if (purchaseMode === 'fork') {
      const name = $('purchase-scenario-name').value.trim();
      if (!name) throw Error('Enter a scenario name.');
      candidate.name = name;
      const results = await Promise.all([projectPlan(purchaseBase), projectPlan(candidate)]);
      if (JSON.stringify(plan) !== purchaseBaseFingerprint) throw Error('Your working plan changed during calculation. Reopen the purchase dialog to use the updated baseline.');
      const data = {name, plan: candidate, baseline_plan: structuredClone(purchaseBase)};
      if (user) {
        if (!saved && !(await savePlan())) throw Error('Save the baseline plan to create a persistent scenario.');
        await api(`/api/plans/${saved.id}/scenarios`, data);
        await refreshScenarios();
      } else {
        scenarios.push({id: uid(), ...data});
        renderScenarios();
      }
      $('purchase-dialog').close();
      go('scenarios');
      await comparePurchaseScenario(data, results);
      tell(user ? 'Purchase scenario saved with its starting baseline.' : 'Purchase scenario saved for this tab only. Sign in to save persistently.');
    } else {
      await acceptPurchasePlan(candidate, purchaseBaseFingerprint);
      $('purchase-dialog').close();
      tell('Future purchase applied and every forecast recalculated.');
    }
  } catch (err) {
    tell(err.message, true);
  } finally {
    button.disabled = false;
  }
};

function tellWithUndo(message, undo) {
  tell(message);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'link-button';
  button.textContent = 'Undo';
  button.onclick = () => { button.disabled = true; undo(); };
  $('notice').append(' ', button);
}

async function removePurchase(id) {
  const previous = structuredClone(plan), fingerprint = JSON.stringify(plan);
  const candidate = planWithPurchase(plan, id, false);
  const sellers = candidate.future_purchases.filter(r => previous.future_purchases.find(p => p.id === r.id)?.sell_purchase_id === id);
  candidate.future_purchases = candidate.future_purchases.filter(r => r.id !== id);
  await acceptPurchasePlan(candidate, fingerprint);
  const removed = JSON.stringify(plan);
  const note = sellers.length ? ` ${sellers.map(r => `“${r.name}”`).join(', ')} no longer sells it.` : '';
  tellWithUndo(`Purchase removed and forecast recalculated.${note}`, async () => {
    try {
      if (JSON.stringify(plan) !== removed) throw Error('Your plan changed after the removal, so it can no longer be undone.');
      await acceptPurchasePlan(previous, removed);
      tell('Purchase restored.');
    } catch (err) {
      tell(err.message, true);
    }
  });
}

document.addEventListener('click', e => {
  const edit = e.target.closest('[data-edit-purchase]'), remove = e.target.closest('[data-remove-purchase]');
  if (edit) openPurchase('current', edit.dataset.editPurchase);
  if (remove) removePurchase(remove.dataset.removePurchase).catch(err => tell(err.message, true));
});
window.addEventListener('hashchange', () => { if (location.hash === '#purchases') schedulePurchaseEffects(); });
renderPurchases();
