const assert=require('node:assert/strict');
const C=require('../site/research_core_30a.js');
const Q=require('../site/research_quality_30b.js');
assert.equal(Q.validDay('2026-10-27'),true);
assert.equal(Q.validDay('2026-02-29'),false);
assert.equal(Q.dayClass('2026-10-22','2026-10-27'),'prior_day');
assert.equal(Q.dayClass('2026-10-28','2026-10-27'),'future');
assert.equal(Q.dayClass('garbled','2026-10-27'),'unverified');
assert.equal(Q.firstCaptureStatus('2026-10-26T15:59:59Z','2026-10-27'),'before_cutoff');
assert.equal(Q.firstCaptureStatus('2026-10-26T16:00:00Z','2026-10-27'),'after_cutoff');
assert.equal(Q.firstCaptureStatus('2026-10-27T08:01:00+08:00','2026-10-27'),'after_cutoff');
assert.equal(Q.firstCaptureStatus('2026-10-26','2026-10-27'),'first_seen_unknown');
assert.equal(Q.firstCaptureStatus('2026-10-26T11:00:00','2026-10-27'),'first_seen_unknown');
assert(Q.captureNote('2026-10-27T00:01:00+08:00','2026-10-27').includes('禁止追認'));

const factor=[
 {stock_id:'8064',stock_name:'東捷',market:'上櫃',price_asof:'2026-10-27',basic_data_eligible:'true',model_eligible:'false',prediction_enabled:'false',verified_factor_count:'0',observed_factor_count:'9'},
 {stock_id:'3533',stock_name:'嘉澤',market:'上市',price_asof:'2026-10-27',basic_data_eligible:'false',model_eligible:'false',prediction_enabled:'false',verified_factor_count:'0',observed_factor_count:'7'}];
const inputs={factor,
 chip:[{stock_id:'8064',flow_asof:'2026-10-27',holder_asof:'2026-10-22',foreign_5d_shares:'1200',trust_5d_shares:'3400',large400_pct:'60',large1000_pct:'50',large400_4w_pp:'0.2',large1000_4w_pp:'0.5'},
       {stock_id:'3533',flow_asof:'2026-10-28',holder_asof:'2026-10-28',foreign_5d_shares:'4000',trust_5d_shares:'5000'}],
 tech:[{stock_id:'8064',price_asof:'2026-10-27',data_status:'可驗證',close_above_ma20:'是',ma20_rising:'是',macd_hist_improving:'是'}],
 risk:[{stock_id:'8064',market:'上櫃',price_asof:'2026-10-27',last_close:'120',price_adjusted:'false'}],
 valuation:[{stock_id:'8064',market:'上櫃',asof:'2026-10-22',pe_ratio:'22',first_seen_utc:'2026-10-27T08:00:00Z'}],
 publication:[{stock_id:'8064',F2_asof_clock_pass:'false',F3_asof_clock_pass:'false',REVENUE_asof_clock_pass:'false'}]
};
const rows=C.merge(inputs),r=rows.find(x=>x.id==='8064'),s=rows.find(x=>x.id==='3533');
const a=Q.summarize(rows,inputs,{revenue:'HTTP 404'});
assert.equal(a.stocks,2);
assert.equal(a.flows,1);
assert.equal(a.holders,1);
assert.equal(a.tech,1);
assert.equal(a.unadjusted,1);
assert.equal(a.predictions,0);
assert.deepEqual(a.priceDates,['2026-10-27']);
assert.equal(a.sources.length,8);
assert.equal(a.sources.find(x=>x.id==='revenue').status,'load_failed');
assert.equal(a.sources.find(x=>x.id==='revenue').error,'HTTP 404');
const evidence=Q.evidence(r);
assert(evidence.some(x=>x.name==='400／1000張集保'&&x.state==='lagged'&&x.asof==='2026-10-22'));
assert(evidence.some(x=>x.name==='F2估值公開時間'&&x.state==='blocked'));
assert(evidence.some(x=>x.name==='正式12因子模型'&&x.state==='blocked'));
assert(Q.evidence(s).some(x=>x.name==='外資／投信5日'&&x.detail.includes('禁止追認')));
assert(Q.evidence(s).some(x=>x.name==='400／1000張集保'&&x.detail.includes('禁止追認')));
assert.equal(Q.sourceCounts(inputs).find(x=>x.id==='revenue').status,'empty');
assert(Q.safeCell('=HYPERLINK("malicious")').includes("'=HYPERLINK"),'formula prefix must be neutralized');
assert.equal(Q.safeCell('  +cmd'),"'  +cmd");
assert.equal(Q.safeCell('-cmd'),"'-cmd");
assert.equal(Q.safeCell(-5),'-5','numerical negatives must remain numeric');
assert.equal(Q.safeCell('含逗號,與"引號"'),'"含逗號,與""引號"""');
const csv=Q.exportRows(rows);
assert(csv.startsWith('\uFEFF股票代號,公司名稱,市場'));
assert(csv.includes('8064,東捷,上櫃'));
assert(csv.includes('2026-10-22'));
assert(csv.includes('歷史回測資格'));
assert(csv.includes('觀察資料；集保為週資料'));
assert.equal(csv.split('\r\n').length,4);
assert.equal(Q.exportRows(rows,{bom:false}).charCodeAt(0),'股'.charCodeAt(0));
const sanitized=Q.exportRows([{...r,name:'=HYPERLINK("http://bad")'}],{bom:false});
assert(sanitized.includes("'=HYPERLINK"),'formula-like stock names must not be executable CSV cells');
console.log('PASS 3.0B: source loading audit, weekly holder and PIT limitations, browser CSV reproducibility and formula injection prevention');
