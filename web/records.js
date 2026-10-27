'use strict';
// Accounts, assets, debts and cash flow tables, and the record editor dialog.
function renderTables() {
  const all = plan.accounts || [],
    acc = all.filter(a => !isPersonalAsset(a)),
    assets = all.filter(a => isPersonalAsset(a)),
    deb = plan.debts || [],
    streams = plan.streams || [];
  $('accounts-table').innerHTML = acc
    .map(
      (a, i) =>
        `<tr><td><strong>${esc(a.name)}</strong></td><td>${esc(a.source_details?.type?.replaceAll('_', ' ') || a.type || 'investment')}</td><td>${money(a.balance)}</td><td>${pct(a.return_rate)}</td><td>${pct(a.fee_rate)}</td><td>${isAvailableAccount(a) ? 'Available' : a.available_from_age != null ? 'From age ' + esc(a.available_from_age) : 'Restricted'}${a.payroll_contribution_monthly ? '<small class="row-sub">Payroll ' + money(a.payroll_contribution_monthly) + '/month</small>' : ''}${a.withdrawal_tax_rate ? '<small class="row-sub">Withdrawal tax ' + pct(a.withdrawal_tax_rate) + '</small>' : ''}</td><td class="row-actions"><button class="link-button" data-move-account="up" data-id="${esc(a.id)}" aria-label="Move ${esc(a.name)} earlier in withdrawal order">↑</button><button class="link-button" data-move-account="down" data-id="${esc(a.id)}" aria-label="Move ${esc(a.name)} later in withdrawal order">↓</button><button class="link-button" data-edit="account" data-id="${esc(a.id)}">Edit</button><button class="link-button danger-text" data-delete="account" data-id="${esc(a.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('accounts-empty').hidden = acc.length > 0;
  $('assets-table').innerHTML = assets
    .map(
      a =>
        `<tr><td><strong>${esc(a.name)}</strong></td><td>${a.type === 'property' ? 'Property' : 'Other asset'}</td><td>${money(a.balance)}</td><td>${pct(a.return_rate)}</td><td class="row-actions"><button class="link-button" data-edit="asset" data-id="${esc(a.id)}">Edit</button><button class="link-button danger-text" data-delete="account" data-id="${esc(a.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('assets-empty').hidden = assets.length > 0;
  $('assets-total').textContent = money(assets.reduce((n, a) => n + (+a.balance || 0), 0));
  $('debts-table').innerHTML = deb
    .map(
      d =>
        `<tr><td><strong>${esc(d.name)}</strong>${d.balance_only ? '<small class="row-sub">Reference only · no payoff modeled</small>' : ''}</td><td>${money(d.balance)}</td><td>${pct(d.annual_rate)}</td><td>${money(d.payment)}</td><td>${money(d.extra_payment)}</td><td class="row-actions"><button class="link-button" data-edit="debt" data-id="${esc(d.id)}">Edit</button><button class="link-button danger-text" data-delete="debt" data-id="${esc(d.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('debts-empty').hidden = deb.length > 0;
  $('streams-table').innerHTML = streams
    .map(
      s =>
        `<tr><td><strong>${esc(s.name)}</strong>${plan.partner ? `<small class="row-sub">${esc(personName(s.owner || 'self'))}</small>` : ''}${s.enabled === false ? '<small class="row-sub">Paused</small>' : ''}</td><td><span class="kind ${s.kind}">${s.kind === 'income' ? 'Income' : 'Expense'}</span></td><td>${money(((+s.amount || 0) * 12) / (+s.every_months || 12))}</td><td>${esc(flowDateLabel(s.start_month || 1))}</td><td>${esc(flowDateLabel((s.end_month || plan.horizon * 12 + 1) - 1))}</td><td>${pct(s.growth_rate)}</td><td>${s.essential ? 'Yes' : 'No'}</td><td class="row-actions"><button class="link-button" data-edit="stream" data-id="${esc(s.id)}">Edit</button><button class="link-button danger-text" data-delete="stream" data-id="${esc(s.id)}">Remove</button></td></tr>`,
    )
    .join('');
  $('streams-empty').hidden = streams.length > 0;
  renderSummary();
  if (typeof renderChildren === 'function') renderChildren();
  if (typeof renderPurchases === 'function') renderPurchases();
  if (typeof renderSocialSecurity === 'function') renderSocialSecurity();
  renderInputs();
}
const definitions = {
  account: {
    title: 'Account',
    fields: [
      ['name', 'Account name', 'text'],
      ['type', 'Account type', 'select', ['cash', 'investment', 'retirement']],
      ['balance', 'Current balance', 'number'],
      ['return_rate', 'Real annual return (%)', 'percent'],
      ['fee_rate', 'Annual fee (%)', 'percent'],
      ['available', 'Available for spending now', 'check'],
      ['available_from_age', 'Unlock spending at age (optional)', 'optionalnumber'],
      ['withdrawal_tax_rate', 'Effective tax on withdrawals (%)', 'optionalpercent'],
      ['payroll_contribution_monthly', 'Monthly payroll deposit already withheld from net pay', 'optionalnumber'],
      ['household_contribution_monthly', 'Monthly deposit funded from household cash', 'optionalnumber'],
      ['contribution_start_month', 'First deposit month index (optional)', 'optionalnumber'],
      ['contribution_end_month', 'Deposit end month index, exclusive (optional)', 'optionalnumber'],
    ],
  },
  asset: {
    title: 'Property or other asset',
    fields: [
      ['name', 'Asset name', 'text'],
      ['type', 'Category', 'select', ['property', 'other']],
      ['balance', 'Estimated value', 'number'],
      ['return_rate', 'Real annual value change (%)', 'percent'],
    ],
  },
  debt: {
    title: 'Debt',
    fields: [
      ['name', 'Debt name', 'text'],
      ['balance', 'Current balance', 'number'],
      ['annual_rate', 'Annual interest rate (%)', 'percent'],
      ['balance_only', 'Reference balance only (payments included in spending; no amortization)', 'check'],
      ['nominal', 'Fixed nominal loan (apply plan inflation)', 'check'],
      ['months', 'Months remaining', 'number'],
      ['payment', 'Required monthly payment', 'number'],
      ['extra_payment', 'Extra monthly payment', 'number'],
    ],
  },
  stream: {
    title: 'Cash flow',
    fields: [
      ['name', 'Name', 'text'],
      ['kind', 'Type', 'select', ['income', 'expense']],
      ['amount', 'Amount per payment', 'number'],
      ['every_months', 'Payment frequency', 'frequency'],
      ['start_month', 'First payment month', 'month'],
      ['end_month', 'Last included month', 'month'],
      ['growth_rate', 'Annual real growth (%)', 'percent'],
      ['enabled', 'Include in plan', 'check'],
      ['essential', 'Essential (expenses)', 'check'],
      ['owner', 'Belongs to', 'owner'],
    ],
  },
};
for (const def of Object.values(definitions)) def.fields.push(['notes', 'Notes / source information', 'textarea']);
let pendingDelete = null;
function openRecord(kind, id) {
  const row = id
    ? (plan[kind === 'account' || kind === 'asset' ? 'accounts' : kind === 'stream' ? 'streams' : 'debts'] || []).find(
        x => x.id === id,
      )
    : null;
  editState = { kind, id, row: row ? { ...row } : null };
  const def = definitions[kind];
  $('dialog-title').textContent = `${row ? 'Edit' : 'Add'} ${def.title.toLowerCase()}`;
  $('dialog-fields').innerHTML = def.fields
    .map(([key, label, type, opts]) => {
      let value = row?.[key];
      if (key === 'type' && kind === 'account' && value === 'other') opts = [...opts, 'other'];
      if (value === undefined)
        value =
          key === 'name' || key === 'notes'
            ? ''
            : key === 'return_rate'
              ? kind === 'asset'
                ? 0
                : plan.return_rate
              : key === 'enabled' || key === 'essential'
                ? true
                : key === 'available'
                  ? kind === 'account'
                    ? (row?.available ?? row?.type !== 'other')
                    : false
                  : key === 'type'
                    ? kind === 'asset'
                      ? 'property'
                      : 'investment'
                    : key === 'kind'
                      ? 'income'
                      : key === 'every_months'
                        ? 12
                        : key === 'start_month'
                          ? 1
                          : key === 'end_month'
                            ? (+plan.horizon || 65) * 12 + 1
                            : key === 'months'
                              ? 360
                              : 0;
      if (type.startsWith('optional')) {
        const display =
          value == null || row?.[key] == null ? '' : type === 'optionalpercent' ? Number(value) * 100 : value;
        return `<label>${label}<input name="${key}" type="number" step="any" min="0" value="${esc(display)}" placeholder="Not set"></label>`;
      }
      if (type === 'textarea')
        return `<label class="record-notes">${label}<textarea name="${key}" rows="3" maxlength="10000">${esc(value)}</textarea></label>`;
      if (type === 'month')
        return `<label>${label}<input name="${key}" type="month" min="${flowMonth(1)}" value="${flowMonth(key === 'end_month' ? value - 1 : value)}" required></label>`;
      if (type === 'frequency') {
        const choices = new Map([
          [1, 'Monthly'],
          [3, 'Quarterly'],
          [6, 'Every six months'],
          [12, 'Annually'],
        ]);
        if (!choices.has(+value)) choices.set(+value, `Every ${value} months`);
        return `<label>${label}<select name="${key}">${[...choices].map(([v, text]) => `<option value="${v}" ${v === +value ? 'selected' : ''}>${text}</option>`).join('')}</select></label>`;
      }
      if (type === 'owner')
        return plan.partner
          ? `<label>${label}<select name="${key}">${['self', 'partner'].map(o => `<option value="${o}" ${o === (value || 'self') ? 'selected' : ''}>${esc(personName(o))}</option>`).join('')}</select><small>Their income stops at their planned life expectancy.</small></label>`
          : '';
      if (type === 'check')
        return `<label class="check-label"><input name="${key}" type="checkbox" ${value ? 'checked' : ''}>${label}</label>`;
      if (type === 'select')
        return `<label>${label}<select name="${key}">${opts.map(o => `<option value="${esc(o)}" ${o === value ? 'selected' : ''}>${esc(recordOptionLabel(o, kind))}</option>`).join('')}</select></label>`;
      const display = type === 'percent' ? Number(value || 0) * 100 : value;
      return `<label>${label}<input name="${key}" type="${type === 'text' ? 'text' : 'number'}" step="${['months', 'every_months', 'start_month', 'end_month'].includes(key) ? '1' : 'any'}" ${['months', 'every_months', 'start_month', 'end_month'].includes(key) ? 'min="1"' : type === 'number' && key !== 'annual_rate' ? 'min="0"' : ''} value="${esc(display)}" ${key === 'name' ? 'maxlength="120"' : ''} required></label>`;
    })
    .join('');
  const accountType = $('dialog-fields').querySelector('[name="type"]'),
    available = $('dialog-fields').querySelector('[name="available"]');
  if (accountType && available && !row)
    accountType.onchange = () => {
      if (['property', 'other'].includes(accountType.value)) available.checked = false;
    };
  if (kind === 'debt') {
    const reference = $('dialog-fields').querySelector('[name="balance_only"]'),
      months = $('dialog-fields').querySelector('[name="months"]');
    if (row?.balance_only && row.months == null) months.value = '';
    const syncReference = () => {
      months.disabled = reference.checked;
      months.required = !reference.checked;
    };
    reference.onchange = syncReference;
    syncReference();
  }
  $('record-dialog').showModal();
}
document.querySelectorAll('[data-add]').forEach(b => (b.onclick = () => openRecord(b.dataset.add)));
document.addEventListener('click', e => {
  const edit = e.target.closest('[data-edit]'),
    del = e.target.closest('[data-delete]'),
    move = e.target.closest('[data-move-account]');
  if (edit) openRecord(edit.dataset.edit, edit.dataset.id);
  if (move) {
    const indices = plan.accounts.map((a, i) => (!isPersonalAsset(a) ? i : -1)).filter(i => i >= 0),
      at = indices.findIndex(i => plan.accounts[i].id === move.dataset.id),
      next = at + (move.dataset.moveAccount === 'up' ? -1 : 1);
    if (at >= 0 && next >= 0 && next < indices.length) {
      const i = indices[at],
        n = indices[next];
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
    $('confirm-message').textContent = `Remove ${row?.name || 'this record'} from your working plan?`;
    $('confirm-dialog').showModal();
  }
});
$('dialog-close').onclick = $('record-cancel').onclick = () => $('record-dialog').close();
$('record-form').onsubmit = async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget).entries());
  const row = { ...(editState.row || {}), id: editState.id || uid() };
  if (editState.kind === 'asset') row.available = false;
  for (const [k, v] of Object.entries(data)) {
    const f = definitions[editState.kind].fields.find(x => x[0] === k);
    if (f?.[2]?.startsWith('optional')) {
      if (v === '') delete row[k];
      else row[k] = Number(v) / (f[2] === 'optionalpercent' ? 100 : 1);
    } else if (f?.[2] === 'check') row[k] = true;
    else if (f?.[2] === 'month') row[k] = flowOffset(v) + (k === 'end_month' ? 1 : 0);
    else if (f?.[2] === 'number' || f?.[2] === 'frequency') row[k] = +v;
    else if (f?.[2] === 'percent') row[k] = +v / 100;
    else row[k] = v;
  }
  for (const [k, , type] of definitions[editState.kind].fields)
    if (type === 'check' && !Object.hasOwn(data, k)) row[k] = false;
  const key =
      editState.kind === 'account' || editState.kind === 'asset'
        ? 'accounts'
        : editState.kind === 'stream'
          ? 'streams'
          : 'debts',
    idx = plan[key].findIndex(r => r.id === row.id);
  const candidate = structuredClone(plan);
  if (idx >= 0) candidate[key][idx] = row;
  else candidate[key].push(row);
  try {
    const result = await projectPlan(candidate);
    plan = candidate;
    $('record-dialog').close();
    touch();
    projection = result;
    renderTables();
    tell('Input applied and projection updated. Save plan to keep these changes.');
  } catch (err) {
    tell(err.message, true);
  }
};
