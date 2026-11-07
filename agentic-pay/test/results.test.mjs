import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const parent = fs.readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');
const app = fs.readFileSync(new URL('../../web/pay/app.js', import.meta.url), 'utf8');
const paid = { type: 'tripfit-pay', status: 'paid', total: 70000,
  lines: [{person:'지민',amount:35000,approval_no:'a1'},{person:'서연',amount:35000,approval_no:'a2'}],
  hash8:'d3ed107e',item:{gid:'3828508',start:'15:00',short_name:'숲체험'},at:'2026-11-07T04:00:00Z'};
function harness(){
  const frame={contentWindow:{}},sh={close:async()=>{calls.close++;}},v={isConnected:true},calls={close:0,render:0,logs:[],islands:[]};v._sheet=sh;
  const context=vm.createContext({frame,sh,v,calls,structuredClone,location:{origin:'https://tripfit.test'},
    input:{item:paid.item,people:[{name:'지민'},{name:'서연'}]},booked:{},
    paymentResults:new Map(),paymentKey:item=>JSON.stringify([item.gid,item.start]),
    paymentForStop:()=>context.paymentResults.get(JSON.stringify(['3828508','15:00'])),
    renderPaymentResult:()=>calls.render++,won:n=>n.toLocaleString('ko-KR'),
    island:{show:value=>calls.islands.push(value)},log:(...args)=>calls.logs.push(args)});
  const code=parent.slice(parent.indexOf('    onResult=async event=>{'),parent.indexOf("    window.addEventListener('message',onResult);"));
  vm.runInContext('let completed=false;'+code,context);
  const event=(data=structuredClone(paid),origin=context.location.origin,source=frame.contentWindow)=>({data,origin,source});
  return {context,calls,event,receive:context.onResult};
}

test('result receiver rejects other origins, frames, stale sheets and mismatched items',async()=>{
  const h=harness();
  await h.receive(h.event(paid,'https://other.test'));await h.receive(h.event(paid,undefined,{}));
  await h.receive(h.event({...paid,item:{...paid.item,start:'16:00'}}));
  h.context.v._sheet={};await h.receive(h.event());
  assert.equal(h.calls.close,0);assert.equal(h.context.paymentResults.size,0);
});

test('paid result closes once, retains receipt data and logs the returned amounts and hash',async()=>{
  const h=harness();await h.receive(h.event());await h.receive(h.event());
  assert.equal(h.calls.close,1);assert.equal(h.calls.render,1);
  assert.equal(h.context.paymentForStop().total,70000);
  assert.deepEqual(h.context.paymentForStop().lines,paid.lines);
  assert.equal(h.calls.logs[0][1],'AGENTIC PAY 결제 완료 70,000원, 승인 2건, 기록 d3ed107e');
  assert.equal(h.calls.islands[0].title,'같이 결제 완료, 70,000원');
});

test('malformed receipts cannot replace payment state',async()=>{
  const h=harness();
  for(const data of [{...paid,total:1},{...paid,hash8:'bad'}, {...paid,lines:[]},
    {...paid,lines:[{...paid.lines[0],amount:-1},paid.lines[1]]}, {...paid,at:'invalid'}])await h.receive(h.event(data));
  assert.equal(h.calls.close,0);assert.equal(h.context.paymentResults.size,0);
});

test('stopped result updates retry state without closing the visible stop scene',async()=>{
  const h=harness();await h.receive(h.event({...paid,status:'stopped',reason:'위임을 취소했어요'}));
  assert.equal(h.context.paymentForStop().reason,'위임을 취소했어요');assert.equal(h.calls.render,1);assert.equal(h.calls.close,0);
  await h.receive(h.event({...paid,status:'stopped',reason:''}));assert.equal(h.calls.render,1);
});

test('standalone does not post; embedded result uses the exact parent origin and item',()=>{
  const messages=[],context=vm.createContext({trip:{item:paid.item},simulation:false,location:{origin:'https://tripfit.test'}});
  context.window={};context.window.parent=context.window;
  vm.runInContext(app.slice(app.indexOf('function notifyParent('),app.indexOf('function stopped(')),context);
  context.notifyParent('paid',{total:70000});assert.equal(messages.length,0);
  context.window.parent={postMessage:(data,origin)=>messages.push({data,origin})};
  context.notifyParent('stopped',{reason:'예약 불가'});
  assert.equal(messages[0].origin,'https://tripfit.test');assert.equal(messages[0].data.status,'stopped');assert.equal(messages[0].data.item.start,'15:00');
});

test('itinerary receipt pill follows the paid item and remains after a replan',()=>{
  const context=vm.createContext({D:{mrt:{date:'2026-11-14'}},paymentResults:new Map(),placeById:{forest:{mrt:{gid:'3828508'}}},
    hhmm:n=>`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`,svg:()=>'',escapeHTML:s=>s,short:s=>s,won:String,CAT:{activity:'lime'}});
  vm.runInContext(parent.slice(parent.indexOf('function paymentKey('),parent.indexOf('function renderPaymentResult(')),context);
  vm.runInContext(parent.slice(parent.indexOf('class Timeline {'),parent.indexOf('  render(plan, o = {}) {'))+'}',context);
  vm.runInContext("paymentResults.set(paymentKey({gid:'3828508',start:'15:00'}),{status:'paid'});var timeline=Object.create(Timeline.prototype);timeline.o={};",context);
  const stop={id:'forest',name:'숲체험',cat:'activity',catKo:'체험',start:900,end:960,walkMin:2,fixed:true};
  assert.match(context.timeline.html(stop,{}),/결제 완료/);
  assert.match(context.timeline.html({...stop,walkMin:10},{}),/결제 완료/);
  assert.doesNotMatch(context.timeline.html({...stop,start:960},{}),/결제 완료/);
});

test('entering the same receipt twice sends exactly one paid notification',()=>{
  const notices=[],element={};
  const context=vm.createContext({stage:4,paidNotice:'',confirmed:{payments:paid.lines.map((l,i)=>({person_id:String(i),amount:l.amount,approval_no:l.approval_no})),total:70000,quote_hash:'d3ed107e'+'0'.repeat(56),paid_at:paid.at},
    trip:{people:[{id:'0',name:'지민'},{id:'1',name:'서연'}],item:{url:'https://example.test/item'}},
    location:{href:'https://tripfit.test/pay/'},URL,frame:()=>{},receiptHead:()=>'',supplierMarkup:()=>'',
    simulationButtons:()=>'',bindSimulations:()=>{},number:String,esc:String,receiptTime:String,icon:()=>'',
    notifyParent:(status,data)=>notices.push({status,data}),$:()=>element,focusTitle:()=>{}});
  vm.runInContext(app.slice(app.indexOf('function complete(){'),app.indexOf("$('#reset').onclick=")),context);
  context.complete();context.complete();assert.equal(notices.length,1);assert.equal(notices[0].data.hash8,'d3ed107e');
});
