'use strict';
// Mirrors fireplanner/social_security.py for the live preview; the engine result is authoritative.
let editingSocialSecurity=null;
const ssAttained=birth=>{const d=new Date(`${birth}T00:00:00`);if(Number.isNaN(d.getTime()))return null;d.setDate(d.getDate()-1);return d};
const ssFra=year=>year<=1954?792:year<=1959?792+2*(year-1954):804;
const ssFactor=(reduction,credits)=>reduction>0?1-(Math.min(reduction,36)*5/9+Math.max(0,reduction-36)*5/12)/100:1+credits*2/3/100;
function ssOption(birth,claim){const d=ssAttained(birth);if(!d)return null;const fra=ssFra(d.getFullYear()),late=d.getDate()!==1?1:0;return {fra,factor:ssFactor(Math.max(0,Math.max(0,fra-claim)-late),Math.max(0,claim-fra))}}
const ssAge=months=>months%12?`${Math.floor(months/12)} and ${months%12} mo`:String(months/12);
function ssStartLabel(row){if(!row)return '—';const base=new Date(`${plan.valuation_date||new Date().toISOString().slice(0,10)}T00:00:00`),d=new Date(base.getFullYear(),base.getMonth()+row.start_month,1);return `${d.toLocaleDateString(undefined,{month:'short',year:'numeric'})}<small class="row-sub">Month ${row.start_month}</small>`}
function renderSocialSecurity(){
  const rows=Array.isArray(plan.social_security)?plan.social_security:[],results=new Map((projection?.social_security||[]).map(r=>[r.id,r]));
  $('ss-table').innerHTML=rows.map(r=>{const result=results.get(r.id),claim=r.claim_age_years*12+(r.claim_age_months||0),option=r.birth_date?ssOption(r.birth_date,claim):null,benefit=result?result.monthly_benefit:option?r.pia_at_fra*option.factor:null;return `<tr><td><strong>${esc(r.name||'Social Security')}</strong>${r.enabled===false?'<small class="row-sub">Paused</small>':''}</td><td>${esc(r.birth_date||r.birth_year)}</td><td>${money(r.pia_at_fra)}</td><td>${ssAge(claim)}</td><td>${money(benefit)}${result?`<small class="row-sub">${(result.factor*100).toFixed(1)}% of full benefit</small>`:''}</td><td>${ssStartLabel(result)}</td><td class="row-actions"><button class="link-button" data-edit-ss="${esc(r.id)}">Edit</button><button class="link-button danger-text" data-remove-ss="${esc(r.id)}">Remove</button></td></tr>`}).join('');
  $('ss-empty').hidden=rows.length>0}
function renderSocialSecurityPreview(){
  const latest=$('ss-claim-years').value==='70';if(latest)$('ss-claim-months').value='0';$('ss-claim-months').disabled=latest;
  const birth=$('ss-birth-date').value,pia=Number($('ss-pia').value),claim=Number($('ss-claim-years').value)*12+Number($('ss-claim-months').value),box=$('ss-compare');
  const chosen=birth?ssOption(birth,claim):null;
  if(!chosen||!(pia>=0)||claim>840){box.innerHTML='<p>Enter a birth date and benefit to compare claiming ages. Claiming is limited to ages 62 through 70.</p>';return}
  const options=[['Earliest, 62',744],[`Full retirement age, ${ssAge(chosen.fra)}`,chosen.fra],['Latest, 70',840]];
  box.innerHTML=options.map(([label,months])=>`<div class="${months===claim?'selected':''}"><span>${esc(label)}</span><strong>${money(pia*ssOption(birth,months).factor)}</strong><small>${(ssOption(birth,months).factor*100).toFixed(1)}% · per month</small></div>`).join('')+`<p>Claiming at ${esc(ssAge(claim))}: <strong>${money(pia*chosen.factor)}</strong> a month (${(chosen.factor*100).toFixed(1)}% of your full benefit).</p>`}
function openSocialSecurity(id){
  const r=id?(plan.social_security||[]).find(x=>x.id===id):null;editingSocialSecurity=r?.id||null;
  $('ss-dialog-title').textContent=r?'Edit Social Security':'Add Social Security';
  $('ss-claim-years').innerHTML=[62,63,64,65,66,67,68,69,70].map(y=>`<option value="${y}">${y}</option>`).join('');
  $('ss-claim-months').innerHTML=Array.from({length:12},(_,m)=>`<option value="${m}">${m}</option>`).join('');
  $('ss-name').value=r?.name||'';$('ss-birth-date').value=r?.birth_date||'';$('ss-pia').value=r?.pia_at_fra??'';
  $('ss-claim-years').value=String(r?.claim_age_years??67);$('ss-claim-months').value=String(r?.claim_age_months??0);$('ss-enabled').checked=r?.enabled!==false;
  renderSocialSecurityPreview();$('ss-dialog').showModal()}
['ss-birth-date','ss-pia','ss-claim-years','ss-claim-months'].forEach(id=>$(id).addEventListener('input',renderSocialSecurityPreview));
$('add-ss').onclick=()=>openSocialSecurity();
$('ss-form').onsubmit=async e=>{e.preventDefault();const years=Number($('ss-claim-years').value),months=Number($('ss-claim-months').value);
  const row={id:editingSocialSecurity||uid(),name:$('ss-name').value.trim(),birth_date:$('ss-birth-date').value,pia_at_fra:Number($('ss-pia').value),claim_age_years:years,claim_age_months:months,enabled:$('ss-enabled').checked};
  const candidate=structuredClone(plan);candidate.social_security=Array.isArray(candidate.social_security)?candidate.social_security:[];const i=candidate.social_security.findIndex(x=>x.id===row.id);if(i<0)candidate.social_security.push(row);else candidate.social_security[i]=row;
  try{const result=await projectPlan(candidate);plan=candidate;touch();projection=result;$('ss-dialog').close();renderTables();showSaveState();tell('Social Security applied and projection updated.')}catch(err){tell(err.message,true)}};
document.addEventListener('click',e=>{const edit=e.target.closest('[data-edit-ss]'),del=e.target.closest('[data-remove-ss]');if(edit)openSocialSecurity(edit.dataset.editSs);if(del&&confirm('Remove this Social Security benefit from the plan?')){plan.social_security=(plan.social_security||[]).filter(r=>r.id!==del.dataset.removeSs);touch();renderTables();runProjection().catch(err=>tell(err.message,true))}});
