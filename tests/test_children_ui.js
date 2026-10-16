'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/children.js','utf8').split('function openChild(')[0];
function render(plan){
  const elements=new Map();
  const context={plan,projection:null,Date,Map,Number,String,
    $:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id)},
    document:{querySelectorAll:()=>[]},esc:String,money:n=>`$${n}`,go:()=>{}};
  vm.createContext(context);vm.runInContext(source+'\nrenderChildren();',context);
  return id=>elements.get(id);
}
const reported={valuation_date:'2026-08-11',members:[],child_accounts:[],
  household_source:{source:{as_of:'2026-08-11'},planner_inputs:{household:{children:{ages:[4,2,0]}}}},
  accounts:[{name:'Education savings',balance:15878,source_details:{type:'education_restricted',monthly_contribution_usd:200}}]};
let get=render(reported);
assert.equal(get('child-count').textContent,'3 reported');
assert.match(get('children-empty').textContent,/ages 4, 2, 0 as of 2026-08-11/);
assert.equal(get('child-total').textContent,'$15878');
assert.match(get('child-accounts-table').innerHTML,/Not assigned yet/);
assert.match(get('child-accounts-table').innerHTML,/\$2400 reported total/);
assert.equal(get('child-accounts-empty').hidden,true);
assert.equal(reported.members.length,0); // Rendering never invents birth dates.
get=render({valuation_date:'2026-08-11',accounts:[],members:[],child_accounts:[]});
assert.equal(get('child-count').textContent,'0');
assert.equal(get('child-total').textContent,'$0');
assert.equal(get('child-accounts-empty').hidden,false);
console.log('Children UI checks passed');
