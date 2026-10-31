const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('section[aria-label="3.0W公開資料發布證據收據"]');
  await panel.waitFor({timeout:60000});
  await page.waitForFunction(()=>document.querySelector('section[aria-label="3.0W公開資料發布證據收據"]')?.innerText.includes('來源檔案'),null,{timeout:60000});
  const intro=await panel.innerText();
  assert(intro.includes('3.0W｜公開資料發布證據收據'));
  assert(intro.includes('發布前'));
  assert(intro.includes('部署後'));
  assert(intro.includes('勝率模型維持停用'));
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  const res=await page.request.get(new URL('./data/release_receipt_30w.json',page.url()).href);
  assert.equal(res.status(),200);
  const receipt=await res.json();
  assert.equal(receipt.version,'3.0W');
  assert.equal(receipt.status,'source_bytes_attested_not_trade_certified');
  assert.equal(receipt.trade_model_enabled,false);
  assert.equal(receipt.certified_trade_samples,0);
  assert.equal(receipt.certified_win_rate,null);
  assert.equal(receipt.cash_market_closure_both_independently_verified,false);
  assert(receipt.source_file_count>=13);
  assert(receipt.source_files.some(r=>r.path.endsWith('.pdf')));
  for(const item of receipt.source_files){
   const file=await page.request.get(new URL(item.path,page.url()).href,{timeout:25000});
   assert.equal(file.status(),200,'public preview missing '+item.path);
   const b=await file.body();
   assert.equal(b.length,item.bytes,'size '+item.path);
   assert.equal(createHash('sha256').update(b).digest('hex'),item.sha256,'SHA '+item.path);
  }
  await panel.locator('summary').click();
  const table=await panel.locator('table').first().innerText();
  assert(table.includes('official_closure_notice_evidence_30u.json'));
  assert(table.includes('tpex_calendar_evidence_30s.json'));
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0W: all '+receipt.source_file_count+' source file bytes match release receipt, original PDFs retained, 7 nav and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
