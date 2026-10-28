const assert=require('node:assert/strict');
const I=require('../site/research_integrity_30c.js');
assert.equal(I.day('2026-10-27'),true);
assert.equal(I.day('2026-02-30'),false);
assert.equal(I.instant('2026-10-27'),null);
assert.equal(I.instant('2026-10-27T09:00:00'),null);
const tables={
 factor:[{stock_id:'8064',stock_name:'東捷',market:'上櫃',price_asof:'2026-10-27'},
         {stock_id:'3533',stock_name:'嘉澤',market:'上市',price_asof:'2026-10-27'}],
 chip:[{stock_id:'8064',flow_asof:'2026-10-27',holder_asof:'2026-10-22'},
       {stock_id:'3533',flow_asof:'2026-10-28',holder_asof:'2026-10-22'}],
 risk:[{stock_id:'8064',market:'上市',stock_name:'東捷',price_asof:'2026-10-27'},
       {stock_id:'3533',market:'上市',stock_name:'錯誤公司名',price_asof:'2026-10-26'}],
 tech:[{stock_id:'8064',price_asof:'2026-10-27'},
       {stock_id:'8064',price_asof:'2026-10-27'}],
 industry:[{stock_id:'9999',market:'上市',asof:'2026-10-27'}],
 valuation:[{stock_id:'8064',market:'上櫃',stock_name:'東捷',asof:'2026-10-27',
             first_seen_utc:'2026-10-26T15:59:59Z'},
            {stock_id:'3533',market:'上市',asof:'2026-10-27',
             first_seen_utc:'2026-10-27T05:00:00Z'}],
 revenue:[{stock_id:'8064',market:'上櫃',table_date:'2026-10-17',
             first_seen_utc:'2026-10-27T09:00:00Z'}],
 publication:[{stock_id:'8064',market:'上櫃',price_asof:'2026-10-27'}]
};
const r=I.inspect(tables);
assert.equal(r.masterStocks,2);
const pairs=r.issues.map(x=>x.source+':'+x.type);
for(const key of ['chip:future_source_day','risk:market_mismatch','risk:name_mismatch',
                  'risk:different_source_day','tech:duplicate_stock','industry:orphan_stock']){
 assert(pairs.includes(key),'missing source identity/date error '+key);
}
assert.equal(r.coverage.chip.dateIssues,1);
assert.equal(r.coverage.tech.duplicateIds,1);
assert.equal(r.coverage.industry.orphanStocks,1);
assert.equal(r.coverage.valuation.alignedDates,2);
assert.equal(r.coverage.valuation.captureAfterCutoff,1);
assert.equal(r.coverage.revenue.captureAfterCutoff,1);
assert(r.captures.some(x=>x.source==='valuation'&&x.id==='8064'&&x.type==='publication_still_unverified'));
assert(r.captures.some(x=>x.source==='valuation'&&x.id==='3533'&&x.type==='capture_after_cutoff'));
assert(I.forStock(r,'3533').issues.some(x=>x.source==='chip'));
assert(I.forStock(r,'8064').captures.some(x=>x.source==='revenue'));
assert.deepEqual(I.forStock(r,'999999'),{issues:[],captures:[]});
const bad=I.inspect({factor:[{stock_id:'8064',market:'上櫃',price_asof:'2026-02-30'}]});
assert(bad.issues.some(x=>x.type==='invalid_price_asof'));
const wrong=I.inspect({factor:tables.factor,chip:[{stock_id:'8064',flow_asof:'2026-10-27'},
 {stock_id:'1234567',flow_asof:'2026-10-27'}]});
assert(wrong.issues.some(x=>x.type==='invalid_stock_id'));
console.log('PASS 3.0C: cross-source duplicate, orphan, market/name drift, daily/future dates and captured after Taipei cutoff');
