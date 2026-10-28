const assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const S=require('../site/research_snapshot_30d.js');
const enc=new TextEncoder();
const bytes=enc.encode('stock_id,price_asof\n8064,2026-10-27\n');
const content=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
async function run(){
 const h=await S.sha256(content,webcrypto.subtle);
 assert.match(h,/^[a-f0-9]{64}$/);
 const sources={};
 for(const [key,name] of Object.entries(S.PATHS)){
  sources[key]={path:'data/'+name,sha256:h,byte_length:bytes.byteLength,row_count:1,unique_stock_count:1};
 }
 const meta={schema_version:'3.0D',snapshot_source_count:8,sources,
   formal_model_scoring_enabled:false,performance_probabilities_enabled:false};
 assert.equal(S.manifestIssue(meta),'');
 assert.equal((await S.verify('factor',content,meta,webcrypto.subtle)).ok,true);
 const modified=enc.encode('stock_id,price_asof\n8064,2026-10-28\n');
 const bad=await S.verify('factor',modified.buffer,meta,webcrypto.subtle);
 assert.equal(bad.ok,false);
 assert.match(bad.reason,/SHA256/);
 assert.equal((await S.verify('factor',enc.encode('a').buffer,meta,webcrypto.subtle)).ok,false);
 assert.equal((await S.verify('factor',content,meta,null)).ok,false);
 assert.notEqual(S.manifestIssue({...meta,snapshot_source_count:7}),'');
 assert.notEqual(S.manifestIssue({...meta,formal_model_scoring_enabled:true}),'');
 assert.notEqual(S.manifestIssue({...meta,sources:{...meta.sources,factor:{...meta.sources.factor,path:'data/evil.csv'}}}),'');
 assert.notEqual(S.manifestIssue({...meta,sources:{...meta.sources,factor:{...meta.sources.factor,sha256:'bad'}}}),'');
 console.log('PASS 3.0D: SHA256 manifest authenticity checks, mixed-version rejection, fail-closed browser capability');
}
run().catch(err=>{console.error(err);process.exitCode=1});
