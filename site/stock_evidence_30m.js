/* TPE-MFDS 3.0M | Single-stock research brief and evidence clocks.
 * All source dates are observations, NOT verified release timestamps.
 * Descriptive status is never a prediction, investment score or backtest.
 */
(function(root){
'use strict';
const DAY=/^\d{4}-\d{2}-\d{2}$/;
function date(v){
 if(typeof v!=='string'||!DAY.test(v))return null;
 const t=new Date(v+'T00:00:00Z');
 return Number.isFinite(t.getTime())&&t.toISOString().slice(0,10)===v?t.getTime():null;
}
function number(v){
 if(v===null||v===undefined||typeof v==='boolean'||String(v).trim()==='')return null;
 const n=Number(String(v).replaceAll(',',''));
 return Number.isFinite(n)?n:null;
}
function short(n,unit=''){
 const v=number(n);return v===null?'—':v.toLocaleString('zh-TW',{maximumFractionDigits:2})+unit;
}
function valueRow(code,title,value,obsDate,priceDate,opts={}){
 const hasDate=date(obsDate)!==null,base=date(priceDate);
 const applicable=!!opts.loaded&&!!opts.row&&hasDate&&base!==null&&
   (opts.requireSameDate?obsDate===priceDate:date(obsDate)<=base);
 const status=!opts.loaded?'來源未載入':!opts.row?'本股無紀錄':
    !hasDate?'日期缺漏／格式錯誤':base===null?'行情基準日缺漏':
    date(obsDate)>base?'來源日晚於行情日':
    opts.requireSameDate&&obsDate!==priceDate?'來源日未與行情對齊':
    '描述性觀察';
 return {code,title,value:applicable?(value??'—'):'—',observed_at:hasDate?obsDate:'—',
    status,usable:applicable,
    note:opts.note||'未核實官方首次公開時分；不可回填歷史交易訊號',
    source:opts.source||'未指定'};
}
function build(opts){
 if(!opts||typeof opts!=='object')throw Error('必須提供逐股來源物件');
 const id=String(opts.stockId??'');
 if(!/^\d{4,6}$/.test(id))throw Error('股票代號不合法');
 const price=opts.priceDate,priceOK=date(price)!==null;
 const sources=opts.sources||{},loaded=opts.loaded||{};
 const name=String(opts.stockName||'');
 for(const [key,row] of Object.entries(sources)){
  if(row&&typeof row==='object'&&row.stock_id&&row.stock_id!==id)
   throw Error('不同股票代號的資料不得混入：'+key);
 }
 const rank=sources.rank||null,chip=sources.chip||null,tech=sources.tech||null;
 const factor=sources.factor||null,rev=sources.revenue||null,risk=sources.risk||null;
 const valuation=sources.valuation||null,income=sources.income||null;
 const rankAsOf=rank?.price_asof||'';
 const flowDate=chip?.flow_asof||rank?.flow_asof||'';
 const holderDate=chip?.holder_asof||rank?.holder_asof||'';
 const datedFlow=priceOK&&flowDate===price;
 const holderDays=priceOK&&date(holderDate)!==null?
   (date(price)-date(holderDate))/86400000:null;
 const holderCurrent=holderDays!==null&&holderDays>=0&&holderDays<=14;
 const techAligned=priceOK&&tech?.data_status==='可驗證'&&
   tech.price_asof===price&&tech.latest_history_date===price;
 const rankCurrent=rank?.rank_status==='可排名'&&rankAsOf===price;
 const chipOK=loaded.chip&&chip!==null;
 const rankOK=loaded.rank&&rank!==null&&rankCurrent;
 const flow=chipOK&&datedFlow;
 const holder=chipOK&&holderCurrent;
 const techOK=loaded.tech&&tech!==null&&techAligned;
 const flowMessage=flow?
   '外資 '+short(chip.foreign_5d_shares,' 股')+'；投信 '+short(chip.trust_5d_shares,' 股'):'—';
 const holderMessage=holder?
   '400張以上 '+short(chip.large400_4w_pp,' pp')+'；1000張以上 '+short(chip.large1000_4w_pp,' pp'):'—';
 const techMessage=techOK?
   short(tech.technical_confirmed_count,'／3')+'；RSI14 '+short(tech.rsi14):'—';
 const revenueDate=rev?.table_date||'';
 const revApplicable=loaded.revenue&&rev&&date(revenueDate)!==null&&priceOK&&date(revenueDate)<=date(price);
 const revText=revApplicable?
   rev.revenue_period+' 營收年增 '+short(rev.month_revenue_yoy_pct,'%'):'—';
 const signal=opts.crossCheck&&rankOK&&techOK?
   opts.crossCheck(rank,tech,price):null;
 const cards=[
  valueRow('institution','法人近5日淨買超',flowMessage,flowDate,price,{
   loaded:!!loaded.chip,row:chip,requireSameDate:true,source:'chip_signals.csv',
   note:'僅外資及投信近5日數量；沒有官方逐筆公告時分認證'}),
  valueRow('holder','集保持股週變化',holderMessage,holderDate,price,{
   loaded:!!loaded.chip,row:chip,source:'chip_signals.csv',
   note:'集保為週資料，僅14天內可作近期觀察；400張以上與1000張以上是重疊級距'}),
  valueRow('technical','技術三確認／RSI',techMessage,tech?.price_asof,price,{
   loaded:!!loaded.tech,row:tech,requireSameDate:true,source:'tech_crosscheck.csv',
   note:'只有日期與最新歷史收盤對齊，才顯示技術原始觀察；股價未還原'}),
  valueRow('revenue','最新營收年增',revText,revenueDate,price,{
   loaded:!!loaded.revenue,row:rev,source:'revenue_snapshot_28c.csv',
   note:'資料表日期不等於公司正式首次公布時分；不同月份不可直接推論獲利'}),
 ];
 if(!holder){cards[1].value='—';cards[1].usable=false;
   if(cards[1].status==='描述性觀察')cards[1].status='集保週資料超過14天';}
 if(!techOK&&cards[2].usable){cards[2].value='—';cards[2].usable=false;
   cards[2].status='技術歷史日或資料資格未核對';}
 if(!factor||!loaded.factor){} // No inference from missing factor records.
 const verifiedCount=loaded.factor&&factor?number(factor.verified_factor_count):null;
 const factorAsOf=factor?.price_asof||'';
 const factorAligned=verifiedCount!==null&&factorAsOf===price;
 const f2SameOrPrior=loaded.valuation&&valuation&&priceOK&&date(valuation.asof)!==null&&date(valuation.asof)<=date(price);
 const riskAligned=loaded.risk&&risk&&priceOK&&risk.price_asof===price;
 const incomeDate=income?.table_date||'';
 const incomeVisible=loaded.income&&income&&priceOK&&date(incomeDate)!==null&&date(incomeDate)<=date(price);
 const sourcesView=[
  {source:'行情基準日',date:priceOK?price:'—',observation:'官方當次價格日期',published:'尚未逐分核實',state:priceOK?'已標示':'缺漏'},
  {source:'籌碼排行',date:rankAsOf||'—',observation:rankCurrent?'可排名且同行情日':'未排名／日期不一致',published:'未核實',state:rankOK?'描述性觀察':'待核對'},
  {source:'法人5日',date:date(flowDate)!==null?flowDate:'—',observation:flow?'與行情日對齊':'未對齊／缺漏',published:'未核實',state:flow?'描述性觀察':'待核對'},
  {source:'集保週持股',date:date(holderDate)!==null?holderDate:'—',observation:holder?'14天內週資料':'過期／缺漏／未來日期',published:'未核實',state:holder?'描述性觀察':'待核對'},
  {source:'技術交叉驗證',date:date(tech?.price_asof)!==null?tech.price_asof:'—',observation:techOK?'原始技術資料同行情日':'歷史日／來源狀態待核對',published:'未核實',state:techOK?'描述性觀察':'待核對'},
  {source:'12因子證據',date:date(factorAsOf)!==null?factorAsOf:'—',observation:factorAligned?short(verifiedCount,'／12 因子已認證'):'未完整核對',published:'未核實',state:factorAligned?'描述性核對':'待核對'},
  {source:'月營收',date:date(revenueDate)!==null?revenueDate:'—',observation:revApplicable?revText:'來源缺漏或晚於行情日',published:rev?.disclosure_time_verified==='true'?'來源標記已核實':'未核實',state:revApplicable?'描述性觀察':'待核對'},
  {source:'收盤風險',date:date(risk?.price_asof)!==null?risk.price_asof:'—',observation:riskAligned?'20／60日未還原收盤觀察':'未對齊／缺漏',published:'不適用',state:riskAligned?'描述性觀察':'待核對'},
  {source:'官方估值',date:date(valuation?.asof)!==null?valuation.asof:'—',observation:f2SameOrPrior?'本益比 '+short(valuation.pe_ratio):'估值日期缺漏／晚於行情日',published:valuation?.quote_publication_at_verified==='true'?'來源標記已核實':'未核實',state:f2SameOrPrior?'描述性觀察':'待核對'},
  {source:'財務報表',date:date(incomeDate)!==null?incomeDate:'—',observation:incomeVisible?String(income.report_period||'原始報表')+'；單位／口徑仍待確認':'缺漏或晚於行情日',published:income?.per_company_filing_time_verified==='true'?'來源標記已核實':'未核實',state:incomeVisible?'描述性觀察':'待核對'}
 ];
 const blockers=[];
 if(!priceOK)blockers.push('行情基準日缺漏或格式錯誤');
 if(!rankOK)blockers.push('本股未在當次可排名籌碼資料，或排名來源日期不一致');
 if(!flow)blockers.push('法人5日與當次行情日期不一致，或法人來源未取得');
 if(!holder)blockers.push('集保週資料缺漏、過期或晚於行情日期');
 if(!techOK)blockers.push('技術交叉資料不完整或最新歷史日未對齊');
 if(!factorAligned||verifiedCount<9)blockers.push('至少9項正式12因子來源驗證資格尚未通過');
 if(!revApplicable)blockers.push('營收表日期未能作當次描述性觀察');
 if(!riskAligned)blockers.push('收盤風險日期未對齊或原始來源缺漏');
 blockers.push('歷史除權息／實際成交價／逐股官方發布時分及樣本外驗證仍不足；正式勝率停用');
 return {
  stock_id:id,stock_name:name,price_date:priceOK?price:'—',
  cards,sources:sourcesView,blockers,
  cross:signal&&signal.confluence===true?'三面條件描述性符合':signal?'三面未同時符合／需核對':'未能驗證三面交集',
  model:factorAligned&&verifiedCount!==null?{
    verified_factors:verifiedCount,source_count:12,eligible:factor.model_eligible==='true'
  }:{verified_factors:null,source_count:12,eligible:false},
  risk:riskAligned?{
    high20:short(risk.prior20_close_high),low20:short(risk.prior20_close_low),
    vol20:short(risk.realized_volatility20_annualized_pct,'%'),
    note:'未還原收盤最高／最低與年化波動，非K棒高低價或可成交支撐壓力'
  }:null,
  probability_enabled:false,strict_backtest_eligible:false,
  caution:'僅現況描述，資料表日期不代表正式發布時分。沒有可認證成交與樣本外驗證前，不顯示勝率、目標價或投資訊號。'
 };
}
function csvCell(x){
 const s=String(x??''),safe=/^[\s]*[=+\-@]/.test(s)||/^[\t\r\n]/.test(s)?"'"+s:s;
 return '"'+safe.replace(/"/g,'""')+'"';
}
function toCSV(report){
 if(!report||report.probability_enabled!==false)throw Error('研究摘要尚未驗證可匯出');
 const rows=[['股票代號','股票名稱','資料來源','來源日期','觀察內容','來源狀態','官方公布時分'],
  ...report.sources.map(x=>[report.stock_id,report.stock_name,x.source,x.date,x.observation,x.state,x.published])];
 return rows.map(x=>x.map(csvCell).join(',')).join('\r\n');
}
const api=Object.freeze({build,toCSV,date,number,valueRow});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSStockEvidence30M=api;
})(typeof window!=='undefined'?window:null);
