/* TPE-MFDS 3.0P | Archived observation timeline (NOT daily trading data).
 * All points MUST be sourced from the first captured and SHA256-verified
 * 2.4A archive for each source-price day using MFDSWatchHistory30O.
 * Public source publication clocks, executions and returns are unverified.
 */
(function(root){
'use strict';
const VALID_ID=/^\d{4,6}$/;
const MAX_DAYS=90;
const MODES=Object.freeze(['all','changes','new_holder','not_updated']);
function safe(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function classify(previous,current){
 if(!previous)return {kind:'baseline',label:'首次封存觀察',changes:[],holderUpdate:'unknown',holderNote:'首次封存，尚無上一期可比較'};
 const a=previous.signal,b=current.signal;
 if(!a&&!b)return {kind:'not_in_archive',label:'兩期均未見於封存候選',changes:[],holderUpdate:'unknown',holderNote:'本股未列入封存候選，不代表無持股或法人未買賣'};
 if(!a&&b)return {kind:'new_candidate',label:'新出現於封存候選',changes:['候選名單出現'],holderUpdate:'unknown',holderNote:'無上期同股資料可比較；不是新的買進訊號'};
 if(a&&!b)return {kind:'missing_candidate',label:'本期未見於封存候選',changes:['候選名單未見'],holderUpdate:'unknown',holderNote:'候選名單之外仍可能有股票資料；不能判定賣出或持股下降'};
 const changes=[];
 if(previous.view.rank!==current.view.rank)changes.push('排名資格改變');
 if(previous.view.tech!==current.view.tech)changes.push('技術確認改變');
 const oldDate=previous.view.holderDate,newDate=current.view.holderDate;
 let holderUpdate='unknown',holderNote='集保資料日期不符合核對資格';
 if(oldDate!=='—'&&newDate!=='—'){
  if(oldDate===newDate){
   holderUpdate='same_week';
   holderNote='兩期集保資料日期相同，不能算作新一週增減';
   if(previous.view.holder!==current.view.holder){
    changes.push('同週資料結構不一致');
    holderUpdate='same_week_conflict';
    holderNote='集保資料日期相同但結構標籤不同，疑似資料版本差異；不得解讀為新持股變化';
   }
  }else if(oldDate<newDate){
   holderUpdate='new_week';
   holderNote='集保週資料來源日更新；不代表首次公開時分已認證';
   if(previous.view.holder!==current.view.holder)changes.push('大戶結構分類改變');
  }else{
   holderUpdate='regressed';
   holderNote='集保資料日期倒退，禁止推論持股結構變化';
   changes.push('集保來源日期倒退');
  }
 }
 const kind=changes.length?'changed':holderUpdate==='new_week'?'holder_refreshed':
   holderUpdate==='same_week'?'unchanged':'insufficient';
 return {kind,label:changes.join('、')||(
    holderUpdate==='new_week'?'集保週來源日更新、主要狀態相同':
    holderUpdate==='same_week'?'主要狀態相同、集保未更新':'無可核實新增變化'),
  changes,holderUpdate,holderNote};
}
function build(verified,stockId,rawRows=[]){
 if(!VALID_ID.test(stockId||''))throw Error('請選擇正確股票代號');
 if(!Array.isArray(verified)||verified.length<2||verified.length>MAX_DAYS)
  throw Error('歷史封存必須是2至90個不同來源價格日');
 const core=root?.MFDSWatchHistory30O;
 if(!core||typeof core.state!=='function')throw Error('3.0O歷史核對元件未載入');
 if(!Array.isArray(rawRows))throw Error('3.0Q歷史來源應為逐股表格');
 const rawIndex=new Map();
 for(const raw of rawRows){
  if(raw.stock_id!==stockId)continue;
  const day=raw.price_session;
  if(!day||rawIndex.has(day))throw Error('3.0Q來源日期重複或缺漏');
  rawIndex.set(day,raw);
 }
 const rows=[],seen=new Set();
 for(const doc of verified){
  if(!doc||doc.byteVerified!==true||doc.publicationVerified!==false||
     !(doc.signals instanceof Map)||typeof doc.date!=='string'||
     !doc.entry||core.dayOf(doc.entry)!==doc.date||!doc.captured)
   throw Error('時間軸資料未通過原始封存身分與SHA256核驗');
  if(seen.has(doc.date)||rows.length&&rows.at(-1).date>=doc.date)
   throw Error('封存交易日重複或非時間遞增，禁止誤算歷史樣本');
  seen.add(doc.date);
  const signal=doc.signals.get(stockId)||null,view=core.state(signal);
  const provenance=rawIndex.get(doc.date)||null;
  let rawEvidence=null;
  if(provenance){
   if(provenance.first_snapshot_id!==doc.entry.snapshot_id||
      provenance.first_snapshot_sha256!==doc.entry.snapshot_sha256||
      provenance.first_captured_at_utc!==doc.captured||
      provenance.raw_input_verified!=='true'||
      !doc.sourceSha256||
      provenance.rank_source_sha256!==doc.sourceSha256['chip_rank.csv']||
      provenance.chip_source_sha256!==doc.sourceSha256['chip_signals.csv']||
      provenance.tech_source_sha256!==doc.sourceSha256['tech_crosscheck.csv'])
    throw Error('3.0Q逐股來源與已驗證原始封存SHA256或時鐘不一致');
   const flow=provenance.flow_5d_observation_usable==='true'&&
      provenance.flow_asof===doc.date;
   const holder=provenance.holder_4w_observation_usable==='true'&&
      provenance.holder_asof<=doc.date&&provenance.holder_asof!=='';
   rawEvidence={
    flowDate:provenance.flow_asof||'—',holderDate:provenance.holder_asof||'—',
    foreign:flow&&provenance.foreign_5d_shares!==''?provenance.foreign_5d_shares:null,
    trust:flow&&provenance.trust_5d_shares!==''?provenance.trust_5d_shares:null,
    holder400:holder&&provenance.large400_4w_pp!==''?provenance.large400_4w_pp:null,
    holder1000:holder&&provenance.large1000_4w_pp!==''?provenance.large1000_4w_pp:null,
    sourceStatus:'已與原始SHA256核對；官方首次公布時分未認證'
   };
  }
  const row={date:doc.date,captured:doc.captured,archiveId:doc.entry.snapshot_id,
    signal,view,stock_id:stockId,
    name:signal?.stock_name||null,priceClock:doc.date,rawEvidence,
    publisherClockVerified:false,byteVerified:true};
  const classification=classify(rows.at(-1)||null,row);
  const {kind,label,changes,holderUpdate,holderNote}=classification;
  Object.assign(row,{kind,label,changes,holderUpdate,holderNote,verified:true});
  rows.push(row);
 }
 const changing=rows.filter(r=>r.kind==='changed'||r.kind==='new_candidate'||r.kind==='missing_candidate');
 const refreshed=rows.filter(r=>r.holderUpdate==='new_week').length;
 const pending=rows.filter(r=>r.holderUpdate==='same_week'||r.holderUpdate==='same_week_conflict').length;
 const unknown=rows.filter(r=>r.view.kind==='not_in_archive').length;
 return {stock_id:stockId,name:rows.findLast(x=>x.name)?.name||'未列入封存候選',
  rows,observations:rows.length,changed_days:changing.length,
  new_holder_week_days:refreshed,same_week_days:pending,not_in_candidates:unknown,
  start:rows[0].date,end:rows.at(-1).date,verifiedAll:true,
  prediction_enabled:false,canEstimateReturns:false,
  limit:'只有封存來源價格日，不代表所有交易日都有觀察；封存時刻不等於資料首次公開時分。舊版簡化訊號未顯示外資／投信股數，但2.4A原始gzip曾封存，3.0Q只恢復已SHA256核對的當時數值；無法證明官方首次公開時間，也無真實成交或還原報酬，不能據以計算勝率或推論主力意圖。'};
}
function subset(report,mode){
 if(!report?.verifiedAll||!MODES.includes(mode))throw Error('時間軸研究資料或篩選方式不合格');
 return report.rows.filter(r=>mode==='all'||
   mode==='changes'&&['changed','new_candidate','missing_candidate'].includes(r.kind)||
   mode==='new_holder'&&r.holderUpdate==='new_week'||
   mode==='not_updated'&&['same_week','same_week_conflict','regressed','unknown'].includes(r.holderUpdate));
}
function render(report,mode='all'){
 if(!report?.verifiedAll)throw Error('未經逐份SHA256驗證，禁止輸出歷史時間軸');
 const rows=subset(report,mode);
 const line=rows.map(r=>{
  const tone=r.kind==='changed'||r.kind==='new_candidate'?'change':
     r.kind==='missing_candidate'||r.holderUpdate==='regressed'?'warning':'neutral';
  const sourceDiff=r.holderUpdate==='same_week_conflict';
  return '<li class="r-timeline-node '+tone+'" data-timeline-day="'+safe(r.date)+'">'+
    '<span class="r-timeline-dot" aria-hidden="true"></span>'+
    '<div class="r-timeline-content"><div class="r-timeline-date"><time datetime="'+safe(r.date)+'">'+safe(r.date)+'</time>'+
    '<span>'+safe(r.label)+'</span></div>'+
    '<div class="r-timeline-details">'+
    '<span>排行：'+safe(r.view.rank)+(r.view.rankNumber&&r.view.rankNumber!=='—'?' · '+safe(r.view.rankNumber):'')+'</span>'+
    '<span>技術：'+safe(r.view.tech)+(r.view.techCount&&r.view.techCount!=='—'?' · '+safe(r.view.techCount)+'/3':'')+'</span>'+
    '<span>大戶結構：'+safe(r.view.holder)+'</span>'+
    '<span>集保週資料日：'+safe(r.view.holderDate)+'</span></div>'+
    '<p class="r-timeline-raw">3.0Q原始數值 · 外資5日：'+safe(r.rawEvidence?.foreign??'—')+
    ' 股；投信5日：'+safe(r.rawEvidence?.trust??'—')+
    ' 股；400張以上4週：'+safe(r.rawEvidence?.holder400??'—')+
    ' pp；1000張以上4週：'+safe(r.rawEvidence?.holder1000??'—')+
    ' pp。<small>'+safe(r.rawEvidence?.sourceStatus||'當次原始逐股數值尚未核對；不可填入最新值')+'</small></p>'+
    '<p class="r-timeline-annotation '+(sourceDiff?'review':'')+'">'+safe(r.holderNote)+'</p>'+
    '<small>首次封存UTC：'+safe(r.captured)+'；SHA256 已驗證，官方公布時刻未核實</small>'+
    '</div></li>';
 }).join('');
 return '<div class="r-timeline-summary"><div><small>封存價格日</small><b>'+report.observations+
   '</b></div><div><small>主要狀態改變日</small><b>'+report.changed_days+
   '</b></div><div><small>集保新來源週</small><b>'+report.new_holder_week_days+
   '</b></div><div><small>週資料未更新日</small><b>'+report.same_week_days+'</b></div></div>'+
   (!rows.length?'<div class="r-empty">所選分類沒有封存觀察。請切回「全部觀察」。</div>':
    '<ol class="r-timeline-list" aria-label="自選股封存價格日時間軸">'+line+'</ol>')+
   '<p class="r-watch-foot">'+safe(report.limit)+'</p>';
}
function cell(v){
 const s=String(v??'');return '"'+(/^\s*[=+\-@]/.test(s)||/^[\t\r\n]/.test(s)?"'"+s:s).replace(/"/g,'""')+'"';
}
function toCSV(report,mode='all'){
 if(!report?.verifiedAll)throw Error('時間軸尚未驗證');
 const header=['股票代號','股票名稱','封存價格日','首次捕捉UTC','封存身分','排名資格',
 '技術狀態','技術確認數','集保結構','集保來源週日期','上一期比較','集保更新分類',
 '集保資料風險','原始位元SHA256校驗','官方首次公布時間',
 '原始外資5日股數','原始投信5日股數','原始400張以上4週pp','原始1000張以上4週pp','原始資料核對狀態'];
 const rows=[header,...subset(report,mode).map(r=>[r.stock_id,report.name,r.date,r.captured,
  r.archiveId,r.view.rank,r.view.tech,r.view.techCount||'—',r.view.holder,r.view.holderDate,
  r.label,r.holderUpdate,r.holderNote,'已通過','未核實',
  r.rawEvidence?.foreign??'',r.rawEvidence?.trust??'',r.rawEvidence?.holder400??'',
  r.rawEvidence?.holder1000??'',r.rawEvidence?.sourceStatus||'缺少已核對來源'])];
 return rows.map(r=>r.map(cell).join(',')).join('\r\n');
}
const api=Object.freeze({MAX_DAYS,MODES,classify,build,subset,render,toCSV});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSWatchTimeline30P=api;
})(typeof window!=='undefined'?window:null);
