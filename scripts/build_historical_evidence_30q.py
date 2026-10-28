#!/usr/bin/env python3
"""3.0Q — recover *already archived* raw stock evidence, without backdating.

Prior 2.4A snapshots retained gzip copies of chip_rank, chip_signals and
tech_crosscheck. 3.0O/P read the summary instead of those raw columns, so their
historical flow/holder changes looked permanently unavailable. This builder
recovers the actual historical as-captured bytes, verifies BOTH manifest and
input SHA256, and publishes one conservative first-capture record per price
session and stock. It does NOT pretend older backfilled rows were public or
collected at their historical price date.

The formal validation is a fail-closed eligibility audit, NOT a model fit.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
UTC=dt.timezone.utc
VERSION='3.0Q'
FILES=('chip_rank.csv','chip_signals.csv','tech_crosscheck.csv','official_snapshot.csv')
COLS=[
 'stock_id','stock_name','market','price_session','first_captured_at_utc',
 'first_snapshot_id','first_snapshot_sha256','rank_source_sha256',
 'chip_source_sha256','tech_source_sha256',
 'rank_status','chip_strength_rank','chip_strength_score','close_unadjusted',
 'flow_asof','holder_asof','foreign_5d_shares','trust_5d_shares',
 'large400_4w_pp','large1000_4w_pp','mid400_999_4w_pp',
 'chip_status','technical_status','technical_confirmed_count',
 'tech_data_status','latest_history_date',
 'raw_input_verified','flow_5d_observation_usable','holder_4w_observation_usable',
 'tech_observation_usable','first_publication_time_verified',
 'eligible_for_historical_trade','blocking_reason']
GATE_CHECKS=(
 ('historical_actions','historical_corporate_actions_complete'),
 ('adjusted_ohlc','adjusted_ohlc_verified'),
 ('publication_clock','source_publication_times_verified'),
 ('independent_outcomes','sample_independence_verified'),
)
PIT_SOURCE_NOTE='本站首次封存時間不等於官方首次公布；過去CSV有資料日期但不能證明當時可取得'


def digest(data):
 return hashlib.sha256(data).hexdigest()

def load_json(raw):
 obj=json.loads(raw.decode('utf-8-sig'))
 if not isinstance(obj,dict):raise ValueError('JSON must be object')
 return obj

def iso_date(s):
 if not isinstance(s,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',s):return None
 try:return dt.date.fromisoformat(s)
 except ValueError:return None

def utc_instant(s):
 if not isinstance(s,str):return None
 try:
  value=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
  return value.astimezone(UTC) if value.tzinfo else None
 except ValueError:return None

def parse_csv(raw,filename):
 reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
 if not reader.fieldnames or 'stock_id' not in reader.fieldnames:
  raise ValueError(filename+' does not contain a stock_id field')
 rows={}
 for x in reader:
  code=x.get('stock_id','').strip()
  if not re.fullmatch(r'\d{4,6}',code) or code in rows:
   raise ValueError(filename+' contains duplicate or invalid stock_id: '+code)
  rows[code]=x
 return rows

def number(v):
 if v is None or not str(v).strip():return None
 try:
  x=float(str(v).replace(',',''))
  if x!=x or x==float('inf') or x==float('-inf'):return None
  return x
 except ValueError:return None

def str_num(v):
 return '' if number(v) is None else str(v).strip()

def first_entries(index):
 items=index.get('snapshots',[])
 if not isinstance(items,list) or index.get('snapshots_total')!=len(items):
  raise ValueError('snapshot index count mismatch')
 by_id=set()
 per_day={}
 for e in items:
  ident=e.get('snapshot_id')
  if not isinstance(ident,str) or ident in by_id:raise ValueError('duplicate or invalid snapshot_id')
  by_id.add(ident)
  dates=e.get('source_price_dates')
  if not isinstance(dates,list) or len(dates)!=1 or not iso_date(dates[0]):
   raise ValueError('snapshot has ambiguous price sessions')
  path=e.get('snapshot_path','')
  if not isinstance(path,str) or not re.fullmatch(
    r'signal_archive/\d{4}/\d{2}/\d{2}/[0-9A-Za-z_-]+/snapshot\.json',path):
   raise ValueError('unsafe snapshot path')
  if not re.fullmatch('[a-f0-9]{64}',str(e.get('snapshot_sha256',''))):
   raise ValueError('snapshot sha is invalid')
  captured=utc_instant(e.get('captured_at_utc'))
  if not captured:raise ValueError('missing snapshot first-seen UTC')
  day=dates[0]
  candidate=per_day.get(day)
  if candidate is None or (captured,ident)<(candidate[0],candidate[1]):
   per_day[day]=(captured,ident,e)
 return [(day,per_day[day][2]) for day in sorted(per_day)]

def recover_archive(data_dir,day,entry):
 """Read only first seen immutable archive; never rescore using latest CSV."""
 archive_root=(data_dir/'signal_archive').resolve()
 source=(data_dir/entry['snapshot_path']).resolve()
 if not source.is_relative_to(archive_root) or not source.is_file():
  raise ValueError('snapshot missing or escaped archive root')
 raw=source.read_bytes()
 if digest(raw)!=entry['snapshot_sha256']:
  raise ValueError('archived JSON SHA256 mismatch')
 manifest=load_json(raw)
 if manifest.get('version')!='2.4A' or manifest.get('snapshot_id')!=entry['snapshot_id'] or \
  manifest.get('captured_at_utc')!=entry['captured_at_utc'] or \
  manifest.get('summary',{}).get('source_price_dates')!=[day] or \
  manifest.get('source_published_at','MISSING') is not None:
  raise ValueError('archived version/date/clock does not match index')
 price=iso_date(day)
 if not price or not utc_instant(entry['captured_at_utc']):
  raise ValueError('invalid first seen time')
 if utc_instant(entry['captured_at_utc']).date()<price:
  raise ValueError('first capture predates observed price session')
 by_name={}
 for name in FILES:
  if name not in manifest.get('source_sha256',{}):
   raise ValueError('required historical raw source missing: '+name)
  stored=source.parent/'inputs'/(name+'.gz')
  if not stored.is_file():raise ValueError('historical gzip file missing: '+name)
  try:
   decompressed=gzip.decompress(stored.read_bytes())
  except (OSError,EOFError) as ex:raise ValueError('historical input corrupt: '+name) from ex
  if digest(decompressed)!=manifest['source_sha256'][name]:
   raise ValueError('historical raw input SHA256 mismatch: '+name)
  by_name[name]=parse_csv(decompressed,name)
 if set(by_name['chip_rank.csv'])!=set(by_name['tech_crosscheck.csv']):
  raise ValueError('archived ranked/tech pools differ')
 # Validate actual official prices against the entire session, not hindsight data.
 official=by_name['official_snapshot.csv']
 has_session=sum(1 for r in official.values() if r.get('asof')==day)
 if not has_session:raise ValueError('archive lacks official prices for this session')
 rows=[]
 for id,rank in sorted(by_name['chip_rank.csv'].items()):
  tech=by_name['tech_crosscheck.csv'][id]
  chip=by_name['chip_signals.csv'].get(id,{})
  if any(rank.get(k,'')!=tech.get(k,'') for k in
         ('rank_status','price_asof','flow_asof','holder_asof')):
   raise ValueError('archive contains contradictory ranked/technical dates: '+id)
  price_date=rank.get('price_asof','')
  flow_date=rank.get('flow_asof','')
  holder_date=rank.get('holder_asof','')
  matched_price=price_date==day
  flow_ok=bool(matched_price and flow_date==day and chip.get('flow_asof')==day and
       number(chip.get('foreign_5d_shares')) is not None and
       number(chip.get('trust_5d_shares')) is not None and
       number(chip.get('flow_days'))==5)
  holder_day=iso_date(holder_date)
  holder_ok=bool(matched_price and holder_day and holder_day<=price and
       (price-holder_day).days<=14 and chip.get('holder_asof')==holder_date and
       number(chip.get('large400_4w_pp')) is not None and
       number(chip.get('large1000_4w_pp')) is not None)
  tech_ok=bool(matched_price and tech.get('latest_history_date')==day and
       tech.get('data_status')=='可驗證' and
       number(tech.get('technical_confirmed_count')) is not None)
  issues=['official_source_publication_time_not_verified',
          'execution_and_transaction_costs_not_verified',
          'adjusted_total_return_not_verified','independent_outcome_not_verified']
  if not matched_price:issues.append('stock_price_source_not_aligned')
  if not flow_ok:issues.append('institutional_five_day_source_incomplete')
  if not holder_ok:issues.append('tdcc_weekly_source_incomplete_or_stale')
  if not tech_ok:issues.append('technical_source_incomplete_or_stale')
  rows.append({
    'stock_id':id,'stock_name':rank.get('stock_name',''),'market':rank.get('market',''),
    'price_session':day,'first_captured_at_utc':entry['captured_at_utc'],
    'first_snapshot_id':entry['snapshot_id'],
    'first_snapshot_sha256':entry['snapshot_sha256'],
    'rank_source_sha256':manifest['source_sha256']['chip_rank.csv'],
    'chip_source_sha256':manifest['source_sha256']['chip_signals.csv'],
    'tech_source_sha256':manifest['source_sha256']['tech_crosscheck.csv'],
    'rank_status':rank.get('rank_status',''),
    'chip_strength_rank':rank.get('chip_strength_rank',''),
    'chip_strength_score':rank.get('chip_strength_score',''),
    'close_unadjusted':rank.get('close','') if matched_price else '',
    'flow_asof':flow_date,'holder_asof':holder_date,
    'foreign_5d_shares':str_num(chip.get('foreign_5d_shares')) if flow_ok else '',
    'trust_5d_shares':str_num(chip.get('trust_5d_shares')) if flow_ok else '',
    'large400_4w_pp':str_num(chip.get('large400_4w_pp')) if holder_ok else '',
    'large1000_4w_pp':str_num(chip.get('large1000_4w_pp')) if holder_ok else '',
    'mid400_999_4w_pp':str_num(tech.get('mid400_999_4w_pp')) if holder_ok else '',
    'chip_status':chip.get('chip_status','') if flow_ok and holder_ok else '',
    'technical_status':tech.get('technical_status','') if tech_ok else '',
    'technical_confirmed_count':str_num(tech.get('technical_confirmed_count')) if tech_ok else '',
    'tech_data_status':tech.get('data_status',''),
    'latest_history_date':tech.get('latest_history_date',''),
    'raw_input_verified':'true','flow_5d_observation_usable':str(flow_ok).lower(),
    'holder_4w_observation_usable':str(holder_ok).lower(),
    'tech_observation_usable':str(tech_ok).lower(),
    'first_publication_time_verified':'false',
    'eligible_for_historical_trade':'false','blocking_reason':';'.join(issues)
  })
 return rows

def gate_report(readiness,rows,unique_sessions):
 checks={}
 for name,field in GATE_CHECKS:
  checks[name]={'passed':readiness.get(field) is True,
                'reason':'official_validation_required' if readiness.get(field) is not True else 'verified'}
 # Cohort age and overlapping stock independently verified by a separate dataset,
 # not by merely counting snapshots or historical raw quote coverage.
 checks['trade_execution']={'passed':False,'reason':'trade_fills_and_commission_slippage_unverified'}
 checks['future_labels']={'passed':False,'reason':'no_independently_verified_adjusted_future_trade_returns'}
 checks['historical_availability']={'passed':False,'reason':'first_capture_is_not_official_publication_time'}
 checks['minimum_out_of_sample']={'passed':False,'reason':'min_3_disjoint_folds_and_adequate_cohort_count_unproven'}
 checks['matured_10_20_60']={'passed':False,'reason':'all_10_20_60_outcomes_not_matured_and_verified'}
 upstream=readiness.get('strict_performance_samples_eligible')
 if upstream not in (0,None):
  raise ValueError('upstream strict eligibility changed; re-audit mandatory')
 can_validate=all(c['passed'] for c in checks.values()) and bool(rows)
 # No model can be launched by a backfilled CSV with old price dates.
 return {'gate_version':VERSION,'model_enabled':bool(can_validate),
  'verified_trade_samples':0,'certified_win_rate':None,
  'required_checks':checks,'pass_count':sum(c['passed'] for c in checks.values()),
  'required_count':len(checks),'unique_price_sessions':unique_sessions,
  'recorded_observations':len(rows),
  'note':'這是正式驗證資格稽核，不是回測結果；資料可讀不代表可據以交易。'}

def build(data_dir=DATA,generated_at=None):
 data_dir=Path(data_dir)
 now=generated_at or dt.datetime.now(UTC)
 if now.tzinfo is None:raise ValueError('audit clock must be timezone-aware')
 idx=load_json((data_dir/'signal_archive_index.json').read_bytes())
 first=first_entries(idx)
 if not first:raise ValueError('no valid independent archived price session')
 rows=[]
 for date,entry in first:rows.extend(recover_archive(data_dir,date,entry))
 if len({(r['stock_id'],r['price_session']) for r in rows})!=len(rows):
  raise ValueError('duplicate stock/price session observation')
 readiness=load_json((data_dir/'research_readiness_meta.json').read_bytes())
 gate=gate_report(readiness,rows,len(first))
 counts=Counter(r['price_session'] for r in rows)
 stats={
  'version':VERSION,'generated_at_utc':now.astimezone(UTC).isoformat().replace('+00:00','Z'),
  'status':'verified_raw_archives_model_blocked',
  'source_index':'signal_archive_index.json',
  'snapshots_in_index':len(idx['snapshots']),
  'unique_first_captured_price_sessions':len(first),
  'first_price_session':first[0][0],'last_price_session':first[-1][0],
  'stock_session_observations':len(rows),
  'eligible_technical_observations':sum(x['tech_observation_usable']=='true' for x in rows),
  'eligible_institutional_5d_observations':sum(x['flow_5d_observation_usable']=='true' for x in rows),
  'eligible_holder_4w_observations':sum(x['holder_4w_observation_usable']=='true' for x in rows),
  'daily_stock_coverage':[{'price_session':d,'rows':counts[d]} for d,_ in first],
  'snapshot_reference':[{'price_session':d,'snapshot_id':item['snapshot_id'],
      'captured_at_utc':item['captured_at_utc'],'snapshot_sha256':item['snapshot_sha256']} for d,item in first],
  'strict_validation':gate,'first_seen_timing_certified':False,
  'backfill_retrospective_allowed':False,
  'notes':[PIT_SOURCE_NOTE,
   '已從2.4A的原始gzip輸入重新取回法人5日與集保4週數值；只採首次封存當時存在的原始檔，不使用後來最新數據。',
   '價量資料未調整公司行動；本檔不含可驗證實際成交、獨立樣本外勝率。',
   '本次重建觀察表並不創造新的歷史封存或宣稱每日都有資料。'],
  'outputs':['historical_evidence_30q.csv','historical_evidence_meta_30q.json']
 }
 data_dir.mkdir(parents=True,exist_ok=True)
 with (data_dir/'historical_evidence_30q.csv').open('w',encoding='utf-8-sig',newline='') as fh:
  writer=csv.DictWriter(fh,fieldnames=COLS)
  writer.writeheader();writer.writerows(rows)
 (data_dir/'historical_evidence_meta_30q.json').write_text(
  json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0Q: verified '+str(len(first))+' original price sessions, '+
  str(len(rows))+' historical stock observations; trade samples=0; probability disabled')
 return stats

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--data-dir',type=Path,default=DATA)
 args=p.parse_args()
 build(args.data_dir)
