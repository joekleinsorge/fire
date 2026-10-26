'use strict';
// Startup: loads after every feature script so the first render includes them all.
async function startup() {
  const hour = new Date().getHours();
  $('greeting').textContent =
    `${hour < 5 ? 'Good evening' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'}. Here's your plan.`;
  fillQuick();
  fillAssumptions();
  $('plan-name').value = plan.name;
  $('valuation-date').value = plan.valuation_date;
  renderTables();
  $('observation-date').value = new Date().toISOString().slice(0, 10);
  let reopen = null;
  try {
    const d = await api('/api/auth/me');
    user = d.user;
    updateAuth();
    const plans = await loadPlans();
    reopen = (plans.find(p => p.id === rememberedPlan()) || plans[0])?.id;
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
startup().finally(offerDraft);
