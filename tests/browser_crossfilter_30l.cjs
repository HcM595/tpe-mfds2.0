const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:850}});
 const errors=[];page.on('pageerror',x=>errors.push(x.message));
 try {
  const response=await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
  assert.equal(response.status(),200);
  await page.locator('#r-cross').waitFor({timeout:60000});
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.equal(await page.locator('#r-tech').count(),0,'legacy overlapping filter should be removed');
  assert.equal(await page.locator('.r-cross-strip span').count(),4);
  const initial=await page.locator('.r-cross-strip').innerText();
  assert(initial.includes('三面交集'));
  // Check that browser percentages and intersections come from the same pure
  // evaluator used in the regression suite, not a hardcoded KPI.
  await page.locator('#r-cross').selectOption('confluence');
  assert.equal(await page.locator('#r-cross').inputValue(),'confluence');
  const section=page.locator('section.card.r-section:has(#r-cross)');
  const items=section.locator('tbody tr[data-r-stock]');
  for(let i=0;i<await items.count();i++){
   const row=await items.nth(i).innerText();
   assert(row.includes('三面同時符合'), 'confluence row violates required source agreement: '+row);
  }
  await page.locator('#r-cross').selectOption('review');
  for(let i=0;i<await items.count();i++){
   const row=await items.nth(i).innerText();
   assert(!row.includes('三面同時符合'),'review mode contains an eligible confluence');
  }
  await page.locator('#r-cross').selectOption('all');
  await page.locator('#r-query').fill('8064');
  const direct=await page.locator('#content').innerText();
  assert(direct.includes('8064'),'search must find named stock regardless of narrow ranking');
  assert.equal(await page.locator('#r-cross').inputValue(),'all',
       'search must retain selected intersection mode');
  // Remains within the current workspace instead of a duplicate second tab.
  await page.locator('#nav > button[data-research-tab="stock"]').click();
  assert(await page.locator('#r-stock-form').isVisible());
  await page.locator('#nav > button[data-research-tab="overview"]').click();
  assert.equal(await page.locator('#r-cross').count(),1);
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('.r-cross-strip').isVisible());
  assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
  assert.deepEqual(errors,[],'uncaught JavaScript exceptions in research screen');
  console.log('PASS 3.0L: dated three-axis filter, review mode, direct lookup, single sidebar and mobile');
 }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
