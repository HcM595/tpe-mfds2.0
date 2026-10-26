const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
   await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(() => document.querySelector('#r-stock-form')!==null,{timeout:60000}).catch(async()=>{
     await page.locator('[data-page="research"]').click();
     await page.locator('[data-r-tab="stock"]').click();
   });
   await page.locator('[data-r-tab="stock"]').click();
   for(const id of ['8064','3533','2345']){
     await page.locator('[data-r-stock="'+id+'"]').first().click();
     await page.waitForFunction(code=>document.querySelector('#content')?.textContent.includes(code+' ')&&document.querySelector('#content')?.textContent.includes('法人每日與大戶每週歷史趨勢'),id,{timeout:60000});
     let panel=page.locator('[aria-label="2.6B法人及大戶歷史趨勢"]');
     await panel.waitFor({timeout:60000});
     const text=await panel.innerText();
     assert(text.includes('5個交易日')&&text.includes('20個交易日'),'no window summary for '+id);
     assert(text.includes('2026-10-22'),'dated source observations absent for '+id);
     assert(await panel.locator('svg').count()>=2,'missing trend charts for '+id);
     assert(!text.includes('NaN'),'NaN appears for '+id);
     console.log('PASS browser stock:',id);
   }
   await page.locator('[data-r-tab="quality"]').click();
   assert(await page.getByText('institutional_trend.csv').count()>0,'quality page missing institutional data');
   assert(await page.getByText('holder_trend.csv').count()>0,'quality page missing holder data');
   await page.locator('[data-r-tab="overview"]').click();
   await page.waitForFunction(() => document.querySelector('#content')?.textContent.includes('身分及基本資料同時符合'),{timeout:60000});
   const screenText=await page.locator('#content').innerText();
   assert(screenText.includes('普通股名錄有核對'),'market company roster eligibility missing');
   assert(await page.locator('#r-query').count()===1,'existing screener missing');
   await page.setViewportSize({width:390,height:844});
   await page.locator('[data-r-tab="stock"]').click();
   assert(await page.locator('#r-stock-code').isVisible(),'mobile stock search missing');
   assert.deepEqual(errors,[],'browser JS exceptions');
   console.log('PASS browser smoke and responsive checks');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
