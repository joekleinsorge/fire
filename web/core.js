'use strict';
// Shared state, helpers, API access, notices, save state and navigation.
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
  oidcLogin = false,
  saved = null,
  scenarios = [],
  observations = [],
  revisions = [],
  editState = null,
  noticeTimer = null,
  workingDirty = false,
  assumptionsPending = false;

function valuationDate() {
  const n = new Date(),
    d = new Date(n.getFullYear(), n.getMonth(), 0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function samplePlan() {
  return {
    name: 'Example household plan',
    valuation_date: valuationDate(),
    age: 35,
    horizon: 60,
    retirement_age: 62,
    return_rate: 0.05,
    withdrawal_rate: 0.04,
    currency: 'USD',
    accounts: [
      {
        id: uid(),
        name: 'Workplace 401(k)',
        type: 'retirement',
        balance: 185000,
        return_rate: 0.05,
        fee_rate: 0.004,
        available: true,
      },
      {
        id: uid(),
        name: 'Brokerage account',
        type: 'investment',
        balance: 90000,
        return_rate: 0.052,
        fee_rate: 0.002,
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
function tell(msg, error = false) {
  const n = $('notice');
  n.hidden = false;
  n.className = 'notice' + (error ? ' error' : '');
  n.textContent = msg;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (n.hidden = true), 6500);
}
function markDirty() {
  workingDirty = true;
  $('save-state').textContent = 'Unsaved changes';
  $('save-state').classList.add('dirty');
}
function touch() {
  markDirty();
  projection = null;
  simulation = null;
  $('simulation-result').innerHTML = '<p>Inputs changed. Run a new simulation.</p>';
  $('comparison-panel').hidden = true;
  renderSummary();
}
function go(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${view}`));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  const title =
    {
      overview: 'Overview',
      accounts: 'Accounts & debts',
      assets: 'Property & assets',
      inputs: 'Plan inputs',
      cashflow: 'Income & spending',
      retirement: 'Retirement tests',
      scenarios: 'Scenarios',
      progress: 'Progress',
      settings: 'Settings',
      children: 'Kids & education',
      purchases: 'Future purchases',
    }[view] || 'Overview';
  $('view-title').textContent = title;
  location.hash = view;
  $('sidebar').classList.remove('open');
  if (view === 'scenarios') refreshScenarios().catch(e => tell(e.message, true));
  if (view === 'progress') refreshObservations().catch(e => tell(e.message, true));
  if (view === 'settings') {
    renderInputs();
    refreshRevisions().catch(e => tell(e.message, true));
  }
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
