'use strict';
// Legacy household imports used "other" for several financial holdings.
function isPersonalAsset(account){
  return account.type==='property'||(account.type==='other'&&!['health_savings','employer_equity','education_restricted'].includes(account.source_details?.type));
}
function recordOptionLabel(value,kind){return ({cash:'Cash',investment:'Investment',retirement:'Retirement',property:'Property',other:kind==='asset'?'Other personal asset':'Other financial holding',income:'Income',expense:'Expense'})[value]||value}
function isAvailableAccount(account){return !isPersonalAsset(account)&&((account.available??true)||(account.available_from_age!=null&&Number(plan.age)>=Number(account.available_from_age)))}
function availableValue(row){return Number(row.available_balance??row.balance??0)}
function portfolioValue(row){return Array.isArray(row.accounts)?row.accounts.reduce((n,balance,i)=>n+(plan.accounts[i]&&isPersonalAsset(plan.accounts[i])?0:Number(balance||0)),0):Number(row.balance??row.closing??0)}
function flowMonth(offset){const [year,month]=String(plan.valuation_date||valuationDate()).split('-').map(Number),d=new Date(year,month-1+Number(offset),1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`}
function flowOffset(value){const [year,month]=String(plan.valuation_date||valuationDate()).split('-').map(Number),[y,m]=String(value).split('-').map(Number);return (y-year)*12+m-month}
function flowDateLabel(offset){const d=new Date(`${flowMonth(offset)}-01T00:00:00`);return d.toLocaleDateString(undefined,{month:'short',year:'numeric'})}
const reviewLabels={current_verified_take_home_pay:['Verified take-home pay','cashflow'],mortgage_remaining_term:['Mortgage term remaining','accounts'],mortgage_payment_escrow_split:['Mortgage payment and escrow split','accounts'],RSU_vesting_and_liquidity:['Employer equity vesting and liquidity','accounts'],SEP_IRA_current_balance_and_holdings:['SEP IRA balance and holdings','accounts'],'529_beneficiary_mapping_and_holdings':['529 beneficiaries and holdings','children'],retirement_spending_tax_basis:['Retirement spending and tax assumptions','cashflow'],pre_medicare_healthcare_cost:['Healthcare before Medicare','cashflow'],vehicle_replacement_reserve:['Vehicle replacement budget','purchases'],home_capital_reserve:['Home maintenance and project reserve','purchases'],social_security_estimates:['Social Security income estimates','cashflow'],tax_return_and_IRA_basis:['Tax return and IRA basis','inputs']};
function renderInputs(){
  if(document.activeElement!==$('plan-notes'))$('plan-notes').value=plan.metadata?.notes||'';
  const entries=Object.entries(plan.unresolved_inputs||{}),missing=entries.filter(([,v])=>v==null||v==='').length;
  $('input-review-count').textContent=missing?`${missing} inputs still need confirmation`:'';
  $('input-review-panel').hidden=!entries.length&&!plan.import_warnings?.length;
  $('input-review-list').innerHTML=entries.map(([key,value])=>{const [label,view]=reviewLabels[key]||[key.replaceAll('_',' '),'inputs'],text=value==null?'':typeof value==='string'?value:JSON.stringify(value);return `<div class="input-review-row"><label>${esc(label)}<textarea rows="2" data-review-input="${esc(key)}" placeholder="Unknown — add confirmed information when available">${esc(text)}</textarea></label><button class="link-button" data-input-jump="${view}">Edit modeled input ↗</button></div>`}).join('');
  $('import-cautions').hidden=!plan.import_warnings?.length;
  $('import-cautions-list').innerHTML=(plan.import_warnings||[]).map(w=>`<li>${esc(w.replace('See the source profile.','Review the missing inputs above.'))}</li>`).join('');
  if(!saved)$('api-sync-state').textContent='';$('api-base').textContent=location.origin+'/api';$('api-plan-id').textContent=saved?.id||'Save a plan first';
}
function initializeInputs(){
  $('plan-notes').oninput=e=>{plan.metadata={...plan.metadata,notes:e.target.value};markDirty()};
  $('input-review-list').onchange=e=>{const key=e.target.dataset.reviewInput;if(!key)return;plan.unresolved_inputs[key]=e.target.value.trim()||null;markDirty();$('input-review-count').textContent=Object.values(plan.unresolved_inputs).some(v=>v==null||v==='')?'Some inputs still need confirmation':''};
  $('input-review-list').onclick=e=>{const b=e.target.closest('[data-input-jump]');if(b)go(b.dataset.inputJump)};
  $('reload-plan').onclick=()=>{if(!saved){tell('Open a saved plan first.',true);return}$('saved-plans').onchange({target:{value:saved.id}})};
}
