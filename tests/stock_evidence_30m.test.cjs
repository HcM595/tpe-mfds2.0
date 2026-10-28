const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Brief=require('../site/stock_evidence_30m.js');
const {parseCSV}=require('../site/research_core_30a.js');
const Cross=require('../site/chip_tech_crossfilter_30l.js');
const data=name=>parseCSV(fs.readFileSync(path.join(__dirname,'../site/data',name),'utf8'));
const row=(rows,id)=>rows.find(x=>x.stock_id===id)||null;
const chipRows=data('chip_signals.csv');
const ranks=data('chip_rank.csv'),techRows=data('tech_crosscheck.csv');
const facs=data('factor_evidence_29a.csv');
const risks=data('risk_observations_28d.csv');
const revs=data('revenue_snapshot_28c.csv');
const vals=data('f2_valuation_29e.csv');
const income=data('income_snapshot_28f.csv');
const official=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/official_meta.json'),'utf8'));
function build(id,override={}){
 const sources={rank:row(ranks,id),chip:row(chipRows,id),tech:row(techRows,id),
   factor:row(facs,id),revenue:row(revs,id),risk:row(risks,id),
   valuation:row(vals,id),income:row(income,id)};
 return Brief.build({stockId:id,stockName:sources.factor?.stock_name||id,
   priceDate:official.display_date,sources,
   loaded:{rank:true,chip:true,tech:true,factor:true,revenue:true,risk:true,valuation:true,income:true},
   crossCheck:Cross.evaluate,...override});
}
assert.equal(Brief.date('2026-02-30'),null);
assert.equal(Brief.date('2026-10-28')!==null,true);
assert.equal(Brief.number(''),null);
assert.equal(Brief.number('Infinity'),null);
assert.equal(Brief.number('NaN'),null);
assert.equal(Brief.number('1,200'),1200);
for(const code of ['8064','3533','2345']){
 const b=build(code);
 assert.equal(b.stock_id,code);
 assert.equal(b.cards.length,4);
 assert.equal(b.sources.length,10);
 assert(b.blockers.length>=1);
 assert.equal(b.probability_enabled,false);
 assert.equal(b.strict_backtest_eligible,false);
 assert(b.blockers.some(x=>x.includes('正式勝率停用')));
 assert(Brief.toCSV(b).includes('官方公布時分'));
 assert(!Brief.toCSV(b).includes('預測勝率80%'));
 for(const item of b.cards){
  if(!item.usable)assert.equal(item.value,'—','missing evidence cannot render a number');
 }
}
const stock=build('8064');
assert(stock.model.eligible===false);
assert(stock.model.verified_factors===0||stock.model.verified_factors===null);
assert(stock.cards[0].usable); // actual 8064 flow date is the current session, but negative shares.
assert(stock.cards[0].value.includes('外資'));
assert(!stock.cross.includes('三面條件描述性符合'));
const copy=JSON.parse(JSON.stringify({rank:row(ranks,'3533'),chip:row(chipRows,'3533'),
 tech:row(techRows,'3533'),factor:row(facs,'3533'),revenue:row(revs,'3533'),
 risk:row(risks,'3533'),valuation:row(vals,'3533'),income:row(income,'3533')}));
const loaded={rank:true,chip:true,tech:true,factor:true,revenue:true,risk:true,valuation:true,income:true};
const config={stockId:'3533',priceDate:official.display_date,sources:copy,loaded,crossCheck:Cross.evaluate};
const orig=Brief.build(config);
assert.equal(orig.price_date,official.display_date);
assert(orig.cards.some(x=>x.usable));
const older=Brief.build({...config,sources:{...copy,chip:{...copy.chip,holder_asof:'2026-09-01'}}});
assert.equal(older.cards[1].value,'—');
assert(older.blockers.some(x=>x.includes('集保週資料缺漏')));
const tooLate=Brief.build({...config,sources:{...copy,revenue:{...copy.revenue,table_date:'2026-10-29'}}});
assert.equal(tooLate.cards[3].value,'—');
assert(tooLate.blockers.some(x=>x.includes('營收表日期')));
const noTech=Brief.build({...config,loaded:{...loaded,tech:false}});
assert.equal(noTech.cards[2].value,'—');
assert.equal(noTech.sources.find(x=>x.source==='技術交叉驗證').state,'待核對');
const techHistory=Brief.build({...config,sources:{...copy,tech:{...copy.tech,latest_history_date:'2026-10-27'}}});
assert.equal(techHistory.cards[2].value,'—');
const priceFuture=Brief.build({...config,priceDate:'2026-10-27'});
assert.equal(priceFuture.cards[0].value,'—');
assert.equal(priceFuture.cards[2].value,'—');
assert.equal(priceFuture.model.eligible,false);
assert.equal(Brief.build({...config,priceDate:'2026-02-30'}).price_date,'—');
assert.throws(()=>Brief.build({...config,sources:{...copy,factor:{...copy.factor,stock_id:'8064'}}}),/不同股票/);
assert.throws(()=>Brief.build({...config,stockId:'BAD'}),/代號/);
const hostile=Brief.build({...config,stockName:' =HYPERLINK("test")'});
const csv=Brief.toCSV(hostile);
assert(csv.includes('"\' =HYPERLINK(""test"")"'));
assert.throws(()=>Brief.toCSV({...hostile,probability_enabled:true}),/未驗證/);
console.log('PASS 3.0M: real 8064, 3533, 2345; source clocks, stale data, missing values, unrelated stocks and CSV formula guard');
