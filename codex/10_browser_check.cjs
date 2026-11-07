// Reproduce the three payment flows and capture both requested viewport sizes.
// Optional PLAYWRIGHT_MODULE / PLAYWRIGHT_EXECUTABLE select an installed browser.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'codex/10_shots');
let browser;const results=[];
async function run(){
 const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/Users/harheem/.npm/_npx/705bc6b22212b352/node_modules/playwright');
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE}:{})});
 for(const [width,height]of [[390,844],[1440,900]]){
  const ctx=await browser.newContext({viewport:{width,height}});
  await ctx.route('http://localhost/**',async route=>{
   const url=new URL(route.request().url());
   // Exercise the real fallback path, without contacting a payment provider.
   if(url.pathname==='/api/pay/recheck')return route.fulfill({status:503,body:'offline fallback check'});
   const relative=url.pathname.endsWith('/')?url.pathname+'index.html':url.pathname;
   const file=path.join(root,'web',relative);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'missing file'});
   const contentType={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json'}[path.extname(file)];
   return route.fulfill({path:file,contentType});
  });
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const url='http://localhost/pay/'+(width===390?'?embed=1':'');
  const shot=async name=>{
   await page.screenshot({path:path.join(out,`${width}-${name}.png`),fullPage:true,animations:'disabled'});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.querySelector('.shell').scrollWidth>document.querySelector('.shell').clientWidth);
   assert.equal(overflow,false,`overflow ${width} ${name}`);
  };
  const hold=async locator=>{await locator.scrollIntoViewIfNeeded();await locator.focus();await page.keyboard.down(' ');await page.waitForTimeout(1150);await page.keyboard.up(' ');};
  const approveBoth=async()=>{await hold(page.locator('.person-card .hold').nth(0));await hold(page.locator('.person-card .hold').nth(0));};
  await page.goto(url);await page.locator('#next').waitFor();await page.evaluate(()=>document.fonts.ready);await shot('01_plan');
  await page.locator('#next').click();await shot('02_mandates');
  await approveBoth();await page.locator('#next').click();await page.locator('.result').waitFor();await shot('03_recheck');
  await page.locator('#next').click();assert.equal(await page.locator('[data-pass=true]').count(),6);await shot('04_quote');
  // A short hold must never approve a payment.
  await page.locator('.hold').focus();await page.keyboard.down(' ');await page.waitForTimeout(250);await page.keyboard.up(' ');assert.equal(await page.locator('.receipt').count(),0);
  await hold(page.locator('.hold'));await page.locator('.receipt').waitFor();await shot('05_paid');
  await page.locator('#technical>summary').click();await page.locator('#test-merchant').click();await page.locator('.blocked').waitFor();assert.match(await page.locator('.blocked').innerText(),/MERCHANT_MISMATCH/);await shot('05_paid_and_rejected');
  await page.locator('#technical>summary').click();await page.locator('#reset').click();await page.locator('#next').click();await approveBoth();await page.locator('#next').click();await page.locator('.result').waitFor();await page.locator('#next').click();
  await page.locator('#technical>summary').click();await page.locator('#test-price').click();assert.equal(await page.locator('.hold').isDisabled(),true);assert.equal(await page.locator('[data-check=price]').getAttribute('data-pass'),'false');await shot('04b_price_stop');
  await page.locator('#reapprove').click();await approveBoth();await page.locator('#next').click();assert.equal(await page.locator('[data-pass=true]').count(),6);await shot('04c_reapproved');await hold(page.locator('.hold'));await page.locator('.receipt').waitFor();assert.match(await page.locator('.receipt-total').innerText(),/76,000/);await shot('05_price_paid');
  assert.deepEqual(errors,[]);results.push({width,height,passed:true,flows:['normal','price-reapproval','merchant-rejection'],pageErrors:errors});await ctx.close();
 }
 await browser.close();fs.writeFileSync(path.join(out,'playwright-status.json'),JSON.stringify({passed:true,results},null,2));
}
run().catch(async e=>{fs.writeFileSync(path.join(out,'playwright-status.json'),JSON.stringify({passed:false,error:String(e.stack),results},null,2));console.error(String(e));await browser?.close();process.exitCode=1;});
