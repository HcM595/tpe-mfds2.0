const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true});
 const errors=[];page.on('pageerror',x=>errors.push(x.message));
 try{
  const r=await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  assert.equal(r.status(),200);
  await page.locator('#nav > button[data-research-tab="stock"]').click();
  await page.locator('#r-stock-form').waitFor({timeout:60000});
  for(const id of ['8064','3533','2345']){
   await page.locator('#r-stock-code').fill(id);
   await page.locator('#r-stock-form button[type="submit"]').click();
   const section=page.locator('section[aria-label="3.0M個股研究證據摘要"]');
   await section.waitFor();
   assert((await section.innerText()).includes(id));
   assert.equal(await section.locator('.r-evidence-mini').count(),4);
   assert.equal(await section.locator('.r-evidence-details').count(),2);
   assert.equal(await section.locator('.r-evidence-risk').count(),1);
   assert((await section.innerText()).includes('正式勝率'));
   assert((await section.innerText()).includes('來源'));
   assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
   await section.locator('.r-evidence-details').first().locator('summary').click();
   assert.equal(await section.locator('.r-evidence-details').first().locator('tbody tr').count(),10,
     'individual clock evidence rows missing');
   const [download]=await Promise.all([
     page.waitForEvent('download'),page.locator('#r-stock-evidence-export').click()
   ]);
   assert(download.suggestedFilename().includes(id));
   const csv=fs.readFileSync(await download.path(),'utf8');
   assert(csv.includes('官方公布時分')&&csv.includes('行情基準日'));
   assert(csv.includes('資料來源')&&csv.includes('12因子'));
   assert(csv.includes(id));
  }
  await page.locator('#r-stock-code').fill('999999');
  await page.locator('#r-stock-form button[type="submit"]').click();
  assert((await page.locator('#content').innerText()).includes('尚未出現在目前已載入的資料'));
  assert.equal(await page.locator('section[aria-label="3.0M個股研究證據摘要"]').count(),0);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#r-stock-code').fill('8064');
  await page.locator('#r-stock-form button[type="submit"]').click();
  const summary=page.locator('.r-evidence-brief');
  assert(await summary.isVisible());
  assert.equal(await summary.locator('.r-evidence-mini').count(),4);
  assert.deepEqual(errors,[],'Uncaught JS runtime errors');
  console.log('PASS 3.0M: three stock studies, 10 evidence clocks, CSV export, unknown stock and mobile');
 }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
