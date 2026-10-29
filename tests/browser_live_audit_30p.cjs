/* Live GitHub Pages site smoke audit. Unlike localhost tests this fetches the
   DEPLOYED public address. No trading decisions or unsafe actions are made.
   User-visible report is printed as single JSON line for easy parsing.
*/
const {chromium}=require('playwright');
const fs=require('node:fs');
const LIVE=process.env.LIVE_SITE_URL||'https://hcm595.github.io/tpe-mfds2.0/';
const EXPECTED_RELEASES=(process.env.EXPECTED_LIVE_RELEASE||'3.0U').split(',').map(x=>x.trim()).filter(Boolean);
const results=[],notes=[];
function brief(e){return String(e?.message||e).slice(0,460);}
async function check(name,task){
 try{const detail=await task();results.push({item:name,status:'pass',detail:detail||''});console.log('AUDIT_PASS '+name+(detail?' '+detail:''));}
 catch(e){results.push({item:name,status:'fail',detail:brief(e)});console.log('AUDIT_FAIL '+name+' '+brief(e));}
}
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1366,height:900},acceptDownloads:true});
 const page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let navigationLoaded=false;
 try{
  await check('公開網站可連線（HTTP 200）',async()=>{
   const response=await page.goto(LIVE,{waitUntil:'domcontentloaded',timeout:45000});
   assert.equal(response.status(),200);navigationLoaded=true;
   return page.url();
  });
  if(!navigationLoaded){console.log('LIVE_AUDIT_JSON '+JSON.stringify({live:LIVE,results,notes,pageErrors:errors}));process.exitCode=1;return;}
  await check('主頁3.0U正式版本及七項唯一選單',async()=>{
   const brand=await page.locator('.logo small').innerText();
   assert(EXPECTED_RELEASES.some(v=>brand.includes(v)),'live version not in '+EXPECTED_RELEASES.join('/')+': '+brand);
   const nav=page.locator('#nav > button.nav-btn');
   assert.equal(await nav.count(),7,'main menu count differs from 7');
   const names=(await nav.allInnerTexts()).map(x=>x.trim());
   for(const n of ['市場總覽','個股研究','籌碼觀察','歷史訊號','資料品質','自選股','設定'])
    assert(names.some(x=>x.includes(n)),'missing '+n);
   assert.equal(await page.locator('#nav details').count(),0);
   return brand;
  });
  await check('文青主題樣式和手機版基礎配置',async()=>{
   assert.equal(await page.locator('link[href="./editorial_30k.css"]').count(),1);
   assert.equal(await page.locator('body').evaluate(x=>getComputedStyle(x).backgroundColor),'rgb(246, 244, 239)');
   await page.setViewportSize({width:390,height:844});
   assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
   await page.setViewportSize({width:1366,height:900});
   return 'style applied, 390px shows seven menu items';
  });
  await check('重要 JS 模組與研究資料端點',async()=>{
   const urls=['./editorial_30k.css','./chip_tech_crossfilter_30l.js','./stock_evidence_30m.js',
     './watchlist_center_30n.js','./watch_history_30o.js','./watch_timeline_30p.js',
     './data/official_meta.json','./data/signal_archive_index.json',
     './data/chip_rank.csv','./data/tech_crosscheck.csv','./data/chip_signals.csv'];
   const out=[];
   for(const path of urls){
    const res=await page.request.get(new URL(path,LIVE).href,{timeout:20000});
    assert.equal(res.status(),200,'missing live '+path+' HTTP '+res.status());
    const body=await res.body();
    assert(body.length>20,'empty published file '+path);
    out.push(path);
   }
   const loaded=await page.evaluate(()=>Boolean(window.MFDSWatchTimeline30P&&window.MFDSWatchHistory30O&&
       window.MFDSWatchlist30N&&window.MFDSStockEvidence30M&&window.MFDSChipTechCrossfilter));
   assert(loaded,'one or more research modules absent in live client');
   return out.length+' deployed assets and source files available';
  });
  await check('官方行情日及上市櫃來源日核對',async()=>{
   const response=await page.request.get(new URL('./data/official_meta.json',LIVE).href,{timeout:20000});
   assert.equal(response.status(),200);
   const meta=await response.json();
   assert(/^\d{4}-\d{2}-\d{2}$/.test(meta.display_date),'source display date absent');
   assert(meta.status==='ok','official source status is '+String(meta.status));
   const pairs=Object.entries(meta.market_dates||{});
   assert(pairs.length>=2,'TWSE/TPEx source dates not individually declared');
   const observed=await page.locator('#banner').innerText();
   assert(observed.includes(meta.display_date),'public price banner disagrees with official_meta.json');
   if(meta.aligned===true)
    assert(pairs.every(([k,d])=>d===meta.display_date),'a source market date differs from declared aligned price');
   const local=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
   const diff=Math.round((Date.parse(local+'T00:00:00Z')-Date.parse(meta.display_date+'T00:00:00Z'))/86400000);
   if(diff>5)notes.push('正式網站行情資料日期距台灣當日'+diff+'日，應檢查市場休市與工作流程');
   return '行情 '+meta.display_date+'；'+pairs.map(([market,d])=>market+':'+d).join('，')+
    '；來源 '+meta.status;
  });
  await check('市場總覽：資料載入、交叉篩選',async()=>{
   await page.locator('#nav > button[data-research-tab="overview"]').click();
   await page.locator('#r-cross').waitFor({timeout:45000});
   const current=await page.locator('#r-cross').inputValue();
   await page.locator('#r-cross').selectOption('confluence');
   assert.equal(await page.locator('#r-cross').inputValue(),'confluence');
   const rows=page.locator('section.r-section:has(#r-cross) tr[data-r-stock]');
   for(const r of await rows.all()){
    const rowText=await r.innerText();
    assert(rowText.includes('三面同時符合'),'intersection row not matching: '+rowText.slice(0,220));
   }
   await page.locator('#r-cross').selectOption(current);
   assert.equal(await page.locator('.r-cross-strip span').count(),4);
   return 'cross-filter usable, '+await rows.count()+' displayed rows';
  });
  await check('個股研究：8064 查詢、證據摘要與 CSV',async()=>{
   await page.locator('#nav > button[data-research-tab="stock"]').click();
   await page.locator('#r-stock-form').waitFor({timeout:45000});
   await page.locator('#r-stock-code').fill('8064');
   await page.locator('#r-stock-form button[type="submit"]').click();
   const evidence=page.locator('section[aria-label="3.0M個股研究證據摘要"]');
   await evidence.waitFor({timeout:45000});
   assert.equal(await evidence.locator('.r-evidence-mini').count(),4);
   assert.equal(await evidence.locator('tbody tr').count(),10);
   assert((await evidence.innerText()).includes('8064'));
   assert(await evidence.locator('#r-stock-deep-link').getAttribute('href'));
   const [download]=await Promise.all([page.waitForEvent('download',{timeout:30000}),
     page.locator('#r-stock-evidence-export').click()]);
   assert(download.suggestedFilename().includes('8064'));
   return 'stock 8064, 4 brief cards, 10 clocks, exported CSV';
  });
  await check('籌碼觀察：法人與大戶同增頁',async()=>{
   await page.locator('#nav > button[data-page="chip"]').click();
   const t=await page.locator('#content').innerText();
   assert(t.includes('法人與大戶同步增持候選名單'));
   assert(t.includes('法人')&&t.includes('集保'));
   return 'chip observation panel accessible';
  });
  await check('歷史訊號：封存、10／20／60日',async()=>{
   await page.locator('#nav > button[data-research-tab="history"]').click();
   const t=await page.locator('#content').innerText();
   assert(t.includes('歷史訊號觀察組')&&t.includes('10／20／60'));
   assert(t.includes('不')||t.includes('未'));return 'historical cohort panel accessible';
  });
  await check('資料品質：研究資料館8個深入入口',async()=>{
   await page.locator('#nav > button[data-research-tab="quality"]').click();
   const p=page.locator('#content');
   assert((await p.innerText()).includes('研究資料館'));
   const links=p.locator('.r-resource-links a[href]');
   assert.equal(await links.count(),8);
   const names=await links.evaluateAll(a=>a.map(x=>x.getAttribute('href')));
   for(const href of names){
    const r=await page.request.get(new URL(href,LIVE).href,{timeout:20000});
    assert.equal(r.status(),200,'broken research library '+href+': '+r.status());
   }
   return '8 accessible library links, each HTTP 200';
  });
  await check('自選股：新增、儲存、篩選、移除及 CSV',async()=>{
   await page.locator('#nav > button[data-page="watch"]').click();
   await page.locator('#r-watch-add-form').waitFor({timeout:45000});
   for(const id of ['8064','3533']){
    await page.locator('#r-watch-add-code').fill(id);
    await page.locator('#r-watch-add-form button[type="submit"]').click();
   }
   assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('mfds-web-watch-v1'))),['8064','3533']);
   assert.equal(await page.locator('tr[data-watch-stock]').count(),2);
   await page.locator('#r-watch-sort').selectOption('code');
   await page.locator('#r-watch-mode').selectOption('review');
   await page.locator('#r-watch-mode').selectOption('all');
   const [download]=await Promise.all([page.waitForEvent('download',{timeout:30000}),
     page.locator('#r-watch-export').click()]);
   assert(download.suggestedFilename().endsWith('.csv'));
   await page.reload({waitUntil:'domcontentloaded'});
   await page.locator('#nav > button[data-page="watch"]').click();
   assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('mfds-web-watch-v1'))),['8064','3533']);
   await page.locator('button[data-action="watch"][data-id="3533"]').waitFor({state:'visible',timeout:90000});
   await page.locator('button[data-action="watch"][data-id="3533"]').click();
   assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('mfds-web-watch-v1'))),['8064']);
   return '2 added, 1 removed, persisted, exported CSV';
  });
  await check('3.0O 歷史兩日期比較與原始 SHA256',async()=>{
   await page.locator('#nav > button[data-page="watch"]').click();
   await page.waitForFunction(()=>document.querySelectorAll('#r-history-first option').length>=2,null,{timeout:90000});
   await page.locator('#r-history-go').click();
   await page.locator('.r-watch-history-verified').waitFor({timeout:70000});
   const t=await page.locator('.r-watch-history-verified').innerText();
   assert(t.includes('SHA256'));
   assert.equal(await page.locator('[data-watch-history-stock="8064"]').count(),1);
   return 'validated 2 archived files';
  });
  await check('3.0P 逐日研究時間軸與 CSV',async()=>{
   await page.locator('#nav > button[data-page="watch"]').click();
   await page.waitForFunction(()=>document.querySelectorAll('#r-timeline-from option').length>=2,null,{timeout:90000});
   const count=await page.locator('#r-timeline-from option').count();
   await page.locator('#r-timeline-stock').selectOption('8064');
   await page.locator('#r-timeline-go').click();
   await page.waitForFunction(n=>document.querySelectorAll('[data-timeline-day]').length===n,count,{timeout:90000});
   assert.equal(await page.locator('[data-timeline-day]').count(),count);
   await page.locator('#r-timeline-filter').selectOption('changes');
   await page.locator('#r-timeline-filter').selectOption('all');
   const [dl]=await Promise.all([page.waitForEvent('download',{timeout:30000}),
     page.locator('#r-timeline-export').click()]);
   assert(dl.suggestedFilename().includes('30P_8064'));
   return count+' unique source-price days successfully SHA256 verified';
  });
  await check('設定：匯入方式與四層因子權重',async()=>{
   await page.locator('#nav > button[data-page="settings"]').click();
   const t=await page.locator('#content').innerText();
   assert(t.includes('資料匯入')&&t.includes('四層因子權重'));
   assert.equal(await page.locator('#drop').count(),1);
   return 'settings reachable, import area visible';
  });
  await check('手機版：主要功能與時間軸',async()=>{
   await page.setViewportSize({width:390,height:844});
   await page.locator('#nav > button[data-page="watch"]').click();
   assert(await page.locator('.r-watch-timeline').isVisible());
   assert.equal(await page.locator('#nav > button.nav-btn').count(),7);
   return '390px seven menu items, watch timeline present';
  });
  await check('前端執行無未捕捉例外',async()=>{
   assert.deepEqual(errors,[]);return '0 pageerror events';
  });
  const label=await page.title();
  if(!EXPECTED_RELEASES.some(v=>label.includes(v)))notes.push('公開網站 HTML <title> 仍是 '+label+'，與目前可接受的發布版本不一致');
  const report={live:LIVE,tested_at:new Date().toISOString(),
    pass:results.filter(x=>x.status==='pass').length,fail:results.filter(x=>x.status==='fail').length,
    items:results,notes,pageErrors:errors};
  fs.writeFileSync('live-site-audit.json',JSON.stringify(report,null,2));
  console.log('LIVE_AUDIT_JSON '+JSON.stringify(report));
  if(report.fail)process.exitCode=1;
 }finally{await browser.close();}
})().catch(e=>{console.error('AUDIT_HARNESS_FAILURE',brief(e));process.exit(1)});
