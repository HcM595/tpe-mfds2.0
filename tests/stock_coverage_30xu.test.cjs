const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ctx={};ctx.globalThis=ctx;vm.runInNewContext(fs.readFileSync('site/stock_coverage_30xu.js','utf8'),ctx);
const m=ctx.MFDSStockCoverage30U;
const data={factor:[{stock_id:'8064',price_asof:'2026-10-28'}],chip:[{stock_id:'3533',flow_asof:'2026-10-28'}]};
const result=m.diagnose('8064',data,{tech:'bad source'});
assert.equal(result.rows.length,9);
assert.equal(result.rows.find(x=>x.key==='factor').present,true);
assert.equal(result.rows.find(x=>x.key==='chip').present,false);
assert.equal(result.rows.find(x=>x.key==='tech').sourceProblem,'bad source');
assert.equal(result.backtestEligible,false);
assert.ok(m.diagnose('abc',data,{}).error);
const graded=m.diagnose('8064',{
 factor:[{stock_id:'8064',price_asof:'2026-10-27'}],
 tech:[{stock_id:'8064',price_asof:'2026-10-31'}],
 risk:[{stock_id:'8064',price_asof:'2026-10-30'}],
 revenue:[{stock_id:'8064',table_date:'2026-09-30'}],
 publication:[{stock_id:'8064'}]
},{},'2026-10-30');
const byKey=k=>graded.rows.find(x=>x.key===k);
assert.equal(byKey('factor').grade,'date_mismatch');
assert.equal(byKey('tech').grade,'future_date');
assert.equal(byKey('risk').grade,'observed');
assert.equal(byKey('revenue').grade,'observed','monthly source must not require same price day');
assert.equal(byKey('publication').grade,'undated');
assert.equal(byKey('chip').grade,'missing');
assert.equal(m.diagnose('8064',data,{factor:'unavailable'},'2026-10-28').rows[0].grade,'source_error');
assert.equal(graded.backtestEligible,false);
console.log('3.0X-U source quality classifications passed');
