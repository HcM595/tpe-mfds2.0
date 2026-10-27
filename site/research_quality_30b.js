/* TPE-MFDS 3.0B — auditable source diagnostics and safe browser-only CSV.
   Source exists / clocks align / historical eligibility are separate checks. */
(function(root){
'use strict';
const SOURCE_NAMES={factor:'12因子主資料',chip:'法人與集保持股',tech:'技術交叉檢查',
 industry:'產業相對觀察',risk:'價格與波動',valuation:'F2原始估值',
 revenue:'月營收',publication:'F2／F3／月營收三時鐘'};
const PRESENT=['factor','chip','tech','industry','risk','valuation','revenue','publication'];
const has=(v)=>v!==null&&v!==undefined&&String(v).trim()!=='';
function validDay(x){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(x||'')))return false;
 const t=Date.parse(x+'T00:00:00Z');
 return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===x;
}
function dayClass(date,price){
 if(!validDay(price)||!validDay(date))return 'unverified';
 if(date>price)return 'future';
 if(date===price)return 'same_day';
 return 'prior_day';
}
function sourceCounts(inputs,failures={}){
 return PRESENT.map(id=>{
   const data=inputs?.[id]||[];
   return {id,name:SOURCE_NAMES[id],count:data.length,
     status:failures[id]?'load_failed':data.length?'loaded':'empty',
     error:String(failures[id]||''),
     note:id==='chip'?'法人為交易日資料，集保為週觀察；公布時刻須另外核查':
      id==='valuation'||id==='revenue'?'資料已取得不等於當時可取得；首次封存時間非公司公告時間':
      id==='publication'?'三時鐘資料提供阻擋原因，非任何模型預測許可':
      id==='risk'?'原始收盤計算未必完成除權息還原':'資料筆數並非可交易股票數或模型得分'};
 });
}
function evidence(r){
 if(!r)return[];
 const value=(ok,reason,asof='')=>({ok,reason,asof:asof||''});
 const risk=r.close!==null?
   value(!r.priceAdjusted,'已取得原始價格；尚未完成除權息調整，僅供描述',r.asof):
   value(false,'缺少與股價日一致的價格來源',r.asof);
 // status is descriptive; do not call raw unadjusted data "verified".
 const cls=r.flowAsOf?dayClass(r.flowAsOf,r.asof):'unverified';
 return [
  {name:'逐股研究主檔',state:r.basicEligible?'observed':'limited',
   detail:r.basicStatus||'未取得',asof:r.asof},
  {name:'原始價格與風險',state:r.close===null?'missing':'observed',
   detail:r.close===null?'價格缺漏／不同步':risk.reason,asof:r.asof},
  {name:'外資／投信5日',state:r.flowDateOK?'observed':'missing',
   detail:r.flowDateOK?'流量觀察日與價格日一致；未證明發佈時刻':
      cls==='future'?'來源日期晚於價格基準日（禁止追認）':'交易日不同步或來源缺漏',
   asof:r.flowAsOf},
  {name:'400／1000張集保',state:r.holderDateOK?'lagged':'missing',
   detail:r.holderDateOK?'較早週資料，僅供現況觀察；獨立公布時刻未核實':
     dayClass(r.holderAsOf,r.asof)==='future'?'集保日期晚於價格日（禁止追認）':'集保持股日期缺漏',
   asof:r.holderAsOf},
  {name:'技術三確認',state:r.aboveMa20===null?'missing':'observed',
   detail:r.aboveMa20===null?'MA20／MACD未同步或缺乏可核對資料':
     '三項技術條件為描述性觀察，不是歷史勝率',asof:r.asof},
  {name:'F2估值公開時間',state:r.releaseF2==='true'?'clock_only':'blocked',
   detail:r.releaseF2==='true'?'僅來源時鐘條件通過，並非12因子通過':
     '無完整公告、首次取得與價格截止點證據；不可作歷史因子',
   asof:r.valuationAsOf},
  {name:'月營收公開時間',state:r.releaseRevenue==='true'?'clock_only':'blocked',
   detail:r.releaseRevenue==='true'?'僅來源時鐘條件通過，不代表模型合格':
     '月營收表格日期不等於逐公司公開時刻；不可作歷史因子',asof:r.revenueTableDate},
  {name:'F3治理公開時間',state:r.releaseF3==='true'?'clock_only':'blocked',
   detail:r.releaseF3==='true'?'僅來源時鐘條件通過，不代表模型合格':
     '逐公司治理公告時刻尚未獨立核實',asof:''},
  {name:'正式12因子模型',state:r.modelEligible&&r.predictionEnabled?'review_required':'blocked',
   detail:'獨立12因子、公司行動價格還原與樣本外驗證未完成；勝率／回測不提供',
   asof:r.asof}
 ];
}
function summarize(rows,inputs,failures={}){
 return {stocks:rows.length,priceDates:[...new Set(rows.map(x=>x.asof).filter(Boolean))].sort(),
   basic:rows.filter(x=>x.basicEligible).length,
   flows:rows.filter(x=>x.flowDateOK).length,
   holders:rows.filter(x=>x.holderDateOK).length,
   tech:rows.filter(x=>x.aboveMa20!==null).length,
   rawPrice:rows.filter(x=>x.close!==null).length,
   unadjusted:rows.filter(x=>x.close!==null&&!x.priceAdjusted).length,
   sourceClockPasses:rows.filter(x=>x.sourceClockPassed).length,
   predictions:rows.filter(x=>x.modelEligible&&x.predictionEnabled).length,
   sources:sourceCounts(inputs,failures)};
}
const COLUMNS=[
 ['stock_id','股票代號',r=>r.id],['stock_name','公司名稱',r=>r.name],
 ['market','市場',r=>r.market],['price_asof','價格資料日',r=>r.asof],
 ['basic_eligible','行情與流動性初步通過',r=>r.basicEligible?'true':'false'],
 ['foreign_5d_shares','外資5日買賣超股數',r=>r.foreign],
 ['trust_5d_shares','投信5日買賣超股數',r=>r.trust],
 ['flow_asof','法人資料日',r=>r.flowAsOf],
 ['holder_asof','集保持股觀察週截至',r=>r.holderAsOf],
 ['holder_large400_pct','400張以上持股占比',r=>r.lot400Pct],
 ['holder_large1000_pct','1000張以上持股占比',r=>r.lot1000Pct],
 ['holder_large400_delta_pp','400張以上4週變動pp',r=>r.lot400Delta],
 ['holder_large1000_delta_pp','1000張以上4週變動pp',r=>r.lot1000Delta],
 ['raw_close','原始收盤價',r=>r.close],
 ['raw_ma20','MA20',r=>r.ma20],['rsi14','RSI14',r=>r.rsi],
 ['technical_status','技術狀態',r=>r.technicalStatus],
 ['f2_pe_raw','原始本益比',r=>r.pe],
 ['f2_first_seen_utc','F2首次封存UTC',r=>r.valuationFirstSeen],
 ['revenue_yoy_pct','月營收年增百分比',r=>r.revenueYoY],
 ['revenue_period','月營收月份',r=>r.revenuePeriod],
 ['revenue_first_seen_utc','月營收首次封存UTC',r=>r.revenueFirstSeen],
 ['price_adjusted','股價完成除權息還原',r=>r.priceAdjusted?'true':'false'],
 ['verified_factor_count','已驗證12因子數',r=>r.verifiedFactors],
 ['model_eligible','模型通過正式資格',r=>r.modelEligible?'true':'false'],
 ['historical_backtest_certified','歷史回測資格',r=>'false'],
 ['research_disclaimer','資料限制',r=>'觀察資料；集保為週資料；歷史公告時點未全核實；非買賣或勝率評級']
];
function safeCell(value){
 if(value===undefined||value===null)return '';
 if(typeof value==='number')return Number.isFinite(value)?String(value):'';
 let s=String(value);
 if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;
 return /[",\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;
}
function exportRows(rows,{bom=true}={}){
 const body=[COLUMNS.map(x=>safeCell(x[1])).join(',')];
 for(const r of rows){
   body.push(COLUMNS.map(x=>safeCell(x[2](r))).join(','));
 }
 return (bom?'\uFEFF':'')+body.join('\r\n')+'\r\n';
}
const api={SOURCE_NAMES,sourceCounts,validDay,dayClass,evidence,summarize,COLUMNS,safeCell,exportRows};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.MFDSResearchQuality=api;
})(typeof window!=='undefined'?window:null);
