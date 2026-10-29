const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const section=page.locator('section[aria-label="3.0R歷史資料覆蓋與發布一致性"]');
  await section.waitFor({timeout:60000});
  await page.waitForFunction(()=>{const x=document.querySelector('section[aria-label="3.0R歷史資料覆蓋與發布一致性"]');return x&&x.innerText.includes('首次封存價格日')&&!x.innerText.includes('尚未產生')},{timeout:60000});
  const title=await section.innerText();
  assert(title.includes('封存連續性與歷史涵蓋稽核'));
  assert(title.includes('不是該股票缺行情'));
  assert(title.includes('正式績效樣本仍為0'));
  assert(title.includes('保持停用'));
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  const links=section.locator('a[href]');
  const hrefs=await links.evaluateAll(items=>items.map(x=>x.getAttribute('href')));
  assert(hrefs.some(v=>v.includes('archive_coverage_meta_30r.json')));
  assert(hrefs.some(v=>v.includes('archive_day_coverage_30r.csv')));
  assert(hrefs.some(v=>v.includes('stock_candidate_coverage_30r.csv')));
  const source=await page.request.get(new URL('./data/archive_coverage_meta_30r.json',page.url()).href);
  assert.equal(source.status(),200);
  const meta=await source.json();
  assert(meta.verified_price_days>=2);
  assert(meta.archived_stock_day_records>=200);
  assert.equal(meta.trade_performance_enabled,false);
  assert.equal(meta.verified_trade_samples,0);
  assert.equal(meta.certified_win_rate,null);
  await section.locator('summary').click();
  const table=section.locator('table').first();
  assert((await table.innerText()).includes('2026-10-23'));
  const rowsText=await table.innerText();
  const eventSource=await page.request.get(new URL('./data/official_closure_notice_evidence_30u.json',page.url()).href);
  if(eventSource.ok()){
   const event=await eventSource.json();
   if(event.sources?.TWSE?.full_original_document_verified===true)
    assert(rowsText.includes('上市原始公告已核對／上櫃仍待獨立核實'));
   else assert(rowsText.includes('臨時休市待補官方公告'));
  }else assert(rowsText.includes('臨時休市待補官方公告'));
  const day=await page.request.get(new URL('./data/archive_day_coverage_30r.csv',page.url()).href);
  assert.equal(day.status(),200);
  assert((await day.text()).includes('extraordinary_closure_requires_official_source'));
  await page.setViewportSize({width:390,height:844});
  assert(await section.isVisible());
  assert.deepEqual(errors,[],'uncaught browser errors');
  console.log('PASS 3.0R: archived-source coverage, exception review, exact status/linked files, 7 unique nav and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
