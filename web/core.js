'use strict';
// Shared state, helpers, API access, notices, drafts, save state and navigation.
const $ = id => document.getElementById(id),
  esc = s =>
    String(s ?? '').replace(
      /[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
const money = n =>
    n === null || n === undefined || !Number.isFinite(Number(n))
      ? '—'
      : new Intl.NumberFormat(undefined, {
          style: 'currency',
          currency: plan.currency || 'USD',
          maximumFractionDigits: 0,
        }).format(Number(n)),
  pct = n => `${(Number(n || 0) * 100).toFixed(1)}%`;
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `r${Date.now()}${Math.random().toString(16).slice(2)}`);
let plan = samplePlan(),
  projection = null,
  simulation = null,
  user = null,
  saved = null,
  scenarios = [],
  observations = [],
  revisions = [],
  editState = null,
  noticeTimer = null,
  dirty = false,
  autoTimer = null;
const quickState = {
  age: 35,
  assets: 300000,
  income: 92000,
  expenses: 61000,
  return_rate: 0.05,
  withdrawal_rate: 0.04,
  horizon: 60,
};
let quickResult = null,
  quickRequest = 0;
function valuationDate() {
  const n = new Date(),
    d = new Date(n.getFullYear(), n.getMonth(), 0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function samplePlan() {
  return {
    name: 'My financial plan',
    valuation_date: valuationDate(),
    age: 35,
    horizon: 60,
    retirement_age: 62,
    return_rate: 0.05,
    withdrawal_rate: 0.04,
    inflation_rate: 0.025,
    currency: 'USD',
    accounts: [
      {
        id: uid(),
        name: 'Workplace 401(k)',
        type: 'retirement',
        balance: 185000,
        return_rate: 0.05,
        fee_rate: 0.004,
        tax_treatment: 'pre_tax',
        withdrawal_tax_rate: 0.22,
        available: true,
      },
      {
        id: uid(),
        name: 'Brokerage account',
        type: 'investment',
        balance: 90000,
        return_rate: 0.052,
        fee_rate: 0.002,
        tax_treatment: 'taxable',
        withdrawal_tax_rate: 0.1,
        available: true,
      },
      {
        id: uid(),
        name: 'Cash reserve',
        type: 'cash',
        balance: 25000,
        return_rate: 0.01,
        fee_rate: 0,
        available: true,
      },
      { id: uid(), name: 'Home', type: 'property', balance: 420000, return_rate: 0.01, fee_rate: 0, available: false },
    ],
    streams: [
      {
        id: uid(),
        name: 'Take-home pay',
        kind: 'income',
        amount: 7666.67,
        every_months: 1,
        start_month: 1,
        end_month: 325,
        start_basis: 'plan',
        end_basis: 'age',
        end_age: 62,
        enabled: true,
        growth_rate: 0,
        essential: true,
      },
      {
        id: uid(),
        name: 'Core living costs',
        kind: 'expense',
        amount: 4250,
        every_months: 1,
        start_month: 1,
        end_month: 721,
        start_basis: 'plan',
        end_basis: 'plan',
        enabled: true,
        growth_rate: 0,
        essential: true,
      },
      {
        id: uid(),
        name: 'Travel & hobbies',
        kind: 'expense',
        amount: 750,
        every_months: 1,
        start_month: 1,
        end_month: 721,
        start_basis: 'plan',
        end_basis: 'plan',
        enabled: true,
        growth_rate: 0,
        essential: false,
      },
      {
        id: uid(),
        name: 'Pension estimate',
        kind: 'income',
        amount: 1500,
        every_months: 1,
        start_month: 325,
        end_month: 721,
        start_basis: 'age',
        start_age: 62,
        end_basis: 'plan',
        enabled: true,
        growth_rate: 0,
        essential: true,
      },
    ],
    debts: [
      {
        id: uid(),
        name: 'Home mortgage',
        balance: 245000,
        annual_rate: 0.038,
        months: 240,
        payment: 1600,
        extra_payment: 0,
      },
    ],
  };
}
async function api(path, body, method) {
  const r = await fetch(path, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let d;
  try {
    d = await r.json();
  } catch {
    throw Error('The server returned an unreadable response.');
  }
  if (!r.ok)
    throw Error(
      typeof d.error === 'string' ? d.error : d.error?.message || d.message || `Request failed (${r.status})`,
    );
  return d;
}
function tell(msg, error = false, ms = 6500) {
  const n = $('notice');
  n.hidden = false;
  n.className = 'notice' + (error ? ' error' : '');
  n.textContent = msg;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (n.hidden = true), ms);
}
function tellAction(msg, label, action, ms = 6500) {
  tell(msg, false, ms);
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'link-button';
  b.textContent = label;
  b.onclick = () => {
    b.disabled = true;
    action();
  };
  $('notice').append(' ', b);
}
// Unsaved edits are kept in this browser so a reload, crash or closed tab can be recovered.
const DRAFT_KEY = 'openfi:draft';
function saveDraft() {
  try {
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ plan, saved_id: saved?.id || null, saved_version: saved?.version || null, at: Date.now() }),
    );
  } catch {}
}
function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {}
}
function readDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    return d && typeof d.plan === 'object' && Array.isArray(d.plan.accounts) ? d : null;
  } catch {
    return null;
  }
}
function offerDraft() {
  const d = readDraft();
  if (!d || JSON.stringify(d.plan) === JSON.stringify(plan)) return;
  const same = saved && d.saved_id === saved.id,
    stale = same && d.saved_version !== saved.version,
    when = new Date(d.at).toLocaleString();
  tellAction(
    `You have unsaved changes to “${d.plan.name || 'a plan'}” from ${when}.${stale ? ' The saved plan has changed since, so restoring keeps them as a new working copy.' : ''}`,
    'Restore them',
    () => {
      plan = d.plan;
      if (!same || stale) saved = null;
      $('plan-name').value = plan.name || '';
      $('valuation-date').value = plan.valuation_date;
      if (!saved) $('saved-plans').value = '';
      fillAssumptions();
      touch();
      renderTables();
      tell('Unsaved changes restored.');
    },
    30000,
  );
}
function touch() {
  dirty = true;
  saveDraft();
  projection = null;
  clearTimeout(autoTimer);
  autoTimer = setTimeout(() => {
    if (!projection) runProjection(true);
  }, 450);
  simulation = null;
  $('simulation-result').innerHTML = '<p>Inputs changed. Run a new simulation.</p>';
  $('comparison-panel').hidden = true;
  renderSummary();
  showSaveState();
}
// One place decides the header status, so a projection never hides unsaved edits.
function showSaveState() {
  const s = $('save-state');
  s.classList.toggle('dirty', dirty);
  s.textContent = dirty
    ? projection
      ? 'Unsaved changes · projection current'
      : 'Unsaved changes'
    : saved
      ? `Saved · v${saved.version}`
      : projection
        ? 'Projection current'
        : 'Not saved';
}
function discardOk(action) {
  if (!dirty) return true;
  const ok = confirm(`Discard unsaved changes to your working plan and ${action}?`);
  if (ok) clearDraft();
  return ok;
}
async function ensureSaved() {
  return saved && !dirty ? true : savePlan();
}
window.addEventListener('beforeunload', e => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = '';
  }
});
function go(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${view}`));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  const title =
    {
      quick: 'Quick calculator',
      overview: 'Overview',
      accounts: 'Accounts & debts',
      cashflow: 'Income & spending',
      retirement: 'Retirement tests',
      scenarios: 'Scenarios',
      progress: 'Progress',
      settings: 'Settings',
      children: 'Kids & education',
      purchases: 'Future purchases',
    }[view] || 'Overview';
  $('view-title').textContent = title;
  if (view !== 'quick') showSaveState();
  if (view === 'quick' && !quickResult) {
    $('save-state').textContent = 'Quick estimate · separate draft';
    $('save-state').classList.remove('dirty');
  }
  location.hash = view;
  $('sidebar').classList.remove('open');
  if (view === 'scenarios') refreshScenarios().catch(e => tell(e.message, true));
  if (view === 'progress') refreshObservations().catch(e => tell(e.message, true));
  if (view === 'settings') refreshRevisions().catch(e => tell(e.message, true));
  if (view === 'quick' && !quickResult) runQuick();
  if (view === 'children' && typeof renderChildren === 'function') renderChildren();
  if (view === 'purchases' && typeof renderPurchases === 'function') renderPurchases();
}
document.querySelectorAll('.nav-item').forEach(
  n =>
    (n.onclick = e => {
      e.preventDefault();
      go(n.dataset.view);
    }),
);
document.querySelectorAll('[data-jump]').forEach(n => (n.onclick = () => go(n.dataset.jump)));
$('menu-toggle').onclick = () => $('sidebar').classList.toggle('open');
