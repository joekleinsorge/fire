'use strict';
// Plan checkup: rule-of-thumb health checks on the working plan, and a ranked list of
// concrete moves, each projected on a copy of the plan so its effect is measured by the
// engine rather than estimated. Nothing changes until the user applies a move.

let checkupFingerprint = null, checkupRequest = 0, checkupMoves = [];

const isCash = a => (a.type || 'investment') === 'cash' && isAvailableAccount(a);
const isInvested = a => ['investment', 'retirement'].includes(a.type || 'investment') && !isPersonalAsset(a);
// Mirrors the engine's tax-efficient ranking: treatment first, else account type.
const orderRank = a =>
  a.tax_treatment
    ? ({ cash: 0, taxable: 1, pretax: 2, roth_qualified: 3 })[a.tax_treatment] ?? 4
    : ({ cash: 0, investment: 1, retirement: 2 })[a.type || 'investment'] ?? 1;
// True when the tax-efficient order would draw spendable accounts in a different order.
function taxOrderDiffers(p) {
  const ranks = (p.accounts || []).filter(isAvailableAccount).map(orderRank);
  return p.withdrawal_order !== 'tax_efficient' && ranks.some((r, i) => i && r < ranks[i - 1]);
}
const liveDebts = p => (p.debts || []).filter(d => (+d.balance || 0) > 0 && !d.balance_only);

// Monthly totals of streams active in month 1, split by essential status.
function monthlyNow(p = plan) {
  const out = {income: 0, expense: 0, essential: 0};
  for (const s of p.streams || []) {
    if (s.enabled === false || (+s.start_month || 1) > 1 || (s.end_month != null && +s.end_month <= 1)) continue;
    const m = (+s.amount || 0) / (+s.every_months || 12);
    if (s.kind === 'income') out.income += m;
    else {
      out.expense += m;
      if (s.essential) out.essential += m;
    }
  }
  return out;
}

function debtPayment(d) {
  if (d.payment != null && d.payment !== '') return +d.payment || 0;
  const r = (+d.annual_rate || 0) / 12, n = +d.months || 360, b = +d.balance || 0;
  return r ? (b * r) / (1 - (1 + r) ** -n) : b / n;
}

