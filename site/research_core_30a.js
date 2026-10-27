/* TPE-MFDS 3.0A: shared factual stock research joins & filters.
   No model scores, success probabilities or point-in-time certifications.
   Holder snapshots are weekly observations; their release clocks are not verified. */
(function(root) {
'use strict';
function parseCSV(text) {
  const s=String(text??'').replace(/^\uFEFF/,'');
  const rows=[];let row=[],v='',inside=false;
  for(let i=0;i<s.length;i++){const c=s[i];
    if(c==='"'){if(inside&&s[i+1]==='"'){v+='"';i++;}else inside=!inside;}
    else if(c===','&&!inside){row.push(v);v='';}
    else if((c==='\r'||c==='\n')&&!inside){if(c==='\r'&&s[i+1]==='\n')i++;row.push(v);if(row.some(x=>x!==''))rows.push(row);row=[];v='';}
    else v+=c;
  }
  if(inside)throw Error('CSV格式錯誤：引號未關閉');
  if(v!==''||row.length){row.push(v);rows.push(row);}
  const columns=rows.shift()||[];
  if(!columns.length)return [];
  return rows.map(r=>Object.fromEntries(columns.map((k,i)=>[k,r[i]??''])));
}
const amount=s=>typeof s==='number'&&Number.isFinite(s)?s:
  (typeof s==='string'&&s.trim()!==''&&Number.isFinite(Number(s))?Number(s):null);
const exists=x=>x!==null&&x!==undefined&&x!=='';
const truth=x=>String(x).toLowerCase()==='true'||x==='是';
const oneDay=(asof,ref)=>Boolean(asof)&&asof===ref;
function lookup(rows) {
 const map=new Map();
 for(const r of rows||[]){
   if(!r.stock_id)continue;
   if(map.has(r.stock_id))throw Error('股票代號重複：'+r.stock_id);
   map.set(r.stock_id,r);
 }
 return map;
}
function merge(sources) {
 const factor=lookup(sources.factor||[]);
 if(!factor.size)throw Error('12因子逐股研究主資料為空');
 const maps={};
 for(const k of ['chip','tech','industry','risk','valuation','revenue','publication']){
   maps[k]=lookup(sources[k]||[]);
 }
 const records=[...factor.values()].map(b=>{
   const id=b.stock_id,p=b.price_asof,chip=maps.chip.get(id)||{},tech=maps.tech.get(id)||{},
      industry=maps.industry.get(id)||{},risk=maps.risk.get(id)||{},
      valuation=maps.valuation.get(id)||{},revenue=maps.revenue.get(id)||{},
      publication=maps.publication.get(id)||{};
   const flowDateOK=oneDay(chip.flow_asof,p);
   const techDateOK=oneDay(tech.price_asof,p)&&tech.data_status==='可驗證';
   const holderDateOK=!!chip.holder_asof&&!!p&&chip.holder_asof<=p;
   const sectorDateOK=oneDay(industry.asof,p)&&(!industry.market||industry.market===b.market);
   const riskDateOK=oneDay(risk.price_asof,p)&&(!risk.market||risk.market===b.market);
   const f2Matched=!!valuation.stock_id&&(!valuation.market||valuation.market===b.market);
   const revenueMatched=!!revenue.stock_id&&(!revenue.market||revenue.market===b.market);
   const foreign=flowDateOK?amount(chip.foreign_5d_shares):null;
   const trust=flowDateOK?amount(chip.trust_5d_shares):null;
   const lot400=holderDateOK?amount(chip.large400_4w_pp):null;
   const lot1000=holderDateOK?amount(chip.large1000_4w_pp):null;
   const yearMonth=(revenueMatched&&revenue.revenue_period)||'';
   const indicator=x=>techDateOK&&['是','否'].includes(x)?x:null;
   return {id,name:b.stock_name,market:b.market,asof:p,
      basicEligible:truth(b.basic_data_eligible),
      basicStatus:b.basic_data_status||'缺資料',
      modelEligible:truth(b.model_eligible),
      predictionEnabled:truth(b.prediction_enabled),
      verifiedFactors:amount(b.verified_factor_count)??0,
      coverageFactors:amount(b.observed_factor_count)??0,
      sourcePostdates:truth(b.source_postdates_price),
      sessionCount:amount(b.price_sessions),
      turnover:amount(b.avg20_trade_value_twd),
      close:riskDateOK?amount(risk.last_close):(techDateOK?amount(tech.close):null),
      ma20:techDateOK?amount(tech.ma20):null,
      ma60:techDateOK?amount(tech.ma60):null,
      rsi:techDateOK?amount(tech.rsi14):null,
      aboveMa20:indicator(tech.close_above_ma20),
      ma20Rising:indicator(tech.ma20_rising),
      macdImprove:indicator(tech.macd_hist_improving),
      technicalStatus:techDateOK?tech.technical_status:'技術資料缺漏／不同步',
      foreign,trust,flowAsOf:chip.flow_asof||'',flowDateOK,
      holderAsOf:chip.holder_asof||'',holderDateOK,
      lot400Pct:holderDateOK?amount(chip.large400_pct):null,
      lot1000Pct:holderDateOK?amount(chip.large1000_pct):null,
      lot400Delta:lot400,lot1000Delta:lot1000,
      institutionDirection:foreign===null||trust===null?'缺資料':
        foreign>0&&trust>0?'外資／投信同向買超':
        foreign<0&&trust<0?'外資／投信同向賣超':'法人分歧／中性',
      holderDirection:lot400===null||lot1000===null?'缺資料':
        lot400>0&&lot1000>0?'雙級距增加':
        lot400<0&&lot1000<0?'雙級距減少':'大戶級距分歧／中性',
      sectorName:sectorDateOK?industry.industry_name_from_revenue:'',
      sectorRelative20:sectorDateOK?amount(industry.industry_relative20_raw_pp):null,
      vol20:riskDateOK?amount(risk.realized_volatility20_annualized_pct):null,
      dd60:riskDateOK?amount(risk.max_close_drawdown60_pct):null,
      riskStatus:riskDateOK?risk.risk_status:'風險資料缺漏',
      priceAdjusted:riskDateOK?truth(risk.price_adjusted):false,
      pe:f2Matched?amount(valuation.pe_ratio):null,
      pb:f2Matched?amount(valuation.pb_ratio):null,
      valuationAsOf:f2Matched?(valuation.asof||''):'',
      valuationFirstSeen:f2Matched?(valuation.first_seen_utc||''):'',
      revenuePeriod:yearMonth,
      revenueYoY:revenueMatched?amount(revenue.month_revenue_yoy_pct):null,
      revenueFirstSeen:revenueMatched?(revenue.first_seen_utc||''):'',
      revenueTableDate:revenueMatched?(revenue.table_date||''):'',
      sourceClockPassed:publication.F2_asof_clock_pass==='true'||
        publication.F3_asof_clock_pass==='true'||
        publication.REVENUE_asof_clock_pass==='true',
      releaseF2:publication.F2_asof_clock_pass||'false',
      releaseF3:publication.F3_asof_clock_pass||'false',
      releaseRevenue:publication.REVENUE_asof_clock_pass||'false',
      original:b
   };
 });
 return records.sort((a,b)=>a.id.localeCompare(b.id,'en',{numeric:true}));
}
function match(r,filter={}) {
 const term=String(filter.q||'').trim().toLowerCase();
 if(term&&!((r.id+' '+r.name).toLowerCase().includes(term)))return false;
 if(filter.market&&filter.market!=='all'&&r.market!==filter.market)return false;
 if(filter.basic==='eligible'&&!r.basicEligible)return false;
 if(filter.institution==='both'&&!(r.foreign>0&&r.trust>0))return false;
 if(filter.institution==='foreign'&&!(r.foreign>0))return false;
 if(filter.institution==='split'&&!(r.institutionDirection==='法人分歧／中性'))return false;
 if(filter.holders==='up'&&!(r.lot400Delta>0&&r.lot1000Delta>0))return false;
 if(filter.holders==='split'&&!(r.holderDirection==='大戶級距分歧／中性'))return false;
 if(filter.technical==='3'&&!(r.aboveMa20==='是'&&r.ma20Rising==='是'&&r.macdImprove==='是'))return false;
 if(filter.technical==='ma20'&&r.aboveMa20!=='是')return false;
 if(filter.technical==='missing'&&r.aboveMa20!==null)return false;
 return true;
}
function filterRows(rows,filter){return rows.filter(x=>match(x,filter));}
const fmt=(value,digits=2)=>value===null||value===undefined||value===''?'—':
  Number.isFinite(Number(value))?Number(value).toLocaleString('zh-TW',{maximumFractionDigits:digits}):String(value);
const pct=(v,digits=2)=>v===null||v===undefined?'—':fmt(v,digits)+'%';
const sign=(v,unit='')=>v===null||v===undefined?'—':(v>0?'+':'')+fmt(v,2)+unit;
const asOfLabel=(date,base)=>!date?'未取得':date===base?'同價格日':date<base?'先前觀察日':'晚於價格日';
const api={parseCSV,amount,truth,lookup,merge,match,filterRows,fmt,pct,sign,asOfLabel};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.MFDSWorkbench=api;
})(typeof window!=='undefined'?window:null);
