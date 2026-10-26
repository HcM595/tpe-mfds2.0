// 2.9M: real Chromium smoke tests for the four standalone research screens.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const base = 'http://127.0.0.1:8765/';
async function run() {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const visit = async path => {
    const response = await page.goto(base + path, {waitUntil: 'domcontentloaded', timeout: 45000});
    assert.equal(response.status(), 200, path + ' HTTP status');
  };
  try {
    // 2.9H: search and disclose all twelve verification gaps, without model score.
    await visit('factor_gaps_29h.html');
    await page.waitForFunction(() => document.querySelector('#message')?.textContent.includes('已找到 8064'), {timeout: 60000});
    assert.equal(await page.locator('#rows tr').count(), 12, 'H must show exactly twelve factors');
    assert(Number((await page.locator('#total').innerText()).replace(/,/g, '')) > 1000, 'H stock universe missing');
    assert((await page.locator('#summary').innerText()).includes('已驗證因子：0/12'), 'H unverifiable factors misrepresented');
    await page.waitForFunction(() => document.querySelectorAll('#pit-clock tbody tr').length === 2, {timeout: 60000});
    const pitH = await page.locator('#pit-clock').innerText();
    assert(pitH.includes('本站首次取得（UTC）'),'H capture clock missing');
    assert(pitH.includes('官方公布時刻（UTC）'),'H publication clock missing');
    assert(pitH.includes('未驗證／不可倒填'),'H missing official announcement not labelled');
    assert(pitH.includes('不可作歷史回測'),'H PIT screen must not permit historical testing');

    await page.locator('#stock').fill('2330');
    await page.locator('#lookup').click();
    assert((await page.locator('#stocktitle').innerText()).startsWith('2330 '), 'H lookup did not change stock');
    console.log('PASS 2.9H: evidence lookup, 12 rows and verification gate');

    // 2.9I: the seven source datasets are rendered together, with dates and risk caveats.
    await visit('stock_research_29i.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('已載入 8064'), {timeout: 60000});
    assert.equal(await page.locator('#out').isVisible(), true, 'I page did not render research detail');
    for (const sel of ['#chip table', '#technical table', '#industry table', '#risk table', '#factor table']) {
      assert(await page.locator(sel).count() > 0, 'I missing panel ' + sel);
    }
    assert((await page.locator('#caveat').innerText()).includes('資料日期'), 'I date disclosure missing');
    await page.waitForFunction(() => document.querySelectorAll('#pit-clock tbody tr').length === 2, {timeout: 60000});
    assert((await page.locator('#pit-clock').innerText()).includes('不可作歷史回測'),'I PIT verification missing');

    assert((await page.locator('#risk').innerText()).includes('價格已還原'), 'I raw-price risk warning missing');
    await page.locator('#query').fill('3533');
    await page.locator('#find').click();
    assert((await page.locator('#heading').innerText()).startsWith('3533 '), 'I lookup did not change stock');
    assert(!(await page.locator('#out').innerText()).includes('NaN'), 'I displays NaN');
    console.log('PASS 2.9I: stock lookup, source panels and price warning');

    // 2.9J: interactive engine switch and per-stock drilldown.
    await visit('dual_engine_29j.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('資料載入完成'), {timeout: 60000});
    assert(Number((await page.locator('#all').innerText()).replace(/,/g,'')) > 1000, 'J factor universe missing');
    await page.locator('#q').fill('8064');
    assert.equal(await page.locator('#rows tr').count(), 1, 'J stock text filtering failed');
    assert((await page.locator('#rows tr').first().innerText()).includes('8064'));
    await page.locator('#engine').selectOption('B');
    assert((await page.locator('#title').innerText()).includes('B｜'), 'J engine selection not reflected');
    await page.locator('#rows tr').first().click();
    assert((await page.locator('#details').innerText()).includes('400張以上大戶4週增加'), 'J conditions not disclosed');
    console.log('PASS 2.9J: market filter, engine B and per-stock conditions');

    // 2.9K: side-by-side dates, unknowns, capital flow and holder direction.
    await visit('compare_29k.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('已載入'), {timeout: 60000});
    assert.equal(await page.locator('#table tbody tr').count(), 4, 'K default comparison must contain four stocks');
    assert((await page.locator('#table').innerText()).includes('8064'));
    await page.locator('#engine').selectOption('B');
    assert((await page.locator('#details').innerText()).includes('本益比低於同業中位數'), 'K B-engine conditions missing');
    await page.locator('#stocks').fill('2330,999999');
    await page.locator('#compare').click();
    assert.equal(await page.locator('#table tbody tr').count(), 2, 'K custom comparison did not refresh');
    assert((await page.locator('#table').innerText()).includes('找不到逐股12因子研究資料'), 'K unknown stock not disclosed');
    assert(!(await page.locator('#table').innerText()).includes('NaN'), 'K displayed NaN');
    console.log('PASS 2.9K: compare 4 stocks, alternate engine, handle missing IDs');

    assert.deepEqual(errors, [], 'Uncaught browser JavaScript errors: ' + errors.join('; '));
    console.log('PASS 2.9M: all four research pages passed real Chromium smoke tests');
  } finally {
    await browser.close();
  }
}
run().catch(e => {console.error(e); process.exitCode = 1;});
