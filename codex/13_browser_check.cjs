// Offline end-to-end checks for result return, revocation and visible stop simulations.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/Users/harheem/.npm/_npx/705bc6b22212b352/node_modules/playwright');
const root=path.resolve(__dirname,'..');
let browser;
async function run(){
 browser=await chromium.launch({headless:true});
 const results=[];
 for(const width of [375,1280]){
  const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
  let inquiryMode='template',availability=true;
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.protocol==='blob:')return route.continue();
   if(url.hostname!=='localhost')return route.abort();
   if(url.pathname==='/api/pay/inquiry'&&inquiryMode==='llm')return route.fulfill({json:{text:'안녕하세요. 15:00에 2명 예약이 가능한지 문의드립니다. 각자 분담 결제할 예정입니다. 우천 진행 여부와 집결지를 알려 주시면 감사하겠습니다.',provider:'axk2',model:'ax-k2',ms:25}});
   if(url.pathname==='/api/pay/recheck'&&!availability)return route.fulfill({json:{available:false,price:null,checked_at:new Date().toISOString(),source:'live',option_start:'15:00'}});
   if(url.pathname.startsWith('/api/'))return route.fulfill({status:404,body:'offline'});
   const relative=url.pathname.endsWith('/')?url.pathname+'index.html':url.pathname;
   const file=path.join(root,'web',relative);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'missing'});
   return route.fulfill({path:file,contentType:{'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json'}[path.extname(file)]});
  });
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const hold=async locator=>{await locator.scrollIntoViewIfNeeded();await locator.focus();await page.keyboard.down(' ');await page.waitForTimeout(1100);await page.keyboard.up(' ');};
  const both=async scope=>{await hold(scope.locator('.person-card .hold').first());await hold(scope.locator('.person-card .hold').first());};
  const quote=async(scope=page)=>{await scope.locator('#next').click();await both(scope);await scope.locator('#next').click();await scope.locator('.result').waitFor();await scope.locator('#next').click();};
  const overflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.querySelector('.shell').scrollWidth>document.querySelector('.shell').clientWidth),false);
  await page.goto('http://localhost/pay/');await page.locator('#next').waitFor();await quote();
  assert.equal(await page.locator('[data-pass=true]').count(),6);
  await page.locator('[data-sim=price]').click();
  assert.equal(await page.locator('[data-check=price]').getAttribute('data-pass'),'false');assert.equal(await page.locator('.hold').isDisabled(),true);
  assert.equal(await page.locator('.simulation-note').textContent(),'시뮬레이션');await overflow();
  await page.locator('#reapprove').click();await both(page);await page.locator('#next').click();await hold(page.locator('.hold'));await page.locator('.receipt').waitFor();
  assert.match(await page.locator('.receipt-total').innerText(),/76,000/);
  await page.locator('[data-sim=merchant]').click();assert.equal(await page.locator('[data-check=merchant]').getAttribute('data-pass'),'false');assert.equal(await page.locator('.hold').isDisabled(),true);
  await page.screenshot({path:`/tmp/tripfit-${width}-merchant-stop.png`,fullPage:true});await overflow();
  await page.locator('#reapprove').click();await both(page);await page.locator('#next').click();assert.equal(await page.locator('[data-pass=true]').count(),6);
  // Revocation is visible in all three mandate stages and can be repaired.
  await page.locator('[data-revoke]').first().click();assert.equal(await page.locator('[data-check=unused]').getAttribute('data-pass'),'false');assert.equal(await page.locator('.hold').isDisabled(),true);
  await page.locator('#reapprove').click();await both(page);await page.locator('[data-revoke]').first().click();assert.equal(await page.locator('.hold').isDisabled(),true);
  await page.goto('http://localhost/pay/');await page.locator('#next').click();await both(page);await page.locator('#next').click();await page.locator('.draft').waitFor();
  assert.match(await page.locator('#inquiry-meta').textContent(),/고정 문안/);assert.match(await page.locator('#inquiry-text').textContent(),/분담.*우천.*집결지/);
  await page.locator('[data-revoke]').first().click();assert.equal(await page.locator('[data-check=unused]').getAttribute('data-pass'),'false');
  inquiryMode='llm';await page.goto('http://localhost/pay/');await page.locator('#next').click();await both(page);await page.locator('#next').click();await page.locator('#inquiry-meta').filter({hasText:'A.X K2 작성'}).waitFor();
  await page.locator('#next').click();await hold(page.locator('.hold'));await page.locator('.receipt').waitFor();await page.locator('[data-sim=price]').click();assert.equal(await page.locator('[data-check=price]').getAttribute('data-pass'),'false');
  availability=false;await page.goto('http://localhost/pay/');await quote();assert.equal(await page.locator('[data-check=available]').getAttribute('data-pass'),'false');assert.equal(await page.locator('.hold').isDisabled(),true);availability=true;
  // Embedded result closes only the active same-origin sheet and survives replanning.
  await page.goto('http://localhost/');await page.waitForFunction(()=>typeof go==='function');await page.evaluate(()=>go(4));await page.locator('.app').first().click();await page.locator('.app').nth(1).click();await page.locator('#openPay:enabled').waitFor();await page.locator('#openPay').click();
  let frame=page.frameLocator('iframe');await frame.locator('#next').waitFor();await quote(frame);
  await frame.locator('[data-revoke]').first().click();await page.locator('#payStopped').waitFor();assert.match(await page.locator('#payStopped').textContent(),/취소.*다시 맡기기/);
  await page.locator('#closePay').click();await page.locator('iframe').waitFor({state:'detached'});await page.locator('#openPay').click();frame=page.frameLocator('iframe');await frame.locator('#next').waitFor();
  await page.evaluate(()=>{window.payMessages=[];addEventListener('message',e=>{if(e.data?.type==='tripfit-pay')payMessages.push(e.data);});const f=document.querySelector('iframe');dispatchEvent(new MessageEvent('message',{origin:'https://other.invalid',source:f.contentWindow,data:{type:'tripfit-pay',status:'stopped',reason:'forged'}}));dispatchEvent(new MessageEvent('message',{origin:location.origin,source:window,data:{type:'tripfit-pay',status:'stopped',reason:'wrong frame'}}));});
  assert.equal(await page.locator('iframe').count(),1);assert.doesNotMatch(await page.locator('#payStopped').textContent(),/forged|wrong frame/);
  await quote(frame);await hold(frame.locator('.hold'));await page.locator('iframe').waitFor({state:'detached'});
  assert.match(await page.locator('#pay').innerText(),/결제 완료.*지민 35,000원.*승인번호.*서연 35,000원/s);
  assert.match(await page.locator('#pay').innerText(),/마이리얼트립에서 예약 확정/);
  assert.equal(await page.locator('#openPay').isDisabled(),true);
  assert.match(await page.locator('#island').innerText(),/같이 결제 완료, 70,000원/);
  const paid=await page.evaluate(()=>payMessages.filter(m=>m.status==='paid'));assert.equal(paid.length,1);assert.equal(paid[0].total,70000);assert.equal(paid[0].hash8.length,8);
  assert.match(await page.locator('body').innerText(),/AGENTIC PAY 결제 완료 70,000원, 승인 2건, 기록 [a-f0-9]{8}/);
  await page.screenshot({path:`/tmp/tripfit-${width}-paid-parent.png`,fullPage:true});
  await page.evaluate(()=>go(5));await page.locator('.ti .pill').filter({hasText:'결제 완료'}).waitFor();
  await page.waitForTimeout(1500);await page.getByRole('button',{name:'붐비는 곳 빼고 다시 짜기'}).click();await page.getByRole('button',{name:'처음부터 다시 보기'}).waitFor();
  assert.equal(await page.locator('.ti .pill').filter({hasText:'결제 완료'}).count(),1);assert.match(await page.locator('.ti').filter({hasText:'결제 완료'}).innerText(),/15:00/);
  await page.screenshot({path:`/tmp/tripfit-${width}-paid-replan.png`,fullPage:true});
  assert.deepEqual(errors,[]);results.push({width,passed:true});await context.close();
 }
 console.log(JSON.stringify({passed:true,results}));await browser.close();
}
run().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});
