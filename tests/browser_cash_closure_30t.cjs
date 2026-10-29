const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('section[aria-label="3.0T現貨臨時休市來源證據鏈"]');
  await panel.waitFor({timeout:60000});
  assert((await panel.innerText()).includes('現貨市場臨時休市來源證據鏈'));
  assert((await panel.innerText()).includes('上櫃 TPEx'));
  assert((await panel.innerText()).includes('上市 TWSE'));
  assert((await panel.innerText()).includes('尚未完成；不可認證完整交易日曆'));
  assert((await panel.innerText()).includes('期交所休市公告僅適用期貨'));
  const metaUrl=new URL('./data/cash_market_closure_evidence_30t.json',page.url());
  const res=await page.request.get(metaUrl.href);
  assert.equal(res.status(),200);
  const m=await res.json();
  assert.equal(m.version,'3.0T');
  assert.equal(m.date,'2026-10-23');
  assert.equal(m.independent_cash_market_originals_verified,false);
  assert.equal(m.official_closure_date_certified_for_both_markets,false);
  assert.equal(m.verified_trade_samples,0);
  assert.equal(m.certified_win_rate,null);
  for(const name of ['TWSE','TPEX']){
   const source=m.sources[name];
   assert(source);
   assert(source.official_source_url.startsWith('https://'));
   assert.equal(source.cash_market_session_closed_certified,false);
   if(source.source_file){
    const raw=await page.request.get(new URL('./data/'+source.source_file,page.url()).href);
    assert.equal(raw.status(),200);
    const hash=await page.evaluate(async b=>{
     const bytes=new Uint8Array(b);
     return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)))
       .map(v=>v.toString(16).padStart(2,'0')).join('');
    },[...await raw.body()]);
    assert.equal(hash,source.source_sha256);
   }
  }
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[],'browser Javascript errors');
  console.log('PASS 3.0T: separate cash market listing evidence, source digest, permanent performance lock, 7-menu and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
