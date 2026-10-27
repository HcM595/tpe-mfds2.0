const assert=require('node:assert/strict');
const C=require('../site/research_core_30a.js');
const parsed=C.parseCSV('\uFEFFstock_id,name,note\r\n8064,"東捷,股份","複數\r\n列"\r\n2330,台積電,"含""引號"""\r\n');
assert.equal(parsed.length,2);
assert.deepEqual(parsed[0],{stock_id:'8064',name:'東捷,股份',note:'複數\r\n列'});
assert.equal(parsed[1].note,'含"引號"');
assert.throws(()=>C.parseCSV('a,b\n1,"unclosed'),/引號未關閉/);
assert.equal(C.amount(''),null);
assert.equal(C.amount('not-available'),null);
assert.equal(C.truth('true'),true);
const factors=[
 {stock_id:'8064',stock_name:'東捷',market:'上櫃',price_asof:'2026-10-27',basic_data_eligible:'true',model_eligible:'false',prediction_enabled:'false',verified_factor_count:'0',observed_factor_count:'10',price_sessions:'160',avg20_trade_value_twd:'8500000'},
 {stock_id:'3533',stock_name:'嘉澤',market:'上市',price_asof:'2026-10-27',basic_data_eligible:'false',model_eligible:'false',prediction_enabled:'false',verified_factor_count:'0',observed_factor_count:'8',avg20_trade_value_twd:''}
];
const sources={factor:factors,
 chip:[
 {stock_id:'8064',flow_asof:'2026-10-27',holder_asof:'2026-10-22',foreign_5d_shares:'25000',trust_5d_shares:'7000',large400_pct:'63.2',large400_4w_pp:'0.8',large1000_pct:'50.1',large1000_4w_pp:'0.6'},
 {stock_id:'3533',flow_asof:'2026-10-26',holder_asof:'2026-10-29',foreign_5d_shares:'999999',trust_5d_shares:'999999',large1000_4w_pp:'3.6'}
 ],
 tech:[{stock_id:'8064',price_asof:'2026-10-27',data_status:'可驗證',ma20:'120',ma60:'123',rsi14:'55.4',ma20_rising:'是',close_above_ma20:'是',macd_hist_improving:'是',technical_status:'三項確認'}],
 industry:[{stock_id:'8064',market:'上櫃',asof:'2026-10-27',industry_relative20_raw_pp:'2.6',industry_name_from_revenue:'光電業'}],
 risk:[{stock_id:'8064',market:'上櫃',price_asof:'2026-10-27',last_close:'122',realized_volatility20_annualized_pct:'41.3',max_close_drawdown60_pct:'-12.8',price_adjusted:'false'}],
 valuation:[{stock_id:'8064',market:'上櫃',asof:'2026-10-22',pe_ratio:'22.4',pb_ratio:'2.1',first_seen_utc:'2026-10-27T01:00:00Z'}],
 revenue:[{stock_id:'8064',market:'上櫃',revenue_period:'2026-09',month_revenue_yoy_pct:'15.7',first_seen_utc:'2026-10-27T01:00:00Z'}],
 publication:[{stock_id:'8064',F2_asof_clock_pass:'false',F3_asof_clock_pass:'false',REVENUE_asof_clock_pass:'false'}]
};
const records=C.merge(sources);
assert.equal(records.length,2);
const a=records.find(x=>x.id==='8064'),b=records.find(x=>x.id==='3533');
assert.equal(a.basicEligible,true);
assert.equal(a.modelEligible,false);
assert.equal(a.foreign,25000);
assert.equal(a.trust,7000);
assert.equal(a.institutionDirection,'外資／投信同向買超');
assert.equal(a.holderAsOf,'2026-10-22');
assert.equal(a.holderDirection,'雙級距增加');
assert.equal(a.lot1000Delta,0.6);
assert.equal(a.aboveMa20,'是');
assert.equal(a.sectorRelative20,2.6);
assert.equal(a.priceAdjusted,false);
assert.equal(a.sourceClockPassed,false);
assert.equal(a.predictionEnabled,false);
assert.equal(b.flowDateOK,false);
assert.equal(b.foreign,null,'stale flows must be missing');
assert.equal(b.holderDateOK,false,'future holder snapshot must be missing');
assert.equal(b.lot1000Delta,null);
assert.equal(C.filterRows(records,{institution:'both'}).length,1);
assert.equal(C.filterRows(records,{holders:'up'}).length,1);
assert.equal(C.filterRows(records,{technical:'3'}).length,1);
assert.equal(C.filterRows(records,{market:'上市'}).length,1);
assert.equal(C.filterRows(records,{q:'東捷'}).length,1);
assert.equal(C.filterRows(records,{basic:'eligible'}).length,1);
assert.equal(C.asOfLabel('2026-10-22','2026-10-27'),'先前觀察日');
assert.equal(C.sign(0.6,' pp'),'+0.6 pp');
assert.throws(()=>C.merge({factor:[...factors,factors[0]]}),/股票代號重複/);
console.log('PASS 3.0A: unified research joins, old weekly shareholder observation, date synchronization and no predictive model');