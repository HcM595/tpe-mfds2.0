/* TPE-MFDS original design eligibility, separate from descriptive chip rank. */
(function(root){
'use strict';
function num(v){if(v===null||v===undefined||String(v).trim()==='')return null;const n=Number(String(v).replace(/,/g,''));return Number.isFinite(n)?n:null;}
function evaluate(points, asof, minDays=120, minTurnover=30000000){
 // Point-in-time rule: later prices must never count toward a historical screen.
 const cutoff=/^\d{4}-\d{2}-\d{2}$/.test(asof||'')?asof:null;
 const clean=(Array.isArray(points)?points:[]).filter(p=>/^\d{4}-\d{2}-\d{2}$/.test(p.date||'')&&num(p.close)>0&&(!cutoff||p.date<=cutoff))
  .slice().sort((a,b)=>a.date.localeCompare(b.date));
 const distinct=[...new Map(clean.map(p=>[p.date,p])).values()];
 const recent=distinct.slice(-20);
 const turnover=recent.length===20&&recent.every(p=>num(p.trade_value_twd)!==null&&num(p.trade_value_twd)>=0)
   ?recent.reduce((x,p)=>x+num(p.trade_value_twd),0)/20:null;
 const pricesCurrent=!!(cutoff&&distinct.length&&distinct[distinct.length-1].date===cutoff);
 const status=distinct.length<minDays?'歷史資料不足':turnover===null?'近20日成交額資料不足':!pricesCurrent?'歷史資料尚未對齊最新收盤日':turnover<minTurnover?'流動性未達門檻':'符合基本資料與流動性條件';
 return {status,eligible:status==='符合基本資料與流動性條件',count:distinct.length,turnover,latest:distinct.at(-1)?.date||'',priceAsOf:asof||'',factorEligible:false};
}
const api={evaluate};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.MFDSResearchEligibility=api;
})(typeof window!=='undefined'?window:null);
