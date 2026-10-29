const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('section[aria-label="3.0U官方臨時休市原始文件稽核"]');
  await panel.waitFor({timeout:60000});
  const text=await panel.innerText();
  assert(text.includes('3.0U｜現貨市場官方休市原始文件'));
  assert(text.includes('2026/10/22'));
  assert(text.includes('2026/10/23')||text.includes('10/23'));
  assert(text.includes('上櫃'));
  assert(text.includes('尚未通過'));
  const pdfLink=await panel.locator('a[href$=".pdf"]').getAttribute('href');
  assert.equal(pdfLink,'https://investoredu.twse.com.tw/FileSystem/FileUpload/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf');
  const metaResponse=await page.request.get(new URL('./data/official_closure_notice_evidence_30u.json',page.url()).href);
  assert.equal(metaResponse.status(),200);
  const meta=await metaResponse.json();
  assert.equal(meta.version,'3.0U');
  assert.equal(meta.date,'2026-10-23');
  assert.equal(meta.both_cash_markets_official_originals_verified,false);
  assert.equal(meta.sources.TPEX.full_original_document_verified,false);
  assert.equal(meta.sources.TWSE.first_publication_timestamp_verified,false);
  assert.equal(meta.trade_performance_enabled,false);
  assert.equal(meta.verified_trade_samples,0);
  assert.equal(meta.certified_win_rate,null);
  if(meta.sources.TWSE.full_original_document_verified===true){
   assert.equal(meta.sources.TWSE.status,'verified_full_original_pdf');
   assert(meta.sources.TWSE.source_sha256);
   const original=await page.request.get(new URL('./data/'+meta.sources.TWSE.source_file,page.url()).href);
   assert.equal(original.status(),200);
   const digest=createHash('sha256').update(await original.body()).digest('hex');
   assert.equal(digest,meta.sources.TWSE.source_sha256);
   assert(text.includes('已核實原始PDF'));
  }else{
   assert.equal(meta.sources.TWSE.status,'official_original_pending');
   assert(text.includes('原始PDF待核'));
  }
  // The 3.0R historical audit may now mark TWSE documentary status while TPEx
  // remains pending, but cannot certify both markets or backtest eligibility.
  const csv=await page.request.get(new URL('./data/archive_day_coverage_30r.csv',page.url()).href);
  assert.equal(csv.status(),200);
  const data=await csv.text();
  assert(data.includes('2026-10-23,上櫃,extraordinary_closure_requires_official_source'));
  if(meta.sources.TWSE.full_original_document_verified===true)
   assert(data.includes('2026-10-23,上市,verified_original_market_closure'));
  else
   assert(data.includes('2026-10-23,上市,extraordinary_closure_requires_official_source'));
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0U: TWSE original full-PDF SHA256 or honest pending; TPEx kept independent, 3.0R date status safe and mobile');
 }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
