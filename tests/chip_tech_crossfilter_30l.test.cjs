const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const X=require('../site/chip_tech_crossfilter_30l.js');
const {parseCSV}=require('../site/research_core_30a.js');

function base(){
 const rank={
   stock_id:'8064',stock_name:'東捷',market:'上櫃',sector:'其他電子',rank_status:'可排名',
   chip_status:'matched',chip_strength_rank:'5',price_asof:'2026-10-27',
   flow_asof:'2026-10-27',holder_asof:'2026-10-22',
   foreign_5d_shares:'50000',trust_5d_shares:'1000',
   mid400_999_4w_pp:'1.2',large1000_4w_pp:'1.4'
 };
 const tech={
   stock_id:'8064',data_status:'可驗證',price_asof:'2026-10-27',
   flow_asof:'2026-10-27',holder_asof:'2026-10-22',
   technical_confirmed_count:'3',technical_status:'三項確認'
 };
 return {rank,tech};
}
const cutoff='2026-10-27';
const {rank,tech}=base();
assert.deepEqual(X.evaluate(rank,tech,cutoff).issues,[]);
assert.equal(X.evaluate(rank,tech,cutoff).confluence,true);
assert.equal(X.screen([rank],[tech],{mode:'confluence',asofLimit:cutoff}).length,1);
for(const field of ['flow_asof','holder_asof','price_asof']){
 const row={...rank,[field]:'2026-10-28'};
 const item=X.evaluate(row,tech,cutoff);
 assert.equal(item.confluence,false,'future date in '+field+' must not pass');
}
for(const field of ['foreign_5d_shares','trust_5d_shares','mid400_999_4w_pp','large1000_4w_pp']){
 for(const value of ['','0','-0.02','NaN','abc']){
  const item=X.evaluate({...rank,[field]:value},tech,cutoff);
  assert.equal(item.confluence,false,field+' missing/zero/falling must never count');
 }
}
const tWrong={...tech,holder_asof:'2026-10-15'};
assert.equal(X.evaluate(rank,tWrong,cutoff).technical,false);
assert.equal(X.evaluate(rank,{...tech,technical_confirmed_count:'2'},cutoff).technical,false);
assert.equal(X.evaluate(rank,{...tech,technical_status:'部分確認'},cutoff).technical,false);
assert.equal(X.evaluate(rank,{...tech,data_status:'缺漏'},cutoff).technical,false);
assert.equal(X.evaluate(rank,{},cutoff).confluence,false);
assert.equal(X.evaluate(rank,tech,'2026-10-26').confluence,false);
assert.equal(X.evaluate(rank,tech,undefined).confluence,false);
assert.equal(X.evaluate({...rank,holder_asof:'2026-10-01'},{...tech,holder_asof:'2026-10-01'},cutoff).confluence,false);
assert.equal(X.day('2026-02-30'),null);
assert.equal(X.day('2026-13-01'),null);
assert.equal(X.day('2026-10-27')!==null,true);
for(const name of X.MODES)assert(Array.isArray(X.screen([rank],[tech],{mode:name,asofLimit:cutoff})));
assert.throws(()=>X.screen([rank,rank],[tech],{asofLimit:cutoff}),/重複/);
assert.throws(()=>X.screen([rank],[tech,tech],{asofLimit:cutoff}),/重複/);
assert.throws(()=>X.screen([rank],[tech],{mode:'predict',asofLimit:cutoff}),/未知/);

// Real published data regression: no computed intersection may violate any
// one of the independently recorded source clocks and independent holder tiers.
const baseDir=path.join(__dirname,'../site/data');
const rankRows=parseCSV(fs.readFileSync(path.join(baseDir,'chip_rank.csv'),'utf8'));
const techRows=parseCSV(fs.readFileSync(path.join(baseDir,'tech_crosscheck.csv'),'utf8'));
const official=JSON.parse(fs.readFileSync(path.join(baseDir,'official_meta.json'),'utf8'));
const limit=official.display_date;
const actual=X.screen(rankRows,techRows,{mode:'confluence',asofLimit:limit});
assert(rankRows.length>=20,'real rank list absent');
assert(actual.length<=rankRows.length,'intersection unexpectedly larger than source');
for(const {row,tech,check} of actual){
 assert.equal(check.confluence,true);
 assert.equal(row.flow_asof,row.price_asof);
 assert.equal(row.price_asof,limit);
 assert.equal(tech.price_asof,row.price_asof);
 assert.equal(tech.holder_asof,row.holder_asof);
 assert(Number(row.foreign_5d_shares)>0&&Number(row.trust_5d_shares)>0);
 assert(Number(row.mid400_999_4w_pp)>0&&Number(row.large1000_4w_pp)>0);
 assert.equal(tech.technical_confirmed_count,'3');
}
assert(!JSON.stringify(actual).includes('predicted_win_rate'));
console.log('PASS 3.0L: actual '+rankRows.length+' rank rows, '+actual.length+
 ' eligible descriptive 3-axis intersections, no date leakage, partial holder tiers never double-counted');