// Each check: {tone: 'good'|'watch'|'act', title, detail}. Thresholds are common rules of thumb.
function planChecks(p = plan, result = projection) {
  const checks = [], now = monthlyNow(p);
  const debts = liveDebts(p);
  const debtMonthly = debts.reduce((t, d) => t + debtPayment(d) + (+d.extra_payment || 0), 0);
  const outflow = now.expense + debtMonthly;
  const essentialOut = now.essential + debtMonthly;

  const cash = (p.accounts || []).filter(isCash).reduce((t, a) => t + (+a.balance || 0), 0);
  if (essentialOut > 0) {
    const months = cash / essentialOut;
    checks.push(months < 3
      ? {tone: 'act', title: 'Build an emergency fund', detail: `Cash covers ${months.toFixed(1)} months of essential costs and debt payments. Three to six months (${money(essentialOut * 3)}–${money(essentialOut * 6)}) cushions a job loss without selling investments.`}
      : months > 24 && +p.retirement_age - +p.age > 5
        ? {tone: 'watch', title: 'Cash may be sitting idle', detail: `Cash covers ${Math.round(months)} months of essential costs. Beyond a reserve, cash usually earns less than inflation over long periods.`}
        : {tone: 'good', title: 'Emergency fund in place', detail: `Cash covers ${months.toFixed(1)} months of essential costs and debt payments.`});
  }

  const costly = debts.filter(d => (+d.annual_rate || 0) >= 0.07).sort((a, b) => b.annual_rate - a.annual_rate);
  if (costly.length) {
    const d = costly[0];
    checks.push({tone: 'act', title: 'Pay down high-interest debt', detail: `${d.name || 'A debt'} charges ${pct(d.annual_rate)} on ${money(d.balance)}. Paying it off early is a guaranteed return few investments match.`});
  } else if (debts.length) {
    checks.push({tone: 'good', title: 'No high-interest debt', detail: 'Every debt charges less than 7% a year.'});
  }

  if (now.income > 0) {
    const rate = (now.income - outflow) / now.income;
    checks.push(rate < 0
      ? {tone: 'act', title: 'Spending exceeds take-home pay', detail: `Expenses and debt payments run ${money(-(now.income - outflow) * 12)} a year over income, which draws down savings.`}
      : rate < 0.1
        ? {tone: 'act', title: 'Savings rate is low', detail: `You keep ${pct(rate)} of take-home pay after spending and debt payments. Raising it toward 15–20% shortens the path to FI more than any return assumption.`}
        : rate < 0.2
          ? {tone: 'watch', title: `Saving ${pct(rate)} of take-home pay`, detail: 'A solid base. Each additional point saved both grows assets and lowers the spending you need to replace.'}
          : {tone: 'good', title: `Saving ${pct(rate)} of take-home pay`, detail: 'A strong savings rate after spending and debt payments.'});
  }

  const invested = (p.accounts || []).filter(isInvested);
  const balance = invested.reduce((t, a) => t + (+a.balance || 0), 0);
  if (balance > 0) {
    const fee = invested.reduce((t, a) => t + (+a.balance || 0) * (+a.fee_rate || 0), 0) / balance;
    if (fee > 0.005) checks.push({tone: 'act', title: 'Investment fees are high', detail: `A weighted ${pct(fee)} a year costs about ${money(balance * fee)} this year alone, and compounds. Broad index funds often charge under 0.1%.`});
    else if (fee > 0.002) checks.push({tone: 'watch', title: `Fees average ${pct(fee)}`, detail: `About ${money(balance * fee)} a year. Lower-cost funds could keep more of your return.`});
    else checks.push({tone: 'good', title: 'Low investment fees', detail: `Fees average ${pct(fee)} a year.`});
  }

  const wr = +p.withdrawal_rate || 0.04;
  if (wr > 0.045) checks.push({tone: 'watch', title: `Withdrawal rate of ${pct(wr)} is aggressive`, detail: 'Rates above about 4% have failed in some historical periods, especially for retirements longer than 30 years. Run a simulation to check.'});

  if (taxOrderDiffers(p))
    checks.push({tone: 'watch', title: 'Withdrawals follow your account list', detail: 'Your list would spend tax-deferred or Roth savings before cash or taxable accounts. A tax-efficient order (cash, taxable, pre-tax, then Roth) usually lowers lifetime tax.'});

  const hasBenefit = (p.social_security || []).some(r => r.enabled !== false) ||
    (p.streams || []).some(s => s.tax_kind === 'social_security' && s.enabled !== false);
  if ((p.currency || 'USD') === 'USD' && !hasBenefit)
    checks.push({tone: 'watch', title: 'No Social Security in the plan', detail: 'If you have earned credits, add the benefit at full retirement age from your statement at ssa.gov; it often covers a large share of retirement spending.'});

  if (result?.first_shortfall_month) {
    const age = result.summary?.first_shortfall_age;
    checks.push({tone: 'act', title: 'Money runs short', detail: `The projection cannot fund spending from ${age != null ? `age ${Math.floor(age)}` : 'a point in the plan'}. Try the moves below, or a later retirement.`});
  }
  return checks;
}

