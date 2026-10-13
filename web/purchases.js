'use strict';
let purchaseEditId=null,purchaseMode='fork',purchaseBase=null,purchaseBaseFingerprint=null;
function purchaseMonthLabel(month,p=plan){const parts=String(p.valuation_date||valuationDate()).split('-').map(Number),date=new Date(parts[0],parts[1]-1+Number(month),1);return date.toLocaleDateString(undefined,{month:'short',year:'numeric'})}
function renderPurchases(){
  const rows=plan.future_purchases||[];
  $('purchase-baseline').textContent=`Baseline ${plan.valuation_date||valuationDate()}. Month 1 is ${purchaseMonthLabel(1)}; all dates move with the baseline.`;
  $('purchase-table').innerHTML=rows.map(row=>`<tr><td><strong>${esc(row.name)}</strong></td><td>${esc(purchaseMonthLabel(row.month))}<small class="row-sub">Month ${row.month}</small></td><td>${money(row.amount)}</td><td>${money(row.annual_upkeep||0)}</td><td>${row.enabled===false?'Excluded':'Included'}</td><td class="row-actions"><button class="link-button" data-edit-purchase="${esc(row.id)}">Edit</button><button class="link-button danger-text" data-remove-purchase="${esc(row.id)}">Remove</button></td></tr>`).join('');
  $('purchase-empty').hidden=rows.length>0;
}
function openPurchase(mode,id){
  purchaseMode=mode;purchaseEditId=id||null;purchaseBase=structuredClone(plan);purchaseBaseFingerprint=JSON.stringify(plan);
  const row=(plan.future_purchases||[]).find(p=>p.id===id),fork=mode==='fork';
  $('purchase-dialog-title').textContent=fork?'Try a purchase scenario':row?'Edit future purchase':'Add to current plan';
  $('purchase-name').value=row?.name||'';$('purchase-amount').value=row?.amount??'';$('purchase-month').value=row?.month??Math.min(24,plan.horizon*12);$('purchase-month').max=plan.horizon*12;
  $('purchase-upkeep').value=row?.annual_upkeep??0;$('purchase-enabled').checked=row?.enabled!==false;
  $('purchase-scenario-label').hidden=!fork;$('purchase-scenario-name').required=fork;$('purchase-scenario-name').value='';
  $('purchase-submit').textContent=fork?'Save scenario & compare':'Apply & recalculate';
  $('purchase-mode-note').textContent=fork?'Save a full independent plan and its starting baseline. Your current plan stays as it is. Signed-in scenarios persist with the saved plan; signed-out scenarios last only in this tab.':'Apply this expense to your working plan. The forecast will be recalculated before the change is accepted.';
  updatePurchaseTiming();$('purchase-dialog').showModal();
}
function updatePurchaseTiming(){$('purchase-timing').textContent=`${purchaseMonthLabel($('purchase-month').value,purchaseBase||plan)} · baseline ${(purchaseBase||plan).valuation_date}`}
$('purchase-month').oninput=updatePurchaseTiming;
$('add-purchase').onclick=()=>openPurchase('current');$('fork-purchase').onclick=()=>openPurchase('fork');
$('purchase-close').onclick=$('purchase-cancel').onclick=()=>$('purchase-dialog').close();
function purchaseMetrics(p,r){return [r.earliest_fi_age,r.fi_age??(r.years_to_target==null?null:Number(p.age)+r.years_to_target),r.target,r.summary?.retirement_balance,r.summary?.ending_assets,r.summary?.ending_net_worth,r.summary?.total_unfunded]}
function purchaseComparisonHTML(left,right,results,leftName,rightName){
  const currency=p=>p.currency||'USD',format=(n,p)=>n==null?'—':new Intl.NumberFormat(undefined,{style:'currency',currency:currency(p),maximumFractionDigits:0}).format(n),values=[purchaseMetrics(left,results[0]),purchaseMetrics(right,results[1])];
  const labels=['Age assets first reach FI target','FI age (at or after planned retirement)','FI target','Assets at planned retirement','End-of-plan assets','End-of-plan net worth','Total unfunded spending'];
  const compatible=currency(left)===currency(right)&&(results[0].metadata?.price_basis===results[1].metadata?.price_basis);
  return `<div class="table-scroll"><table class="purchase-comparison"><thead><tr><th>Outcome</th><th>${esc(leftName)}</th><th>${esc(rightName)}</th><th>Change</th></tr></thead><tbody>${labels.map((label,i)=>{const a=values[0][i],b=values[1][i],age=i<2,cell=(v,p)=>age?v==null?'Not reached':String(v):format(v,p),delta=a==null||b==null||!compatible?'—':age?(b===a?'No change':`${b-a>0?'+':''}${b-a} year${Math.abs(b-a)===1?'':'s'}`):`${b-a>0?'+':''}${format(b-a,right)}`;return `<tr><th>${label}</th><td>${cell(a,left)}</td><td>${cell(b,right)}</td><td>${delta}</td></tr>`}).join('')}</tbody></table></div><p class="small-note">Planned retirement ages: ${left.age==null?'—':left.retirement_age} / ${right.retirement_age}. A one-time purchase reduces assets; ongoing upkeep can also increase your FI target. “Age assets first reach FI target” is the first modeled year-end with spendable assets at the target, even before your planned retirement. FI age is the first such year-end at or after planned retirement; neither is an optimized retirement date.</p>`;
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
$('purchase-form').onsubmit=async e=>{
  e.preventDefault();if(!$('purchase-form').reportValidity())return;
  const button=$('purchase-submit');button.disabled=true;
  try{
    const row={id:purchaseEditId||uid(),name:$('purchase-name').value.trim(),amount:Number($('purchase-amount').value),month:Number($('purchase-month').value),annual_upkeep:Number($('purchase-upkeep').value),enabled:$('purchase-enabled').checked};
    if(!row.name)throw Error('Enter a purchase name.');
    const candidate=structuredClone(purchaseBase),rows=candidate.future_purchases||[],index=rows.findIndex(p=>p.id===row.id);if(index<0)rows.push(row);else rows[index]=row;candidate.future_purchases=rows;
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
