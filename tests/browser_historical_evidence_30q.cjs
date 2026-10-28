const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:850}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('[aria-label="3.0Q歷史證據與正式驗證稽核"]');
  await panel.waitFor({timeout:60000});
  const t=await panel.innerText();
  assert(t.includes('歷史原始證據')&&t.includes('正式驗證'));
  assert(t.includes('正式交易績效樣本')&&t.includes('禁止啟用'));
  assert(t.includes('下載完整可追溯歷史CSV'));
  await panel.locator('summary').click();
  assert((await panel.innerText()).includes('官方'));
  const meta=await page.evaluate(()=>window.MFDSWatchTimeline30P?true:false);
  assert(meta);
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  const url=await panel.locator('a[href*="historical_evidence_30q.csv"]').getAttribute('href');
  const response=await page.request.get(new URL(url,page.url()).href);
  assert.equal(response.status(),200);
  const txt=await response.text();
  assert(txt.includes('first_snapshot_sha256'));
  assert(txt.includes('foreign_5d_shares')&&txt.includes('large1000_4w_pp'));
  const jsonResponse=await page.request.get(new URL('./data/historical_evidence_meta_30q.json',page.url()).href);
  assert.equal(jsonResponse.status(),200);
  const metaJson=await jsonResponse.json();
  assert(metaJson.unique_first_captured_price_sessions>=2);
  assert.equal(metaJson.strict_validation.verified_trade_samples,0);
  assert.equal(metaJson.strict_validation.model_enabled,false);
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0Q: historical SHA-bound evidence and trade eligibility blockers shown in research quality (responsive)');
 }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
