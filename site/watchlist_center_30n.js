/* TPE-MFDS 3.0N · browser-only watchlist evidence center.
   Source timestamps are observation dates, not authenticated public release times.
   No trades, live monitoring, calibrated probabilities or user positions stored.
*/
(function(root){
'use strict';
const STOCK_RE=/^\d{4,6}$/,MAX=100,MODES=['all','confluence','review'];
function ids(raw){
 if(!Array.isArray(raw))return [];
 return [...new Set(raw.filter(x=>typeof x==='string'&&STOCK_RE.test(x)))].slice(0,MAX);
}
function add(raw,code){
 const current=ids(raw);
 if(typeof code!=='string'||!STOCK_RE.test(code.trim()))throw Error('請輸入4至6碼數字股票代號');
 const id=code.trim();
 if(current.includes(id))return current;
 if(current.length>=MAX)throw Error('最多可追蹤100檔股票');
 return [...current,id];
}
function index(rows){
 if(!Array.isArray(rows))return new Map();
 const map=new Map();
 for(const item of rows){if(!item?.stock_id)continue;
  const code=String(item.stock_id);
  if(map.has(code))throw Error('研究來源存在重複股票代號：'+code);
  map.set(code,item);
 }
 return map;
}
function build(codes,context){
 if(!context||typeof context!=='object'||typeof context.brief!=='function')
  throw Error('缺少可信的逐股資料核對引擎');
 const stockIds=ids(codes);
 const official=context.official||{};
 const priceDate=official.display_date||'';
 const sourceKeys=['rank','chip','tech','factor','revenue','risk','valuation','income'];
 const lookups={},loaded={};
 for(const key of sourceKeys){
  lookups[key]=index(context.sources?.[key]);
  loaded[key]=Array.isArray(context.sources?.[key]);
 }
 const quotes=index(context.quoteMode==='official'?context.quotes:[]);
 const records=[];
 for(const id of stockIds){
  const sources=Object.fromEntries(sourceKeys.map(k=>[k,lookups[k].get(id)||null]));
  const observed=[sources.factor,sources.rank,sources.tech,sources.revenue,
    sources.risk,context.names?.[id],quotes.get(id)];
  const n=observed.find(v=>v?.stock_name)?.stock_name||'名稱尚待核對';
  const check=context.brief({stockId:id,stockName:n,priceDate,sources,loaded,
    crossCheck:context.crossCheck});
  const quote=quotes.get(id);
  const currentPrice=quote&&quote.asof===priceDate&&Number.isFinite(Number(quote.close))&&
    Number(quote.close)>0 ? Number(quote.close):null;
  const first=check.cards.slice(0,3);
  const outstanding=first.filter(c=>!c.usable).length;
  records.push({
   id,name:String(n),price:currentPrice,price_asof:currentPrice===null?'—':priceDate,
   price_status:currentPrice===null?'缺少當次官方行情':'當次官方收盤',
   flow:first[0],holder:first[1],technical:first[2],revenue:check.cards[3],
   three_axes:check.cross==='三面條件描述性符合',
   three_label:check.cross,detail:check,
   urgent_review:outstanding>0,unverified_dimensions:outstanding,
   factor_verified:check.model.verified_factors,
   source_date:priceDate||'—',
  });
 }
 return {
  records,stock_count:records.length,
  three_axes_count:records.filter(r=>r.three_axes).length,
  data_review_count:records.filter(r=>r.urgent_review).length,
  official_price_count:records.filter(r=>r.price!==null).length,
  source_price_asof:priceDate||'—',
  source_loaded:sourceKeys.filter(k=>loaded[k]).length,
  source_expected:sourceKeys.length,
  probability_enabled:false,
  warning:'本機自選代號不等於持股；結果為封存資料的描述性觀察，並非即時訊號、獲利預測或已校準勝率。',
 };
}
function view(report,{mode='all',query='',sort='manual'}={}){
 if(!report||!Array.isArray(report.records)||!MODES.includes(mode))
  throw Error('自選股篩選參數不正確');
 const q=String(query).trim().toLowerCase();
 const rows=report.records.filter(r=>
   (!q||(r.id+' '+r.name).toLowerCase().includes(q))&&
   (mode==='all'||mode==='confluence'&&r.three_axes||mode==='review'&&r.urgent_review));
 if(sort==='code')rows.sort((a,b)=>a.id.localeCompare(b.id));
 else if(sort==='review')rows.sort((a,b)=>b.unverified_dimensions-a.unverified_dimensions||a.id.localeCompare(b.id));
 else if(sort!=='manual')throw Error('未知自選股排序');
 return rows;
}
function cell(v){
 const str=String(v??'');
 const safe=/^\s*[=+\-@]/.test(str)||/^[\t\r\n]/.test(str)?"'"+str:str;
 return '"'+safe.replace(/"/g,'""')+'"';
}
function toCSV(records){
 if(!Array.isArray(records))throw Error('匯出內容不是股票清單');
 const rows=[['股票代號','股票名稱','官方收盤價','股價資料日','法人近5日','法人資料日',
   '大戶持股4週變化','集保資料日','技術三確認','技術資料日',
   '營收年增','營收資料日','三面交集','待核對條件數','來源價格基準日','研究限制']];
 for(const item of records){
  if(!item?.id||!STOCK_RE.test(item.id)||item.detail?.probability_enabled!==false)
   throw Error('未核實來源資料不得匯出');
  rows.push([item.id,item.name,item.price??'',item.price_asof,
   item.flow.value,item.flow.observed_at,item.holder.value,item.holder.observed_at,
   item.technical.value,item.technical.observed_at,item.revenue.value,item.revenue.observed_at,
   item.three_label,item.unverified_dimensions,item.source_date,item.detail.caution]);
 }
 return rows.map(row=>row.map(cell).join(',')).join('\r\n');
}

function escapeHtml(v){
 return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function render(report,opts={}){
 const selected=ids(opts.codes||[]);
 const mode=opts.mode||'all',sort=opts.sort||'manual',query=opts.query||'';
 const pending=!!opts.loading,failed=String(opts.error||'');
 const count=selected.length;
 const visible=report&&!failed?view(report,{mode,sort,query}):[];
 const status=(c)=>'<small>'+escapeHtml(c.observed_at)+' · '+escapeHtml(c.status)+'</small>';
 const field=(c)=>(c.usable?escapeHtml(c.value):'<span class="r-watch-dim">—</span>')+status(c);
 const tableRows=visible.map(r=>'<tr data-watch-stock="'+escapeHtml(r.id)+'">'+
   '<td><strong>'+escapeHtml(r.id)+'</strong><div class="hint">'+escapeHtml(r.name)+'</div></td>'+
   '<td>'+(r.price===null?'—':r.price.toLocaleString('zh-TW',{maximumFractionDigits:2}))+
     '<small>'+escapeHtml(r.price_asof)+'</small></td>'+
   '<td>'+field(r.flow)+'</td><td>'+field(r.holder)+'</td>'+
   '<td>'+field(r.technical)+'</td><td>'+field(r.revenue)+'</td>'+
   '<td><span class="chip '+(r.three_axes?'real':'weak')+'">'+escapeHtml(r.three_label)+'</span>'+
   '<small>'+(r.unverified_dimensions?'關鍵資料未核對 '+r.unverified_dimensions+' 項':'來源日期已對齊；並非正式公告時分認證')+'</small></td>'+
   '<td><div class="r-watch-actions"><button type="button" class="btn mini" data-action="watchResearch" data-id="'+escapeHtml(r.id)+'">研究</button>'+
   '<button type="button" class="btn mini" data-action="watch" data-id="'+escapeHtml(r.id)+'">移除</button></div></td></tr>').join('');
 const summary=report&&count?'<div class="r-watch-metrics">'+
  '<div><small>追蹤股票</small><b>'+report.stock_count+'</b><span>僅儲存代號；不保存持股與成本</span></div>'+
  '<div><small>三面交集</small><b>'+(report.source_loaded>=3?report.three_axes_count:'—')+'</b><span>描述性資料，並非勝率</span></div>'+
  '<div><small>關鍵資料待核對</small><b>'+(report.source_loaded>=3?report.data_review_count:'—')+'</b><span>法人、大戶、技術缺口</span></div>'+
  '<div><small>當次官方收盤價</small><b>'+(opts.quoteMode==='official'?report.official_price_count:'—')+'</b><span>示範行情絕不混用</span></div>'+
  '</div>':'';
 const optionHtml=(options,current)=>options.map(x=>'<option value="'+x[0]+'"'+(x[0]===current?' selected':'')+'>'+x[1]+'</option>').join('');
 return '<div class="r-watch-intro"><div class="r-eyebrow">WATCHLIST STUDIO · 3.0N</div>'+
   '<h2>自選股 · 研究追蹤中心</h2>'+
   '<p>法人、集保、技術與基本面一次比較；僅為封存資料的來源觀察，不提供即時買賣訊號與預測勝率。</p></div>'+
  '<section class="card r-watch-main" aria-label="3.0N自選股追蹤中心">'+
  '<div class="r-section-title"><div><h3>我的研究名單</h3>'+
  '<p>自選代號只保存在本機瀏覽器；不記錄持股與買賣成本，無跨裝置同步。</p></div>'+
  '<span class="chip">'+count+'／'+MAX+' 檔</span></div>'+
  '<form id="r-watch-add-form" class="r-watch-add"><label for="r-watch-add-code">加入股票代號</label>'+
  '<input id="r-watch-add-code" class="field" inputmode="numeric" autocomplete="off" maxlength="6" placeholder="例如 8064" aria-label="加入自選股票">'+
  '<button class="btn btn-primary" type="submit">＋ 加入追蹤</button></form>'+
  (pending?'<p class="r-watch-notice" role="status">研究來源正在讀取；尚未取得資料不能視為零檔符合。</p>':'')+
  (failed?'<p class="r-watch-notice" role="alert">自選股來源核對失敗：'+escapeHtml(failed)+'</p>':'')+
  (report&&count&&report.source_loaded<report.source_expected?
   '<p class="r-watch-notice" role="status">已取得 '+report.source_loaded+'／'+report.source_expected+
   ' 類研究來源；缺漏不會被當成符合條件。</p>':'')+
  '<div class="r-watch-asof"><span>價格基準日：'+escapeHtml(report?.source_price_asof||'—')+'</span>'+
  '<span>法人與集保持股日期各自顯示</span>'+
  '<button type="button" class="btn mini" data-action="watchRefresh">↻ 更新研究資料</button></div>'+
  summary+
  '<div class="r-watch-tools"><label for="r-watch-query">搜尋'+
  '<input id="r-watch-query" class="field" value="'+escapeHtml(query)+'" placeholder="代號或名稱"></label>'+
  '<label for="r-watch-mode">狀態<select id="r-watch-mode" class="field">'+
  optionHtml([['all','全部自選'],['confluence','三面交集'],['review','關鍵資料待核對']],mode)+'</select></label>'+
  '<label for="r-watch-sort">排序<select id="r-watch-sort" class="field">'+
  optionHtml([['manual','加入順序'],['code','股票代號'],['review','缺口優先']],sort)+'</select></label>'+
  '<button type="button" class="btn mini" id="r-watch-export"'+(!report||!count?' disabled':'')+'>↓ 匯出比較 CSV</button></div>'+
  (!count?'<div class="r-empty">尚無自選股。輸入股票代號，即可開始建立研究清單。</div>':
   failed?'<div class="r-empty">來源內容異常，已停止本次比較；請先更新資料或查看資料品質。</div>':
   pending?'<div class="r-empty">資料讀取中，暫不列出未核實研究結果。</div>':
   !visible.length?'<div class="r-empty">沒有符合目前條件的股票；可切回「全部自選」。</div>':
   '<div class="table-wrap"><table class="data-table r-table r-watch-table"><thead>'+
   '<tr><th>股票</th><th>官方收盤價</th><th>法人近5日</th><th>大戶4週</th>'+
   '<th>技術</th><th>月營收</th><th>研究狀態</th><th>操作</th></tr></thead>'+
   '<tbody>'+tableRows+'</tbody></table></div>')+
  '<p class="r-watch-foot">'+escapeHtml(report?.warning||'尚無可核實研究來源。')+
  ' 股價、法人、集保、技術及財務日期不一定一致；未驗證績效不能顯示勝率。</p></section>';
}

const api=Object.freeze({MAX,ids,add,index,build,view,toCSV,render});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSWatchlist30N=api;
})(typeof window!=='undefined'?window:null);
