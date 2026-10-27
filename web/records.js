'use strict';
// Accounts, debts and cash flows: tables, the record editor and deletion.
function renderTables() {
  const acc = plan.accounts || [],
    deb = plan.debts || [],
    streams = plan.streams || [];
  $('accounts-table').innerHTML = acc
    .map(
      (a, i) =>
        `<tr><td><strong>${esc(a.name)}</strong></td><td>${esc(a.type || 'investment')}</td><td>${money(a.balance)}</td><td>${pct(a.return_rate)}</td><td>${pct(a.fee_rate)}</td><td>${taxLabel(a)}<small class="row-sub">${pct(taxRate(a))} on withdrawals</small></td><td>${(a.available ?? !['property', 'other'].includes(a.type)) ? 'Available' : 'Restricted'}</td><td class="row-actions"><button class="link-button" data-move-account="up" data-id="${esc(a.id)}" aria-label="Move ${esc(a.name)} earlier in withdrawal order">↑</button><button class="link-button" data-move-account="down" data-id="${esc(a.id)}" aria-label="Move ${esc(a.name)} later in withdrawal order">↓</button><button class="link-button" data-edit="account" data-id="${esc(a.id)}">Edit</button><button class="link-button danger-text" data-delete="account" data-id="${esc(a.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('accounts-empty').hidden = acc.length > 0;
  $('debts-table').innerHTML = deb
    .map(
      d =>
        `<tr><td><strong>${esc(d.name)}</strong></td><td>${money(d.balance)}</td><td>${pct(d.annual_rate)}${d.inflation_rate != null ? `<small class="row-sub">${pct(d.inflation_rate)} inflation</small>` : ''}</td><td>${d.payment == null ? 'Calculated' : money(d.payment)}</td><td>${money(d.extra_payment)}</td><td class="row-actions"><button class="link-button" data-edit="debt" data-id="${esc(d.id)}">Edit</button><button class="link-button danger-text" data-delete="debt" data-id="${esc(d.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('debts-empty').hidden = deb.length > 0;
  $('streams-table').innerHTML = streams
    .map(
      s =>
        `<tr><td><strong>${esc(s.name)}</strong>${plan.partner ? `<small class="row-sub">${esc(personName(s.owner || 'self'))}</small>` : ''}${s.enabled === false ? '<small class="row-sub">Paused</small>' : ''}</td><td><span class="kind ${s.kind}">${s.kind === 'income' ? 'Income' : 'Expense'}</span></td><td>${money(((+s.amount || 0) * 12) / (+s.every_months || 12))}</td><td>${streamStartLabel(s)}</td><td>${streamEndLabel(s)}</td><td>${pct(s.growth_rate)}</td><td>${s.essential ? 'Yes' : 'No'}</td><td class="row-actions"><button class="link-button" data-edit="stream" data-id="${esc(s.id)}">Edit</button><button class="link-button danger-text" data-delete="stream" data-id="${esc(s.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('streams-empty').hidden = streams.length > 0;
  renderSummary();
  if (typeof renderChildren === 'function') renderChildren();
  if (typeof renderPurchases === 'function') renderPurchases();
  if (typeof renderSocialSecurity === 'function') renderSocialSecurity();
  if (typeof syncWhatIf === 'function') syncWhatIf();
  if (typeof renderCheckup === 'function') renderCheckup();
  if (typeof renderProgressChart === 'function') renderProgressChart();
}
// Phase-1 tax model: one flat effective rate per account, applied by the engine as a withdrawal gross-up.
const taxTreatments = {
    after_tax: 'After tax (no tax due)',
    pre_tax: 'Pre-tax (401(k), traditional IRA)',
    roth: 'Roth',
    taxable: 'Taxable brokerage',
  },
  taxDefaults = { after_tax: 0, pre_tax: 0.22, roth: 0, taxable: 0.1 },
  taxLabel = a =>
    ({ after_tax: 'After tax', pre_tax: 'Pre-tax', roth: 'Roth', taxable: 'Taxable' })[
      a.tax_treatment || 'after_tax'
    ] || 'After tax',
  taxRate = a => a.withdrawal_tax_rate ?? taxDefaults[a.tax_treatment || 'after_tax'] ?? 0;
const definitions = {
  account: {
    title: 'Account',
    fields: [
      ['name', 'Account name', 'text'],
      ['type', 'Account type', 'select', ['cash', 'investment', 'retirement', 'property', 'other']],
      ['balance', 'Current balance', 'number'],
      ['return_rate', 'Real annual return (%)', 'percent'],
      ['fee_rate', 'Annual fee (%)', 'percent'],
      ['tax_treatment', 'Tax treatment', 'select', Object.entries(taxTreatments)],
      ['withdrawal_tax_rate', 'Tax on withdrawals (% · flat tax model)', 'percent'],
      ['gain_share', 'Gain share of withdrawals (% · taxable accounts, federal model; blank uses plan)', 'percent'],
      ['owner', 'Belongs to', 'owner'],
      ['available', 'Available for spending', 'check'],
    ],
  },
  debt: {
    title: 'Debt',
    fields: [
      ['name', 'Debt name', 'text'],
      ['balance', 'Current balance', 'number'],
      ['annual_rate', 'Annual interest rate (% as quoted)', 'percent'],
      ['inflation_rate', 'Expected inflation (% · blank uses plan)', 'percent'],
      ['months', 'Months remaining', 'number'],
      ['payment', 'Required monthly payment (blank to calculate)', 'number'],
      ['extra_payment', 'Extra monthly payment', 'number'],
    ],
  },
  stream: {
    title: 'Cash flow',
    fields: [
      ['name', 'Name', 'text'],
      ['kind', 'Type', 'select', ['income', 'expense']],
      ['amount', 'Amount per payment', 'number'],
      ['every_months', 'Payment frequency (months)', 'number'],
      ['owner', 'Belongs to', 'owner'],
      ['start', 'Starts', 'timing'],
      ['end', 'Ends', 'timing'],
      ['growth_rate', 'Annual real growth (%)', 'percent'],
      ['taxable_share', 'Taxable share of income (% · federal tax model)', 'percent'],
      ['enabled', 'Include in plan', 'check'],
      ['essential', 'Essential (expenses)', 'check'],
    ],
  },
};
let pendingDelete = null;
function openRecord(kind, id) {
  const row = id
    ? (plan[kind === 'account' ? 'accounts' : kind === 'stream' ? 'streams' : 'debts'] || []).find(x => x.id === id)
    : null;
  editState = { kind, id, row: row ? { ...row } : null };
  const def = definitions[kind];
  $('dialog-title').textContent = `${row ? 'Edit' : 'Add'} ${def.title.toLowerCase()}`;
  $('dialog-fields').innerHTML = def.fields
    .map(([key, label, type, opts]) => {
      let value = row?.[key];
      if (value === undefined)
        value =
          key === 'name'
            ? ''
            : key === 'enabled' || key === 'essential'
              ? true
              : key === 'available'
                ? kind === 'account'
                  ? !['property', 'other'].includes(row?.type)
                  : false
                : key === 'type'
                  ? 'investment'
                  : key === 'kind'
                    ? 'income'
                    : key === 'every_months'
                      ? 1
                      : key === 'start_month'
                        ? 1
                        : key === 'end_month'
                          ? (+plan.horizon || 65) * 12 + 1
                          : key === 'months'
                            ? 360
                            : key === 'payment'
                              ? ''
                              : key === 'inflation_rate' || key === 'gain_share'
                                ? ''
                                : key === 'tax_treatment'
                                  ? 'after_tax'
                                  : key === 'withdrawal_tax_rate'
                                    ? taxRate(row || {})
                                    : 0;
      if (type === 'owner')
        return plan.partner
          ? `<label>${label}<select name="owner"><option value="self" ${(row?.owner || 'self') === 'self' ? 'selected' : ''}>You</option><option value="partner" ${row?.owner === 'partner' ? 'selected' : ''}>${esc(personName('partner'))}</option></select><small>Ages, required distributions and income that stops at a life expectancy use this person.</small></label>`
          : '';
      if (type === 'timing') return timingField(key, row);
      if (type === 'check')
        return `<label class="check-label"><input name="${key}" type="checkbox" ${value ? 'checked' : ''}>${label}</label>`;
      if (type === 'select')
        return `<label>${label}<select name="${key}">${opts
          .map(o => {
            const [v, text] = Array.isArray(o) ? o : [o, o];
            return `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(text)}</option>`;
          })
          .join('')}</select></label>`;
      const display = value === '' ? '' : type === 'percent' ? Number(value || 0) * 100 : value;
      return `<label>${label}<input name="${key}" type="${type === 'text' ? 'text' : 'number'}" step="${['months', 'every_months', 'start_month', 'end_month'].includes(key) ? '1' : 'any'}" ${['months', 'every_months', 'start_month', 'end_month'].includes(key) ? 'min="1"' : type === 'number' && key !== 'annual_rate' ? 'min="0"' : key === 'withdrawal_tax_rate' ? 'min="0" max="90"' : ''} value="${esc(display)}" ${key === 'name' ? 'maxlength="120"' : ''} ${key === 'payment' ? 'placeholder="Calculated from rate and term"' : key === 'inflation_rate' ? `placeholder="Plan default (${pct(plan.inflation_rate)})"` : 'required'}></label>`;
    })
    .join('');
  const accountType = $('dialog-fields').querySelector('[name="type"]'),
    available = $('dialog-fields').querySelector('[name="available"]');
  if (accountType && available && !row)
    accountType.onchange = () => {
      if (['property', 'other'].includes(accountType.value)) available.checked = false;
    };
  const treatment = $('dialog-fields').querySelector('[name="tax_treatment"]'),
    taxInput = $('dialog-fields').querySelector('[name="withdrawal_tax_rate"]');
  if (treatment && taxInput)
    treatment.onchange = () => {
      taxInput.value = taxDefaults[treatment.value] * 100;
    };
  $('dialog-fields')
    .querySelectorAll('[data-timing]')
    .forEach(sel => (sel.onchange = syncTimingInputs));
  $('record-dialog').showModal();
}
document.querySelectorAll('[data-add]').forEach(b => (b.onclick = () => openRecord(b.dataset.add)));
document.addEventListener('click', e => {
  const edit = e.target.closest('[data-edit]'),
    del = e.target.closest('[data-delete]'),
    move = e.target.closest('[data-move-account]');
  if (edit) openRecord(edit.dataset.edit, edit.dataset.id);
  if (move) {
    const i = plan.accounts.findIndex(a => a.id === move.dataset.id),
      n = i + (move.dataset.moveAccount === 'up' ? -1 : 1);
    if (i >= 0 && n >= 0 && n < plan.accounts.length) {
      [plan.accounts[i], plan.accounts[n]] = [plan.accounts[n], plan.accounts[i]];
      touch();
      renderTables();
    }
  }
  if (del) {
    pendingDelete = { kind: del.dataset.delete, id: del.dataset.id };
    const row = (
      plan[pendingDelete.kind === 'account' ? 'accounts' : pendingDelete.kind === 'stream' ? 'streams' : 'debts'] || []
    ).find(x => x.id === pendingDelete.id);
    const ref =
        pendingDelete.kind === 'account' ? 'sell_account_id' : pendingDelete.kind === 'debt' ? 'payoff_debt_id' : null,
      linked = ref
        ? (plan.future_purchases || []).filter(p => p[ref] === pendingDelete.id).map(p => `“${p.name}”`)
        : [];
    $('confirm-message').textContent =
      `Remove ${row?.name || 'this record'} from your working plan?${linked.length ? ` ${linked.join(', ')} will no longer ${ref === 'sell_account_id' ? 'sell it' : 'pay it off'}.` : ''}`;
    $('confirm-dialog').showModal();
  }
});
$('dialog-close').onclick = $('record-cancel').onclick = () => $('record-dialog').close();
$('record-form').onsubmit = e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget).entries());
  const row = { ...(editState.row || {}), id: editState.id || uid() };
  for (const [k, v] of Object.entries(data)) {
    const f = definitions[editState.kind].fields.find(x => x[0] === k);
    if (f?.[2] === 'check') row[k] = true;
    else if (f?.[2] === 'number') {
      if (k === 'payment' && v === '') delete row[k];
      else row[k] = +v;
    } else if (f?.[2] === 'percent') {
      if ((k === 'inflation_rate' || k === 'gain_share') && v === '') delete row[k];
      else row[k] = +v / 100;
    } else row[k] = v;
  }
  for (const [k, , type] of definitions[editState.kind].fields)
    if (type === 'check' && !Object.hasOwn(data, k)) row[k] = false;
  if (editState.kind === 'stream') {
    try {
      readTiming(row, data);
    } catch (err) {
      tell(err.message, true);
      return;
    }
  }
  const key = editState.kind === 'account' ? 'accounts' : editState.kind === 'stream' ? 'streams' : 'debts',
    idx = (plan[key] = plan[key] || []).findIndex(r => r.id === row.id);
  if (idx >= 0) plan[key][idx] = row;
  else plan[key].push(row);
  $('record-dialog').close();
  touch();
  renderTables();
};
document.querySelectorAll('[data-close]').forEach(b => (b.onclick = () => $(b.dataset.close).close()));
$('confirm-cancel').onclick = $('confirm-close').onclick = () => $('confirm-dialog').close();
$('confirm-delete').onclick = () => {
  if (!pendingDelete) return;
  if (pendingDelete.kind === 'plan') {
    const id = pendingDelete.id;
    api(`/api/plans/${id}`, {}, 'DELETE')
      .then(() => {
        saved = null;
        pendingDelete = null;
        rememberPlan(null);
        dirty = true;
        showSaveState();
        $('saved-plans').value = '';
        $('confirm-dialog').close();
        loadPlans();
        tell('Saved plan deleted. The working copy is still available in this tab.');
      })
      .catch(e => tell(e.message, true));
    return;
  }
  const kind = pendingDelete.kind,
    key = kind === 'account' ? 'accounts' : kind === 'stream' ? 'streams' : 'debts';
  plan[key] = plan[key].filter(r => r.id !== pendingDelete.id);
  const ref = kind === 'account' ? 'sell_account_id' : kind === 'debt' ? 'payoff_debt_id' : null;
  if (ref)
    for (const p of plan.future_purchases || [])
      if (p[ref] === pendingDelete.id) {
        delete p[ref];
        if (ref === 'sell_account_id') delete p.payoff_debt_id;
      }
  pendingDelete = null;
  $('confirm-dialog').close();
  touch();
  renderTables();
};
