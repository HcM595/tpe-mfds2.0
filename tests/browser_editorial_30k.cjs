const {chromium}=require('playwright');
const assert=require('node:assert/strict');

(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const errors=[];
 page.on('pageerror',err=>errors.push(err.message));
 try{
   await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
   const seven=['市場總覽','個股研究','籌碼觀察','歷史訊號','資料品質','自選股','設定'];
   assert.deepEqual((await page.locator('#nav > button').allInnerTexts()).map(x=>x.trim().split(/\n/).at(-1).trim()),seven);
   assert.equal(await page.locator('#nav details').count(),0);
   assert.equal(await page.locator('#nav a').count(),0,'no duplicate sidebar tool navigation');
   await page.waitForFunction(()=>document.querySelector('#r-eligibility-view')!==null,{timeout:60000});
   const background=await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor);
   assert.equal(background,'rgb(246, 244, 239)','paper palette not loaded');
   const sidebar=await page.locator('.sidebar').evaluate(el=>getComputedStyle(el).position);
   assert.equal(sidebar,'sticky','desktop sidebar must remain visible');
   await page.locator('#nav > button[data-research-tab="quality"]').click();
   await page.locator('.r-resource-links').waitFor();
   const links=await page.locator('.r-resource-links a').evaluateAll(nodes=>nodes.map(a=>a.getAttribute('href')));
   assert.equal(links.length,8,'eight distinct evidence sources should be contextual');
   assert.equal(new Set(links).size,8,'evidence library duplicates destinations');
   assert(links.includes('./research_hub_30a.html'));
   await page.locator('#nav > button[data-page="chip"]').click();
   assert((await page.locator('#content').innerText()).includes('法人與大戶同步增持候選名單'));
   await page.locator('#nav > button[data-research-tab="stock"]').click();
   await page.locator('#r-stock-code').fill('8064');
   await page.locator('#r-stock-form button[type="submit"]').click();
   assert((await page.locator('#content').innerText()).includes('8064'));
   await page.setViewportSize({width:390,height:844});
   const pos=await page.locator('.sidebar').evaluate(el=>getComputedStyle(el).position);
   assert.equal(pos,'relative','mobile nav must be scrollable without sticky obstruction');
   const nav=page.locator('#nav');
   assert(await nav.isVisible());
   assert.equal(await nav.locator('button').count(),7);
   const response=await page.goto('http://127.0.0.1:8765/research_hub_30a.html',{waitUntil:'domcontentloaded'});
   assert.equal(response.status(),200);
   assert.equal(await page.locator('body.workbench-editorial').count(),1);
   assert.equal(await page.locator('header nav a').count(),1,
     'verification workbench must not repeat evidence navigation');
   await page.waitForFunction(()=>document.querySelector('#snapshot-status')?.textContent.includes('9 份來源')||
         document.querySelector('#snapshot-status')?.textContent.includes('/9 份來源'),{timeout:60000});
   assert(!((await page.locator('#snapshot-status').innerText()).includes('八類')));
   assert.deepEqual(errors,[],'uncaught browser JS errors');
   console.log('PASS 3.0K: unique navigation, contextual evidence links, responsive editorial theme, existing stock and chip flows');
 } finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
