/* 3.0X-U: single-stock source presence audit; not historical eligibility. */
(function(root){
'use strict';
const KEYS=['factor','chip','tech','industry','risk','valuation','revenue','publication','actions'];
function diagnose(id,tables,failures){
 const stock=String(id||'').trim();
 if(!/^\d{4,6}$/.test(stock))return {error:'請輸入4至6位股票代號',rows:[],backtestEligible:false};
 const rows=KEYS.map(key=>{
   const items=Array.isArray(tables?.[key])?tables[key]:[];
   const matches=items.filter(r=>String(r.stock_id||'').trim()===stock);
   const available=!failures?.[key]&&matches.length>0;
   const dates=[...new Set(matches.flatMap(r=>['price_asof','flow_asof','holder_asof','asof','table_date','period'].map(k=>r[k]).filter(Boolean)))];
   return {key,present:available,matchedRows:matches.length,sourceProblem:failures?.[key]||null,dates:dates.slice(0,5),
     reason:failures?.[key]?'來源載入或快照驗證失敗':matches.length?'有來源紀錄；不代表已驗證公告時點':'本資料表沒有此股紀錄；不等於股票無行情'};
 });
 return {stock_id:stock,rows,backtestEligible:false,reason:'尚未完成時點、除權息及獨立樣本外交易績效資格驗證'};
}
root.MFDSStockCoverage30U={diagnose,KEYS};
})(typeof window!=='undefined'?window:globalThis);
