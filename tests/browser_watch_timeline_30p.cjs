const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-page="watch"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#r-timeline-from option').length>=2,{timeout:60000});
  assert.equal(await page.locator('section[aria-label="3.0P自選股研究時間軸"]').count(),1);
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7,'do not create duplicate menu');
  for(const id of ['8064','3533','2345']){
   await page.locator('#r-watch-add-code').fill(id);
   await page.locator('#r-watch-add-form button[type=submit]').click();
  }
  assert.equal(await page.locator('#r-timeline-stock option').count(),3);
  await page.locator('#r-timeline-stock').selectOption('8064');
  const days=await page.locator('#r-timeline-from option').evaluateAll(items=>items.map(x=>x.value));
  assert(days.length>=2,'must have at least two unique source-price days');
  await page.locator('#r-timeline-from').selectOption(days[0]);
  await page.locator('#r-timeline-to').selectOption(days.at(-1));
  await page.locator('#r-timeline-go').click();
  const nodes=page.locator('[data-timeline-day]');
  await page.waitForFunction(n=>document.querySelectorAll('[data-timeline-day]').length===n,days.length,{timeout:60000});
  assert.equal(await nodes.count(),days.length,'all archived price dates must be shown once each');
  assert.deepEqual(await nodes.evaluateAll(items=>items.map(x=>x.getAttribute('data-timeline-day'))),days);
  assert((await page.locator('.r-timeline-info').innerText()).includes('不重複計算'));
  assert((await page.locator('.r-watch-timeline').innerText()).includes('SHA256'));
  assert((await page.locator('.r-watch-timeline').innerText()).includes('不代表所有交易日'));
  await page.locator('#r-timeline-filter').selectOption('new_holder');
  for(const n of await nodes.all())assert((await n.innerText()).includes('集保週資料日'));
  await page.locator('#r-timeline-filter').selectOption('changes');
  assert((await page.locator('.r-timeline-summary').innerText()).includes('狀態改變'));
  await page.locator('#r-timeline-filter').selectOption('all');
  const [download]=await Promise.all([page.waitForEvent('download'),
    page.locator('#r-timeline-export').click()]);
  assert(download.suggestedFilename().includes('30P_8064'));
  const csv=fs.readFileSync(await download.path(),'utf8');
  assert(csv.includes('首次捕捉UTC')&&csv.includes('官方首次公布時間'));
  assert(csv.includes('集保來源週日期')&&csv.includes('未核實'));
  assert.equal(csv.split('\r\n').length,days.length+1);
  await page.locator('#r-timeline-stock').selectOption('3533');
  assert((await page.locator('.r-timeline-list').innerText()).includes('3533') ||
    (await page.locator('.r-watch-timeline').innerText()).includes('3533'));
  await page.locator('#r-timeline-to').selectOption(days[0]);
  assert.equal(await page.locator('.r-timeline-list').count(),0,'date changes must invalidate prior output');
  await page.locator('#r-timeline-go').click();
  await page.locator('section.r-watch-timeline [role=alert]').waitFor({timeout:15000});
  assert((await page.locator('section.r-watch-timeline [role=alert]').innerText()).includes('兩個不同日期'));
  await page.locator('#r-timeline-to').selectOption(days.at(-1));
  await page.locator('#r-timeline-go').click();
  await page.waitForFunction(n=>document.querySelectorAll('[data-timeline-day]').length===n,days.length,{timeout:60000});
  // Old 3.0O two-day comparison remains available below the timeline.
  assert.equal(await page.locator('#r-history-first').count(),1);
  assert.equal(await page.locator('#r-history-go').count(),1);
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('.r-watch-timeline').isVisible());
  assert(await page.locator('#r-timeline-stock').isVisible());
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.deepEqual(errors,[],'page Javascript errors');
  console.log('PASS 3.0P: all unique archived days, SHA timeline, filters, CSV, invalidated ranges, retained 3.0O and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
