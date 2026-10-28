const assert=require('node:assert/strict');
const {chromium}=require('playwright');
async function main(){
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:850}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  const res=await page.goto('http://127.0.0.1:8765/research_hub_30a.html?view=quality',{waitUntil:'domcontentloaded',timeout:45000});
  assert.equal(res.status(),200);
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  assert(await page.locator('#screen-quality').isVisible(),'source quality tab not visible');
  const summary=await page.locator('#integrity-summary').innerText();
  assert(summary.includes('身分／日期需核對'),'cross-table issue counts missing');
  assert(summary.includes('首次取得／公告資格提醒'),'first-capture limit explanation missing');
  assert((await page.locator('#integrity-rows').innerText()).length>15,'diagnostic issue explorer empty');
  await page.locator('#integrity-filter').selectOption('captures');
  await page.locator('#integrity-q').fill('8064');
  const filtered=await page.locator('#integrity-rows').innerText();
  assert(filtered.includes('8064'),'unable to filter source clock evidence by stock');
  assert(filtered.includes('首次取得')||filtered.includes('正式公告'),'source capture information missing');
  const buttons=await page.locator('#integrity-rows [data-integrity-stock="8064"]').count();
  assert(buttons>=1,'stock evidence deep link missing');
  await page.locator('#integrity-rows [data-integrity-stock="8064"]').first().click();
  assert(await page.locator('#screen-detail').isVisible(),'drilldown from source issue did not open stock');
  assert((await page.locator('#detail-status').innerText()).includes('8064'));
  const audit=await page.locator('#integrity-detail').innerText();
  assert(audit.includes('首次取得')||audit.includes('尚未核實'),'per-stock source audit missing');
  await page.locator('#tab-quality').click();
  await page.locator('#integrity-filter').selectOption('issues');
  await page.locator('#integrity-q').fill('this-company-does-not-exist');
  assert((await page.locator('#integrity-rows').innerText()).includes('沒有對應的待查項目'),'empty issue search not handled');
  await page.locator('#integrity-q').fill('');
  assert.equal((await page.locator('#quality-model').innerText()).trim(),'0','unvalidated model must stay disabled');
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#screen-quality').isVisible(),'mobile quality view should remain accessible');
  assert.deepEqual(errors,[],'browser exceptions: '+errors.join('; '));
  console.log('PASS 3.0C: official source identity/date quality explorer, stock drilldown, capture-time caveats, mobile and no model scores');
 }finally{await browser.close()}
}
main().catch(e=>{console.error(e);process.exitCode=1});