// Candidate moves. Each returns {id, title, detail, plan} or null when it does not apply.
function checkupCandidates(p = plan) {
  const out = [], now = monthlyNow(p), years = Math.max(0, +p.retirement_age - +p.age);
  const add = (id, title, detail, edit) => {
    const copy = structuredClone(p);
    if (edit(copy) !== false) out.push({id, title, detail, plan: copy});
  };

  if (years > 0 && now.income > 0) {
    const extra = Math.max(100, Math.round((now.income * 0.05) / 50) * 50);
    add('save-more', `Save ${money(extra)} more a month`, 'Invested from now until retirement, from a raise, side income or lower costs.', c => {
      c.streams = c.streams || [];
      c.streams.push({id: uid(), name: 'Extra savings (checkup)', kind: 'income', amount: extra, every_months: 1,
        start_month: 1, end_month: years * 12 + 1, enabled: true, growth_rate: 0, essential: false});
    });
  }

  const flexible = (p.streams || []).filter(s => s.kind === 'expense' && s.enabled !== false && !s.essential);
  if (flexible.length)
    add('trim-flexible', 'Trim flexible spending by 20%', `Applies to ${flexible.map(s => s.name || 'unnamed').slice(0, 3).join(', ')}${flexible.length > 3 ? '…' : ''}, now and in retirement.`, c => {
      for (const s of c.streams) if (s.kind === 'expense' && s.enabled !== false && !s.essential) s.amount = Math.round((+s.amount || 0) * 80) / 100;
    });

  const invested = (p.accounts || []).filter(isInvested);
  if (invested.some(a => (+a.fee_rate || 0) > 0.001))
    add('cut-fees', 'Move to low-cost index funds', 'Caps investment and retirement account fees at 0.05% a year.', c => {
      for (const a of c.accounts) if (isInvested(a) && (+a.fee_rate || 0) > 0.0005) a.fee_rate = 0.0005;
    });

  const costly = liveDebts(p).filter(d => (+d.annual_rate || 0) >= 0.06).sort((a, b) => b.annual_rate - a.annual_rate)[0];
  if (costly) {
    const extra = Math.max(100, Math.round(debtPayment(costly) * 0.5 / 50) * 50);
    add('pay-debt', `Pay ${money(extra)} extra a month on ${costly.name || 'your costliest debt'}`, `It charges ${pct(costly.annual_rate)}; extra payments come out of monthly cash flow.`, c => {
      const d = c.debts.find(x => x.id === costly.id) || c.debts[p.debts.indexOf(costly)];
      d.extra_payment = (+d.extra_payment || 0) + extra;
    });
  }

  const debtMonthly = liveDebts(p).reduce((t, d) => t + debtPayment(d) + (+d.extra_payment || 0), 0);
  const reserve = Math.round(((now.essential || now.expense) + debtMonthly) * 6);
  const cashRows = (p.accounts || []).filter(isCash);
  const cash = cashRows.reduce((t, a) => t + (+a.balance || 0), 0);
  const target = (p.accounts || []).find(a => isInvested(a) && isAvailableAccount(a) && orderRank(a) === 1)
    || (p.accounts || []).find(a => isInvested(a) && isAvailableAccount(a));
  if (target && reserve > 0 && cash - reserve > Math.max(5000, reserve * 0.25) && years > 3) {
    const move = Math.round((cash - reserve) / 100) * 100;
    add('invest-cash', `Invest ${money(move)} of extra cash`, `Keeps six months of costs (${money(reserve)}) in cash and moves the rest to ${target.name || 'investments'}.`, c => {
      let left = move;
      for (const a of c.accounts.filter(isCash)) {
        const take = Math.min(left, Math.max(0, +a.balance || 0));
        a.balance = (+a.balance || 0) - take;
        left -= take;
      }
      const t = c.accounts.find(a => a.id === target.id) || c.accounts[p.accounts.indexOf(target)];
      t.balance = (+t.balance || 0) + move - left;
    });
  }

  if (taxOrderDiffers(p))
    add('tax-order', 'Withdraw in a tax-efficient order', 'Cash and after-tax first, then taxable, pre-tax, and Roth last.', c => { c.withdrawal_order = 'tax_efficient'; });

  for (const r of p.social_security || []) {
    if (r.enabled === false || +r.claim_age_years >= 70) continue;
    add(`ss-${r.id}`, `Claim ${r.name || 'Social Security'} at 70`, `Instead of ${r.claim_age_years}${+r.claim_age_months ? ` and ${r.claim_age_months} months` : ''}. Delayed credits raise the benefit for life, and for a surviving spouse.`, c => {
      const row = c.social_security.find(x => x.id === r.id);
      row.claim_age_years = 70;
      row.claim_age_months = 0;
    });
  }
  return out;
}

// Years sooner (positive) that assets first reach the FI target; a plan that newly reaches
// it counts as a full horizon gained, one that no longer reaches it as the reverse.
function yearsGained(base, next, p = plan) {
  const b = base?.earliest_fi_age, n = next?.earliest_fi_age, end = +p.age + +p.horizon;
  return (b ?? end) - (n ?? end);
}

