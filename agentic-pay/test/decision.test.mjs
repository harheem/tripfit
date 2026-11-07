import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {choices,decisionMarkup,decisionLog,validDecision,rulesDecision} from '../../web/pay/decision.js';
import {createWorld,recordDecision,auditLog,verifyChain} from '../../web/pay/engine/engine.js';

const pass={provider:'articul8-bivia',model:'dec-1',value:choices[0],status:'answered',final:'proceed',reason:'맡긴 범위 안이에요',probability:.97,distribution:{[choices[0]]:.97,[choices[1]]:.03},ms:180};
const stop={...pass,value:choices[1],final:'stop',reason:'방금 조회한 가격 38,000원이 맡긴 35,000원을 넘었어요',probability:.93,distribution:{[choices[0]]:.07,[choices[1]]:.93}};
const checks=['merchant','product','price','available','expiry','unused'].map(key=>({key,ok:true,evidence:'맞아요',detail:'맞아요'}));
const app=fs.readFileSync(new URL('../../web/pay/app.js',import.meta.url),'utf8');
function harness(fetch,reduced=false,ready=true){
  const nodes=Object.fromEntries(['#decision','.hold','#reapprove','#manual-check','#cancel','.phone'].map(key=>[key,{hidden:true,disabled:true,isConnected:true,innerHTML:'',scrollIntoView(){},querySelector(){return this;},animate(){events.push('shake');}}]));
  const events=[],notices=[],records=[];
  const context=vm.createContext({decisionRun:0,decisionController:null,decision:null,AbortController,setTimeout,clearTimeout,
    stage:4,trip:{item:{short_name:'숲체험',start:'15:00',merchant_label:'마이리얼트립'},date:'2026-11-14',people:[{name:'지민'},{name:'서연'}]},
    quote:{total:70000,lines:[{name:'지민',mandate_max:35000,amount:35000},{name:'서연',mandate_max:35000,amount:35000}]},
    stopCode:'',world:{},fetch,inspection:()=>({ready}),rulesDecision,validDecision,decisionMarkup,decisionLog,
    $:selector=>nodes[selector],esc:String,money:n=>`${n.toLocaleString('ko-KR')}원`,
    matchMedia:()=>({matches:reduced}),api:{recordDecision:(...args)=>records.push(args)},audit:()=>{},notifyParent:(...args)=>notices.push(args)});
  vm.runInContext(app.slice(app.indexOf('async function lastDecision('),app.indexOf('function receiptHead(')),context);
  return {context,nodes,events,notices,records,run:()=>context.lastDecision(checks,ready)};
}
const response=data=>async()=>({ok:true,json:async()=>structuredClone(data)});

test('pending and model results display source and supplied probabilities only',()=>{
  assert.match(decisionMarkup(null),/Articul8 Bivia가 마지막으로 판단하는 중/);
  assert.match(decisionMarkup(pass),/결제해도 돼요/);assert.match(decisionMarkup(pass),/97%/);
  assert.match(decisionMarkup(stop),/STOP/);assert.match(decisionMarkup(stop),/결제를 막았어요/);assert.match(decisionMarkup(stop),/--fill:93%/);
  assert.match(decisionMarkup(stop),/Articul8 Bivia dec-1, 180ms/);
  const rules={...stop,provider:'rules'};
  assert.match(decisionMarkup(rules),/규칙 판단/);assert.doesNotMatch(decisionMarkup(rules),/decision-bars|93%|97%/);
});

test('abstention locks payment and offers human review without a STOP stamp',async()=>{
  const h=harness(response({...pass,status:'abstained',value:null,final:'stop'}));await h.run();
  assert.equal(h.nodes['.hold'].disabled,true);assert.equal(h.nodes['#manual-check'].hidden,false);
  assert.equal(h.nodes['#reapprove'].hidden,true);assert.deepEqual(h.events,[]);
  assert.match(h.nodes['#decision'].innerHTML,/확신이 없어서 결정하지 않았어요/);
  assert.doesNotMatch(h.nodes['#decision'].innerHTML,/stop-stamp/);
});

