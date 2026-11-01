/* 3.0X-U: single-stock source presence audit; not historical eligibility. */
(function(root){
'use strict';
const KEYS=['factor','chip','tech','industry','risk','valuation','revenue','publication','actions'];
function diagnose(id,tables,failures,priceDate=''){
 const stock=String(id||'').trim();
 if(!/^\d{4,6}$/.test(stock))return {error:'請輸入4至6位股票代號',rows:[],backtestEligible:false};
 const rows=KEYS.map(key=>{
   const items=Array.isArray(tables?.[key])?tables[key]:[];
   const matches=items.filter(r=>String(r.stock_id||'').trim()===stock);
   const available=!failures?.[key]&&matches.length>0;
   const dates=[...new Set(matches.flatMap(r=>['price_asof','flow_asof','holder_asof','asof','table_date','period'].map(k=>r[k]).filter(Boolean)))];
   const priceClock=['factor','tech','industry','risk','actions'].includes(key);
   const observed=priceClock?matches.map(r=>r.price_asof||r.asof||'').filter(Boolean):[];
   const future=priceDate&&observed.some(d=>/^\d{4}-\d{2}-\d{2}$/.test(d)&&d>priceDate);
   const mismatch=priceDate&&observed.length>0&&observed.every(d=>d!==priceDate);
   const grade=failures?.[key]?'source_error':!matches.length?'missing':future?'future_date':mismatch?'date_mismatch':!dates.length?'undated':'observed';
   const reasons={source_error:'來源載入或快照驗證失敗',missing:'本資料表沒有此股紀錄；不等於股票無行情',future_date:'來源所屬日晚於行情基準日，不得當作當日已知資料',date_mismatch:'價格日資料與行情基準日不一致',undated:'有來源紀錄但未提供可核對日期',observed:'有來源紀錄；未驗證官方首次公告時分'};
   return {key,present:available,matchedRows:matches.length,sourceProblem:failures?.[key]||null,dates:dates.slice(0,5),grade,reason:reasons[grade]};
 });
 return {stock_id:stock,rows,backtestEligible:false,reason:'尚未完成時點、除權息及獨立樣本外交易績效資格驗證'};
}
root.MFDSStockCoverage30U={diagnose,KEYS};
})(typeof window!=='undefined'?window:globalThis);
