const assert=require('node:assert/strict');
const {chromium}=require('playwright');
async function main(){
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:850}});
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  const response=await page.goto('http://127.0.0.1:8765/research_hub_30a.html',{waitUntil:'domcontentloaded',timeout:45000});
  assert.equal(response.status(),200);
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  const universe=Number((await page.locator('#universe').innerText()).replace(/,/g,''));
  assert(universe>=1500,'3.0 workbench should index all listed/OTC master stocks');
  assert.equal((await page.locator('#approved').innerText()).trim(),'0','unverified scores must remain disabled');
  assert((await page.locator('#loading').innerText()).includes('來源載入成功不等於歷史回測資格'));
  assert((await page.locator('main > p.note').innerText()).includes('集保持股為週資料'));
  await page.locator('#size').selectOption('20');
  assert.equal(await page.locator('#market-rows tr').count(),20);
  await page.locator('#next').click();
  assert((await page.locator('#pages').innerText()).startsWith('2 / '),'pagination not updated');
  await page.locator('#q').fill('8064');
  assert.equal(await page.locator('#market-rows tr').count(),1,'market search failed');
  const rowText=await page.locator('#market-rows').innerText();
  assert(rowText.includes('8064'),'stock row missing after search');
  assert(rowText.includes('週截至'),'holder report week not disclosed');
  await page.locator('#market-rows [data-stock="8064"]').click();
  assert(await page.locator('#screen-detail').isVisible(),'stock research screen not visible');
  assert((await page.locator('#detail-status').innerText()).includes('8064'));
  const info=await page.locator('#detail').innerText();
  for(const phrase of ['法人交易','集保觀察週截至','公告可得時點','正式模型資格','來源晚於價格日','月營收所屬月份']){
    assert(info.includes(phrase),'missing stock research evidence '+phrase);
  }
  assert(info.includes('停用'),'nonvalidated model must be unavailable');
  await page.locator('#tab-compare').click();
  await page.locator('#stock-list').fill('8064,3533,2330');
  await page.locator('#compare').click();
  assert((await page.locator('#compare-view').innerText()).includes('8064'));
  assert.equal(await page.locator('#compare-view thead th').count(),4,'compare table needs stock and 3 company columns');
  assert((await page.locator('#compare-view').innerText()).includes('1000張以上近4週變動'));
  await page.locator('#stock-list').fill('8064,999999');
  await page.locator('#compare').click();
  assert((await page.locator('#compare-status').innerText()).includes('未知代號 999999'));
  assert.equal(await page.locator('#compare-view thead th').count(),2);
  await page.goto('http://127.0.0.1:8765/research_hub_30a.html?view=detail&stock=3533');
  await page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
  assert((await page.locator('#detail-status').innerText()).includes('3533'),'deep-linked stock failed');
  assert(await page.locator('#screen-detail').isVisible());
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#screen-detail').isVisible(),'mobile detail hidden');
  assert.deepEqual(errors,[],'browser runtime errors: '+errors.join('; '));
  console.log('PASS 3.0A: whole-market filters, pagination, drilldown, weekly holder dates, five-stock comparison, deep linking and mobile UI');
 }finally{await browser.close()}
}
main().catch(err=>{console.error(err);process.exitCode=1});