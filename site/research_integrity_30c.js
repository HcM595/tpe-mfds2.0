/* TPE-MFDS 3.0C — auditable cross-table identity/date consistency.
 * These checks are data hygiene, NOT point-in-time eligibility or buy signals.
 * Source-specific missing coverage is reported separately, not treated as a
 * historical failure. A first-captured record after the cutoff is a separate
 * information-availability flag, not evidence of incorrect current data. */
(function(root){
'use strict';
const DETAILS={
 factor:{label:'12因子主資料',date:'price_asof',sameDay:true},
 chip:{label:'法人與集保持股',date:'flow_asof',sameDay:true},
 tech:{label:'技術交叉檢查',date:'price_asof',sameDay:true},
 industry:{label:'產業相對觀察',date:'asof',sameDay:true},
 risk:{label:'價格波動',date:'price_asof',sameDay:true},
 valuation:{label:'F2原始估值',date:'asof',sameDay:false,firstSeen:'first_seen_utc'},
 revenue:{label:'月營收',date:'table_date',sameDay:false,firstSeen:'first_seen_utc'},
 publication:{label:'F2／F3／營收公告時鐘',date:'price_asof',sameDay:true}
};
function day(s){
 if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;
 const d=Date.parse(s+'T00:00:00Z');
 return Number.isFinite(d)&&new Date(d).toISOString().slice(0,10)===s;
}
function instant(s){
 if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(s))return null;
 const ms=Date.parse(s);return Number.isFinite(ms)?ms:null;
}
function tidy(s){return String(s??'').replace(/\s+/g,'').toLowerCase()}
function inspect(tables){
 const issues=[],captures=[],coverage={},indexed={}; let ref=new Map();
 const add=(scope,source,id,type,detail)=>scope.push({source,id,type,detail});
 for(const [source,spec] of Object.entries(DETAILS)){
  const rows=tables?.[source]||[],map=new Map(),duplicate=new Set(),stockIds=new Set();
  rows.forEach((r,i)=>{
   const id=String(r.stock_id||'').trim();
   if(!/^\d{4,6}$/.test(id)){add(issues,source,id,'invalid_stock_id','第'+(i+2)+'列股票代號不符合格式');return}
   if(map.has(id)){duplicate.add(id);add(issues,source,id,'duplicate_stock','來源中同一股票代號重複');return}
   map.set(id,r);stockIds.add(id);
  });
  indexed[source]=map;
  coverage[source]={label:spec.label,rows:rows.length,uniqueStocks:stockIds.size,duplicateIds:duplicate.size,orphanStocks:0,matchedStocks:0,alignedDates:0,dateIssues:0,captureAfterCutoff:0};
 }
 ref=indexed.factor;
 const baseline=new Map([...ref.entries()].filter(([id,r])=>day(r.price_asof)));
 for(const [id,r] of ref){
  if(!day(r.price_asof))add(issues,'factor',id,'invalid_price_asof','主檔價格基準日期缺漏或無效');
  if(r.market!=='上市'&&r.market!=='上櫃')add(issues,'factor',id,'invalid_market','主檔市場類別未核實');
 }
 for(const [source,spec] of Object.entries(DETAILS)){
  if(source==='factor')continue;
  const count=coverage[source];
  for(const [id,r] of indexed[source]){
   const m=ref.get(id);
   if(!m){
    count.orphanStocks++;
    add(issues,source,id,'orphan_stock','來源股票不在12因子主資料母體');
    continue;
   }
   count.matchedStocks++;
   if(r.market&&m.market&&tidy(r.market)!==tidy(m.market)){
    add(issues,source,id,'market_mismatch','來源市場 '+r.market+' 與主檔 '+m.market+' 不符');
   }
   if(r.stock_name&&m.stock_name&&tidy(r.stock_name)!==tidy(m.stock_name)){
    add(issues,source,id,'name_mismatch','名稱不同；可能更名或來源不同步，應核對');
   }
   const p=m.price_asof,asof=String(r[spec.date]||'');
   if(!day(p))continue;
   if(!day(asof)){
    count.dateIssues++;
    add(issues,source,id,'missing_source_day','來源日期未取得或無效');
   }else if(asof>p){
    count.dateIssues++;
    add(issues,source,id,'future_source_day','來源所屬日晚於股票價格基準日，不能追認');
   }else if(spec.sameDay&&asof!==p){
    count.dateIssues++;
    add(issues,source,id,'different_source_day','每日資料日與價格日不同步；該來源不得當日使用');
   }else count.alignedDates++;
   if(spec.firstSeen&&day(p)){
    const capture=instant(r[spec.firstSeen]||'');
    const cutoff=Date.parse(p+'T00:00:00+08:00');
    if(capture===null){
     add(captures,source,id,'first_seen_unknown','首次取得時間未核實；不代表歷史當日已公開');
    }else if(capture>=cutoff){
     count.captureAfterCutoff++;
     add(captures,source,id,'capture_after_cutoff','首次取得晚於當日臺北00:00；不可回填為歷史已知資料');
    }else{
     add(captures,source,id,'publication_still_unverified','本站取得日早於保守截止，但官方首次公告仍未驗證');
    }
   }
  }
 }
 return {masterStocks:ref.size,issues,captures,coverage};
}
function forStock(report,id){
 if(!report)return {issues:[],captures:[]};
 return {issues:report.issues.filter(x=>x.id===id),captures:report.captures.filter(x=>x.id===id)};
}
const api={DETAILS,day,instant,inspect,forStock};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.MFDSIntegrity=api;
})(typeof window!=='undefined'?window:null);
