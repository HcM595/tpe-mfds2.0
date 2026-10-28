const assert=require('node:assert/strict');
const {chromium}=require('playwright');
async function run(){
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1240,height:860}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/research_hub_30a.html?view=quality',{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  assert((await page.locator('#snapshot-status').innerText()).includes('9/9'),'nine research files must match same release');
  assert.equal(await page.locator('#manifest-rows tr').count(),9);
  assert((await page.locator('#action-summary').innerText()).includes('已觀察到歷史除權息事件'));
  assert.equal((await page.locator('#quality-model').innerText()).trim(),'0','model remains disabled');
  await page.locator('#tab-detail').click();
  await page.locator('#stock-id').fill('1101');
  await page.locator('#lookup').click();
  const audited=await page.locator('#action-detail').innerText();
  assert(audited.includes('官方歷史事件觀察筆數'));
  assert(audited.includes('官方除權息前收／參考價'));
  assert(audited.includes('正式除權息還原與總報酬資格'));
  assert(audited.includes('不得計算'),'observations should not enable total returns');
  await page.locator('#tab-compare').click();
  await page.locator('#stock-list').fill('1101,3533');
  await page.locator('#compare').click();
  assert((await page.locator('#compare-view').innerText()).includes('歷史除權息事件（僅已觀察）'));
  assert((await page.locator('#compare-view').innerText()).includes('歷史還原及總報酬'));
  await page.route('**/data/corporate_action_readiness_30e.csv',async route=>{
   const response=await route.fetch();
   await route.fulfill({response,body:(await response.text())+'\n',contentType:'text/csv; charset=utf-8'});
  });
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  assert((await page.locator('#snapshot-status').innerText()).includes('8/9'),'modified corporate action data must be quarantined');
  assert((await page.locator('#action-summary').innerText()).includes('除權息稽核來源異常'));
  await page.locator('#tab-detail').click();
  await page.locator('#stock-id').fill('1101');
  await page.locator('#lookup').click();
  assert((await page.locator('#action-detail').innerText()).includes('來源未取得或版本不一致'));
  assert.deepEqual(errors,[],'browser runtime errors '+errors.join('; '));
  console.log('PASS 3.0E: ex-right event/price reference audit, 9-source manifest, tampering quarantine and no total-return claims');
 }finally{await browser.close()}
}
run().catch(e=>{console.error(e);process.exitCode=1});
