const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {parseCSV}=require('../site/research_core_30a.js');
const Brief=require('../site/stock_evidence_30m.js');
const Cross=require('../site/chip_tech_crossfilter_30l.js');
const W=require('../site/watchlist_center_30n.js');

const dir=path.join(__dirname,'../site/data/');
const csv=name=>parseCSV(fs.readFileSync(dir+name,'utf8').replace(/^\uFEFF/,''));
const data=(name)=>{
 const rows=csv(name),heads=rows[0];
 return rows.slice(1).filter(x=>x.some(y=>y.trim())).map(x=>
   Object.fromEntries(heads.map((h,i)=>[h,(x[i]||'').trim()])));
};
const keys={rank:'chip_rank.csv',chip:'chip_signals.csv',tech:'tech_crosscheck.csv',
 factor:'factor_evidence_29a.csv',revenue:'revenue_snapshot_28c.csv',
 risk:'risk_observations_28d.csv',valuation:'f2_valuation_29e.csv',
 income:'income_snapshot_28f.csv'};
const sources=Object.fromEntries(Object.entries(keys).map(([k,p])=>[k,data(p)]));
const official=JSON.parse(fs.readFileSync(dir+'official_meta.json','utf8'));
const ids=['8064','3533','2345'];
const quotes=[{stock_id:'8064',stock_name:'東捷',close:121.5,asof:official.display_date}];
const options={sources,official,quotes,quoteMode:'official',
 brief:Brief.build,crossCheck:Cross.evaluate};
assert.deepEqual(W.ids(['3533','3533','bad','DEMO01','8064',42,'2345']),['3533','8064','2345']);
assert.deepEqual(W.ids(new Array(102).fill('8064')),['8064']);
assert.deepEqual(W.ids(null),[]);
assert.deepEqual(W.add(['3533'],'8064'),['3533','8064']);
assert.deepEqual(W.add(['3533'],'3533'),['3533']);
assert.throws(()=>W.add([], 'undefined'),/數字股票代號/);
assert.throws(()=>W.add([], '"><script>alert(1)</script>'),/數字股票代號/);
assert.throws(()=>W.add(Array.from({length:100},(_,i)=>String(1000+i)), '2330'),/100/);
const report=W.build(ids,options);
assert.equal(report.stock_count,3);
assert.equal(report.records.length,3);
assert.equal(report.source_loaded,report.source_expected);
assert.equal(report.source_expected,8);
assert.equal(report.source_price_asof,official.display_date);
assert.equal(report.probability_enabled,false);
assert.equal(report.official_price_count,1);
assert.equal(report.records[0].price,121.5);
assert.equal(report.records[1].price,null);
assert.equal(report.records[0].flow.observed_at,official.display_date);
assert(report.records.every(r=>r.detail.probability_enabled===false));
assert(report.records.every(r=>r.detail.blockers.some(x=>x.includes('正式勝率停用'))));
assert(report.records.some(r=>r.unverified_dimensions>=1));
for(const view of ['all','confluence','review']){
 const list=W.view(report,{mode:view});
 assert(list.every(r=>report.records.includes(r)));
 if(view==='confluence')assert(list.every(r=>r.three_axes));
 if(view==='review')assert(list.every(r=>r.urgent_review));
}
assert.equal(W.view(report,{query:'8064'}).length,1);
assert.equal(W.view(report,{query:'沒有這檔'}).length,0);
assert.equal(W.view(report,{sort:'code'})[0].id,'2345');
assert.throws(()=>W.view(report,{mode:'probability'}),/不正確/);
assert.throws(()=>W.view(report,{sort:'magic'}),/未知/);
const actualCsv=W.toCSV(report.records);
assert(actualCsv.includes('股票代號')&&actualCsv.includes('官方收盤價'));
assert(actualCsv.includes('法人資料日')&&actualCsv.includes('集保資料日'));
assert(actualCsv.includes('正式勝率'));
assert.equal(actualCsv.split('\r\n').length,4);
const html=W.render(report,{codes:ids,mode:'all',quoteMode:'official'});
assert(html.includes('3.0N自選股追蹤中心'));
assert(html.includes('8064')&&html.includes('3533')&&html.includes('2345'));
assert(html.includes('r-watch-export')&&html.includes('r-watch-add-form'));
assert(!html.includes('已驗證預測勝率'));
assert.equal((html.match(/data-watch-stock=/g)||[]).length,3);
const protectedHtml=W.render(report,{codes:ids,mode:'all',query:'" onmouseover="alert(1)'});
assert(!protectedHtml.includes('value="" onmouseover='));
const fakeReport=W.build(ids,{...options,quoteMode:'demo',quotes});
assert.equal(fakeReport.official_price_count,0,'demo and real price must not be mixed');
const missing=W.build(ids,{...options,sources:{},quotes:[]});
assert.equal(missing.source_loaded,0);
assert.equal(missing.three_axes_count,0);
assert.equal(missing.official_price_count,0);
assert(missing.records.every(r=>!r.flow.usable&&!r.holder.usable&&!r.technical.usable));
const failedHTML=W.render(missing,{codes:ids,loading:true,quoteMode:'demo'});
assert(failedHTML.includes('正在讀取')&&failedHTML.includes('—'));
const contaminated={...options,sources:{...sources,rank:[...sources.rank,...sources.rank.slice(0,1)]}};
assert.throws(()=>W.build(ids,contaminated),/重複/);
const injected=structuredClone(report);
injected.records[0].name='=1+1';
assert(W.toCSV(injected.records).includes('"\'=1+1"'));
injected.records[0].detail.probability_enabled=true;
assert.throws(()=>W.toCSV(injected.records),/未核實/);
console.log('PASS 3.0N: 8064/3533/2345 real archived watchlist, 8 data sources, strict missing/identity gates, filters, XSS/CSV safety');
