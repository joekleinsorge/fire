'use strict';
// Review information is presented alongside outputs; unknown facts never
// become zero-valued modeled purchases or synthetic child birth dates.
let showHistoricalScenarios=false,scenarioGroup='All',latestScenarioRuns=[],scenarioResultsLoading=false;
function planningRuns(){return [...runHistory,...latestScenarioRuns].sort((a,b)=>b.created-a.created||b.id.localeCompare(a.id))}
function planningPanel(id,view){
  let panel=$(id);
  if(!panel){panel=document.createElement('article');panel.id=id;panel.className='panel planning-review';const parent=$(`view-${view}`);parent.insertBefore(panel,parent.children[1]||null)}
  return panel;
}
function renderPlanningReview(){
  const review=plan.planning_review||{},missing=review.blockers||[];
  const panel=planningPanel('planning-readiness','overview');
  panel.hidden=!missing.length&&!review.reviewed_on;
  panel.innerHTML=`<p class="eyebrow">PLAN QUALITY</p><h2>${missing.length?'Draft — confirm remaining inputs':'Reviewed assumptions'}</h2><p>${missing.length?`${missing.length} open items can change the result. A completed calculation means the model ran; it does not confirm affordability or retirement readiness.`:'Review the assumptions and source dates before using these estimates.'}</p>${missing.length?`<details><summary>What still needs confirmation</summary><ul>${missing.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}<p class="small-note">Valuation ${esc(plan.valuation_date)} · ${esc(review.source_date_note||'Account balances retain their recorded source dates.')}</p><button class="link-button" data-planning-jump="inputs">Review plan inputs ↗</button>`;
  const c=plan.compensation_summary;if(c)panel.insertAdjacentHTML('beforeend',`<p><strong>${money(c.gross_base_annual)} base + ${money(c.gross_bonus_annual)} target bonus.</strong> Estimated net: ${money(c.net_base_monthly)}/month base and ${money(c.net_bonus_quarterly)}/quarter bonus. MFJ · Florida · ${esc(c.children)} children. <button class="link-button" data-planning-jump="cashflow">Review income ↗</button></p>`);const pay=planningPanel('compensation-review','cashflow');pay.hidden=!c;
  if(c)pay.innerHTML=`<p class="eyebrow">HOUSEHOLD COMPENSATION</p><h2>${money(c.gross_base_annual)} base + ${money(c.gross_bonus_annual)} target bonus</h2><p>Married filing jointly · Florida · ${esc(c.children)} reported children · ${money(c.spouse_income_annual)} spouse earned income in stored profile.</p><div class="summary-strip"><div><span>Gross target compensation / year</span><strong>${money(c.gross_base_annual+c.gross_bonus_annual)}</strong></div><div><span>Estimated net base / month</span><strong>${money(c.net_base_monthly)}</strong></div><div><span>Estimated net bonus / quarter</span><strong>${money(c.net_bonus_quarterly)}</strong></div></div><p class="small-note">${esc(c.notes)}</p><p class="small-note">Payroll retirement deposits: ${money(c.payroll_retirement_annual)}/year, already withheld from the estimated take-home figures. They are deposited separately into the 401(k) forecast.</p>`;
  const assumptions=planningPanel('planning-assumptions','inputs');assumptions.hidden=!(review.assumptions||[]).length;
  assumptions.innerHTML=`<h2>Assumptions used in the current comparisons</h2><ul>${(review.assumptions||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
  const kids=planningPanel('reported-family','children'),reported=plan.household_source?.planner_inputs?.household?.children?.ages||[];
  kids.hidden=!reported.length||(plan.members||[]).length>=reported.length;const familyDate=plan.household_source?.source?.as_of||'date unconfirmed';const educationDeposit=(plan.accounts||[]).filter(a=>a.source_details?.type==='education_restricted').reduce((n,a)=>n+Number(a.household_contribution_monthly||0),0)||plan.household_source?.planner_inputs?.education_goal?.observed_monthly_contribution_usd;
  kids.innerHTML=`<h2>Reported family and account status</h2><p class="small-note">Ages below are from the stored household profile, not calculated from birth dates. Birth dates and beneficiaries remain unconfirmed.</p><div class="table-scroll"><table><thead><tr><th>Child</th><th>Reported age</th><th>Birth date</th><th>529 beneficiary</th><th>Trump Account</th></tr></thead><tbody>${reported.map((age,i)=>`<tr><td>Child ${i+1} · name not provided</td><td>${esc(age)} as of ${esc(familyDate)}</td><td>Not provided</td><td>Not mapped</td><td>Status and eligibility unconfirmed</td></tr>`).join('')}</tbody></table></div><p class="small-note">The combined 529 holding is counted once and remains restricted. ${educationDeposit!=null?`Reported ${money(educationDeposit)}/month funding is budgeted;`:'Contribution amount needs confirmation;'} beneficiary projections need the missing mapping. No Trump Account balance, deposit or pilot eligibility is assumed.</p>`;
  if(missing.length&&projection)$('health-status').textContent='Draft — inputs need confirmation';if(projection)$('fi-age-note').textContent='Reference target crossing; use retirement cash-flow tests to judge timing';
}
const baseRenderTables=renderTables;
renderTables=function(){baseRenderTables();renderPlanningReview()};
document.addEventListener('click',e=>{const jump=e.target.closest('[data-planning-jump]');if(jump)go(jump.dataset.planningJump)});

function archivedScenarioIds(){return new Set(plan.archived_scenario_ids||[])}
renderScenarios=function(){
  const archived=archivedScenarioIds(),all=[...scenarios],groups=[...new Set(all.filter(s=>!archived.has(s.id)).map(s=>s.data?.metadata?.group||'Other'))],visible=all.filter(s=>(showHistoricalScenarios||!archived.has(s.id))&&(scenarioGroup==='All'||(s.data?.metadata?.group||'Other')===scenarioGroup));
  let controls=$('scenario-history-controls');
  if(!controls){controls=document.createElement('div');controls.id='scenario-history-controls';controls.className='scenario-history-controls';$('scenario-list').before(controls)}
  controls.innerHTML=`<label>Scenario group <select id="scenario-group">${['All',...groups].map(g=>`<option ${g===scenarioGroup?'selected':''}>${esc(g)}</option>`).join('')}</select></label><p>${visible.length} scenarios shown · ${all.filter(s=>archived.has(s.id)).length} earlier drafts kept in history</p><label class="check-label"><input id="show-historical-scenarios" type="checkbox" ${showHistoricalScenarios?'checked':''}> Show earlier drafts and calculations</label>`;
  $('scenario-group').onchange=e=>{scenarioGroup=e.target.value;renderScenarios()};$('show-historical-scenarios').onchange=e=>{showHistoricalScenarios=e.target.checked;renderScenarios();renderRunHistory()};
  const wrap=$('scenario-list');wrap.innerHTML='';
  if(!visible.length){wrap.innerHTML='<div class="panel empty-state">No current scenarios saved.</div>';return}
  for(const s of visible){
    const p=scenarioPlan(s),md=s.data?.metadata||{},needs=md.status==='needs_inputs';
    const latest=planningRuns().find(r=>r.scenario_id===s.id&&r.kind==='project'),result=latest?.result,summary=result?.summary||{};
    const el=document.createElement('article');el.className='panel scenario-card';
    const cost=md.purchase_summary;const event=summary.purchase_events?.find(e=>e.id===cost?.purchase_id);
    el.innerHTML=`<span class="scenario-tag">${archived.has(s.id)?'EARLIER DRAFT':needs?'NEEDS INPUTS':'SAVED COMPARISON'}</span><h2>${esc(scenarioName(s))}</h2><p>${esc(md.rationale||md.notes||md.purpose||'')}</p>${needs?`<p class="method-note">${esc((md.missing_inputs||[]).join(' · '))}</p>`:''}${md.budget_analysis?`<p class="method-note">Highest living budget found in this bounded fixed-return search: ${money(md.budget_analysis.annual_living_budget)} per year. Minimum acceptable in this case: ${money(md.budget_analysis.minimum_acceptable_annual)}. ${md.budget_analysis.acceptable?'At or above the entered floor; still requires risk and input review.':'Below the entered floor or still unfunded — this does not meet your lifestyle requirement.'} Healthcare,capital allowances and taxes remain additional.</p>`:''}${cost?`<div class="summary-strip"><div><span>Cash needed after home sale</span><strong>${money(event?.required_cash_after_sale??cost.cash_needed_after_sale)}</strong></div><div><span>Mortgage principal & interest / month</span><strong>${money(cost.principal_interest_monthly)}</strong></div><div><span>Tax, insurance, HOA & upkeep / year</span><strong>${money(cost.annual_carrying_cost)}</strong></div></div><p class="small-note">${esc(cost.notes)}</p>`:''}${saved&&s.data?.base_version!==saved.version?`<p class="method-note">Snapshot uses household version ${esc(s.data?.base_version)}; current household is version ${esc(saved.version)}. This comparison retains its earlier inputs.</p>`:''}<p class="small-note">Retirement age ${esc(p.retirement_age)} · baseline version ${esc(s.data?.base_version??'unrecorded')} · ${esc(p.valuation_date)}</p><div class="scenario-result">${needs?'Not calculated — required inputs are missing':latest?`${esc(latest.status)} · engine ${esc(result?.metadata?.engine_version||'—')}`:scenarioResultsLoading?'Loading saved calculation…':'No saved calculation yet'}${summary.blocked_purchases?`<p>A planned closing or payoff was blocked. Funding gap including the entered reserve: <strong>${money(summary.purchase_funding_gap)}</strong>. Unfunded transactions are not executed.</p>`:''}${summary.conversion_gross||summary.blocked_conversions?`<p>Roth conversions completed: ${money(summary.conversion_gross)}; conversion tax ${money(summary.conversion_tax)}; blocked events ${summary.blocked_conversions||0}.</p>`:''}${result?`<p>Essential retirement spending: ${result.essential_spending_funded===true?'funded in this fixed-return case':result.essential_spending_funded===false?'shortfall in this fixed-return case':'not available'}. ${summary.first_shortfall_age!=null?'First modeled shortfall at age '+Number(summary.first_shortfall_age).toFixed(1)+'.':''}</p>`:''}</div><div class="button-row">${latest?`<button class="button secondary" data-open-planning-run="${esc(latest.id)}">View results and assumptions</button>`:''}${needs?'':`<button class="button text-button" data-run-scenario="${esc(s.id)}">Run projection</button><button class="button text-button" data-run-scenario="${esc(s.id)}" data-run-kind="simulate">Run simulation</button>`}<button class="button text-button" data-open-scenario="${esc(s.id)}">Open inputs</button></div>`;
    wrap.append(el);
  }
};
const baseRenderRunHistory=renderRunHistory;
renderRunHistory=function(){const all=runHistory;try{if(!showHistoricalScenarios)runHistory=all.filter(r=>!archivedScenarioIds().has(r.scenario_id));baseRenderRunHistory()}finally{runHistory=all}};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-open-planning-run]');if(b){try{const {job}=await api(`/api/jobs/${encodeURIComponent(b.dataset.openPlanningRun)}`);renderSavedRun(job);$('run-detail').scrollIntoView({behavior:'smooth'})}catch(err){tell(err.message,true)}}});
const baseRenderSavedRun=renderSavedRun;
renderSavedRun=function(job){baseRenderSavedRun(job);if(job.result?.metadata?.engine_version!=='2.3.0'){$('run-detail').insertAdjacentHTML('afterbegin','<p class="method-note">Historical calculation: this result predates the current tax,basis,RMD,conversion and source-input model. Open a current comparison for the revised model.</p>')}};

// Refresh saved data when returning to this tab, while preserving unsaved edits.
let checkingPlanVersion=false;
async function checkSavedPlanVersion(){
  if(!saved||!user||document.hidden||checkingPlanVersion)return;
  checkingPlanVersion=true;
  try{const head=await api(`/api/plans/${encodeURIComponent(saved.id)}`);if(head.version>saved.version){if(workingDirty){tell(`Saved version ${head.version} is available. Export your unsaved edits or reload the saved plan.`,true)}else await $('saved-plans').onchange({target:{value:saved.id}})}}catch{}finally{checkingPlanVersion=false}
}
window.addEventListener('focus',checkSavedPlanVersion);
document.addEventListener('visibilitychange',checkSavedPlanVersion);
renderPlanningReview();

const advancedCosts=document.createElement('div');advancedCosts.className='form-grid';
advancedCosts.innerHTML='<label>Buyer closing and moving costs<input id="purchase-transaction-costs" type="number" min="0" step="any" value="0"></label><label>Minimum liquid reserve after closing<input id="purchase-liquid-reserve" type="number" min="0" step="any" value="0"></label><label class="check-label"><input id="purchase-nominal-loan" type="checkbox">Fixed nominal mortgage (apply plan inflation)</label><label>Existing essential costs replaced per month<input id="purchase-replaced-expenses" type="number" min="0" step="any" value="0"></label><label>Current housing costs replaced in retirement / month<input id="purchase-retirement-replaced" type="number" min="0" step="any" value="0"></label><label>Replacement ends at month index (exclusive)<input id="purchase-replaced-end" type="number" min="1" max="1801" value="1801"></label>';
$('purchase-advanced').append(advancedCosts);
const baseOpenPurchase=openPurchase;
openPurchase=function(mode,id){baseOpenPurchase(mode,id);const row=(purchaseBase.future_purchases||[]).find(x=>x.id===id);$('purchase-transaction-costs').value=row?.transaction_costs??0;$('purchase-liquid-reserve').value=row?.minimum_cash_reserve??0;$('purchase-nominal-loan').checked=row?.nominal_loan??true;$('purchase-replaced-expenses').value=row?.replaces_expense_monthly??0;$('purchase-replaced-end').value=row?.replaces_expense_end_month??1801;$('purchase-retirement-replaced').value=row?.replaces_retirement_expense_monthly??0;updatePurchasePreview()};
const baseReadPurchaseRow=readPurchaseRow;
readPurchaseRow=function(preview=false){return {...baseReadPurchaseRow(preview),transaction_costs:Number($('purchase-transaction-costs').value),minimum_cash_reserve:Number($('purchase-liquid-reserve').value),nominal_loan:$('purchase-nominal-loan').checked,replaces_expense_monthly:Number($('purchase-replaced-expenses').value),replaces_expense_end_month:Number($('purchase-replaced-end').value),replaces_retirement_expense_monthly:Number($('purchase-retirement-replaced').value)}};
advancedCosts.oninput=()=>updatePurchasePreview();


// Coverage is saved with the household plan; comparisons use durable results.
function renderPlanningCoverage(){
  const rows=plan.planning_coverage||[];
  const panel=planningPanel('planning-coverage','overview');panel.hidden=!rows.length;
  $('view-overview').querySelector('.kpi-grid').after(panel);
  panel.innerHTML=`<p class="eyebrow">YOUR PLANNING CHECKLIST</p><h2>What this plan covers</h2><p>Modeled means an explicit scenario exists. It does not mean a purchase is affordable or the inputs are confirmed.</p><div class="table-scroll"><table><thead><tr><th>Goal</th><th>Coverage</th><th>Included and still needed</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.goal)}</strong>${r.scenario_ids?.length?`<br><button class="link-button" data-coverage-group="${esc(r.group)}">View ${r.scenario_ids.length} comparisons ↗</button>`:''}</td><td>${esc(r.status)}</td><td>${esc(r.note)}</td></tr>`).join('')}</tbody></table></div>`;
  const dates=planningPanel('planning-source-dates','inputs');dates.hidden=!rows.length;
  dates.innerHTML=`<h2>Balance sources and freshness</h2><p>The valuation date anchors the forecast; it does not refresh a bank balance. Report dates and underlying statements can differ.</p><div class="table-scroll"><table><thead><tr><th>Account</th><th>Entered balance</th><th>Latest report</th><th>Underlying statement</th></tr></thead><tbody>${(plan.accounts||[]).map(a=>{const source=a.source_details||{},latest=source.latest_reported_snapshot||{};return `<tr><td>${esc(a.name)}</td><td>${money(a.balance)}</td><td>${esc(latest.reported_on||source.as_of||'Not recorded')}</td><td>${esc(latest.underlying_statement_date||source.as_of||'Not recorded')}</td></tr>`}).join('')}</tbody></table></div>`;
}
const coveredRenderReview=renderPlanningReview;
renderPlanningReview=function(){coveredRenderReview();renderPlanningCoverage()};
const coveredRenderScenarios=renderScenarios;
renderScenarios=function(){
  coveredRenderScenarios();
  const archived=archivedScenarioIds(),active=scenarios.filter(s=>!archived.has(s.id));
  const rows=active.filter(s=>scenarioGroup==='All'||s.data?.metadata?.group===scenarioGroup);
  const base=active.find(s=>scenarioName(s)==='Keep current home — base');
  const baseline=planningRuns().find(r=>r.scenario_id===base?.id&&r.kind==='project'&&r.status==='completed')?.result?.summary;
  let panel=$('scenario-comparison');if(!panel){panel=document.createElement('article');panel.id='scenario-comparison';panel.className='panel';$('scenario-list').before(panel)}
  panel.innerHTML=`<p class="eyebrow">SAVED RESULTS</p><h2>Compare outcomes</h2><p>All amounts are in plan-start purchasing power. Retirement assets below are spendable at the entered retirement age; restricted holdings are excluded. Differences compare with the current-home base case and also reflect any retirement-date changes.</p><div class="table-scroll"><table><thead><tr><th>Scenario</th><th>Retirement age</th><th>Spendable at retirement</th><th>Change vs current-home base</th><th>Purchase funding</th><th>First retirement cash shortfall</th></tr></thead><tbody>${rows.map(s=>{const run=planningRuns().find(r=>r.scenario_id===s.id&&r.kind==='project'&&r.status==='completed'),sum=run?.result?.summary,needs=s.data?.metadata?.status==='needs_inputs',delta=sum&&baseline?sum.retirement_available_balance-baseline.retirement_available_balance:null;return `<tr><td>${run?`<button class="link-button" data-open-planning-run="${esc(run.id)}">${esc(scenarioName(s))}</button>`:esc(scenarioName(s))}</td><td>${esc(scenarioPlan(s).retirement_age)}</td><td>${sum?money(sum.retirement_available_balance):'—'}</td><td>${delta==null?'—':(delta>0?'+':'')+money(delta)}</td><td>${needs?'Needs inputs':!sum?(scenarioResultsLoading?'Loading saved result…':'Not calculated'):sum.blocked_purchases?`Blocked · ${money(sum.purchase_funding_gap)} gap`:'No blocked transactions'}</td><td>${sum?(('first_retirement_shortfall_age' in sum?sum.first_retirement_shortfall_age:sum.first_shortfall_age)==null?'None in fixed case':Number('first_retirement_shortfall_age' in sum?sum.first_retirement_shortfall_age:sum.first_shortfall_age).toFixed(1)):'—'}</td></tr>`}).join('')}</tbody></table></div><p class="small-note">A blocked purchase leaves the household in the existing home. A funded forecast in that case does not establish affordability of the requested purchase. Fixed returns omit sequence risk; review simulations and conservative/adverse cases before acting.</p>`;
};
document.addEventListener('click',e=>{const b=e.target.closest('[data-coverage-group]');if(b){scenarioGroup=b.dataset.coverageGroup;go('scenarios');renderScenarios()}});
renderPlanningCoverage();

const historyRefreshRuns=refreshRuns;
refreshRuns=async function(append=false){
  scenarioResultsLoading=true;renderScenarios();
  try{
    await historyRefreshRuns(append);
    if(!saved){latestScenarioRuns=[];return}
    const id=saved.id;
    if(!append){const result=await api(`/api/plans/${encodeURIComponent(id)}/latest-runs`);if(saved?.id!==id)return;latestScenarioRuns=result.runs||[]}
  }finally{scenarioResultsLoading=false;renderScenarios()}
};
