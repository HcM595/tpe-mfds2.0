/* 3.0X-T descriptive nine-source coverage, independent from predictive scoring. */
(async function(){
 const panel=document.getElementById('coverage-30xt');
 if(!panel)return;
 const status=document.getElementById('coverage-30xt-status');
 const table=document.getElementById('coverage-30xt-rows');
 const text=(v)=>v===null||v===undefined||v===''?'缺漏':String(v);
 const cell=(tr,v)=>{const td=document.createElement('td');td.textContent=text(v);tr.appendChild(td)};
 try{
  const resp=await fetch('./data/source_coverage_30xs.json',{cache:'no-store'});
  if(!resp.ok)throw Error('HTTP '+resp.status);
  const raw=await resp.json();
  if(raw.version!=='3.0X-S'||!Array.isArray(raw.sources)||raw.sources.length!==9||
      raw.prediction_enabled!==false||raw.certified_trade_samples!==0||raw.win_rate!==null)
    throw Error('來源版本或正式績效安全閘門不符合預期');
  const known=new Set(['factor','chip','tech','industry','risk','valuation','revenue','publication','actions']);
  if(new Set(raw.sources.map(s=>s.key)).size!==9||raw.sources.some(s=>!known.has(s.key)))
    throw Error('來源數量或名稱不符');
  table.replaceChildren();
  raw.sources.forEach(s=>{
   const tr=document.createElement('tr');
   [s.key,s.rows,s.unique_stocks,s.missing_asof,s.asof_min,s.asof_max].forEach(v=>cell(tr,v));
   table.appendChild(tr);
  });
  status.textContent='九來源資料筆數已讀取。資料列數不等於獨立交易樣本；正式勝率停用。首次封存交易日：'+text(raw.historical_first_captured_sessions)+'；已認證交易樣本：0。';
 }catch(err){
  table.replaceChildren();
  status.textContent='九來源覆蓋摘要目前無法核對：'+String(err.message||err)+'。不以空白或舊資料冒充正常。';
 }
})();
