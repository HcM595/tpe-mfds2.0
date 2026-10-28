const assert=require('node:assert/strict');
const {chromium}=require('playwright');
async function main(){
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1200,height:820}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  const url='http://127.0.0.1:8765/research_hub_30a.html?view=quality';
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  assert(await page.locator('#screen-quality').isVisible());
  assert((await page.locator('#snapshot-status').innerText()).includes('8/8'),'8-byte source manifest verification failed');
  assert.equal(await page.locator('#manifest-rows tr').count(),8);
  assert((await page.locator('#manifest-summary').innerText()).includes('建立UTC：'),'manifest generation UTC clock should be explicit');
  assert.equal((await page.locator('#quality-model').innerText()).trim(),'0');
  await page.route('**/data/chip_signals.csv',async route=>{
   const result=await route.fetch();
   const text=await result.text();
   await route.fulfill({response:result,body:text+'\n',contentType:'text/csv; charset=utf-8'});
  });
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  const receipt=await page.locator('#snapshot-status').innerText();
  assert(receipt.includes('7/8')&&receipt.includes('部分資料異常'),'modified source should be quarantined');
  assert((await page.locator('#manifest-rows').innerText()).includes('SHA256')||
         (await page.locator('#manifest-rows').innerText()).includes('檔案大小'),'manifest cause missing');
  assert((await page.locator('#quality-rows').innerText()).includes('讀取失敗'),'quality panel must show quarantine');
  assert.equal((await page.locator('#quality-flows').innerText()).trim(),'0','invalid chip file must not yield institutional flows');
  assert.equal((await page.locator('#quality-holders').innerText()).trim(),'0','invalid chip file must not yield holder counts');
  await page.unrouteAll();
  await page.route('**/data/factor_evidence_29a.csv',async route=>{
    const r=await route.fetch();await route.fulfill({response:r,body:'stock_id\n8064\n'});
  });
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('無法啟動'),{timeout:60000});
  assert((await page.locator('#snapshot-status').innerText()).includes('來源快照校驗失敗'));
  assert.deepEqual(errors,[],'JavaScript page errors '+errors.join('; '));
  console.log('PASS 3.0D: 8 source hashes verified, tampered optional source quarantined, tampered research master blocks page');
 }finally{await browser.close()}
}
main().catch(err=>{console.error(err);process.exitCode=1});
