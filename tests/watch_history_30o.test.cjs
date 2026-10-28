const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
global.window={crypto:crypto.webcrypto};
const H=require('../site/watch_history_30o.js');
const root=path.join(__dirname,'../site/data');
const index=JSON.parse(fs.readFileSync(path.join(root,'signal_archive_index.json'),'utf8'));
const days=H.catalog(index);
assert(days.length>=2,'must have at least two independent source-price dates');
assert(days.length<=index.snapshots.length);
assert.deepEqual(days.map(x=>x.date),[...days.map(x=>x.date)].sort());
assert(days.some(d=>d.versions>1),'duplicate archive sessions should not increase observation dates');
assert(index.snapshots.length>days.length,'archive reruns must not become independent samples');
assert(days.every(d=>d.first.source_price_dates.length===1&&d.date===d.first.source_price_dates[0]));
assert(days.every(d=>d.revisions>=0&&d.versions>=1));
assert.throws(()=>H.catalog({snapshots:[{...days[0].first,snapshot_sha256:'f'}]}),/索引/);
assert.throws(()=>H.catalog({snapshots:[days[0].first,days[0].first]}),/重複/);
const load=async p=>new Uint8Array(fs.readFileSync(path.join(root,p)));
(async()=>{
 const before=await H.loadSnapshot(days.at(-2).first,load);
 const after=await H.loadSnapshot(days.at(-1).first,load);
 assert(before.byteVerified&&after.byteVerified);
 assert.equal(before.publicationVerified,false);
 assert.equal(after.publicationVerified,false);
 assert.equal(before.date,days.at(-2).date);
 assert.equal(after.date,days.at(-1).date);
 for(const id of ['8064','3533','2345']){
  const r=H.compare(before,after,[id]);
  assert.equal(r.rows.length,1);
  assert.equal(r.verifiedBoth,true);
  assert.equal(r.rows[0].eligibleWinRate,false);
  assert(r.rows[0].before.flow.includes('未封存'));
  assert(r.rows[0].after.flow.includes('未封存'));
 }
 const codes=['8064','3533','2345'];
 const report=H.compare(before,after,codes);
 assert.equal(report.rows.length,3);
 assert(report.firstDate<report.secondDate);
 assert(report.rows.every(r=>r.firstCapture===before.captured&&r.lastCapture===after.captured));
 assert.throws(()=>H.compare(after,before,codes),/較早交易日/);
 assert.throws(()=>H.compare({...before,byteVerified:false},after,codes),/SHA256/);
 const empty=H.compare(before,after,['999999']);
 assert.equal(empty.rows[0].change,'兩期均未列入封存候選');
 assert(!empty.rows[0].change.includes('持股下降'));
 for(const r of report.rows){
  if(r.before.kind!=='not_in_archive'&&r.after.kind!=='not_in_archive'&&r.before.holderDate===r.after.holderDate)
   assert(r.holderCaution.includes('不得解讀為新一週'));
 }
 const csv=H.toCSV(report);
 assert(csv.includes('較早封存日')&&csv.includes('較晚封存日'));
 assert(csv.includes('較早集保資料日')&&csv.includes('較晚集保資料日'));
 assert.equal(csv.split('\r\n').length,4);
 assert.throws(()=>H.toCSV({...report,verifiedBoth:false}),/未經/);
 assert(H.toCSV({...report,rows:[{...report.rows[0],name:'=1+1'}]}).includes('"\u0027=1+1"'));
 let broken=()=>load(days.at(-2).first.snapshot_path).then(bytes=>{
  const modified=new Uint8Array(bytes);modified[30]^=0x04;return modified;
 });
 await assert.rejects(()=>H.loadSnapshot(days.at(-2).first,broken),/SHA256/);
 await assert.rejects(()=>H.loadSnapshot({...days.at(-2).first,snapshot_path:'../../index.html'},load),/封存路徑/);
 const clone=JSON.parse(fs.readFileSync(path.join(root,days.at(-2).first.snapshot_path),'utf8'));
 clone.signals[0].flow_asof='2028-01-01';
 const badBytes=new TextEncoder().encode(JSON.stringify(clone));
 const newSha=crypto.createHash('sha256').update(badBytes).digest('hex');
 await assert.rejects(()=>H.loadSnapshot({...days.at(-2).first,snapshot_sha256:newSha},async()=>badBytes),/日期不一致/);
 console.log('PASS 3.0O: '+index.snapshots.length+' archives -> '+days.length+
   ' unique price days; verified two actual source files, isolated stock history, no fake institutional flows');
})().catch(e=>{console.error(e);process.exit(1)});
