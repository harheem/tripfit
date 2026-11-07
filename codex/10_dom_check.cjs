// Runs the rendered flow with the unmodified payment engine. jsdom cannot verify pixel layout.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {JSDOM,VirtualConsole}=require('/Users/harheem/.npm/_npx/9dfd41d38db56959/node_modules/jsdom');
const root=path.resolve(__dirname,'..'),out=path.join(root,'codex/10_shots');
const pause=ms=>new Promise(r=>setTimeout(r,ms));const results=[];
async function until(fn,label){for(let i=0;i<800;i++){if(fn())return;await pause(5);}throw Error('Timeout: '+label);}
async function setup({live=false,unavailable=false,external=false}={}){
 const api=await import(pathToFileURL(path.join(root,'web/pay/api.js')));
 const errors=[],calls=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(String(e)));
 const dom=new JSDOM(fs.readFileSync(path.join(root,'web/pay/index.html'),'utf8'),{url:'http://localhost/pay/?embed=1',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
 const w=dom.window;w.__api=api;w.structuredClone=structuredClone;w.CSS={supports:()=>true};w.ResizeObserver=class{observe(){}};w.scrollTo=()=>{};w.Element.prototype.scrollIntoView=()=>{};w.document.fonts={ready:Promise.resolve()};
 if(external){const input=JSON.parse(fs.readFileSync(path.join(root,'web/pay/data/trip.json')));input.people=[{id:'a',name:'민아'},{id:'b',name:'윤호'}];input.item.short_name='새 체험';input.item.price=42000;input.item.start='16:30';input.snapshot.price=42000;w.TRIPFIT_PAY_INPUT=input;}
 w.fetch=async(url,options={})=>{
  calls.push({url,body:options.body&&JSON.parse(options.body)});
  if(url==='/api/pay/recheck')return {ok:live,json:async()=>({available:!unavailable,price:external?42000:35000,source:'live',checked_at:new Date().toISOString(),option_start:external?'16:30':'15:00'})};
  return {ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(root,'web/pay',url)))};
 };
 const source=fs.readFileSync(path.join(root,'web/pay/app.js'),'utf8').replace("import * as api from './api.js';",'const api=window.__api;');
 await w.eval(`(async()=>{${source}\nwindow.__pay={settle:audit,inspection,quoteScreen,mandateScreen,get world(){return world},get trip(){return trip},get quote(){return quote},get confirmed(){return confirmed},get mandates(){return mandates}};})()`);
 const $=s=>w.document.querySelector(s),$$=s=>[...w.document.querySelectorAll(s)];
 const click=s=>{assert.ok($(s),'missing '+s);assert.equal($(s).disabled,false,'disabled '+s);$(s).click();};
 const hold=async(s,ms=1120)=>{const el=$(s);assert.ok(el);assert.equal(el.disabled,false);el.dispatchEvent(new w.KeyboardEvent('keydown',{key:' ',bubbles:true}));await pause(ms);el.dispatchEvent(new w.KeyboardEvent('keyup',{key:' ',bubbles:true}));await pause(30);};
 const approveBoth=async()=>{await hold('.person-card .hold');await hold('.person-card .hold');};
 const toQuote=async()=>{click('#next');await approveBoth();click('#next');await until(()=>$('.result'),'reservation');click('#next');};
 return {w,dom,$,$$,click,hold,approveBoth,toQuote,errors,calls};
}
(async()=>{
 const p=await setup();const {$,$$,click,hold,approveBoth,w}=p;
 assert.equal(w.document.body.classList.contains('embed'),true);assert.equal($('#technical').open,false);assert.match($('#flow').textContent,/현장 결제 2곳/);
 click('#next');await hold('.person-card .hold',180);assert.equal($$('.approved').length,0);assert.equal($$('.person-card .hold')[1].disabled,true);await approveBoth();assert.equal($$('.approved').length,2);click('#next');await until(()=>$('.result'),'fallback result');assert.match($('.result').textContent,/저장된 조회 결과/);assert.equal($('.draft').open,false);click('#next');
 assert.equal($$('[data-pass=true]').length,6);assert.equal($('.hold').disabled,false);const originalButton=$('.hold');await pause(1100);assert.equal($('.hold'),originalButton,'expiry ticker must not replace the hold button');await hold('.hold');await until(()=>$('.receipt'),'normal receipt');assert.equal(w.__pay.confirmed.total,70000);assert.match($('.supplier').textContent,new RegExp(w.__pay.confirmed.quote_hash.slice(0,8)));assert.equal(w.__pay.world.pay.payments.length,2);
 click('#test-merchant');await until(()=>$('.blocked'),'rejection');assert.match($('.blocked').textContent,/MERCHANT_MISMATCH/);assert.equal(w.__pay.world.pay.payments.length,2);assert.equal(await w.__api.verifyChain(w.__api.auditLog(w.__pay.world)),true);
 results.push({flow:'normal, short-hold cancellation, persistent countdown, snapshot fallback, receipt/supplier hash, merchant rejection',passed:true});
 click('#reset');await p.toQuote();click('#test-price');await until(()=>$('#reapprove'),'price stop');assert.equal($('[data-check=price]').dataset.pass,'false');assert.equal($('.hold').disabled,true);assert.match($('.price-change').textContent,/35,000.*38,000/);click('#reapprove');await approveBoth();click('#next');assert.equal($$('[data-pass=true]').length,6);assert.equal(w.__pay.quote.total,76000);await hold('.hold');await until(()=>$('.receipt'),'reapproved receipt');assert.equal(w.__pay.confirmed.total,76000);results.push({flow:'price increase → payment locked → reapproval → 76,000 receipt',passed:true});assert.deepEqual(p.errors,[]);await p.w.__pay.settle();p.dom.window.close();
 const live=await setup({live:true,external:true});await live.toQuote();assert.equal(live.$$('.check[data-pass=true]').length,6);assert.equal(live.w.__pay.quote.total,84000);assert.match(live.$('#flow').textContent,/새 체험/);assert.match(live.$('#flow').textContent,/16:30/);assert.deepEqual(live.calls.find(c=>c.url==='/api/pay/recheck').body.start,'16:30');results.push({flow:'live API response + external TRIPFIT_PAY_INPUT names, time, price',passed:true});
 // Advance the engine clock beyond the mandate deadline: displayed state must fail closed.
 live.w.__pay.world.clock.advance(3*3600000);live.w.__pay.quoteScreen();assert.equal(live.$('[data-check=expiry]').dataset.pass,'false');assert.equal(live.$('.hold').disabled,true);assert.ok(live.$('#reapprove'));live.click('#reapprove');await live.approveBoth();live.click('#next');assert.equal(live.$('.hold').disabled,false);results.push({flow:'expired mandate locks payment and allows renewed delegation',passed:true});await live.w.__pay.settle();live.dom.window.close();
 const sold=await setup({live:true,unavailable:true});await sold.toQuote();assert.equal(sold.$('[data-check=available]').dataset.pass,'false');assert.equal(sold.$('.hold').disabled,true);assert.match(sold.$('#flow').textContent,/다른 시각 선택/);results.push({flow:'sold-out response → red failed availability check + locked payment',passed:true});await sold.w.__pay.settle();sold.dom.window.close();
 fs.writeFileSync(path.join(out,'dom-results.json'),JSON.stringify({passed:true,limitation:'DOM flow validation only; no pixel layout or real pointer/touch validation',results},null,2));console.log(JSON.stringify({passed:true,results},null,2));
})().catch(e=>{fs.writeFileSync(path.join(out,'dom-results.json'),JSON.stringify({passed:false,error:e.stack,results},null,2));console.error(e);process.exit(1);});
