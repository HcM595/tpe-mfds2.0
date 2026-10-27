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
    assert((await page.locator('#release-audit').innerText()).includes('正式公布時刻未驗證'),
      'I stock source audit must explicitly block missing official release');
    assert((await page.locator('#release-audit').innerText()).includes('月營收'),
      'I should also audit monthly revenue first-seen and release clocks');

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
    assert((await page.locator('#details').innerText()).includes('未核實F2正式公布時間'), 'J future or unverified F2 must stay unknown');
    const wrongRelease = await page.evaluate(() => window.MFDSAsOfGate.clockGate({
      priceDay:'2026-10-22',reportDay:'2026-10-22',
      firstSeen:'2026-10-21T10:00:00Z',officialPublished:'2026-10-22T00:01:00Z',
      sourceVerified:true
    }));
    assert.equal(wrongRelease.eligible,false,'J timezone-aware gate must reject after-cutoff disclosures');
    const jDetails = await page.locator('#details').innerText();
    assert(/同業本益比低於中位數（原值）[^]*?缺資料/.test(jDetails), 'J must block unverified F2 from passing');

    console.log('PASS 2.9J: market filter, engine B and per-stock conditions');

    // 2.9K: side-by-side dates, unknowns, capital flow and holder direction.
    await visit('compare_29k.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('已載入'), {timeout: 60000});
    assert.equal(await page.locator('#table tbody tr').count(), 4, 'K default comparison must contain four stocks');
    assert((await page.locator('#table').innerText()).includes('8064'));
    await page.locator('#engine').selectOption('B');
    assert((await page.locator('#details').innerText()).includes('本益比低於同業中位數'), 'K B-engine conditions missing');
    const kDetails = await page.locator('#details').innerText();
    assert(kDetails.includes('未核實官方公告時間'), 'K future F2 must be marked not assessable');
    assert(kDetails.includes('無法判定'), 'K should show unknown factor conditions');
    assert.equal(await page.evaluate(() => typeof window.MFDSAsOfGate.revenue), 'function',
      'K must use same release clock validator as dual engine');

    await page.locator('#stocks').fill('2330,999999');
    await page.locator('#compare').click();
    assert.equal(await page.locator('#table tbody tr').count(), 2, 'K custom comparison did not refresh');
    assert((await page.locator('#table').innerText()).includes('找不到逐股12因子研究資料'), 'K unknown stock not disclosed');
    assert(!(await page.locator('#table').innerText()).includes('NaN'), 'K displayed NaN');
    console.log('PASS 2.9K: compare 4 stocks, alternate engine, handle missing IDs');

    // 2.9P: archival candidates are never self-certified as company filing times.
    await visit('publication_review_29p.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('符合搜尋'), {timeout: 60000});
    assert(Number((await page.locator('#total').innerText()).replace(/,/g,'')) > 5000, 'P evidence universe incomplete');
    assert.equal(await page.locator('#rows tr').count(), 3, 'P should show F2 F3 and monthly revenue for 8064');
    const proofText=await page.locator('#rows').innerText();
    assert(proofText.includes('待獨立公告核實')&&proofText.includes('歷史回測不可用'),
      'P candidates must not be mislabeled as verified historical knowledge');
    assert((await page.locator('#verified').innerText()).trim()==='0','P invented verified source times');
    await page.locator('#factor').selectOption('REVENUE');
    assert.equal(await page.locator('#rows tr').count(),1,'P factor filter failed');
    await page.locator('#factor').selectOption('all');
    await page.locator('#q').fill('2330');
    assert.equal(await page.locator('#rows tr').count(),3,'P stock lookup failed');
    await visit('publication_review_29p.html?stock=3533');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('符合搜尋'), {timeout: 60000});
    assert.equal(await page.locator('#rows tr').count(),3,'P stock deep link should show all factor sources');
    assert((await page.locator('#rows tr').first().innerText()).includes('3533'),
       'P page did not preserve stock ID passed from research detail');
    console.log('PASS 2.9P: source proof queue, factor filters and fail-closed release timestamps');

    // 2.9Q: material announcements are events; never certify F2/F3/revenue release.
    await visit('material_events_29q.html');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('符合搜尋'), {timeout:60000});
    assert.equal((await page.locator('#verified').innerText()).trim(),'0',
      'Q should never certify original public release without independent proof');
    assert.equal((await page.locator('#mapped').innerText()).trim(),'0',
      'Q material information must not become F2/F3/revenue signals');
    assert((await page.locator('.notice').innerText()).includes('不是各項財務資料首次公布時間'),
      'Q must distinguish speech time from financial release time');
    await page.locator('#q').fill('8064');
    assert((await page.locator('#status').innerText()).includes('符合搜尋'),
      'Q searchable stock event catalogue missing');
    await page.locator('#market').selectOption('上櫃');
    assert.equal((await page.locator('#verified').innerText()).trim(),'0');
    console.log('PASS 2.9Q: material speech clock, no retrospective factor-release certification');

    // 2.9R: title-only event correlations cannot become historical F2/F3/revenue.
    await visit('event_crosscheck_29r.html?stock=8064');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('符合'), {timeout: 60000});
    assert(Number((await page.locator('#total').innerText()).replace(/,/g,'')) > 5000,'R factor review stock coverage');
    assert.equal(await page.locator('#rows tr').count(),3,'R 8064 must have F2 F3 and revenue review');
    assert.equal((await page.locator('#proved').innerText()).trim(),'0','R cannot certify any first public disclosure');
    await page.locator('#q').fill('9904');
    assert.equal(await page.locator('#rows tr').count(),3,'R stock filter must retain three evidence types');
    const content = await page.locator('#rows').innerText();
    assert(content.includes('歷史回測不可用'),'R must visibly block historical use');
    assert(!(await page.locator('#rows').innerText()).includes('NaN'),'R should not display NaN');
    await page.locator('#factor').selectOption('F2');
    assert.equal(await page.locator('#rows tr').count(),1,'R factor filtering failed');
    const f2Row=await page.locator('#rows tr').first().innerText();
    assert(f2Row.includes('F2 原始估值')&&f2Row.includes('0'),'R must not attach financial warnings to F2 PE');
    await page.locator('#factor').selectOption('all');
    await page.locator('#candidate').selectOption('yes');
    assert.equal(await page.locator('#rows tr').count(),1,'R no true factor release candidates for income warning');
    assert((await page.locator('#rows').innerText()).includes('沒有符合條件'), 'R false event candidate was invented');
    console.log('PASS 2.9R: stock/company matching, unrelated event negative control and no time certification');

    // 2.9S: inspect raw official statements and retain first-seen distinction.
    await visit('event_body_audit_29s.html?stock=3680');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('符合'), {timeout:60000});
    assert(Number((await page.locator('#total').innerText()).replace(/,/g,''))>=1,'S archived statement list missing');
    assert(Number((await page.locator('#body').innerText()).replace(/,/g,''))>=1,'S no original raw bodies validated');
    assert.equal((await page.locator('#eligible').innerText()).trim(),'0','S must never certify first-publication time');
    assert((await page.locator('#rows').innerText()).includes('3680'),'S stock deep link failed');
    assert((await page.locator('#rows').innerText()).includes('首封存UTC'),'S first seen clock missing');
    assert((await page.locator('#rows').innerText()).includes('未驗證／不可回測'),'S stock erroneously backtest eligible');
    await page.locator('#rows details summary').first().click();
    assert((await page.locator('#rows .excerpt').first().innerText()).length>10,'S body excerpt missing');
    await page.locator('#q').fill('4958');
    assert((await page.locator('#rows').innerText()).includes('4958'),'S event search failed');
    await page.locator('#state').selectOption('invalid');
    assert((await page.locator('#rows').innerText()).includes('沒有符合條件') ||
           (await page.locator('#rows').innerText()).includes('來源版本未完成核對'),
           'S evidence status filter failed');
    console.log('PASS 2.9S: raw material body, source first-seen, stock search and no-release gate');
    assert.deepEqual(errors, [], 'Uncaught browser JavaScript errors: ' + errors.join('; '));
    console.log('PASS 2.9M: all four research pages passed real Chromium smoke tests');
  } finally {
    await browser.close();
  }
}
run().catch(e => {console.error(e); process.exitCode = 1;});
