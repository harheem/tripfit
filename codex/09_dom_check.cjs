// UI contract checks. jsdom has no layout engine: real pixel fit remains a browser check.
const fs = require('node:fs'), assert = require('node:assert/strict');
const {JSDOM, VirtualConsole} = require('/Users/harheem/.npm/_npx/9dfd41d38db56959/node_modules/jsdom');
const root = require('node:path').resolve(__dirname,'..');
const html = fs.readFileSync(root+'/web/index.html','utf8');
const demo = fs.readFileSync(root+'/web/demo_data.js','utf8');
const data = JSON.parse(demo.split('window.DEMO = ')[1].replace(/;\s*$/,''));
const pause = ms => new Promise(r=>setTimeout(r,ms));
async function waitFor(fn, label) {for(let i=0;i<1200;i++){if(fn())return;await pause(2);}throw Error('Timeout: '+label);}
async function check(width,live){
 const errors=[],warnings=[],calls=[],frames=new Set();
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(String(e)));vc.on('warn',(...v)=>warnings.push(v));
 const fixture=structuredClone(data);if(live)fixture.sessionId='session-contract';
 let source=html.replace('<script src="demo_data.js"></script>',`<script>window.DEMO=${JSON.stringify(fixture)}</script>`);
 source=source.replace('go(0);\n})();','go(0);\nwindow.__09={fitNumber,openPOI,autoplay,allHistory,concessionCounts,recommendedFor,get autoPlaying(){return autoPlaying}};\n})();');
 const dom=new JSDOM(source,{url:live?'http://tripfit.test/':'file:///tripfit/web/index.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.innerWidth=width;w.innerHeight=width===390?844:900;w.CSS={supports:()=>false};
  w.ResizeObserver=class{observe(){}};w.document.fonts={ready:Promise.resolve()};
  w.matchMedia=q=>({matches:q.includes('prefers-reduced')?false:width<=700,addEventListener(){}});
  const timeout=w.setTimeout.bind(w);w.setTimeout=(fn,ms,...args)=>timeout(fn,Math.min(ms,8),...args);
  w.requestAnimationFrame=fn=>{const id=timeout(()=>{frames.delete(id);if(w.document)fn(w.performance.now());},4);frames.add(id);return id;};
  w.cancelAnimationFrame=id=>{frames.delete(id);w.clearTimeout(id);};
  w.HTMLElement.prototype.animate=w.SVGElement.prototype.animate=function(){const a={finished:Promise.resolve(),cancel(){}};timeout(()=>a.onfinish?.(),0);return a;};
  w.Element.prototype.getAnimations=()=>[];
  w.Element.prototype.scrollTo=function({top}){this.scrollTop=top;};w.Element.prototype.scrollIntoView=function(){};
  w.Element.prototype.getBoundingClientRect=()=>({left:0,top:0,width:width-70,height:40,right:width-70,bottom:40});
  w.Element.prototype.setPointerCapture=function(){};w.SVGElement.prototype.getTotalLength=()=>150;w.SVGElement.prototype.getPointAtLength=()=>({x:40,y:40});
  w.fetch=async(path,options={})=>{
   const body=options.body?JSON.parse(options.body):null;calls.push({path,body});let result;
   if(path==='/api/demo')result=fixture;
   else if(path==='/api/mrt')result=fixture.mrt;
   else if(path==='/api/parse')result={fallback:true,ms:1,constraints:{people:fixture.people.map(p=>({hard:[],prefs:fixture.prefs[p.name]}))}};
   else if(path==='/api/plan'){
    result=structuredClone({series:fixture.series,defaultIdx:fixture.defaultIdx,solveMs:5});
    for(const plan of result.series)for(const person of fixture.people){
     const items=plan.checklist[person.name];for(const it of items){if(body.muted.some(m=>m.person===person.name&&m.label===it.label)){it.weight=0;it.muted=true;}}
     const weight=items.reduce((s,i)=>s+i.weight,0)||1;plan.sat[person.name]=Math.round(1000*items.reduce((s,i)=>s+i.weight*i.fulfilled,0)/weight)/10;
    }
   }else if(path==='/api/what-if'){
    const W=fixture.whatif.choices.find(c=>c.pick===body.pick);
    if(body.relax){const r=W.relaxations.find(r=>r.id===body.relax);result={pick:W.pick,infeasible:false,relaxationId:r.id,plan:r.plan,diff:r.diff,replan:r.replan};}
    else result={pick:W.pick,infeasible:W.infeasible,reason:W.reason,recommended:W.recommended,relaxations:W.relaxations.map(({plan,diff,replan,...r})=>r)};
   }else if(path==='/api/replan')result={plan:fixture.replan.plan};
   else throw Error('Unexpected fetch '+path);
   return {ok:true,json:async()=>JSON.parse(JSON.stringify(result))};
  };
 }});
 const w=dom.window,$=sel=>w.document.querySelector(sel),cv=()=>$('#view').lastElementChild, key=k=>w.dispatchEvent(new w.KeyboardEvent('keydown',{key:k}));
 await waitFor(()=>w.__09,'boot');
 assert.equal(w.document.body.classList.contains('mobile'),width===390);
 assert.equal($('link[rel=icon]').getAttribute('href'),'favicon.svg');assert.ok($('.app-brand .logo-check'));assert.equal($('#capLogo').hidden,false);
 // Fit arithmetic with a simulated overflow; this is explicitly not a rendered-width assertion.
 const probe=w.document.createElement('div');const probeCSS=w.document.createElement('style');probeCSS.textContent='.probe{font-size:100px}';w.document.head.append(probeCSS);probe.className='probe';w.document.body.append(probe);
 Object.defineProperty(probe,'clientWidth',{get:()=>120});Object.defineProperty(probe,'scrollWidth',{get:()=>Math.ceil((parseFloat(probe.style.fontSize)||100)*3)});
 w.__09.fitNumber(probe);assert.ok(probe.scrollWidth<=probe.clientWidth);probe.remove();
 key('2');await waitFor(()=>cv().querySelector('#fnO')?.dataset.v===Number(data.sources.orderings).toLocaleString('ko-KR'),'rolling large number');
 assert.equal($('#capLogo').hidden,true);
 key('3');await waitFor(()=>cv()._run,'balance');
 const balance=cv(),head=balance.querySelector('[data-person="0"]');assert.equal(head.getAttribute('aria-expanded'),'false');head.click();
 assert.equal(head.getAttribute('aria-expanded'),'true');assert.match(balance.querySelector('#formula0').textContent,/100×1.0 \+ 50×0.7/);
 for(const formula of balance.querySelectorAll('.formula'))assert.equal(formula.dataset.calculated,formula.dataset.sat);
 assert.match(balance.querySelector('#formula0').textContent,/79.4%/);assert.match(balance.querySelector('#minSat').textContent,/79% · 둘 중 낮은 쪽/);
 balance.querySelector('#nJ').click();assert.equal(head.getAttribute('aria-expanded'),'false');
 balance._scaleTo(0);assert.equal(balance.querySelector('#formula0').dataset.sat,'100.0');balance._scaleTo(data.defaultIdx);
 for(const id of ['exh_daelim','cafe_onion']){
  balance.querySelector(`.ti[data-id="${id}"] .stop`).click();assert.ok(balance._sheet);assert.match(balance._sheet.el.textContent,id==='exh_daelim'?/전시는 꼭 보고 싶어/:/카페에서 좀 쉬고 싶어/);
  assert.equal(balance._sheet.el.querySelectorAll('.q-row').length,3);balance._sheet.el.querySelector('.sheet-close').click();await waitFor(()=>!balance.querySelector('.sheet'),'POI close');
 }
 balance.querySelector('.mks [data-pid="cafe_onion"]').dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
 assert.match(balance._sheet.el.textContent,/지점 4곳/);assert.match(balance._sheet.el.textContent,/샘플/);
 const sheet=balance._sheet.el;sheet.scrollTop=0;
 for(const [type,y]of[['touchstart',100],['touchmove',210],['touchend',210]]){const e=new w.Event(type,{bubbles:true,cancelable:true});Object.defineProperty(e,'touches',{value:[{clientX:100,clientY:y}]});sheet.dispatchEvent(e);}
 await waitFor(()=>!balance.querySelector('.sheet'),'finger dismiss');
 if(live){
  const row=balance.querySelector('#cli0 .ci');row.click();await waitFor(()=>balance.querySelector('#cli0 .ci').getAttribute('aria-pressed')==='true','mute');
  assert.equal(w.__09.concessionCounts()['지민'],2);row.click();await waitFor(()=>balance.querySelector('#cli0 .ci').getAttribute('aria-pressed')==='false','undo mute');assert.equal(w.__09.concessionCounts()['지민'],1);
 }
 key('4');await waitFor(()=>cv().querySelector('.slot'),'product sheet');const activity=cv();
 assert.equal(activity.querySelectorAll('.option-chip').length,4);assert.equal(activity.querySelector('.in-window b').textContent,'15:00');
 assert.match(activity.querySelector('.product-evidence').textContent,/실조회 · 12:46/);assert.ok(!activity.querySelector('.sheet').textContent.includes('⭐'));
 assert.equal(activity.querySelector('.product-link').target,'_blank');assert.ok(activity.querySelector('.slots.single'));assert.match(activity.querySelector('.slot-end').textContent,/120분 · 17:00 종료/);
 activity.querySelector('.slot').click();activity.querySelector('#addBtn').click();await waitFor(()=>activity.querySelector('.recommended'),'recommendation');
 assert.equal(activity.querySelector('.relax').dataset.id,'category_min:cafe');assert.match(activity.querySelector('.recommended .preview').textContent,/지민 59 · 서연 60/);
 assert.match(activity.querySelector('.reasons').textContent,/이번엔 서연 차례/);activity.querySelector('[data-ledger]').click();assert.match(activity._sheet.el.textContent,/10.12 · 익선동 · 지민/);activity._sheet.el.querySelector('.sheet-close').click();await waitFor(()=>!activity.querySelector('.sheet'),'ledger close');
 activity.querySelector('.recommended').click();await waitFor(()=>!activity.querySelector('.cta-wrap .btn').disabled,'conceded plan');
 assert.equal(w.__09.concessionCounts()['서연'],1);activity.querySelector('.stop.lock').click();assert.ok(activity._sheet.el.querySelector('a.product-link[href^="https://experiences.myrealtrip.com/"]'));activity._sheet.el.querySelector('.sheet-close').click();
 await waitFor(()=>!activity.querySelector('.sheet'),'MRT POI close');activity.querySelector('.cta-wrap .btn').click();await waitFor(()=>cv().querySelector('.concession-next'),'agreement ledger');
 assert.match(cv().querySelector('.concession-next').textContent,/서연 ‘카페 1곳’ → 다음엔 지민 차례/);
 cv().querySelector('[data-poi]').click();assert.ok(cv()._sheet);cv()._sheet.el.querySelector('.sheet-close').click();
 key('6');await waitFor(()=>cv()._run,'replan');await cv()._run();await waitFor(()=>cv().querySelector('.stop.lock'),'locked booking');cv().querySelector('.stop.lock').click();assert.ok(cv()._sheet);
 key('R');assert.equal(w.__09.concessionCounts()['서연'],0);assert.equal(w.__09.concessionCounts()['지민'],1);assert.equal($('#capLogo').hidden,false);
 const auto=w.__09.autoplay();await waitFor(()=>cv()._scaleTo && cv()._run,'autoplay balance');
 // Automatic playback must reject casual POI taps.
 w.__09.openPOI(cv(),'exh_daelim',data.series[data.defaultIdx].stops.find(s=>s.id==='exh_daelim'));assert.equal(cv()._sheet,undefined);
 await auto;assert.equal($('#capN b').textContent,'06');
 assert.equal(warnings.length,0,JSON.stringify(warnings));assert.equal(errors.length,0,errors.join('\n'));
 if(live)assert.ok(calls.filter(c=>c.body&&['/api/plan','/api/what-if','/api/replan'].includes(c.path)).every(c=>c.body.sessionId==='session-contract'));
 const result={width,height:width===390?844:900,mode:live?'mock API contract + sessionId':'offline with memory storage fallback',passed:'numbers arithmetic, formula/slider, POI cards/markers/MRT, finger dismissal, product chips/link, recommendation, ledger/undo/reset, agreement, replan, full autoplay; runtime errors 0; warnings 0',renderedLayout:'NOT VERIFIED: jsdom has no layout engine'};
 for(const id of frames)w.clearTimeout(id);frames.clear();dom.window.close();return result;
}
(async()=>{const results=[];for(const [width,live]of [[1440,true],[390,false]]){const result=await check(width,live);results.push(result);console.log(JSON.stringify(result));}fs.writeFileSync(root+'/codex/09_shots/dom-results.json',JSON.stringify(results,null,2)+'\n');})().catch(e=>{console.error(e);process.exitCode=1;});
