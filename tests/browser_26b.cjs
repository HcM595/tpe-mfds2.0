const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
   await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
   // 2.8E: one sidebar navigation; no duplicated research tab bar.
   assert.equal(await page.locator('#nav > button.nav-btn').count(),7,'main navigation contains duplicate legacy pages');
   assert.equal(await page.locator('#nav > button[data-page="stock"]').count(),0,'legacy stock screen must be collapsed');
   assert.equal(await page.locator('#nav-advanced').count(),1,'preserved advanced tools missing');
   await page.locator('#nav > button[data-page="research"][data-research-tab="stock"]').click();
   await page.locator('#r-stock-form').waitFor({timeout:60000});
   assert.equal(await page.locator('#nav > button.nav-btn.active').count(),1,'multiple primary entries marked active');
   assert((await page.locator('.logo small').innerText()).includes('2.8G'),'sidebar version misleading');
   assert.equal(await page.locator('.r-tabs').count(),0,'duplicated top research tabs not removed');
   for(const id of ['8064','3533','2345']){
     await page.locator('[data-r-stock="'+id+'"]').first().click();
     await page.waitForFunction(code=>document.querySelector('#content')?.textContent.includes(code+' ')&&document.querySelector('#content')?.textContent.includes('法人每日與大戶每週歷史趨勢'),id,{timeout:60000});
     let panel=page.locator('[aria-label="2.6B法人及大戶歷史趨勢"]');
     await panel.waitFor({timeout:60000});
     const text=await panel.innerText();
     assert(text.includes('5個交易日')&&text.includes('20個交易日'),'no window summary for '+id);
     assert(/20\d\d-\d\d-\d\d/.test(text),'dated source observations absent for '+id);
     assert(await panel.locator('svg').count()>=2,'missing trend charts for '+id);
     assert(!text.includes('NaN'),'NaN appears for '+id);
     const researchText=await page.locator('#content').innerText();
     assert(researchText.includes('2.8B S1／S3 歷史資料描述性觀察'),'descriptive factor section missing '+id);
     assert(researchText.includes('法人5日期末'),'normalized flow date missing '+id);
     assert(researchText.includes('未還原'),'price corporate-action limitations missing '+id);
     assert(researchText.includes('2.8C 公司月營收與產業相對強弱'),'fundamental industry panel missing '+id);
     assert(researchText.includes('出表日期不等於個別公司公告時點'),'monthly publication caveat missing '+id);
     assert(researchText.includes('2.8D 波段風險觀察'),'risk analysis section missing '+id);
     assert(researchText.includes('2.8F 季度淨利及 F1 財務品質驗證'),'income quality panel missing '+id);
     assert(researchText.includes('2.8G 公開資訊觀測站營業活動現金流'),'official cashflow panel missing '+id);
     assert(researchText.includes('年初')&&researchText.includes('單位'),'cashflow unit or YTD warnings missing '+id);
     assert(researchText.includes('出表日期不是逐家公司申報時點')||researchText.includes('尚無可核實的本股一般業季度損益表'),'financial filing caveat missing '+id);
     assert(researchText.includes('前20日最高收盤參考'),'risk high reference missing '+id);
     assert(researchText.includes('沒有')||researchText.includes('未驗證'),'finance limitations unmarked '+id);
     assert(!researchText.includes('ATR 已計算'),'nonexistent ATR should not be claimed '+id);
     console.log('PASS browser stock:',id);
   }
   await page.locator('#nav > button[data-page="research"][data-research-tab="quality"]').click();
   assert(await page.getByText('institutional_trend.csv').count()>0,'quality page missing institutional data');
   assert(await page.getByText('holder_trend.csv').count()>0,'quality page missing holder data');
   await page.locator('#nav > button[data-page="research"][data-research-tab="overview"]').click();
   await page.waitForFunction(() => document.querySelector('#content')?.textContent.includes('身分及基本資料同時符合'),{timeout:60000});
   const screenText=await page.locator('#content').innerText();
   assert(screenText.includes('普通股名錄有核對'),'market company roster eligibility missing');
   assert(screenText.includes('原始四層12子因子就緒稽核'),'factor readiness missing');
   assert(screenText.includes('2.8G 財務 F1 原始淨利與官方現金流觀察'),'financial coverage section missing');
   assert(screenText.includes('現金流淨利比率繼續停用'),'cashflow ratio disabled warning missing');
   assert(screenText.includes('0 / 12'),'unverified factor model must not claim readiness');
   assert(await page.locator('#r-eligibility-view').count()===1,'eligibility status filter missing');
   await page.locator('#r-eligibility-view').selectOption('all');
   await page.waitForFunction(()=>document.querySelector('#r-eligibility-page')?.textContent.includes('第 1／'),{timeout:60000});
   const before=await page.locator('#r-eligibility-page').innerText();
   assert(before.includes('每頁60檔'),'eligibility pagination label missing');
   assert(await page.locator('[data-r-action="elig-next"]').isEnabled(),'full-market next page should be available');
   await page.locator('[data-r-action="elig-next"]').click();
   assert((await page.locator('#r-eligibility-page').innerText()).includes('第 2／'),'eligibility next page broken');
   await page.locator('#r-eligibility-view').selectOption('excluded');
   assert((await page.locator('#r-eligibility-page').innerText()).includes('第 1／'),'changing eligibility scope must reset page');
   assert(await page.locator('#r-query').count()===1,'existing screener missing');
   // Main chip rule is distinct from weighted ranking and must remain reachable.
   await page.locator('#nav > button[data-page="chip"]').click();
   assert((await page.locator('#content').innerText()).includes('法人與大戶同步增持候選名單'),'strict synchronized inflow rule missing');
   // Legacy pages are still available, but clearly labelled as nonproduction comparison.
   await page.locator('#nav-advanced summary').click();
   await page.locator('#nav-advanced button[data-page="screener"]').click();
   assert((await page.locator('#content').innerText()).includes('舊版比較／CSV 功能'),'legacy screener missing caveat');
   await page.locator('#nav > button[data-page="research"][data-research-tab="stock"]').click();
   await page.locator('#r-stock-code').fill('2345');
   await page.locator('#r-stock-form button[type="submit"]').click();
   await page.locator('button[data-action="watch"][data-id="2345"]').click();
   await page.locator('#nav > button[data-page="watch"]').click();
   assert(await page.locator('button[data-action="watchResearch"][data-id="2345"]').count()===1,'watchlist modern stock link missing');
   await page.locator('button[data-action="watchResearch"][data-id="2345"]').click();
   assert((await page.locator('#content').innerText()).includes('2345 智邦'),'watchlist did not open modern research');
   await page.setViewportSize({width:390,height:844});
   await page.locator('#nav > button[data-page="research"][data-research-tab="stock"]').click();
   assert(await page.locator('#r-stock-code').isVisible(),'mobile stock search missing');
   assert.deepEqual(errors,[],'browser JS exceptions');
   console.log('PASS browser smoke and responsive checks');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
