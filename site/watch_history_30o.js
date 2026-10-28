/* TPE-MFDS 3.0O · first-captured point-in-time watchlist comparisons.
 * One FIRST archived snapshot per source-price day; repeat/revisions are not
 * independent observations. Snapshot SHA256 checked against archive index.
 * Does NOT validate first PUBLIC publication time or create historical trades.
 */
(function(root){
'use strict';
const ID=/^\d{4,6}$/;
const DATE=/^\d{4}-\d{2}-\d{2}$/;
const HASH=/^[a-f0-9]{64}$/;
const PATH=/^signal_archive\/\d{4}\/\d{2}\/\d{2}\/[A-Za-z0-9_-]+\/snapshot\.json$/;
function day(text){
 if(typeof text!=='string'||!DATE.test(text))return false;
 const d=new Date(text+'T00:00:00Z');
 return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===text;
}
function dayOf(entry){
 const dates=entry?.source_price_dates;
 return Array.isArray(dates)&&dates.length===1&&day(dates[0])?dates[0]:null;
}
function catalog(index){
 if(!index||!Array.isArray(index.snapshots))throw Error('封存索引缺漏');
 const grouped=new Map(),ids=new Set();
 for(const x of index.snapshots){
  const d=dayOf(x);
  if(!d)continue;
  if(typeof x.snapshot_id!=='string'||!PATH.test(x.snapshot_path||'')||
     !HASH.test(x.snapshot_sha256||'')||!Number.isFinite(Date.parse(x.captured_at_utc||''))||
     ids.has(x.snapshot_id))throw Error('歷史封存索引有重複或不可信的來源身分');
  ids.add(x.snapshot_id);
  if(!grouped.has(d))grouped.set(d,[]);
  grouped.get(d).push(x);
 }
 return [...grouped].sort((a,b)=>a[0].localeCompare(b[0])).map(([date,records])=>{
   records.sort((a,b)=>a.captured_at_utc.localeCompare(b.captured_at_utc)||
     a.snapshot_id.localeCompare(b.snapshot_id));
   return {date,first:records[0],versions:records.length,
     revisions:records.filter(r=>r.signal_fingerprint!==records[0].signal_fingerprint).length};
 });
}
function utf8DigestHex(bytes){
 return Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function loadSnapshot(entry,load){
 if(!entry||!PATH.test(entry.snapshot_path||'')||!HASH.test(entry.snapshot_sha256||''))
   throw Error('封存路徑與校驗碼無效');
 if(typeof load!=='function')throw Error('缺少原始封存讀取工具');
 const bytes=await load(entry.snapshot_path);
 if(!(bytes instanceof Uint8Array))throw Error('封存必須使用原始位元組核實SHA256');
 if(!root?.crypto?.subtle)throw Error('瀏覽器無法執行SHA256校驗');
 const actual=utf8DigestHex(await root.crypto.subtle.digest('SHA-256',bytes));
 if(actual!==entry.snapshot_sha256)throw Error('封存SHA256與歷史索引不符，禁止比較');
 let doc;
 try{doc=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes))}
 catch(e){throw Error('封存JSON讀取失敗')}
 if(doc.version!=='2.4A'||doc.snapshot_id!==entry.snapshot_id||
    doc.captured_at_utc!==entry.captured_at_utc||
    doc.signal_fingerprint!==entry.signal_fingerprint||
    doc.source_published_at!==null||!Array.isArray(doc.signals)||
    !Array.isArray(doc.summary?.source_price_dates)||
    dayOf(entry)!==doc.summary.source_price_dates[0]||
    doc.summary.source_price_dates.length!==1||
    typeof doc.source_sha256!=='object')
   throw Error('封存內容或來源日期不符合PIT研究格式');
 const found=new Map();
 for(const signal of doc.signals){
  const id=signal.stock_id;
  if(!ID.test(id||'')||found.has(id))throw Error('封存訊號股票身分缺漏或重複');
  if(signal.price_asof!==dayOf(entry)||signal.flow_asof!==dayOf(entry)||
     !day(signal.holder_asof)||signal.holder_asof>dayOf(entry))
    throw Error('封存價格、法人與集保日期不一致');
  found.set(id,signal);
 }
 return {entry,signals:found,date:dayOf(entry),captured:doc.captured_at_utc,
   sourceSha256:doc.source_sha256,
   publicationVerified:false,byteVerified:true};
}
function state(signal){
 if(!signal)return {kind:'not_in_archive',rank:'未見於封存候選',tech:'無候選可核對',
   holder:'無候選可核對',holderDate:'—',flow:'未封存逐筆淨買超'};
 const ranked=signal.rank_status==='可排名';
 const tech=signal.technical_data_status==='可驗證'&&
   signal.technical_status==='三項確認'&&signal.technical_confirmed_count==='3';
 const techKnown=signal.technical_data_status==='可驗證'&&
   ['0','1','2','3'].includes(String(signal.technical_confirmed_count));
 const holder=signal.holder_structure||'尚未判定';
 return {kind:ranked?'candidate':'unranked',
   rank:ranked?'當次可排名':'當次未納入',
   tech:techKnown?(tech?'技術三確認':'技術未達三確認'):'技術資料不足',
   techCount:techKnown?signal.technical_confirmed_count:'—',
   holder,holderDate:signal.holder_asof||'—',
   flow:'未封存外資／投信原始股數；不可推論法人同買',
   score:ranked?signal.chip_strength_score:'—',rankNumber:ranked?signal.chip_strength_rank:'—'};
}
function compare(before,after,stockIds){
 if(!before||!after||!before.byteVerified||!after.byteVerified)throw Error('兩份快照均須SHA256驗證');
 if(before.date>=after.date)throw Error('必須先選較早交易日，再選較晚交易日');
 if(!Array.isArray(stockIds))throw Error('自選代號清單格式不正確');
 const result=[];
 for(const id of [...new Set(stockIds)]){
  if(!ID.test(id))continue;
  const a=before.signals.get(id),b=after.signals.get(id);
  const old=state(a),now=state(b);
  let change;
  if(!a&&!b)change='兩期均未列入封存候選';
  else if(!a&&b)change='新出現在封存候選（非新買進訊號）';
  else if(a&&!b)change='本期未見封存候選（不能判定持股下降）';
  else{
   const fields=['rank','tech','holder'];
   change=fields.every(k=>old[k]===now[k])?'主要觀察狀態相同':'主要觀察狀態改變';
  }
  const updated=a&&b?a.holder_asof!==b.holder_asof:null;
  const caution=a&&b&&a.holder_asof===b.holder_asof?
   '兩期集保資料日期相同，不得解讀為新一週持股變化':
   '大戶封存為每週觀察；變化非已驗證的官方首次公布時分';
  result.push({id,name:b?.stock_name||a?.stock_name||'無封存名稱',
   before:old,after:now,change,holderUpdated:updated,holderCaution:caution,
   firstCapture:before.captured,lastCapture:after.captured,
   eligibleWinRate:false});
 }
 return {firstDate:before.date,secondDate:after.date,firstId:before.entry.snapshot_id,
  secondId:after.entry.snapshot_id,rows:result,verifiedBoth:true,
  limitation:'原始快照SHA256已核實，但觀察首次封存時間不是官方資料首次公布時間；不可據此回測交易勝率或報酬。'};
}
function safe(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function csvCell(v){
 const s=String(v??'');
 return '"'+(/^\s*[=+\-@]/.test(s)||/^[\t\r\n]/.test(s)?"'"+s:s).replace(/"/g,'""')+'"';
}
function toCSV(report){
 if(!report?.verifiedBoth)throw Error('未經雙快照驗證，不得匯出');
 const records=[['股票代號','股票名稱','較早封存日','較晚封存日','較早排行狀態',
  '較晚排行狀態','較早技術','較晚技術','較早大戶結構','較晚大戶結構',
  '較早集保資料日','較晚集保資料日','對照結論','集保週資料限制','更早首次封存UTC','較晚首次封存UTC'],
  ...report.rows.map(r=>[r.id,r.name,report.firstDate,report.secondDate,
   r.before.rank,r.after.rank,r.before.tech,r.after.tech,r.before.holder,r.after.holder,
   r.before.holderDate,r.after.holderDate,r.change,r.holderCaution,r.firstCapture,r.lastCapture])];
 return records.map(r=>r.map(csvCell).join(',')).join('\r\n');
}
const api=Object.freeze({catalog,dayOf,loadSnapshot,state,compare,toCSV,safe});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSWatchHistory30O=api;
})(typeof window!=='undefined'?window:null);