test('model acceptance enables the button; scope failures still veto acceptance',async()=>{
  const h=harness(response(pass));await h.run();assert.equal(h.nodes['.hold'].disabled,false);assert.equal(h.notices.length,0);
  const blocked=harness(response(pass),false,false);await blocked.run();
  assert.equal(blocked.nodes['.hold'].disabled,true);assert.equal(blocked.context.decision.final,'stop');
  assert.ok(blocked.context.decision.override_reason);
  assert.match(blocked.records[0][2],/진행 제안, 엔진이 결제 멈춤/);
});

test('rejection shakes once, unlocks reapproval and returns Bivia reason and log',async()=>{
  const h=harness(response(stop));await h.run();
  assert.equal(h.nodes['.hold'].disabled,true);assert.equal(h.nodes['#reapprove'].hidden,false);
  assert.deepEqual(h.events,['shake']);assert.equal(h.notices[0][0],'stopped');
  assert.equal(h.notices[0][1].decider,'Articul8 Bivia');assert.equal(h.notices[0][1].reason,stop.reason);
  assert.equal(h.notices[0][1].decision_log,'ARTICUL8 Bivia 판단: 결제 멈춤 93%, 180ms');
  const reduced=harness(response(stop),true);await reduced.run();assert.deepEqual(reduced.events,[]);
});

test('failed transport applies local rules and never attributes the fallback to Bivia',async()=>{
  const h=harness(async()=>{throw new Error('offline');});h.context.quote.lines[0].amount=38000;
  await h.run();assert.equal(h.context.decision.provider,'rules');assert.equal(h.nodes['.hold'].disabled,true);
  assert.match(h.context.decision.reason,/38,000.*35,000/);assert.equal(h.notices[0][1].decider,'규칙 판단');
  assert.doesNotMatch(h.nodes['#decision'].innerHTML,/decision-bars|%/);
});

test('late decisions cannot enable payment or notify after navigation or a newer request',async()=>{
  let resolve;
  const h=harness(()=>new Promise(done=>{resolve=done;}));
  const pending=h.run();h.context.decisionRun++;
  resolve({ok:true,json:async()=>pass});await pending;
  assert.equal(h.nodes['.hold'].disabled,true);assert.equal(h.notices.length,0);assert.equal(h.records.length,0);
});

test('merchant simulation reaches decision input as a different merchant',async()=>{
  let payload;
  const h=harness(async(url,options)=>{payload=JSON.parse(options.body);return {ok:true,json:async()=>stop};});
  h.context.stopCode='MERCHANT_MISMATCH';await h.run();
  assert.equal(payload.merchant.actual,'다른 판매처');assert.notEqual(payload.merchant.actual,payload.merchant.expected);
});

test('malformed or contradictory acceptance cannot pass validation',()=>{
  assert.equal(validDecision({...pass,value:choices[1]}),false);
  assert.equal(validDecision({...pass,status:'abstained',value:null}),false);
  assert.equal(validDecision({...pass,provider:'unknown'}),false);
});

test('public Bivia result is part of the verified engine audit chain',async()=>{
  const world=createWorld();recordDecision(world,stop,decisionLog(stop));await world.audit.flush();
  const rows=auditLog(world);assert.equal(rows[0].action,'ARTICUL8 Bivia 판단: 결제 멈춤 93%, 180ms');
  assert.equal(await verifyChain(rows),true);assert.equal(rows[0].detail.final,'stop');
});


test('merchant simulation still changes the requested seller after a price refusal',async()=>{
  let screens=0;
  const context=vm.createContext({paying:false,stage:4,epoch:0,decisionController:null,decisionRun:0,decision:null,
    simulation:false,recheckController:null,inquiryController:null,clearHolds:()=>{},clearTimeout,expiryTimer:null,
    stopReason:'가격 초과',stopCode:'AMOUNT_OVER_LIMIT',world:{},trip:{},$$:()=>[],
    api:{buildQuote:()=>({status:'NEEDS_REAPPROVAL'})},quoteScreen:()=>screens++});
  vm.runInContext(app.slice(app.indexOf('async function simulateStop('),app.indexOf("$('#test-price').onclick=")),context);
  await context.simulateStop('merchant');
  assert.equal(context.stopCode,'MERCHANT_MISMATCH');assert.equal(screens,1);
});
