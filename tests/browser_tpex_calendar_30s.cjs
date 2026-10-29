const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  await page.locator('#nav > button[data-research-tab="quality"]').click();
  const panel=page.locator('section[aria-label="3.0S上櫃官方年曆來源稽核"]');
  await panel.waitFor({timeout:60000});
  await page.waitForFunction(()=>document.querySelector('section[aria-label="3.0S上櫃官方年曆來源稽核"]')?.innerText.includes('官方115年年曆原始PDF'),{timeout:60000});
  const html=await panel.innerText();
  assert(html.includes('櫃買中心')&&html.includes('上櫃'));
  assert(html.includes('2026/10/23'));
  assert(html.includes('尚未封存'));
  assert(html.includes('尚未完整認證'));
  assert(!html.includes('勝率：85%'));
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  const res=await page.request.get(new URL('./data/tpex_calendar_evidence_30s.json',page.url()).href);
  assert.equal(res.status(),200);
  const meta=await res.json();
  assert.equal(meta.version,'3.0S');
  assert(meta.official_pdf_url.endsWith('.pdf'));
  assert.equal(meta.annual_market_closure_dates_independently_verified,false);
  assert.equal(meta['2026_10_23_extraordinary_closure_official_original_verified'],false);
  assert.equal(meta.certified_backtest_eligible,false);
  const links=await panel.locator('a[href]').evaluateAll(nodes=>nodes.map(x=>x.getAttribute('href')));
  assert(links.some(x=>x.includes('11400754581.html')));
  assert(links.some(x=>x.includes('114007545811-1.pdf')));
  await page.setViewportSize({width:390,height:844});
  assert(await panel.isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS 3.0S: official TPEx source, honest pending status, 7-menu quality panel and mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
