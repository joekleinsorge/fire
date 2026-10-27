'use strict';
// Saved revisions, blank plans, sign-in, saved plans, save, import and export.
async function refreshRevisions() {
  if (!saved) {
    revisions = [];
    $('revision-list').innerHTML = '<p class="small-note">Sign in and open a saved plan to view its history.</p>';
    return;
  }
  const d = await api(`/api/plans/${saved.id}/revisions`);
  revisions = d.revisions || [];
  const latest = Math.max(saved.version, ...revisions.map(r => r.version));
  $('api-sync-state').textContent =
    latest > saved.version
      ? `A newer saved version (v${latest}) is available. Export unsaved edits before reloading if you want to keep them.`
      : `This tab has saved version ${saved.version}.`;
  $('revision-list').innerHTML =
    [...revisions]
      .reverse()
      .map(
        r =>
          `<div class="revision-row"><div class="revision-meta"><strong>Version ${r.version}${r.version === saved.version ? ' · loaded in this tab' : ''}</strong><small>${esc(new Date(r.created * 1000).toLocaleString())}</small></div><button class="button secondary" data-restore-revision="${r.version}" ${r.version === saved.version ? 'disabled' : ''}>Restore as new version</button></div>`,
      )
      .join('') || '<p class="small-note">No saved revisions yet.</p>';
}
document.addEventListener('click', async e => {
  const button = e.target.closest('[data-restore-revision]');
  if (!button) return;
  const version = Number(button.dataset.restoreRevision);
  if (!saved || !Number.isInteger(version)) return;
  const revision = revisions.find(row => row.version === version);
  if (!revision) return;
  if (!confirm(`Restore version ${version} as a new version? Your current saved version will remain in history.`))
    return;
  try {
    const head = await api(`/api/plans/${saved.id}`);
    saved = head;
    plan = {
      ...structuredClone(revision.plan),
      name: head.name,
      accounts: revision.plan.accounts || [],
      streams: revision.plan.streams || [],
      debts: revision.plan.debts || [],
      valuation_date: revision.plan.valuation_date || head.created_at?.slice(0, 10) || valuationDate(),
    };
    $('plan-name').value = head.name;
    $('valuation-date').value = plan.valuation_date;
    projection = await projectPlan(plan);
    fillAssumptions();
    renderTables();
    await savePlan();
    await refreshRevisions();
    tell(`Restored version ${version} as new version ${saved.version}.`);
  } catch (err) {
    tell(err.message, true);
  }
});
function createBlank() {
  if (workingDirty && !confirm('Start a blank plan and replace your unsaved edits?')) return;
  plan = {
    name: 'Untitled plan',
    valuation_date: valuationDate(),
    age: 35,
    horizon: 60,
    retirement_age: 65,
    return_rate: 0.04,
    withdrawal_rate: 0.04,
    currency: 'USD',
    accounts: [],
    streams: [],
    debts: [],
  };
  saved = null;
  projection = null;
  observations = [];
  scenarios = [];
  $('saved-plans').value = '';
  fillAssumptions();
  $('plan-name').value = plan.name;
  $('valuation-date').value = plan.valuation_date;
  renderTables();
  touch();
  go('inputs');
  tell('Blank plan created. Set assumptions, then add accounts, income, and spending.');
}
$('blank-plan').onclick = createBlank;
async function auth(register = false) {
  if (!$('auth-form').reportValidity()) return;
  try {
    const d = await api('/api/auth/' + (register ? 'register' : 'login'), {
      email: $('email').value,
      password: $('password').value,
    });
    user = d.user;
    $('auth-dialog').close();
    $('password').value = '';
    updateAuth();
    await loadPlans();
    if (register) tell('Account created. You can now save this plan.');
  } catch (e) {
    $('auth-error').textContent = e.message;
  }
}
$('auth-form').onsubmit = e => {
  e.preventDefault();
  auth(false);
};
$('register').onclick = () => auth(true);
$('auth-close').onclick = () => $('auth-dialog').close();
$('account-button').onclick = async () => {
  if (oidcLogin) {
    window.location.href = user ? '/oauth2/sign_out?rd=%2F' : '/oauth2/start?rd=%2F%3Fsso%3D1';
    return;
  }
  if (user) {
    try {
      await api('/api/auth/logout', {});
      user = null;
      saved = null;
      $('saved-plans').value = '';
      updateAuth();
      tell('Signed out. This working copy remains in this tab.');
    } catch (e) {
      tell(e.message, true);
    }
  } else openAuth();
};
$('settings-auth').onclick = () => (user ? savePlan() : openAuth());
$('delete-plan').onclick = () => {
  if (!saved) {
    tell('Choose a saved plan first.', true);
    return;
  }
  pendingDelete = { kind: 'plan', id: saved.id };
  $('confirm-message').textContent =
    `Delete “${saved.name}” and its saved revisions, scenarios, and observations? This cannot be undone.`;
  $('confirm-dialog').showModal();
};
function openAuth() {
  if (oidcLogin) {
    window.location.href = '/oauth2/start?rd=%2F%3Fsso%3D1';
    return;
  }
  $('auth-dialog').showModal();
  $('email').focus();
}
function updateAuth() {
  $('account-button').textContent = user
    ? 'Sign out · ' + user.email
    : oidcLogin
      ? 'Sign in with Dex'
      : 'Sign in to save';
  $('settings-auth').textContent = user ? 'Save current plan' : 'Sign in or create account';
}
async function loadPlans() {
  if (!user) return;
  try {
    const d = await api('/api/plans');
    $('saved-plans').innerHTML =
      '<option value="">Current working plan</option>' +
      (d.plans || []).map(p => `<option value="${esc(p.id)}">${esc(p.name)} · v${p.version}</option>`).join('');
    $('saved-plan-list').textContent = (d.plans || []).length
      ? `${d.plans.length} saved plan${d.plans.length === 1 ? '' : 's'} available in the plan selector.`
      : 'No saved plans yet.';
    return d.plans || [];
  } catch (e) {
    tell(e.message, true);
    return [];
  }
}
async function uploadLocalRecords() {
  const local = scenarios.filter(s => !s.data),
    notes = observations.filter(o => o.local);
  for (const s of local)
    await api(`/api/plans/${saved.id}/scenarios`, {
      name: s.name,
      plan: s.plan,
      ...(s.baseline_plan ? { baseline_plan: s.baseline_plan } : {}),
    });
  for (const { id, local: _, ...o } of notes) await api(`/api/plans/${saved.id}/observations`, o);
  await refreshScenarios();
  await refreshObservations();
}
function rememberPlan(id) {
  try {
    id ? localStorage.setItem('openfi:last-plan', id) : localStorage.removeItem('openfi:last-plan');
  } catch {}
}
function rememberedPlan() {
  try {
    return localStorage.getItem('openfi:last-plan');
  } catch {
    return null;
  }
}
async function savePlan() {
  if (assumptionsPending && !(await applyAssumptions())) return false;
  if (!user) {
    openAuth();
    return false;
  }
  const fingerprint = JSON.stringify(plan),
    body = { name: plan.name || 'My financial plan', plan: JSON.parse(fingerprint) };
  if (saved) {
    body.version = saved.version;
    saved = await api('/api/plans/' + saved.id, body, 'PUT');
  } else {
    saved = await api('/api/plans', body);
    $('saved-plans').value = saved.id; /* Automatic upload of browser-only records is disabled. */
  }
  await loadPlans();
  $('saved-plans').value = saved.id;
  if (JSON.stringify(plan) !== fingerprint || assumptionsPending) {
    markDirty();
    tell('Saved the submitted version. Newer edits in this tab still need saving.');
    return true;
  }
  workingDirty = false;
  $('save-state').textContent = `Saved · v${saved.version}`;
  $('save-state').classList.remove('dirty');
  tell(`Saved ${saved.name}, version ${saved.version}.`);
  return true;
}
$('save-plan').onclick = () => {
  savePlan().catch(e => tell(e.message, true));
};
$('saved-plans').onchange = async e => {
  const id = e.target.value;
  if (!id) return;
  try {
    if (workingDirty && !confirm('Open the saved plan and replace your unsaved edits in this tab?')) {
      $('saved-plans').value = saved?.id || '';
      return;
    }
    const p = await api('/api/plans/' + encodeURIComponent(id));
    saved = p;
    workingDirty = false;
    simulation = null;
    plan = {
      ...p.plan,
      name: p.name,
      accounts: p.plan.accounts || [],
      streams: p.plan.streams || [],
      debts: p.plan.debts || [],
      valuation_date: p.plan.valuation_date || p.created_at?.slice(0, 10) || valuationDate(),
    };
    $('plan-name').value = p.name;
    $('valuation-date').value = plan.valuation_date;
    projection = null;
    fillAssumptions();
    projection = await projectPlan(plan);
    touchAfterRun();
    renderTables();
    await refreshScenarios();
    await refreshObservations();
    tell(`Opened ${p.name}, revision ${p.version}.`);
  } catch (err) {
    tell(err.message, true);
  }
};
function download(filename, content, type) {
  const blob = new Blob([content], { type }),
    url = URL.createObjectURL(blob),
    a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1200);
}
$('export-json').onclick = () => download('openfi-plan.json', JSON.stringify(plan, null, 2), 'application/json');
$('export-annual').onclick = async () => {
  try {
    const r = projection || (await projectPlan(plan)),
      fields = [
        'year',
        'age',
        'balance',
        'available_balance',
        'net_worth',
        'debt_balance',
        'income',
        'expenses',
        'essential_expenses',
        'desired_expenses',
        'funded_expenses',
        'purchase_paid',
        'purchase_upkeep',
        'child_contributions',
        'child_education',
        'unfunded',
        'essential_unfunded',
        'desired_unfunded',
        'purchase_unfunded',
        'child_unfunded',
      ],
      lines = [
        ['Open FI annual projection'],
        ['engine_version', r.metadata?.engine_version || ''],
        ['valuation_date', plan.valuation_date || ''],
        ['currency', plan.currency || 'USD'],
        ['price_basis', r.metadata?.price_basis || ''],
        [],
        fields,
        ...(r.annual || []).map(row => fields.map(k => row[k] ?? '')),
      ];
    download(
      'openfi-annual-projection.csv',
      lines.map(row => row.map(csvCell).join(',')).join('\r\n'),
      'text/csv;charset=utf-8',
    );
  } catch (e) {
    tell(e.message, true);
  }
};
$('export-simulation').onclick = () => {
  if (!simulation?.paths?.length) {
    tell('Run and complete a retirement simulation first.', true);
    return;
  }
  const fields = [
      'trial',
      'year',
      'age',
      'balance',
      'net_worth',
      'unfunded',
      'retirement_year',
      'portfolio_survives',
      'essential_spending_funded',
      'desired_lifestyle_funded',
      'retirement_feasible',
      'accumulation_shortfall',
      'first_shortfall_year',
      'cumulative_unfunded',
    ],
    lines = [
      ['Open FI simulation paths'],
      ['engine_version', simulation.metadata?.engine_version || ''],
      ['mode', simulation.metadata?.settings?.mode || ''],
      ['seed', simulation.metadata?.settings?.seed ?? ''],
      ['price_basis', simulation.metadata?.price_basis || ''],
      [],
      fields,
    ];
  for (const path of simulation.paths) {
    const annual = path.annual || [{ year: path.retirement_year, balance: path.ending_balance }];
    for (const row of annual)
      lines.push(
        fields.map(k =>
          k === 'trial'
            ? path.trial
            : k === 'retirement_year'
              ? path.retirement_year
              : k === 'portfolio_survives'
                ? path.portfolio_survives
                : k === 'essential_spending_funded'
                  ? path.essential_spending_funded
                  : k === 'desired_lifestyle_funded'
                    ? path.desired_lifestyle_funded
                    : k === 'retirement_feasible'
                      ? path.retirement_feasible
                      : k === 'accumulation_shortfall'
                        ? path.accumulation_shortfall
                        : k === 'first_shortfall_year'
                          ? path.first_shortfall_year
                          : k === 'cumulative_unfunded'
                            ? path.cumulative_unfunded
                            : (row[k] ?? ''),
        ),
      );
  }
  download(
    'openfi-simulation-paths.csv',
    lines.map(row => row.map(csvCell).join(',')).join('\r\n'),
    'text/csv;charset=utf-8',
  );
};
$('print-overview').onclick = () => {
  go('overview');
  window.print();
};
function csvCell(value) {
  const text = typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '');
  return `"${text.replaceAll('"', '""')}"`;
}
$('import-json').onchange = async e => {
  const f = e.target.files?.[0];
  if (!f) return;
  try {
    const document = JSON.parse(await f.text()),
      p =
        document.plan && typeof document.plan === 'object'
          ? { ...document.plan, name: document.name || document.plan.name }
          : document;
    if (
      !p ||
      typeof p !== 'object' ||
      !Array.isArray(p.accounts) ||
      !Array.isArray(p.streams) ||
      !Array.isArray(p.debts)
    )
      throw Error('The JSON file must contain accounts, streams and debts arrays.');
    const candidate = { ...p, name: p.name || 'Imported plan', valuation_date: p.valuation_date || valuationDate() },
      result = await projectPlan(candidate);
    if (workingDirty && !confirm('Import this plan and replace your unsaved edits?')) {
      e.target.value = '';
      return;
    }
    workingDirty = true;
    plan = candidate;
    saved = null;
    projection = result;
    simulation = null;
    observations = [];
    scenarios = [];
    $('saved-plans').value = '';
    $('plan-name').value = plan.name;
    $('valuation-date').value = plan.valuation_date;
    fillAssumptions();
    touch();
    projection = result;
    renderTables();
    go('inputs');
    tell('Plan imported as a working copy. Review inputs and save it to keep changes.');
  } catch (err) {
    tell(err.message, true);
  }
  e.target.value = '';
};
async function startup() {
  const hour = new Date().getHours();
  $('greeting').textContent =
    `${hour < 5 ? 'Good evening' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'}. Here's your plan.`;
  fillAssumptions();
  $('plan-name').value = plan.name;
  $('valuation-date').value = plan.valuation_date;
  renderTables();
  $('observation-date').value = new Date().toISOString().slice(0, 10);
  let reopen = null;
  try {
    let d = await api('/api/auth/me');
    oidcLogin = !!d.oidc;
    if (oidcLogin && new URLSearchParams(location.search).has('sso')) d = await api('/api/auth/oidc');
    user = d.user;
    updateAuth();
    if (user) {
      const plans = await loadPlans();
      reopen = (plans.find(p => p.id === rememberedPlan()) || plans[0])?.id;
    }
  } catch {}
  if (reopen) {
    $('saved-plans').value = reopen;
    await $('saved-plans').onchange({ target: { value: reopen } });
    if (saved) {
      const view = location.hash.slice(1);
      if (view && $(`view-${view}`)) go(view);
      return;
    }
  }
  const view = location.hash.slice(1);
  if (view && $(`view-${view}`)) go(view);
  try {
    projection = await projectPlan(plan);
    touchAfterRun();
    renderTables();
  } catch (e) {
    $('projection-note').textContent = e.message;
  }
}
const savePlanOriginal = savePlan;
savePlan = async () => {
  const result = await savePlanOriginal();
  if (result && saved) {
    rememberPlan(saved.id);
    await refreshRevisions();
  }
  return result;
};
const savedPlanChangeHandler = $('saved-plans').onchange;
$('saved-plans').onchange = async e => {
  await savedPlanChangeHandler(e);
  if (saved) {
    rememberPlan(saved.id);
    await refreshRevisions();
  }
};
