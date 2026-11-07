// Run from tripfit/. Uses the exported solver data, served through Playwright routing.
// No listening port or live provider calls are needed.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_EXECUTABLE, BEFORE_HTML (defaults to HEAD:web/index.html).
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'codex/09_shots');
const data=JSON.parse(fs.readFileSync(path.join(root,'web/demo_data.js'),'utf8').split('window.DEMO = ')[1].replace(/;\s*$/,''));
const beforeHTML=process.env.BEFORE_HTML ? fs.readFileSync(process.env.BEFORE_HTML,'utf8') : require('node:child_process').execFileSync('git',['show','HEAD:web/index.html'],{cwd:root,encoding:'utf8'});
const results=[];let browser;
async function run(){
 const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE}:{})});
 for(const [width,height]of [[1440,900],[390,844]]){
  const ctx=await browser.newContext({viewport:{width,height},isMobile:width===390,hasTouch:width===390});
  let old=false;const errors=[],warnings=[],requests=[];
  await ctx.route('http://tripfit.test/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname.startsWith('/api/')){
    const body=route.request().postDataJSON();requests.push({path:url.pathname,body});let json;
    if(url.pathname==='/api/demo')json=data;
    else if(url.pathname==='/api/mrt')json=data.mrt;
    else if(url.pathname==='/api/parse')json={fallback:true,ms:1,constraints:{people:data.people.map(p=>({hard:[],prefs:data.prefs[p.name]}))}};
    else if(url.pathname==='/api/what-if'){
     const W=data.whatif.choices.find(c=>c.pick===body.pick);
     if(body.relax){const r=W.relaxations.find(r=>r.id===body.relax);json={pick:W.pick,infeasible:false,relaxationId:r.id,plan:r.plan,diff:r.diff,replan:r.replan};}
     else json={pick:W.pick,infeasible:W.infeasible,reason:W.reason,recommended:W.recommended,relaxations:W.relaxations.map(({plan,diff,replan,...r})=>r)};
    }else if(url.pathname==='/api/replan')json={plan:data.replan.plan};
    else return route.fulfill({status:404,body:'Unknown test route'});
    return route.fulfill({json});
   }
   const file=url.pathname==='/'?'index.html':url.pathname.slice(1);
   if(old&&file==='index.html')return route.fulfill({body:beforeHTML,contentType:'text/html'});
   const target=path.join(root,'web',file);
   if(!target||!fs.existsSync(target))return route.fulfill({status:404,body:'Not found'});
   const ext=path.extname(target),mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'}[ext];
   return route.fulfill({path:target,contentType:mime});
  });
  const page=await ctx.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());if(m.type()==='warning')warnings.push(m.text());});
  const cv=()=>page.locator('#view > div').last();
  const shot=async name=>page.screenshot({path:path.join(out,`${width}-${name}.png`),animations:'disabled'});
  const step=async key=>{await page.keyboard.press(key);await page.waitForTimeout(550);};
  const close=async()=>{await cv().locator('.sheet-close').click();await cv().locator('.sheet').waitFor({state:'detached'});};
  if(beforeHTML){
   old=true;await page.goto('http://tripfit.test/');await step('4');await cv().locator('.slot').first().waitFor();await shot('product-before');old=false;errors.length=0;warnings.length=0;
  }
  await page.goto('http://tripfit.test/');await cv().locator('.app-brand').waitFor();await page.waitForTimeout(850);await shot('logo');
  assert.equal(await page.locator('link[rel=icon]').getAttribute('href'),'favicon.svg');
  await page.locator('#capLogo').evaluate(el=>{if(el.hidden)throw Error('Logo hidden on step 0');});
  await page.keyboard.press('2');
  await page.waitForFunction(n=>document.querySelector('#fnO')?.dataset.v===n,data.sources.orderings.toLocaleString('ko-KR'));
  await page.waitForTimeout(150);
  const fit=await cv().locator('#fnN').evaluate(el=>({scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,fontSize:getComputedStyle(el).fontSize}));
  assert.ok(fit.scrollWidth<=fit.clientWidth,JSON.stringify(fit));await shot('number');
  await step('3');await cv().locator('#formula0[data-sat]').waitFor();
  await cv().locator('[data-person="0"]').click();await cv().locator('#formula0').waitFor({state:'visible'});
  assert.match(await cv().locator('#formula0').innerText(),/100×1.0 \+ 50×0.7/);
  assert.equal(await cv().locator('#formula0').getAttribute('data-calculated'),'79.4');await shot('formula-jimin');
  await cv().locator('[data-person="1"]').click();assert.equal(await cv().locator('#formula1').getAttribute('data-calculated'),'83.1');await shot('formula-seoyeon');
  for(const id of ['exh_daelim','cafe_onion']){
   await cv().locator(`.ti[data-id="${id}"] .stop`).click();await cv().locator('.sheet').waitFor();await shot(`poi-${id}`);
   assert.equal(await cv().locator('.sheet .q-row').count(),3);await close();
  }
  await cv().locator('.mks [data-pid="cafe_onion"]').click();await cv().locator('.sheet').waitFor();await shot('poi-map-marker');await close();
  await step('4');await cv().locator('.slot').waitFor();await shot('product-after');
  assert.equal(await cv().locator('.option-chip').count(),4);assert.equal(await cv().locator('.option-chip.in-window b').innerText(),'15:00');
  assert.equal(await cv().locator('.product-link').getAttribute('target'),'_blank');
  await cv().locator('.product-link').evaluate(el=>{const c=getComputedStyle(el);if(c.textDecorationLine!=='none')throw Error('Default link underline');});
  await cv().locator('.slot').first().click();await cv().locator('#addBtn').click();await cv().locator('.relax.recommended').waitFor();
  await page.waitForTimeout(3400);await shot('recommendation');
  assert.equal(await cv().locator('.relax').first().getAttribute('data-id'),'category_min:cafe');
  await cv().locator('[data-ledger]').click();await cv().locator('.sheet').waitFor();await shot('ledger');await close();
  await cv().locator('.recommended').click();await cv().locator('.stop.lock').waitFor();await page.waitForTimeout(1700);
  await cv().locator('.stop.lock').click();await cv().locator('.sheet .product-link').waitFor();await shot('poi-mrt');
  await cv().locator('.sheet .product-link').scrollIntoViewIfNeeded();await shot('poi-mrt-link');await close();
  await cv().locator('.cta-wrap .btn').click();await cv().locator('.concession-next').waitFor();await shot('agreement');
  assert.match(await cv().locator('.concession-next').innerText(),/다음엔 지민 차례/);
  const numeric=await cv().locator('.rc .gr,#split .gr').evaluateAll(nodes=>nodes.map(el=>({value:el.textContent,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth})));
  assert.ok(numeric.every(n=>n.scrollWidth<=n.clientWidth),JSON.stringify(numeric));
  await page.keyboard.press('R');await cv().locator('.app-brand').waitFor();
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('tripfit.concessions.v1')||'[]').length),0);
  await ctx.close();results.push({width,height,fit,numeric,errors,warnings});
  assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
 }
 await browser.close();fs.writeFileSync(path.join(out,'playwright-status.json'),JSON.stringify({passed:true,results},null,2)+'\n');
}
fs.mkdirSync(out,{recursive:true});
run().catch(async e=>{if(browser)await browser.close();const failure={passed:false,error:e.message,results};fs.writeFileSync(path.join(out,'playwright-status.json'),JSON.stringify(failure,null,2)+'\n');console.error(e.message);process.exitCode=1;});
