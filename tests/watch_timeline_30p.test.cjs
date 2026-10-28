const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
global.window={crypto:crypto.webcrypto};
const H=require('../site/watch_history_30o.js');
global.window.MFDSWatchHistory30O=H;
const P=require('../site/watch_timeline_30p.js');
const root=path.join(__dirname,'../site/data');
const index=JSON.parse(fs.readFileSync(path.join(root,'signal_archive_index.json'),'utf8'));
const days=H.catalog(index);
const read=async p=>new Uint8Array(fs.readFileSync(path.join(root,p)));
(async()=>{
 assert(days.length>=2&&days.length<=P.MAX_DAYS,'actual archive supports a bounded chronology');
 const docs=[];
 for(const x of days)docs.push(await H.loadSnapshot(x.first,read));
 const result=P.build(docs,'8064');
 assert.equal(result.stock_id,'8064');
 assert.equal(result.verifiedAll,true);
 assert.equal(result.prediction_enabled,false);
 assert.equal(result.canEstimateReturns,false);
 assert.equal(result.rows.length,days.length);
 assert.deepEqual(result.rows.map(r=>r.date),days.map(x=>x.date));
 assert(result.rows.every(r=>r.verified&&r.captured===docs.find(d=>d.date===r.date).captured));
 assert(result.rows.every(r=>r.publisherClockVerified===false));
 assert.equal(result.rows[0].kind,'baseline');
 assert(result.rows[0].holderNote.includes('首次封存'));
 assert(result.limit.includes('不代表所有交易日'));
 assert(result.limit.includes('沒有逐股外資'));
 assert(result.changed_days<=days.length-1);
 assert(result.new_holder_week_days<=days.length-1);
 for(const mode of P.MODES){
  const subset=P.subset(result,mode);
  assert(subset.every(r=>result.rows.includes(r)));
  const html=P.render(result,mode);
  assert(P.subset(result,mode).length?html.includes('首次封存UTC'):html.includes('所選分類沒有封存觀察'));
  assert(html.includes('封存價格日'));
  const csv=P.toCSV(result,mode);
  assert(csv.includes('集保更新分類')&&csv.includes('官方首次公布時間'));
  assert(csv.includes('未核實'));
  assert(!csv.includes('預測勝率80%'));
 }
 assert.throws(()=>P.subset(result,'trading_signals'),/篩選方式/);
 assert.throws(()=>P.build([docs[1],docs[0]],'8064'),/重複或非時間遞增/);
 assert.throws(()=>P.build([docs[0],docs[0]],'8064'),/重複或非時間遞增/);
 assert.throws(()=>P.build([docs[0]],'8064'),/2至90/);
 assert.throws(()=>P.build(docs,'DEMO1'),/股票代號/);
 assert.throws(()=>P.build([{...docs[0],byteVerified:false},docs[1]],'8064'),/SHA256/);
 assert.throws(()=>P.build([{...docs[0],publicationVerified:true},docs[1]],'8064'),/SHA256/);
 assert.throws(()=>P.toCSV({...result,verifiedAll:false}),/尚未驗證/);
 const bad=structuredClone(result);
 bad.rows[0].name='=1+1';bad.name='=HYPERLINK("xx")';
 assert(P.toCSV(bad).includes('"\'=HYPERLINK(""xx"")"'));
 // A controlled synthetic sequence exercises data-source rollover and traps:
 // same weekly source date is NOT a new holder observation, even when its
 // reprocessed label changes; backwards holder date must be marked invalid.
 const id='2393';
 const seed=docs.find(x=>x.signals.has(id));
 assert(seed,'real archive has a stock with verified holder and tech clocks');
 const original=seed.signals.get(id);
 const mk=(date,captured,holderDate,holder,tech,rank='可排名')=>{
  const signal={...original,stock_id:id,stock_name:'億光',
   holder_asof:holderDate,holder_structure:holder,rank_status:rank,
   technical_data_status:'可驗證',technical_status:tech===3?'三項確認':'部分確認',
   technical_confirmed_count:String(tech)};
  const d={date,captured,entry:{...seed.entry,snapshot_id:'test-'+date,
    source_price_dates:[date]},byteVerified:true,publicationVerified:false,
    signals:new Map([[id,signal]])};
  return d;
 };
 const a=mk('2026-10-19','2026-10-20T00:01:00Z','2026-10-16','雙級距增加',2);
 const b=mk('2026-10-20','2026-10-21T00:01:00Z','2026-10-16','雙級距增加',3);
 const c=mk('2026-10-21','2026-10-22T00:01:00Z','2026-10-16','持股結構分歧',3);
 const d=mk('2026-10-22','2026-10-23T00:01:00Z','2026-10-22','持股結構分歧',3);
 const e=mk('2026-10-23','2026-10-24T00:01:00Z','2026-10-21','雙級距增加',3);
 const synt=P.build([a,b,c,d,e],id);
 assert.equal(synt.rows[1].holderUpdate,'same_week');
 assert(synt.rows[1].changes.includes('技術確認改變'));
 assert.equal(synt.rows[2].holderUpdate,'same_week_conflict');
 assert(synt.rows[2].holderNote.includes('不得解讀為新持股變化'));
 assert(!synt.rows[2].changes.includes('大戶結構分類改變'));
 assert.equal(synt.rows[3].holderUpdate,'new_week');
 assert.equal(synt.rows[3].kind,'holder_refreshed');
 assert.equal(synt.rows[4].holderUpdate,'regressed');
 assert(synt.rows[4].holderNote.includes('禁止推論'));
 const absent=mk('2026-10-24','2026-10-25T00:01:00Z','2026-10-22','雙級距增加',3);
 absent.signals=new Map();
 const newList=P.build([a,absent],id);
 assert.equal(newList.rows[1].kind,'missing_candidate');
 assert(newList.rows[1].label.includes('未見'));
 assert.throws(()=>P.build([absent,a],id),/重複或非時間遞增/);
 const newEntry=P.build([absent,{...a,date:'2026-10-25',captured:'2026-10-26T00:01:00Z',
  entry:{...a.entry,source_price_dates:['2026-10-25']}}],id);
 assert.equal(newEntry.rows[1].kind,'new_candidate');
 console.log('PASS 3.0P: '+index.snapshots.length+' archive versions / '+days.length+
 ' unique price days; verified full SHA chronology, actual 8064 and synthetic weekly-date edge cases');
})().catch(e=>{console.error(e);process.exit(1)});
