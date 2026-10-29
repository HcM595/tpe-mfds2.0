#!/usr/bin/env python3
"""3.0R: Cross-check 3.0Q's original-input lineage and archive-day coverage.

Distinguish: a verified first-captured archive, an *unverified possible*
trading day, and a reported extraordinary market closure whose official
original is not yet archived. A non-candidate security is NOT missing data.
Never convert raw historical observations into trades or measured win rate.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
import archive_official_closure_30u as original_30u

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
VERSION='3.0R'
COLUMNS=('date','market','status','archived_candidate_rows','official_closed','unverified_closure_lead','reason')
STOCK_COLUMNS=('stock_id','stock_name','market','first_candidate_date','last_candidate_date',
 'first_captured_candidate_days','total_archived_price_days','other_archived_days_not_in_candidates',
 'flow_5d_source_rows','holder_4w_source_rows','technical_source_rows',
 'first_publication_time_verified','verified_trade_samples','note')
MARKETS=('上市','上櫃')
HEX=re.compile(r'^[0-9a-f]{64}$')
ID=re.compile(r'^\d{4,6}$')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def get_json(path):
 obj=json.loads(path.read_text(encoding='utf-8-sig'))
 if not isinstance(obj,dict):raise ValueError(path.name+' must contain an object')
 return obj
def date(value):
 if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
  raise ValueError('date invalid: '+str(value))
 return dt.date.fromisoformat(value)
def read_rows(raw):
 rd=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
 if not rd.fieldnames or len(rd.fieldnames)!=len(set(rd.fieldnames)):
  raise ValueError('missing or duplicated CSV header')
 required={'stock_id','price_session','first_snapshot_id','first_snapshot_sha256',
           'first_captured_at_utc','rank_source_sha256','chip_source_sha256',
           'tech_source_sha256','raw_input_verified','flow_5d_observation_usable',
           'holder_4w_observation_usable','tech_observation_usable',
           'first_publication_time_verified','eligible_for_historical_trade'}
 if not required.issubset(rd.fieldnames):raise ValueError('3.0Q required fields missing')
 return list(rd)
def verify(data):
 """No trust in counts, filenames, or flags without consistent source identity."""
 index=get_json(data/'signal_archive_index.json')
 meta=get_json(data/'historical_evidence_meta_30q.json')
 csv_raw=(data/'historical_evidence_30q.csv').read_bytes()
 rows=read_rows(csv_raw)
 if meta.get('version')!='3.0Q' or meta.get('status')!='verified_raw_archives_model_blocked':
  raise ValueError('3.0Q provenance meta not ready')
 if not isinstance(index.get('snapshots'),list) or \
    len(index['snapshots'])!=index.get('snapshots_total'):
  raise ValueError('2.4A archive index count invalid')
 if meta.get('snapshots_in_index')!=index['snapshots_total']:
  raise ValueError('3.0Q not regenerated for the current source archive index')
 refs=meta.get('snapshot_reference')
 if not isinstance(refs,list) or len(refs)!=meta.get('unique_first_captured_price_sessions'):
  raise ValueError('3.0Q independent first-capture reference mismatch')
 index_refs={x.get('snapshot_id'):x for x in index['snapshots']}
 expected={}
 for ref in refs:
  d=ref.get('price_session')
  date(d)
  if d in expected:raise ValueError('duplicate 3.0Q price session')
  sid=ref.get('snapshot_id')
  idx=index_refs.get(sid)
  if not idx or idx.get('source_price_dates')!=[d] or \
     idx.get('snapshot_sha256')!=ref.get('snapshot_sha256') or \
     idx.get('captured_at_utc')!=ref.get('captured_at_utc') or \
     not HEX.fullmatch(ref.get('snapshot_sha256','')):
   raise ValueError('3.0Q first-capture reference does not match immutable index')
  for other in index['snapshots']:
   if other.get('source_price_dates')==[d] and \
      (other.get('captured_at_utc',''),other.get('snapshot_id',''))<\
      (ref['captured_at_utc'],sid):
    raise ValueError('3.0Q did not choose earliest dated archive')
  expected[d]=ref
 if not expected or len(rows)!=meta.get('stock_session_observations'):
  raise ValueError('3.0Q row count mismatch')
 if list(expected)!=sorted(expected):raise ValueError('3.0Q sessions out of order')
 if meta.get('first_price_session')!=min(expected) or meta.get('last_price_session')!=max(expected):
  raise ValueError('3.0Q first and last dates differ from archive references')
 uniq=set()
 by_day=Counter()
 by_market=Counter()
 by_stock=defaultdict(list)
 source_hashes={}
 usable=Counter()
 for r in rows:
  d=r.get('price_session','')
  code=r.get('stock_id','')
  if d not in expected or not ID.fullmatch(code):raise ValueError('invalid stock or archive day')
  ident=(d,code)
  if ident in uniq:raise ValueError('duplicate stock and price date')
  uniq.add(ident)
  ref=expected[d]
  if r.get('first_snapshot_id')!=ref['snapshot_id'] or \
     r.get('first_snapshot_sha256')!=ref['snapshot_sha256'] or \
     r.get('first_captured_at_utc')!=ref['captured_at_utc']:
   raise ValueError('historical stock row not bound to first-capture record')
  if r.get('raw_input_verified')!='true' or \
     r.get('first_publication_time_verified')!='false' or \
     r.get('eligible_for_historical_trade')!='false':
   raise ValueError('source/publication/trade flags breach provenance rule')
  if not r.get('blocking_reason'):raise ValueError('missing historical eligibility blocker')
  stamps=tuple(r.get(key,'') for key in
   ('rank_source_sha256','chip_source_sha256','tech_source_sha256'))
  if any(not HEX.fullmatch(x) for x in stamps):raise ValueError('missing original input SHA')
  if d in source_hashes and source_hashes[d]!=stamps:
   raise ValueError('multiple original raw source versions for one first capture')
  source_hashes[d]=stamps
  capture=dt.datetime.fromisoformat(r['first_captured_at_utc'].replace('Z','+00:00'))
  if capture.tzinfo is None or capture.date()<date(d):
   raise ValueError('historical capture clock precedes observed price session')
  for col,numbercol,flag in (
    ('flow','foreign_5d_shares','flow_5d_observation_usable'),
    ('holder','large400_4w_pp','holder_4w_observation_usable'),
    ('tech','technical_confirmed_count','tech_observation_usable')):
   state=r.get(flag)
   if state not in ('true','false'):raise ValueError(flag+' not boolean')
   if state=='false' and r.get(numbercol,'').strip():
    raise ValueError('invalid source row contains a backfilled measurement')
   if state=='true':
    if not r.get(numbercol,'').strip():raise ValueError('valid source row has no raw measurement')
    usable[col]+=1
  if r['flow_5d_observation_usable']=='true':
   if r.get('flow_asof')!=d or not r.get('trust_5d_shares','').strip():
    raise ValueError('institutional row source date/value missing')
  if r['holder_4w_observation_usable']=='true':
   holder_date=date(r.get('holder_asof'))
   if holder_date>date(d) or (date(d)-holder_date).days>14 or not r.get('large1000_4w_pp','').strip():
    raise ValueError('TDCC weekly date/value not trustworthy')
  m=r.get('market')
  if m not in MARKETS:raise ValueError('unrecognized market classification '+str(m))
  by_day[d]+=1
  by_market[(d,m)]+=1
  by_stock[code].append(r)
 for item in meta.get('daily_stock_coverage',[]):
  if by_day[item.get('price_session')]!=item.get('rows'):
   raise ValueError('3.0Q day count disagrees with original CSV')
 if set(by_day)!=set(expected):raise ValueError('some first-captured price days have no rows')
 for key,field in [('flow','eligible_institutional_5d_observations'),
                   ('holder','eligible_holder_4w_observations'),
                   ('tech','eligible_technical_observations')]:
  if usable[key]!=meta.get(field):raise ValueError('3.0Q source completeness count mismatch')
 gate=meta.get('strict_validation',{})
 if gate.get('model_enabled') is not False or gate.get('verified_trade_samples')!=0 or \
    gate.get('certified_win_rate') is not None:
  raise ValueError('unverified performance metric was enabled')
 return {'index':index,'meta':meta,'rows':rows,'csv_sha256':sha(csv_raw),
         'refs':expected,'by_day':by_day,'by_market':by_market,'by_stock':by_stock,
         'verified_sources':dict(usable)}

def coverage(verification,calendar,exceptions,official_doc_events=None):
 if calendar.get('status')!='ok' or calendar.get('years') is None:
  raise ValueError('official calendar missing or invalid')
 start=date(min(verification['refs']))
 end=date(max(verification['refs']))
 closed=set()
 for year in range(start.year,end.year+1):
  src=calendar.get('years',{}).get(str(year))
  if not isinstance(src,dict) or src.get('status')!='twse_official_verified':
   raise ValueError('official TWSE holiday year not verified')
  for x in src.get('closed_dates',[]):closed.add(date(x))
 # Official regular calendar is not itself an official extraordinary closure notice.
 leads=set()
 for r in exceptions:
  if r.get('official_temporary_closure_notice_archived')=='是':continue
  if r.get('market') in MARKETS and r.get('issue'):
   dtday=date(r.get('date'))
   if start<=dtday<=end:leads.add((r['market'],dtday))
 official_doc_events=official_doc_events or set()
 rows=[]
 cursor=start
 while cursor<=end:
  d=cursor.isoformat()
  for market in MARKETS:
   if cursor.weekday()>=5 or cursor in closed:continue
   if (market,d) in official_doc_events:
    if d in verification['refs']:
     raise ValueError('full-market closure conflicts with a claimed first-captured trade date')
    status='verified_original_market_closure'
    why='已核實該現貨市場完整官方原始休市PDF；來源公文發布日不等於本站先知的時間'
   elif d in verification['refs']:
    status='verified_first_capture'
    why='本站確有該價位日首次不可改寫的源檔；不代表整個市場有全體股票訊號'
   elif (market,cursor) in leads:
    status='extraordinary_closure_requires_official_source'
    why='臨時停市有線索但未核對官方原始公告；不可把此日算成市場缺漏或已核實交易日'
   else:
    status='unarchived_possible_session'
    why='官方常規休市表未列此日；仍待核對市場行情及個別臨停，不能直接宣稱漏跑'
   rows.append({'date':d,'market':market,'status':status,
       'archived_candidate_rows':verification['by_market'][(d,market)] if d in verification['refs'] else '',
       'official_closed':str(status=='verified_original_market_closure').lower(),
       'unverified_closure_lead':str((market,cursor) in leads and status!='verified_original_market_closure').lower(),
       'reason':why})
  cursor+=dt.timedelta(days=1)
 return rows

def build_stock_coverage(data):
 n=data['refs'].__len__()
 output=[]
 for code,rows in sorted(data['by_stock'].items()):
  sorted_rows=sorted(rows,key=lambda x:x['price_session'])
  names={x['stock_name'] for x in rows}
  markets={x['market'] for x in rows}
  if len(markets)!=1:raise ValueError('stock market changed across archived candidates')
  output.append({'stock_id':code,'stock_name':sorted_rows[-1]['stock_name'],
     'market':next(iter(markets)),
     'first_candidate_date':sorted_rows[0]['price_session'],
     'last_candidate_date':sorted_rows[-1]['price_session'],
     'first_captured_candidate_days':len(rows),
     'total_archived_price_days':n,
     'other_archived_days_not_in_candidates':n-len(rows),
     'flow_5d_source_rows':sum(x['flow_5d_observation_usable']=='true' for x in rows),
     'holder_4w_source_rows':sum(x['holder_4w_observation_usable']=='true' for x in rows),
     'technical_source_rows':sum(x['tech_observation_usable']=='true' for x in rows),
     'first_publication_time_verified':'false','verified_trade_samples':0,
     'note':'未入候選不等於行情缺漏或股價下跌；僅是已封存候選出現次數。'})
 return output

def write_csv(path,fields,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields)
  writer.writeheader();writer.writerows(rows)

def run(data_dir=DATA,now=None):
 data_dir=Path(data_dir)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('generated time must contain offset')
 check=verify(data_dir)
 cal=get_json(data_dir/'official_session_calendar.json')
 with (data_dir/'market_session_exceptions.csv').open('r',encoding='utf-8-sig',newline='') as f:
  ex=list(csv.DictReader(f))
 official_doc_events=set()
 source_u=data_dir/'official_closure_notice_evidence_30u.json'
 source_u_sha=None
 if source_u.is_file():
  event=get_json(source_u)
  if event.get('version')!='3.0U' or event.get('date')!='2026-10-23':
   raise ValueError('3.0U event manifest version/date is not valid')
  twse=event.get('sources',{}).get('TWSE',{})
  if twse.get('full_original_document_verified') is True:
   if not original_30u.check_local(data_dir,event):
    raise ValueError('TWSE original closure attestation could not be independently verified')
   official_doc_events.add(('上市','2026-10-23'))
  elif twse.get('status')!='official_original_pending':
   raise ValueError('unrecognized 3.0U TWSE original status')
  if event.get('both_cash_markets_official_originals_verified') is not False or \
     event.get('trade_performance_enabled') is not False:
   raise ValueError('3.0U market or performance gate cannot be elevated')
  source_u_sha=sha(source_u.read_bytes())
 sessions=coverage(check,cal,ex,official_doc_events)
 stocks=build_stock_coverage(check)
 status=Counter(x['status'] for x in sessions)
 meta={
   'version':VERSION,'generated_at_utc':now.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),
   'status':'original_sources_verified_no_performance',
   'source_csv_sha256':check['csv_sha256'],
   'source_historical_meta_sha256':sha((data_dir/'historical_evidence_meta_30q.json').read_bytes()),
   'source_archive_index_sha256':sha((data_dir/'signal_archive_index.json').read_bytes()),
   'source_calendar_sha256':sha((data_dir/'official_session_calendar.json').read_bytes()),
   'source_market_exceptions_sha256':sha((data_dir/'market_session_exceptions.csv').read_bytes()),
   'source_official_closure_30u_sha256':source_u_sha,
   'independently_documented_cash_market_closures':sorted([{'market':m,'date':d} for m,d in official_doc_events],key=lambda x:(x['date'],x['market'])),
   'first_archived_price_date':min(check['refs']),
   'last_archived_price_date':max(check['refs']),
   'verified_price_days':len(check['refs']),
   'archived_stock_day_records':len(check['rows']),
   'stocks_appearing_in_any_archive':len(stocks),
   'verified_raw_source_rows':check['verified_sources'],
   'day_market_status_counts':dict(status),
   'coverage_label':'此為首次封存候選資料的價格日覆蓋盤點，非官方確認的逐日交易日曆',
   'candidate_stock_warning':'未列入封存候選不代表該股票沒有行情或法人沒有買賣',
   'coverage_blockers':[
       '上櫃市場行事曆未經獨立官方機器驗證',
       '臨時停市原始官方公告未能全部歸檔',
       '來源價格日不等於官方公布時點',
       '未調整公司行動的價格不可計算績效'],
   'official_publication_time_verified':False,
   'trade_performance_enabled':False,'verified_trade_samples':0,
   'certified_win_rate':None,
   'outputs':['archive_day_coverage_30r.csv','stock_candidate_coverage_30r.csv','archive_coverage_meta_30r.json']
 }
 write_csv(data_dir/'archive_day_coverage_30r.csv',COLUMNS,sessions)
 write_csv(data_dir/'stock_candidate_coverage_30r.csv',STOCK_COLUMNS,stocks)
 (data_dir/'archive_coverage_meta_30r.json').write_text(
    json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0R VERIFIED: '+str(meta['verified_price_days'])+' price dates; '+
       str(meta['archived_stock_day_records'])+' stock-date candidates; official outcome samples 0')
 return meta

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--data-dir',type=Path,default=DATA)
 args=p.parse_args()
 run(args.data_dir)
