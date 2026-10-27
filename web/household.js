'use strict';
function renderHouseholdSource(){
  const source=plan.household_source,panel=$('household-source-panel'),notice=$('household-import-notice');
  panel.hidden=!source;notice.hidden=!source;
  if(!source){$('household-source').replaceChildren();$('household-warnings').replaceChildren();return}
  notice.textContent='Imported household draft · Source date '+(source.source?.as_of||'unknown')+'. Income, debt payoff, withdrawal access, and retirement assumptions need review. Full profile and limitations are in Settings.';
  $('household-warnings').innerHTML='<ul>'+(plan.import_warnings||[]).map(s=>`<li>${esc(s)}</li>`).join('')+'</ul>';
  function label(key){return String(key).replaceAll('_',' ')}
  function render(value){
    if(value===null)return '<em>Unknown / not supplied</em>';
    if(typeof value!=='object')return esc(String(value));
    if(Array.isArray(value))return value.length?'<ul>'+value.map(v=>'<li>'+render(v)+'</li>').join('')+'</ul>':'<em>None recorded</em>';
    return Object.entries(value).map(([k,v])=>v&&typeof v==='object'?`<details><summary>${esc(label(k))}</summary><div style="padding: .5rem 1rem">${render(v)}</div></details>`:`<p><strong>${esc(label(k))}:</strong> ${render(v)}</p>`).join('');
  }
  $('household-source').innerHTML=render(source)+render({unresolved_inputs:plan.unresolved_inputs});
}
