const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('section[aria-label="3.0V官方PDF來源完整性稽核"]');
  await panel.waitFor({timeout:60000});
  const content=await panel.innerText();
  assert(content.includes('3.0V｜官方PDF來源完整性稽核'));
  assert(content.includes('證交所 10/23 原始全文'));
  assert(content.includes('櫃買中心 2026 年原始年曆'));
  assert(content.includes('櫃買中心 10/23 事件原文'));
  assert(content.includes('勝率模型維持停用'));
  const res=await page.request.get(new URL('./data/official_source_readiness_30v.json',page.url()).href);
  assert.equal(res.status(),200);
  const meta=await res.json();
  assert.equal(meta.version,'3.0V');
  assert.equal(meta.pdf_extractor_present,true);
  assert.equal(meta.pdf_extractor,'pdftotext');
  assert.equal(meta.certified_trade_outcomes,0);
  assert.equal(meta.certified_win_rate,null);
  assert.equal(meta.trade_model_enabled,false);
  assert.equal(meta.official_closure_proven_for_both_markets,false);
  assert.equal(meta.annual_tpex_session_classification_verified,false);
  assert.equal(meta.markets.TPEX_otc_full_closure_notice_2026_10_23.status,
              'pending_independent_full_original');
  for(const m of [meta.markets.TWSE_listed_cash_closure_2026_10_23,
                 meta.markets.TPEX_otc_annual_calendar_2026])
   assert(['pending','verified_original_annual_document','verified_original_market_event'].includes(m.status));
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0V: PDF extraction tool enabled, official source status honest, distinct markets, strict 0 samples and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
