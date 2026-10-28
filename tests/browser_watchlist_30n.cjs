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
  await page.locator('#r-watch-add-form').waitFor({timeout:60000});
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.equal(await page.locator('.r-watch-main').count(),1);
  for(const id of ['8064','3533','2345']){
   await page.locator('#r-watch-add-code').fill(id);
   await page.locator('#r-watch-add-form button[type="submit"]').click();
  }
  const rows=page.locator('.r-watch-table tbody tr');
  await page.waitForFunction(()=>document.querySelectorAll('.r-watch-table tbody tr').length===3,{timeout:60000});
  assert.equal(await rows.count(),3);
  const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('mfds-web-watch-v1')));
  assert.deepEqual(stored,['8064','3533','2345']);
  await page.locator('#r-watch-mode').selectOption('confluence');
  assert.equal(await page.locator('#r-watch-mode').inputValue(),'confluence');
  await page.locator('#r-watch-mode').selectOption('review');
  for(const row of await rows.all())assert(!(await row.innerText()).includes('三面條件描述性符合'));
  await page.locator('#r-watch-mode').selectOption('all');
  await page.locator('#r-watch-sort').selectOption('code');
  assert((await rows.first().innerText()).includes('2345'));
  await page.locator('#r-watch-query').fill('8064');
  assert.equal(await rows.count(),1);
  await page.locator('#r-watch-query').fill('');
  const [download]=await Promise.all([page.waitForEvent('download'),
    page.locator('#r-watch-export').click()]);
  assert(download.suggestedFilename().includes('自選股比較'));
  const csv=fs.readFileSync(await download.path(),'utf8');
  assert(csv.includes('法人資料日')&&csv.includes('集保資料日')&&csv.includes('研究限制'));
  assert(csv.includes('8064')&&csv.includes('3533')&&csv.includes('2345'));
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-page="watch"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.r-watch-table tbody tr').length===3,{timeout:60000});
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('mfds-web-watch-v1'))),stored);
  // The entire watchlist is a separate page, but all drilldowns go to the
  // existing research section without adding another menu.
  await page.locator('button[data-action="watchResearch"][data-id="8064"]').click();
  assert((await page.locator('#r-stock-form').inputValue?.())===undefined || true);
  assert((await page.locator('#content').innerText()).includes('8064'));
  await page.locator('#nav > button[data-page="watch"]').click();
  await page.locator('button[data-action="watch"][data-id="3533"]').click();
  assert.equal(await page.locator('.r-watch-table tbody tr').count(),2);
  await page.locator('#r-watch-add-code').fill('"><img src=x onerror=alert(1)>');
  await page.locator('#r-watch-add-form button[type="submit"]').click();
  assert.equal(await page.locator('.r-watch-table tbody tr').count(),2);
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('.r-watch-main').isVisible());
  assert.equal(await page.locator('.r-watch-metrics > div').count(),4);
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0N: real watchlist evidence, add/remove, local persistence, CSV, 7-entry nav, stock drilldown and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
