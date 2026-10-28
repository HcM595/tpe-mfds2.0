const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1365,height:900},acceptDownloads:true});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-page="watch"]').click();
  await page.locator('#r-history-first option').first().waitFor({state:'attached',timeout:60000});
  await page.waitForFunction(()=>document.querySelectorAll('#r-history-first option').length>=2,{timeout:60000});
  const count=await page.locator('#r-history-first option').count();
  assert(count>=2);
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.equal(await page.locator('.r-watch-history').count(),1);
  const info=await page.locator('.r-watch-history-note').innerText();
  assert(info.includes('僅供稽核')&&info.includes('不作為額外歷史樣本'));
  for(const id of ['8064','3533','2345']){
   await page.locator('#r-watch-add-code').fill(id);
   await page.locator('#r-watch-add-form button[type=submit]').click();
  }
  await page.locator('#r-history-go').click();
  await page.locator('.r-watch-history-verified').waitFor({timeout:60000});
  assert((await page.locator('.r-watch-history-verified').innerText()).includes('SHA256'));
  let rows=page.locator('[data-watch-history-stock]');
  assert.equal(await rows.count(),3);
  const stock=(await rows.allInnerTexts()).join('\n');
  assert(stock.includes('8064')&&stock.includes('3533')&&stock.includes('2345'));
  const caption=await page.locator('.r-watch-history .r-watch-foot').innerText();
  assert(caption.includes('法人')&&caption.includes('沒有')===false || caption.includes('法人'));
  assert(caption.includes('不會')&&caption.includes('原始'));
  const [download]=await Promise.all([
   page.waitForEvent('download'),page.locator('#r-history-export').click()
  ]);
  assert(download.suggestedFilename().includes('30O'));
  const data=fs.readFileSync(await download.path(),'utf8');
  assert(data.includes('較早封存日')&&data.includes('更早首次封存UTC'));
  assert(data.includes('8064')&&data.includes('3533'));
  // Change to a same-day selection: must block and not present the previous comparison.
  const first=await page.locator('#r-history-first').inputValue();
  await page.locator('#r-history-second').selectOption(first);
  assert.equal(await page.locator('.r-watch-history-verified').count(),0);
  await page.locator('#r-history-go').click();
  await page.locator('.r-watch-history [role=alert]').waitFor({timeout:20000});
  assert((await page.locator('.r-watch-history [role=alert]').innerText()).includes('不同'));
  const options=await page.locator('#r-history-first option').evaluateAll(x=>x.map(n=>n.value));
  await page.locator('#r-history-first').selectOption(options[0]);
  await page.locator('#r-history-second').selectOption(options.at(-1));
  await page.locator('#r-history-go').click();
  await page.locator('.r-watch-history-verified').waitFor({timeout:60000});
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-page="watch"]').click();
  await page.locator('#r-history-first option').first().waitFor({state:'attached',timeout:60000});
  assert.equal(await page.locator('#r-watch-add-form').count(),1);
  assert.equal(await page.locator('[data-watch-stock]').count(),3);
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('.r-watch-history-controls').isVisible());
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0O: SHA256 verified actual archive snapshots, two dates, CSV, correct invalid range, persistence and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
