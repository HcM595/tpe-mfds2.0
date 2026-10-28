/* 3.0D: verify deployed CSV bytes against the manifest generated in the
 * SAME site/data build. Protects against partial or mixed-version publishing.
 * Does not prove first official publication, investment returns, or history. */
(function(root){
'use strict';
const PATHS={
 factor:'factor_evidence_29a.csv',
 chip:'chip_signals.csv',
 tech:'tech_crosscheck.csv',
 industry:'industry_relative_28c.csv',
 risk:'risk_observations_28d.csv',
 valuation:'f2_valuation_29e.csv',
 revenue:'revenue_snapshot_28c.csv',
 publication:'publication_gate_29o.csv'
};
const HEX=/^[a-f0-9]{64}$/;
function manifestIssue(manifest){
 if(!manifest||manifest.schema_version!=='3.0D'||manifest.snapshot_source_count!==8||
    !manifest.sources||typeof manifest.sources!=='object')return '快照版本或清單結構不符合3.0D';
 if(manifest.formal_model_scoring_enabled!==false||manifest.performance_probabilities_enabled!==false)
    return '來源快照不應宣稱已啟用模型分數或預測';
 for(const [key,name] of Object.entries(PATHS)){
  const x=manifest.sources[key];
  if(!x||x.path!=='data/'+name||!HEX.test(x.sha256||'')||
     !Number.isSafeInteger(x.byte_length)||x.byte_length<1||
     !Number.isSafeInteger(x.row_count)||x.row_count<0||
     x.unique_stock_count>x.row_count)return '資料清單有缺漏或欄位異常：'+key;
 }
 return '';
}
async function sha256(data,subtle){
 const digest=await subtle.digest('SHA-256',data);
 return Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
}
async function verify(key,buffer,manifest,subtle){
 const declared=manifest?.sources?.[key],name=PATHS[key];
 if(!name||!declared||declared.path!=='data/'+name)return {ok:false,reason:'找不到對應來源清單'};
 if(!(buffer instanceof ArrayBuffer))return {ok:false,reason:'來源資料不是完整位元組'};
 if(buffer.byteLength!==declared.byte_length)return {ok:false,reason:'檔案大小與發布快照不符'};
 if(!subtle||typeof subtle.digest!=='function')return {ok:false,reason:'瀏覽器無法使用SHA256校驗'};
 let actual;
 try{actual=await sha256(buffer,subtle)}catch(err){return {ok:false,reason:'SHA256檢查失敗：'+String(err.message||err).slice(0,90)}}
 if(actual!==declared.sha256)return {ok:false,reason:'SHA256與發布快照不符（可能混入不同版本）'};
 return {ok:true,reason:'SHA256與已發布快照一致',sha256:actual};
}
const api={PATHS,manifestIssue,sha256,verify};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.MFDSSnapshot=api;
})(typeof window!=='undefined'?window:null);
