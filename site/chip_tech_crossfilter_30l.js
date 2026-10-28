/* TPE-MFDS 3.0L: descriptive chip x technical intersection.
 * Not a backtest, model rating, or verified timestamp of public disclosure.
 * All missing/misaligned source data fail closed.
 */
(function(root){
'use strict';
const MODES=Object.freeze(['all','institution','holders','technical','confluence','review']);
function day(v){
 if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v))return null;
 const d=new Date(v+'T00:00:00Z');
 return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===v?d.getTime():null;
}
function numeric(v){
 if(typeof v!=='string'&&typeof v!=='number')return null;
 if(String(v).trim()==='')return null;
 const n=Number(v);return Number.isFinite(n)?n:null;
}
function evaluate(rank,tech,asofLimit){
 const issues=[];
 if(!rank||typeof rank!=='object'||!(/^\d{4,6}$/.test(String(rank.stock_id||'')))){
  return {id:'',ready:false,flow:false,holders:false,technical:false,confluence:false,
    issues:['股票代號或排行資料缺漏']};
 }
 const id=String(rank.stock_id),price=day(rank.price_asof),flowDate=day(rank.flow_asof),
       holderDate=day(rank.holder_asof),cutoff=asofLimit?day(asofLimit):null;
 const ready=rank.rank_status==='可排名'&&rank.chip_status==='matched'&&
   (rank.market==='上市'||rank.market==='上櫃')&&price!==null &&
   cutoff!==null && price===cutoff;
 if(!ready)issues.push('普通股候選排行或行情日期不合格');
 const flowAligned=ready&&flowDate===price;
 if(!flowAligned)issues.push('法人日與收盤日未對齊');
 const holderAligned=ready&&holderDate!==null&&holderDate<=price&&
   (price-holderDate)<=14*86400000;
 if(!holderAligned)issues.push('集保週資料逾期、缺漏或晚於價格日');
 const institution=flowAligned&&numeric(rank.foreign_5d_shares)>0&&
   numeric(rank.trust_5d_shares)>0;
 if(!institution)issues.push('外資與投信近5日未同時淨買超或資料不足');
 // 400張以上是包含1000張的累積級距，必須改用不重疊的400-999與1000+。
 const holders=holderAligned&&numeric(rank.mid400_999_4w_pp)>0&&
   numeric(rank.large1000_4w_pp)>0;
 if(!holders)issues.push('400–999張與1000張以上持股未同步增加或資料不足');
 const sameTech=!!tech&&tech.stock_id===id&&tech.data_status==='可驗證'&&
   day(tech.price_asof)===price&&day(tech.flow_asof)===price&&
   day(tech.holder_asof)===holderDate&&price!==null;
 const technical=ready&&sameTech&&numeric(tech.technical_confirmed_count)===3&&
   tech.technical_status==='三項確認';
 if(!technical)issues.push('技術三確認來源不完整或日期不一致');
 return {
  id,ready,flow:institution,holders,technical,confluence:institution&&holders&&technical,
  price_asof:rank.price_asof,flow_asof:rank.flow_asof,holder_asof:rank.holder_asof,
  holder_lag_days:holderAligned?Math.round((price-holderDate)/86400000):null,
  issues,
 };
}
function screen(rankRows,techRows,opts={}){
 if(!Array.isArray(rankRows)||!Array.isArray(techRows))throw Error('資料來源格式不正確');
 const mode=opts.mode||'all';
 if(!MODES.includes(mode))throw Error('未知交叉篩選條件');
 if(opts.asofLimit&&!day(opts.asofLimit))throw Error('最新研究日格式不正確');
 const tech=new Map();
 for(const row of techRows){
  if(row?.stock_id){
   if(tech.has(row.stock_id))throw Error('技術資料重複股票代號：'+row.stock_id);
   tech.set(row.stock_id,row);
  }
 }
 const results=[],ids=new Set();
 for(const row of rankRows){
  if(!row?.stock_id)continue;
  if(ids.has(row.stock_id))throw Error('排行資料重複股票代號：'+row.stock_id);
  ids.add(row.stock_id);
  if(row.rank_status!=='可排名')continue;
  if(opts.market&&opts.market!=='全部'&&row.market!==opts.market)continue;
  const q=String(opts.query||'').trim().toLowerCase();
  if(q&&!String([row.stock_id,row.stock_name,row.sector].join(' ')).toLowerCase().includes(q))continue;
  const check=evaluate(row,tech.get(row.stock_id),opts.asofLimit);
  if(mode==='institution'&&!check.flow||mode==='holders'&&!check.holders||
     mode==='technical'&&!check.technical||mode==='confluence'&&!check.confluence||
     mode==='review'&&check.confluence)continue;
  results.push({row,tech:tech.get(row.stock_id)||{},check});
 }
 results.sort((a,b)=>{
  const an=numeric(a.row.chip_strength_rank),bn=numeric(b.row.chip_strength_rank);
  return (an??Number.MAX_SAFE_INTEGER)-(bn??Number.MAX_SAFE_INTEGER)||
    a.row.stock_id.localeCompare(b.row.stock_id);
 });
 return results;
}
const CSV_KEYS=Object.freeze([
 ['stock_id','股票代號'],['stock_name','股票名稱'],['market','市場'],
 ['price_asof','行情資料日'],['flow_asof','法人資料日'],['holder_asof','集保資料日'],
 ['foreign_5d_shares','外資5日股數'],['trust_5d_shares','投信5日股數'],
 ['mid400_999_4w_pp','400-999張4週變動pp'],['large1000_4w_pp','1000張以上4週變動pp'],
 ['chip_strength_rank','籌碼觀察名次']
]);
function csvCell(x){
 const raw=String(x??'');
 // Spreadsheet formula injection can be hidden behind whitespace/control bytes.
 const guarded=/^[\s]*[=+\-@]/.test(raw)||/^[\t\r\n]/.test(raw)?"'"+raw:raw;
 return '"'+guarded.replace(/"/g,'""')+'"';
}
function toCSV(items){
 if(!Array.isArray(items))throw Error('交叉匯出結果格式不正確');
 const head=[...CSV_KEYS.map(x=>x[1]),'法人同買','兩級距大戶同增','技術三確認','三面交集','資料問題'];
 const lines=[head.map(csvCell).join(',')];
 for(const entry of items){
  const r=entry?.row,c=entry?.check;
  if(!r||!c)throw Error('來源尚未通過交叉核對');
  const fields=[...CSV_KEYS.map(([name])=>r[name]??''),c.flow?'符合':'未通過',
    c.holders?'符合':'未通過',c.technical?'符合':'未通過',
    c.confluence?'符合':'未通過',c.issues.join('；')];
  lines.push(fields.map(csvCell).join(','));
 }
 return lines.join('\r\n');
}
const api=Object.freeze({evaluate,screen,MODES,day,toCSV});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSChipTechCrossfilter=api;
})(typeof window!=='undefined'?window:null);