function cushion(r) {
  const bal = r?.summary?.retirement_available_balance, target = r?.target;
  return bal == null || target == null ? null : bal - target;
}

// Rank by FI age gained, then by the retirement cushion (assets at retirement less target).
function rankMoves(base, moves, p = plan) {
  return moves
    .map(m => ({...m, gained: yearsGained(base, m.result, p), cushion: (cushion(m.result) ?? 0) - (cushion(base) ?? 0),
      shortfallFixed: !!base?.first_shortfall_month && !m.result.first_shortfall_month}))
    .filter(m => m.gained > 0 || m.cushion > 1 || m.shortfallFixed)
    .sort((a, b) => b.shortfallFixed - a.shortfallFixed || b.gained - a.gained || b.cushion - a.cushion);
}

function renderChecks() {
  const box = $('checkup-checks');
  if (!box) return;
  const checks = planChecks();
  const order = {act: 0, watch: 1, good: 2};
  checks.sort((a, b) => order[a.tone] - order[b.tone]);
  const label = {act: 'Act', watch: 'Review', good: 'Good'};
  box.innerHTML = checks.map(c => `<li class="check ${c.tone}"><span class="check-tag">${label[c.tone]}</span><div><strong>${esc(c.title)}</strong><small>${esc(c.detail)}</small></div></li>`).join('');
  const act = checks.filter(c => c.tone === 'act').length;
  const score = $('checkup-score');
  score.textContent = act ? `${act} to act on` : checks.some(c => c.tone === 'watch') ? 'Worth a review' : 'Looking good';
  score.className = `status-pill${act ? ' alert' : checks.some(c => c.tone === 'watch') ? '' : ' good'}`;
}

function moveImpact(m) {
  const parts = [];
  if (m.shortfallFixed) parts.push('Removes the shortfall');
  if (m.gained > 0) parts.push(`FI ${m.gained === 1 ? '1 year' : `${m.gained} years`} sooner`);
  if (Math.abs(m.cushion) >= 1) parts.push(`${m.cushion > 0 ? '+' : '−'}${money(Math.abs(m.cushion))} at retirement`);
  return parts;
}

async function renderCheckup() {
  renderChecks();
  const box = $('checkup-moves');
  if (!box || !projection) return;
  const fingerprint = JSON.stringify(plan);
  if (fingerprint === checkupFingerprint) return;
  checkupFingerprint = fingerprint;
  const request = ++checkupRequest, base = projection, candidates = checkupCandidates();
  if (!candidates.length) {
    box.innerHTML = '<li class="move-empty">No standard moves apply to this plan.</li>';
    return;
  }
  box.innerHTML = '<li class="move-empty">Testing each move against your plan…</li>';
  const settled = await Promise.allSettled(candidates.map(c => projectPlan(c.plan)));
  if (request !== checkupRequest) return;
  const tested = candidates.map((c, i) => settled[i].status === 'fulfilled' ? {...c, result: settled[i].value} : null).filter(Boolean);
  checkupMoves = rankMoves(base, tested);
  box.innerHTML = checkupMoves.length
    ? checkupMoves.map((m, i) => `<li class="move"><span class="move-rank">${i + 1}</span><div><strong>${esc(m.title)}</strong><small>${esc(m.detail)}</small></div><div class="move-impact">${moveImpact(m).map(t => `<strong>${esc(t)}</strong>`).join('')}<button class="link-button" type="button" data-apply-move="${esc(m.id)}">Apply</button></div></li>`).join('')
    : '<li class="move-empty">None of the standard moves improves this plan further.</li>';
}

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-apply-move]');
  if (!btn) return;
  const m = checkupMoves.find(x => x.id === btn.dataset.applyMove);
  if (!m) return;
  const before = plan;
  plan = structuredClone(m.plan);
  touch();
  projection = m.result;
  fillAssumptions();
  renderTables();
  tellAction(`Applied: ${m.title}.`, 'Undo', () => {
    plan = before;
    touch();
    fillAssumptions();
    renderTables();
    runProjection();
  });
});
