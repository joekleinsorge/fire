'use strict';
// Progress observations compared with the projection.
async function refreshObservations() {
  if (saved) {
    const d = await api(`/api/plans/${saved.id}/observations`);
    observations = (d.observations || []).map(r => ({ id: r.id, ...r.data }));
  }
  renderObservations();
}
function renderObservations() {
  const rows = [...observations].sort((a, b) => String(b.date).localeCompare(String(a.date)));
  $('observations-table').innerHTML = rows
    .map(
      o =>
        `<tr><td>${esc(o.date)}</td><td>${money(o.balance)}</td><td>${esc(o.note || '—')}</td><td class="row-actions"><button class="link-button danger-text" data-delete-observation="${esc(o.id)}" aria-label="Remove observation from ${esc(o.date)}">Remove</button></td></tr>`,
    )
    .join('');
  $('observations-empty').hidden = rows.length > 0;
  if (!rows.length) {
    $('latest-balance').textContent = '—';
    $('latest-date').textContent = 'No observation yet';
    $('observed-projection').textContent = '—';
    $('observed-difference').textContent = '—';
    return;
  }
  const latest = rows[0];
  $('latest-balance').textContent = money(latest.balance);
  $('latest-date').textContent = latest.date;
  const base = String(plan.valuation_date || '').slice(0, 10),
    obs = String(latest.date || '').slice(0, 10),
    parts = base.match(/^(\d{4})-(\d{2})/) || [],
    date = obs.match(/^(\d{4})-(\d{2})/);
  let months = null;
  if (parts.length && date) months = obs < base ? -1 : (+date[1] - +parts[1]) * 12 + (+date[2] - +parts[2]);
  const estimate = projectedPortfolioAt(months);
  $('observed-projection').textContent =
    estimate == null
      ? months == null
        ? 'Baseline unavailable'
        : months < 0
          ? 'Before plan baseline'
          : 'Outside projection'
      : money(estimate);
  $('observed-difference').textContent = estimate == null ? '—' : money(latest.balance - estimate);
  if (typeof renderProgressChart === 'function') renderProgressChart();
}
// Observations record a portfolio balance, so they are compared with spendable (available) accounts.
function projectedPortfolioAt(months) {
  const rows = projection?.monthly || [];
  if (months == null || months < 0) return null;
  if (months === 0) return calcSnapshot().available;
  return months <= rows.length ? (rows[months - 1]?.available_balance ?? null) : null;
}
function monthsSinceBaseline(day) {
  const base = String(plan.valuation_date || '').slice(0, 10),
    obs = String(day || '').slice(0, 10),
    b = base.match(/^(\d{4})-(\d{2})/),
    d = obs.match(/^(\d{4})-(\d{2})/);
  if (!b || !d) return null;
  return obs < base ? -1 : (+d[1] - +b[1]) * 12 + (+d[2] - +b[2]);
}
$('add-observation').onclick = () => {
  $('observation-date').value = new Date().toISOString().slice(0, 10);
  $('observation-balance').value = '';
  $('observation-note').value = '';
  $('observation-dialog').showModal();
};
$('observation-form').onsubmit = async e => {
  e.preventDefault();
  const observation = {
    date: $('observation-date').value,
    balance: +$('observation-balance').value,
    note: $('observation-note').value,
  };
  try {
    if (user) {
      if (!(await ensureSaved())) return;
      await api(`/api/plans/${saved.id}/observations`, observation);
    } else observations.push({ id: uid(), local: true, ...observation });
    $('observation-dialog').close();
    await refreshObservations();
    tell(user ? 'Observation saved to this plan.' : 'Observation recorded for this session.');
  } catch (err) {
    tell(err.message, true);
  }
};
document.addEventListener('click', async e => {
  const button = e.target.closest('[data-delete-observation]');
  if (!button) return;
  const id = button.dataset.deleteObservation;
  if (!confirm('Remove this progress observation?')) return;
  try {
    if (saved) await api(`/api/plans/${saved.id}/observations/${encodeURIComponent(id)}`, {}, 'DELETE');
    observations = observations.filter(row => row.id !== id);
    renderObservations();
    tell('Progress observation removed.');
  } catch (err) {
    tell(err.message, true);
  }
});
