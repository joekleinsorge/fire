'use strict';
let purchaseEditId=null,purchaseMode='fork',purchaseBase=null,purchaseBaseFingerprint=null;
function purchaseMonthLabel(month,p=plan){const parts=String(p.valuation_date||valuationDate()).split('-').map(Number),date=new Date(parts[0],parts[1]-1+Number(month),1);return date.toLocaleDateString(undefined,{month:'short',year:'numeric'})}
// Purchases store a month offset from the plan baseline; the dialog edits it as a calendar month.
function baselineParts(p=plan){return String(p.valuation_date||valuationDate()).split('-').map(Number)}
function offsetToMonth(offset,p=plan){const [y,m]=baselineParts(p),d=new Date(y,m-1+Number(offset),1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`}
function monthToOffset(value,p=plan){const [y,m]=baselineParts(p),[vy,vm]=String(value).split('-').map(Number);return (vy-y)*12+(vm-m)}
function renderPurchases(){
  const rows=plan.future_purchases||[];
  $('purchase-baseline').textContent=`Baseline ${plan.valuation_date||valuationDate()}. Month 1 is ${purchaseMonthLabel(1)}; all dates move with the baseline.`;
  $('purchase-table').innerHTML=rows.map(row=>`<tr><td><strong>${esc(row.name)}</strong></td><td>${esc(purchaseMonthLabel(row.month))}<small class="row-sub">Month ${row.month}</small></td><td>${money(row.amount)}${row.loan_amount?`<small class="row-sub">${money(row.amount-row.loan_amount)} cash · ${money(row.loan_amount)} borrowed</small>`:''}${row.adds_asset?'<small class="row-sub">Kept as an asset</small>':''}${row.sell_account_id?`<small class="row-sub">Sells ${esc((plan.accounts||[]).find(a=>a.id===row.sell_account_id)?.name||'an asset')}</small>`:''}</td><td>${money(row.annual_upkeep||0)}${row.annual_upkeep?`<small class="row-sub">${row.upkeep_years?`For ${row.upkeep_years} year${row.upkeep_years===1?'':'s'}`:'Ongoing'}</small>`:''}</td><td>${row.enabled===false?'Excluded':'Included'}</td><td class="row-actions"><button class="link-button" data-edit-purchase="${esc(row.id)}">Edit</button><button class="link-button danger-text" data-remove-purchase="${esc(row.id)}">Remove</button></td></tr>`).join('');
  $('purchase-empty').hidden=rows.length>0;
}
function openPurchase(mode,id){
  purchaseMode=mode;purchaseEditId=id||null;purchaseBase=structuredClone(plan);purchaseBaseFingerprint=JSON.stringify(plan);
  const row=(plan.future_purchases||[]).find(p=>p.id===id),fork=mode==='fork';
  $('purchase-dialog-title').textContent=fork?'Try a purchase scenario':row?'Edit future purchase':'Add to current plan';
  $('purchase-name').value=row?.name||'';$('purchase-amount').value=row?.amount??'';$('purchase-month').value=offsetToMonth(row?.month??Math.min(24,plan.horizon*12));$('purchase-month').min=offsetToMonth(1);$('purchase-month').max=offsetToMonth(plan.horizon*12);
  $('purchase-upkeep').value=row?.annual_upkeep??0;$('purchase-upkeep-years').value=row?.upkeep_years??'';$('purchase-loan').value=row?.loan_amount??0;$('purchase-loan-rate').value=((row?.loan_rate??.06)*100).toFixed(2);$('purchase-loan-years').value=Math.round((row?.loan_months??360)/12);$('purchase-asset').checked=!!row?.adds_asset;$('purchase-sell').innerHTML='<option value="">Nothing</option>'+(plan.accounts||[]).filter(a=>a.id).map(a=>`<option value="${esc(a.id)}">${esc(a.name)} · ${money(a.balance)}</option>`).join('');$('purchase-sell').value=row?.sell_account_id||'';$('purchase-sell-cost').value=((row?.sell_cost_rate??.06)*100).toFixed(1);$('purchase-payoff').innerHTML='<option value="">None</option>'+(plan.debts||[]).filter(d=>d.id).map(d=>`<option value="${esc(d.id)}">${esc(d.name)} · ${money(d.balance)}</option>`).join('');$('purchase-payoff').value=row?.payoff_debt_id||'';$('purchase-asset-return').value=((row?.asset_return??0)*100).toFixed(1);$('purchase-enabled').checked=row?.enabled!==false;
  $('purchase-scenario-label').hidden=!fork;$('purchase-scenario-name').required=fork;$('purchase-scenario-name').value='';
  $('purchase-submit').textContent=fork?'Save scenario & compare':'Apply & recalculate';
  $('purchase-mode-note').textContent=fork?'Save a full independent plan and its starting baseline. Your current plan stays as it is. Signed-in scenarios persist with the saved plan; signed-out scenarios last only in this tab.':'Apply this expense to your working plan. The forecast will be recalculated before the change is accepted.';
  $('purchase-advanced').open=!!(row?.loan_amount||row?.sell_account_id||row?.adds_asset);updatePurchaseTiming();previewBase=null;previewRequest++;$('purchase-dialog').showModal();updatePurchasePreview();
}
function updatePurchaseTiming(){const p=purchaseBase||plan,offset=monthToOffset($('purchase-month').value,p);$('purchase-timing').textContent=Number.isFinite(offset)&&offset>=1?`${offset} month${offset===1?'':'s'} after your ${p.valuation_date} baseline`:`Choose a month after your ${p.valuation_date} baseline`}
$('purchase-month').oninput=updatePurchaseTiming;
$('add-purchase').onclick=()=>openPurchase('current');$('fork-purchase').onclick=()=>openPurchase('fork');
$('purchase-close').onclick=$('purchase-cancel').onclick=()=>$('purchase-dialog').close();
function purchaseMetrics(p,r){const short=r.summary?.first_shortfall_age;return [r.earliest_fi_age,r.fi_age??(r.years_to_target==null?null:Number(p.age)+r.years_to_target),short==null?null:Math.floor(short),r.target,r.summary?.retirement_available_balance,r.summary?.ending_assets,r.summary?.ending_net_worth,r.summary?.total_unfunded]}
function purchaseComparisonHTML(left,right,results,leftName,rightName){
  const currency=p=>p.currency||'USD',format=(n,p)=>n==null?'—':new Intl.NumberFormat(undefined,{style:'currency',currency:currency(p),maximumFractionDigits:0}).format(n),values=[purchaseMetrics(left,results[0]),purchaseMetrics(right,results[1])];
  const labels=['Age assets first reach FI target','FI age (at or after planned retirement)','Age money first runs short','FI target','Spendable assets at planned retirement','End-of-plan assets','End-of-plan net worth','Total unfunded spending'];
  const compatible=currency(left)===currency(right)&&(results[0].metadata?.price_basis===results[1].metadata?.price_basis);
  return `<div class="table-scroll"><table class="purchase-comparison"><thead><tr><th>Outcome</th><th>${esc(leftName)}</th><th>${esc(rightName)}</th><th>Change</th></tr></thead><tbody>${labels.map((label,i)=>{const a=values[0][i],b=values[1][i],age=i<3,cell=(v,p)=>age?v==null?(i===2?'Never':'Not reached'):String(v):format(v,p),delta=a==null||b==null||!compatible?'—':age?(b===a?'No change':`${b-a>0?'+':''}${b-a} year${Math.abs(b-a)===1?'':'s'}`):`${b-a>0?'+':''}${format(b-a,right)}`;return `<tr><th>${label}</th><td>${cell(a,left)}</td><td>${cell(b,right)}</td><td>${delta}</td></tr>`}).join('')}</tbody></table></div><p class="small-note">Planned retirement ages: ${left.age==null?'—':left.retirement_age} / ${right.retirement_age}. A one-time purchase reduces assets; ongoing upkeep can also increase your FI target. “Age assets first reach FI target” is the first modeled year-end with spendable assets at the target, even before your planned retirement. FI age is the first such year-end at or after planned retirement; neither is an optimized retirement date.</p>`;
}
async function comparePurchaseScenario(s,precomputed){
  const data=s.data||s,left=structuredClone(data.baseline_plan||plan),right=structuredClone(data.plan),results=precomputed||await Promise.all([projectPlan(left),projectPlan(right)]);
  $('comparison-panel').hidden=false;$('comparison-chart').innerHTML=chartForCompare(results);
  $('comparison-cards').innerHTML=purchaseComparisonHTML(left,right,results,data.baseline_plan?'Saved starting baseline':left.name||'Current plan',scenarioName(s));
  $('comparison-cards').classList.add('purchase-comparison-wrap');
  $('comparison-panel').scrollIntoView({behavior:'smooth'});
}
async function acceptPurchasePlan(candidate,startingFingerprint){
  const result=await projectPlan(candidate);
  if(JSON.stringify(plan)!==startingFingerprint)throw Error('Your working plan changed during calculation. Try again using the updated plan.');
  plan=candidate;touch();projection=result;simulation=null;renderTables();
  $('save-state').textContent='Unsaved changes · projection current';$('save-state').classList.add('dirty');
}
function readPurchaseRow(forPreview=false){
  const row={id:purchaseEditId||uid(),name:$('purchase-name').value.trim(),amount:Number($('purchase-amount').value),month:monthToOffset($('purchase-month').value,purchaseBase),annual_upkeep:Number($('purchase-upkeep').value),enabled:$('purchase-enabled').checked};
  const years=$('purchase-upkeep-years').value.trim(),loan=Number($('purchase-loan').value||0);
  if(years)row.upkeep_years=Number(years);
  if(loan){row.loan_amount=loan;row.loan_rate=Number($('purchase-loan-rate').value)/100;row.loan_months=Number($('purchase-loan-years').value)*12}
  if($('purchase-sell').value){row.sell_account_id=$('purchase-sell').value;row.sell_cost_rate=Number($('purchase-sell-cost').value)/100}
  if($('purchase-payoff').value){if(!row.sell_account_id)throw Error('Choose an asset to sell before paying off a debt from the sale.');row.payoff_debt_id=$('purchase-payoff').value}
  if($('purchase-asset').checked){row.adds_asset=true;row.asset_return=Number($('purchase-asset-return').value)/100}
  if(!row.name){if(!forPreview)throw Error('Enter a purchase name.');row.name='Preview'}
  if(!Number.isInteger(row.month)||row.month<1)throw Error('Choose a purchase month after the plan baseline.');
  if(loan>row.amount)throw Error('The amount borrowed cannot exceed the purchase cost.');
  return row;
}
function purchaseCandidate(row){const candidate=structuredClone(purchaseBase),rows=candidate.future_purchases||[],index=rows.findIndex(p=>p.id===row.id);if(index<0)rows.push(row);else rows[index]=row;candidate.future_purchases=rows;return candidate}
// Live preview: re-project the candidate as the dialog changes; stale responses are dropped.
let previewTimer=null,previewRequest=0,previewBase=null;
function previewAge(value){return value==null?'not reached':`age ${value}`}
function previewDelta(before,after,unit){if(before==null||after==null||before===after)return '';const d=after-before;return ` (${d>0?'+':''}${unit==='years'?`${d} year${Math.abs(d)===1?'':'s'}`:money(d)})`}
async function updatePurchasePreview(){
  const box=$('purchase-preview'),request=++previewRequest;
  let row;try{row=readPurchaseRow(true)}catch(err){box.className='purchase-preview muted';box.textContent=$('purchase-amount').value?err.message:'Enter a cost and month to preview the effect on your plan.';return}
  if(!$('purchase-amount').value){box.className='purchase-preview muted';box.textContent='Enter a cost and month to preview the effect on your plan.';return}
  box.className='purchase-preview muted';box.textContent='Updating preview…';
  try{
    const [base,next]=await Promise.all([previewBase||(previewBase=projectPlan(purchaseBase)),projectPlan(purchaseCandidate(row))]);
    if(request!==previewRequest)return;
    const short=r=>r.summary?.first_shortfall_age==null?null:Math.floor(r.summary.first_shortfall_age),lines=[
      next.earliest_fi_age==null?`Assets <strong>never reach</strong> your FI target${base.earliest_fi_age!=null?` (now ${previewAge(base.earliest_fi_age)})`:''}`:`Assets reach your FI target at <strong>${previewAge(next.earliest_fi_age)}</strong>${previewDelta(base.earliest_fi_age,next.earliest_fi_age,'years')}`,
      `FI target <strong>${money(next.target)}</strong>${previewDelta(base.target,next.target)}`,
      `Spendable at planned retirement <strong>${money(next.summary?.retirement_available_balance)}</strong>${previewDelta(base.summary?.retirement_available_balance,next.summary?.retirement_available_balance)}`];
    if(short(next)!=null)lines.push(`<span class="danger-text">Money first runs short at age ${short(next)}</span>`);
    box.className='purchase-preview'+(short(next)!=null?' warn':'');box.innerHTML=`<span class="eyebrow">PREVIEW · NOT SAVED</span>${lines.map(l=>`<span>${l}</span>`).join('')}`;
  }catch(err){if(request===previewRequest){box.className='purchase-preview muted';box.textContent=err.message}}
}
$('purchase-form').addEventListener('input',()=>{clearTimeout(previewTimer);previewTimer=setTimeout(updatePurchasePreview,350)});
$('purchase-form').addEventListener('change',()=>{clearTimeout(previewTimer);previewTimer=setTimeout(updatePurchasePreview,150)});
$('purchase-form').onsubmit=async e=>{
  e.preventDefault();if(!$('purchase-form').reportValidity())return;
  const button=$('purchase-submit');button.disabled=true;
  try{
    const candidate=purchaseCandidate(readPurchaseRow());
    if(purchaseMode==='fork'){
      const name=$('purchase-scenario-name').value.trim();if(!name)throw Error('Enter a scenario name.');candidate.name=name;
      const results=await Promise.all([projectPlan(purchaseBase),projectPlan(candidate)]);
      if(JSON.stringify(plan)!==purchaseBaseFingerprint)throw Error('Your working plan changed during calculation. Reopen the purchase dialog to use the updated baseline.');
      const data={name,plan:candidate,baseline_plan:structuredClone(purchaseBase)};
      if(user){if(!saved&&!(await savePlan()))throw Error('Save the baseline plan to create a persistent scenario.');await api(`/api/plans/${saved.id}/scenarios`,data);await refreshScenarios()}else{scenarios.push({id:uid(),...data});renderScenarios()}
      $('purchase-dialog').close();go('scenarios');await comparePurchaseScenario(data,results);
      tell(user?'Purchase scenario saved with its starting baseline.':'Purchase scenario saved for this tab only. Sign in to save persistently.');
    }else{await acceptPurchasePlan(candidate,purchaseBaseFingerprint);$('purchase-dialog').close();tell('Future purchase applied and every forecast recalculated.')}
  }catch(err){tell(err.message,true)}finally{button.disabled=false}
};
document.addEventListener('click',async e=>{
  const edit=e.target.closest('[data-edit-purchase]'),remove=e.target.closest('[data-remove-purchase]');
  if(edit)openPurchase('current',edit.dataset.editPurchase);
  if(remove&&confirm('Remove this future purchase from your working plan?')){try{const fingerprint=JSON.stringify(plan),candidate=structuredClone(plan);candidate.future_purchases=(candidate.future_purchases||[]).filter(p=>p.id!==remove.dataset.removePurchase);await acceptPurchasePlan(candidate,fingerprint);tell('Purchase removed and forecast recalculated.')}catch(err){tell(err.message,true)}}
});
renderPurchases();
