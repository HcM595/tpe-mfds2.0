const assert=require('node:assert/strict');
const {chromium}=require('playwright');
async function main(){
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:850},acceptDownloads:true});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const go=()=>page.goto('http://127.0.0.1:8765/research_hub_30a.html',{waitUntil:'domcontentloaded',timeout:45000});
 const ready=()=>page.waitForFunction(()=>document.querySelector('#loading')?.textContent.includes('已載入'),{timeout:60000});
 try{
  await go();await ready();
  await page.locator('#tab-quality').click();
  assert(await page.locator('#screen-quality').isVisible(),'new quality screen should open');
  const total=Number((await page.locator('#quality-universe').innerText()).replace(/,/g,''));
  assert(total>1500,'audit must use whole current stock universe');
  assert.equal((await page.locator('#quality-model').innerText()).trim(),'0','unverified model not eligible');
  assert.equal(await page.locator('#quality-rows tr').count(),8,'all eight data sources should be diagnosed');
  assert((await page.locator('#quality-status').innerText()).includes('價格資料日'),'source quality should state price as-of');
  assert((await page.locator('#quality-rows').innerText()).includes('集保為週觀察'),'holder cadence should be disclosed');
  await page.locator('#tab-detail').click();
  await page.locator('#stock-id').fill('8064');
  await page.locator('#lookup').click();
  assert.equal(await page.locator('#evidence tbody tr').count(),9,'all nine factual and source clock checks');
  const detail=await page.locator('#evidence').innerText();
  for(const phrase of ['集保','未核實','不可作歷史回測','模型','F2估值公開時間']){
   assert(detail.includes(phrase),'missing stock-level provenance explanation: '+phrase);
  }
  await page.locator('#tab-market').click();
  await page.locator('#q').fill('8064');
  assert.equal(await page.locator('#market-rows tr').count(),1);
  const [download]=await Promise.all([
    page.waitForEvent('download',{timeout:20000}),
    page.locator('#export-market').click()
  ]);
  assert(download.suggestedFilename().startsWith('mfds_30b_market_observations_'),'filtered CSV name should include snapshot date');
  assert(download.suggestedFilename().endsWith('.csv'));
  // Read download file from browser via Node filesystem, assert source timestamp and gate fields.
  const fs=require('node:fs');
  const file=await download.path();
  const csv=fs.readFileSync(file,'utf8');
  assert(csv.includes('股票代號,公司名稱'));
  assert(csv.includes('8064'));
  assert(csv.includes('歷史回測資格'));
  assert(csv.includes('false'));
  assert.equal(csv.split('\r\n').length,3,'filtered export must include one row and header');
  await page.locator('#tab-compare').click();
  await page.locator('#stock-list').fill('8064,3533');
  const [pair]=await Promise.all([
    page.waitForEvent('download',{timeout:20000}),
    page.locator('#export-compare').click()
  ]);
  assert(pair.suggestedFilename().startsWith('mfds_30b_stock_comparison_'));
  const content=fs.readFileSync(await pair.path(),'utf8');
  assert(content.includes('8064,東捷'));
  assert(content.includes('3533,嘉澤'));
  assert.equal(content.split('\r\n').length,4,'two stock records plus header');
  await page.goto('http://127.0.0.1:8765/research_hub_30a.html?view=quality');
  await ready();
  assert(await page.locator('#screen-quality').isVisible(),'quality view deep link must load');
  assert.deepEqual(errors,[],'unhandled browser errors '+errors.join(';'));
  console.log('PASS 3.0B: whole-universe data diagnostics, stock-level source dates, safe CSV exports and deep-linked quality view');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1});
