'use strict';
let runHistory=[],runCursor=null,runPlanId=null,selectedRun=null,runPollTimer=null;
function runMoney(value,currency){return value==null?'—':new Intl.NumberFormat(undefined,{style:'currency',currency:currency||'USD',maximumFractionDigits:0}).format(value)}
function runAge(result,snapshot){return result?.fi_age??(result?.years_to_target==null?null:Number(snapshot?.plan?.age)+result.years_to_target)}
function runHasUnfundedAssetBug(result){return result?.metadata?.engine_version==='2.1.0'&&(result.monthly||[]).some(r=>r.purchase_asset_added>0&&r.purchase_unfunded>1e-8)}
async function refreshRuns(append=false){
  if(!saved){runHistory=[];runCursor=null;runPlanId=null;selectedRun=null;$('run-detail').hidden=true;renderRunHistory();return}
  const id=saved.id;if(!append&&runPlanId!==id){selectedRun=null;$('run-detail').hidden=true}
  const data=await api(`/api/plans/${id}/runs${append&&runCursor?'?before='+encodeURIComponent(runCursor):''}`);
  if(saved?.id!==id)return;runPlanId=id;runHistory=append?[...runHistory,...data.runs]:data.runs;runCursor=data.next_cursor;renderRunHistory();
  if(runHistory.some(r=>['queued','running'].includes(r.status))){clearTimeout(runPollTimer);runPollTimer=setTimeout(()=>{if(saved?.id===id&&$('view-scenarios').classList.contains('active'))refreshRuns().then(renderScenarios).catch(e=>tell(e.message,true))},1200)}
}
function renderRunHistory(){
  $('runs-table').innerHTML=runHistory.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small class="row-sub">${r.scenario_id?'Saved scenario':`Plan version ${r.plan_version??'unknown'}`} · ${esc(r.id.slice(0,8))}</small></td><td>${esc(new Date(r.created*1000).toLocaleString())}</td><td>${r.kind==='simulate'?'Simulation':'Projection'}</td><td>${esc(r.status)}</td><td>${esc(r.result?.metadata?.engine_version||'—')}</td><td><button class="link-button" data-view-run="${esc(r.id)}">View saved run</button></td></tr>`).join('');
  $('runs-empty').hidden=runHistory.length>0;$('runs-empty').textContent=saved?'No logged calculations yet. Save a scenario or log a projection to begin.':'Sign in and save a plan to keep scenarios and calculation history.';
  $('older-runs').hidden=!runCursor;
}
async function watchSavedRun(id,applyToPlan=false,inputSnapshot=null){
  const {job}=await api(`/api/jobs/${encodeURIComponent(id)}`);
  if(['queued','running'].includes(job.status)){setTimeout(()=>watchSavedRun(id,applyToPlan,inputSnapshot).catch(e=>tell(e.message,true)),700);return}
  if(applyToPlan&&inputSnapshot===JSON.stringify(plan)&&job.result){if(job.kind==='project'){projection=job.result;renderTables()}else{simulation=job.result;renderSimulation(simulation)}}
  if(saved?.id===job.plan_id){await refreshRuns();renderScenarios();if(selectedRun?.id===id)renderSavedRun(job)}
  if(job.status==='completed')tell(`Calculation logged. View it later in Scenarios → Calculation history.`);else tell(`Logged calculation ${job.status}: ${job.error||'No completed result.'}`,true);
}
async function startScenarioRun(id,kind='project'){
  if(!saved){openAuth();return}const data={kind,metadata:{origin:'planner UI'}};
  if(kind==='simulate')data.settings=simulationSettings();
  const {job}=await api(`/api/plans/${saved.id}/scenarios/${encodeURIComponent(id)}/run`,data);await refreshRuns();watchSavedRun(job.id).catch(e=>tell(e.message,true));return job;
}
async function logPlanProjection(){
  if(!user){openAuth();tell('Sign in to save and log this calculation.',true);return}
  try{if(!(await savePlan())||workingDirty)return;const fingerprint=JSON.stringify(plan),{job}=await api(`/api/plans/${saved.id}/run`,{kind:'project',version:saved.version,metadata:{origin:'planner UI'}});tell('Projection queued and logged.');watchSavedRun(job.id,true,fingerprint).catch(e=>tell(e.message,true))}catch(e){tell(e.message,true)}
}
function renderSavedRun(job){
  selectedRun=job;const snap=job.snapshot,result=job.result,currency=snap.plan.currency||'USD',money=value=>runMoney(value,currency),name=job.name||'Saved calculation';
  $('run-detail').hidden=false;
  let html=`<div class="panel-head"><div><p class="eyebrow">SAVED CALCULATION</p><h2>${esc(name)}</h2><p class="small-note">${esc(new Date(job.created*1000).toLocaleString())} · ${esc(job.status)} · run ${esc(job.id)} · baseline version ${job.plan_version??'not recorded'}</p></div><button class="link-button" id="close-run">Close</button></div>`;
  html+=`<p class="small-note">Engine ${esc(result?.metadata?.engine_version||snap.submitted_engine_version||'not recorded')} · ${esc(currency)} · valuation ${esc(snap.plan.valuation_date||'not recorded')}</p>`;
  if(runHasUnfundedAssetBug(result))html+='<p class="method-note">This historical run used an older engine that added unpaid property value to net worth. Use a run from engine 2.1.1 or later for corrected asset values. The original result is preserved for your records.</p>';
  for(const meta of [snap.scenario_metadata,snap.metadata])if(meta?.notes||meta?.rationale)html+=`<p>${esc(meta.notes||meta.rationale)}</p>`;
  if(!result)html+=`<p class="method-note">${esc(job.error||'This calculation has not completed. No results are available yet.')}</p>`;
  else if(job.kind==='project'){
    html+=`<div class="summary-strip"><div><span>FI age</span><strong>${runAge(result,snap)??'Not reached'}</strong></div><div><span>FI target</span><strong>${money(result.target)}</strong></div><div><span>Ending net worth</span><strong>${money(result.summary?.ending_net_worth)}</strong></div></div>`;
    if(result.baseline_projection&&snap.baseline_plan)html+=purchaseComparisonHTML(snap.baseline_plan,snap.plan,[result.baseline_projection,result],'Saved baseline',name);
    html+=`<details><summary>Saved annual results</summary><div class="table-scroll"><table><thead><tr><th>Year</th><th>Age</th><th>Available assets</th><th>Net worth</th><th>Unfunded</th></tr></thead><tbody>${(result.annual||[]).map(r=>`<tr><td>${r.year}</td><td>${r.age}</td><td>${money(availableValue(r))}</td><td>${money(r.net_worth)}</td><td>${money(r.unfunded)}</td></tr>`).join('')}</tbody></table></div></details>`;
  }else{
    const outcomes=result.outcomes||{};html+=`<div class="summary-strip">${[['Essential spending funded',outcomes.essential_spending_funded],['Desired lifestyle funded',outcomes.desired_lifestyle_funded],['Portfolio survives',outcomes.portfolio_survives]].map(([label,value])=>`<div><span>${label}</span><strong>${value?.rate==null?'—':pct(value.rate)}</strong><small>${value?.numerator??0} of ${value?.denominator??0} eligible paths</small></div>`).join('')}</div><p class="small-note">${result.completed??0} trials completed · ending asset median ${money(result.ending_assets?.median)} · seed ${esc(snap.settings?.seed??result.metadata?.settings?.seed??'engine default')}</p><details><summary>Saved annual percentile bands</summary><div class="table-scroll"><table><thead><tr><th>Year</th><th>10th percentile</th><th>Median</th><th>90th percentile</th></tr></thead><tbody>${(result.annual_bands||[]).map(r=>`<tr><td>${r.year}</td><td>${money(r.p10)}</td><td>${money(r.median)}</td><td>${money(r.p90)}</td></tr>`).join('')}</tbody></table></div></details>`;
  }
  html+=`<details class="run-assumptions"><summary>Assumptions used in this run</summary><p>Age ${esc(snap.plan.age)} · retirement ${esc(snap.plan.retirement_age)} · ${esc(snap.plan.horizon)} years · default real return ${pct(snap.plan.return_rate)} · withdrawal rate ${pct(snap.plan.withdrawal_rate)}</p><p>${snap.plan.accounts?.length||0} holdings · ${snap.plan.streams?.length||0} cash flows · ${snap.plan.debts?.length||0} debts · ${snap.plan.child_accounts?.length||0} child accounts. Account returns, access rules, schedules, sources, and notes are preserved in the saved inputs.</p><div class="button-row"><button class="button secondary" id="open-run-inputs">Open saved inputs as working copy</button><button class="button secondary" id="download-run-inputs">Download saved inputs</button><button class="button secondary" id="download-run-result">Download saved result</button></div></details><p class="small-note">These are stored results from the original run. Viewing them does not recalculate with today's assumptions or engine.</p>`;
  $('run-detail').innerHTML=html;$('close-run').onclick=()=>$('run-detail').hidden=true;
  $('download-run-inputs').onclick=()=>download(`openfi-run-${job.id}-inputs.json`,JSON.stringify(snap,null,2),'application/json');
  $('download-run-result').onclick=()=>download(`openfi-run-${job.id}-result.json`,JSON.stringify({id:job.id,created:job.created,status:job.status,result:job.result},null,2),'application/json');
  $('open-run-inputs').onclick=()=>{if(workingDirty&&!confirm('Open these saved inputs and replace your unsaved edits?'))return;plan=structuredClone(snap.plan);saved=null;observations=[];scenarios=[];projection=null;simulation=null;fillAssumptions();$('plan-name').value=plan.name||name;$('valuation-date').value=plan.valuation_date;touch();if(job.kind==='project')projection=result;else if(result)simulation=result;renderTables();go('inputs');tell('Opened the exact saved run inputs as an independent working copy. Save to keep edits.')};
}
function initializeRuns(){
  $('refresh-runs').onclick=()=>refreshScenarios().catch(e=>tell(e.message,true));$('older-runs').onclick=()=>refreshRuns(true).catch(e=>tell(e.message,true));
  $('runs-table').onclick=async e=>{const button=e.target.closest('[data-view-run]');if(!button)return;try{const {job}=await api(`/api/jobs/${encodeURIComponent(button.dataset.viewRun)}`);renderSavedRun(job);$('run-detail').scrollIntoView({behavior:'smooth'})}catch(err){tell(err.message,true)}};
  document.addEventListener('click',e=>{const button=e.target.closest('[data-run-scenario]');if(button)startScenarioRun(button.dataset.runScenario,button.dataset.runKind||'project').catch(err=>tell(err.message,true))});
}
